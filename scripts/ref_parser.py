"""Reference parser and tiny LOB model for the simplified ITCH subset."""

from __future__ import annotations

import argparse
import enum
import struct
from dataclasses import dataclass
from pathlib import Path

try:
    from .packet_gen import MESSAGE_LENGTHS, EventKind, MsgType, parseMsgType
except ImportError:  # pragma: no cover - supports direct script imports
    from packet_gen import MESSAGE_LENGTHS, EventKind, MsgType, parseMsgType

VALID_ORDER_REF = 1 << 0
VALID_NEW_ORDER_REF = 1 << 1
VALID_SIDE = 1 << 2
VALID_QTY = 1 << 3
VALID_PRICE = 1 << 4
VALID_MATCH_NUMBER = 1 << 5
VALID_STOCK = 1 << 6

ADD_VALID_MASK = VALID_ORDER_REF | VALID_SIDE | VALID_QTY | VALID_PRICE | VALID_STOCK
EXEC_VALID_MASK = VALID_ORDER_REF | VALID_QTY | VALID_MATCH_NUMBER
CANCEL_VALID_MASK = VALID_ORDER_REF | VALID_QTY
DELETE_VALID_MASK = VALID_ORDER_REF
REPLACE_VALID_MASK = VALID_ORDER_REF | VALID_NEW_ORDER_REF | VALID_QTY | VALID_PRICE


class ParseError(ValueError):
    pass


class BookError(ValueError):
    pass


class Side(enum.Enum):
    BUY = "B"
    SELL = "S"


@dataclass(frozen=True)
class ItchEvent:
    kind: EventKind
    stock_locate: int
    tracking_number: int
    timestamp: int
    order_ref: int = 0
    new_order_ref: int = 0
    side: Side | None = None
    qty: int = 0
    price: int = 0
    match_number: int = 0
    stock: bytes = b"\x00" * 8
    valid_mask: int = 0


def _event_kind_char(kind: EventKind) -> str:
    if kind is EventKind.ADD:
        return "A"
    if kind is EventKind.EXECUTE:
        return "E"
    if kind is EventKind.CANCEL:
        return "X"
    if kind is EventKind.DELETE:
        return "D"
    if kind is EventKind.REPLACE:
        return "U"
    return "*"


def _valid_or_n(valid_mask: int, bit: int, value: int) -> str:
    return str(value) if valid_mask & bit else "N"


def _format_stock(stock: bytes) -> str:
    """Mirror the C++ normalized output: print leading A-Z bytes only."""

    chars: list[str] = []
    for byte in stock[:8]:
        if ord("A") <= byte <= ord("Z"):
            chars.append(chr(byte))
        else:
            break
    return "".join(chars)


def format_event(event: ItchEvent) -> str:
    """Format one event like cpp/itch_spec.cpp operator<<.

    The output intentionally omits tracking_number because the current C++
    normalized event print format omits it too.
    """

    side = "N"
    if event.valid_mask & VALID_SIDE and event.side is not None:
        side = "B" if event.side is Side.BUY else "S"

    price = "N"
    if event.valid_mask & VALID_PRICE:
        price = f"{event.price / 10_000:.4f}"

    stock = "N"
    if event.valid_mask & VALID_STOCK:
        stock = _format_stock(event.stock)

    return " ".join(
        [
            _event_kind_char(event.kind),
            str(event.stock_locate),
            str(event.timestamp),
            _valid_or_n(event.valid_mask, VALID_ORDER_REF, event.order_ref),
            _valid_or_n(event.valid_mask, VALID_NEW_ORDER_REF, event.new_order_ref),
            side,
            _valid_or_n(event.valid_mask, VALID_QTY, event.qty),
            price,
            _valid_or_n(event.valid_mask, VALID_MATCH_NUMBER, event.match_number),
            stock,
            f"{event.valid_mask:08b}",
        ]
    )


def format_stream(stream: bytes) -> str:
    return "\n".join(format_event(event) for event in parse_stream(stream))


@dataclass(frozen=True)
class Order:
    stock_locate: int
    stock: bytes
    side: Side
    qty: int
    price: int


def parse_header(packet: bytes) -> tuple[MsgType, int, int, int]:
    if len(packet) < 11:
        raise ParseError("packet is shorter than common header")

    msg_type = parseMsgType(packet[0])
    if msg_type is None:
        raise ParseError(f"unknown message type byte 0x{packet[0]:02x}")

    locate, tracking, timestamp_bytes = struct.unpack(">HH6s", packet[1:11])
    return msg_type, locate, tracking, int.from_bytes(timestamp_bytes, "big")


def parse_packet(packet: bytes) -> ItchEvent:
    msg_type, locate, tracking, timestamp = parse_header(packet)
    expected_len = MESSAGE_LENGTHS[msg_type]
    if len(packet) != expected_len:
        raise ParseError(
            f"{msg_type.value} message must be {expected_len} bytes, got {len(packet)}"
        )

    body = packet[11:]
    if msg_type is MsgType.ADD:
        order_ref, side_raw, qty, stock, price = struct.unpack(">QcI8sI", body)
        try:
            side = Side(side_raw.decode("ascii"))
        except ValueError as exc:
            raise ParseError("ADD side must be 'B' or 'S'") from exc
        return ItchEvent(
            kind=EventKind.ADD,
            stock_locate=locate,
            tracking_number=tracking,
            timestamp=timestamp,
            order_ref=order_ref,
            side=side,
            qty=qty,
            price=price,
            stock=stock,
            valid_mask=ADD_VALID_MASK,
        )

    if msg_type is MsgType.EXECUTE:
        order_ref, qty, match_number = struct.unpack(">QIQ", body)
        return ItchEvent(
            kind=EventKind.EXECUTE,
            stock_locate=locate,
            tracking_number=tracking,
            timestamp=timestamp,
            order_ref=order_ref,
            qty=qty,
            match_number=match_number,
            valid_mask=EXEC_VALID_MASK,
        )

    if msg_type is MsgType.CANCEL:
        order_ref, qty = struct.unpack(">QI", body)
        return ItchEvent(
            kind=EventKind.CANCEL,
            stock_locate=locate,
            tracking_number=tracking,
            timestamp=timestamp,
            order_ref=order_ref,
            qty=qty,
            valid_mask=CANCEL_VALID_MASK,
        )

    if msg_type is MsgType.DELETE:
        (order_ref,) = struct.unpack(">Q", body)
        return ItchEvent(
            kind=EventKind.DELETE,
            stock_locate=locate,
            tracking_number=tracking,
            timestamp=timestamp,
            order_ref=order_ref,
            valid_mask=DELETE_VALID_MASK,
        )

    order_ref, new_order_ref, qty, price = struct.unpack(">QQII", body)
    return ItchEvent(
        kind=EventKind.REPLACE,
        stock_locate=locate,
        tracking_number=tracking,
        timestamp=timestamp,
        order_ref=order_ref,
        new_order_ref=new_order_ref,
        qty=qty,
        price=price,
        valid_mask=REPLACE_VALID_MASK,
    )


def parse_stream(stream: bytes) -> list[ItchEvent]:
    events: list[ItchEvent] = []
    offset = 0
    while offset < len(stream):
        msg_type = parseMsgType(stream[offset])
        if msg_type is None:
            raise ParseError(f"unknown message type at offset {offset}")

        expected_len = MESSAGE_LENGTHS[msg_type]
        end = offset + expected_len
        if end > len(stream):
            raise ParseError(
                f"truncated {msg_type.value} message at offset {offset}: "
                f"need {expected_len} bytes, have {len(stream) - offset}"
            )

        events.append(parse_packet(stream[offset:end]))
        offset = end
    return events


class TinyLob:
    """Reference lifecycle model for order-level ITCH semantics."""

    def __init__(self) -> None:
        self.orders: dict[int, Order] = {}

    def apply(self, event: ItchEvent) -> None:
        if event.kind is EventKind.ADD:
            self._add(event)
        elif event.kind is EventKind.EXECUTE:
            self._reduce(event.order_ref, event.qty, "execute")
        elif event.kind is EventKind.CANCEL:
            self._reduce(event.order_ref, event.qty, "cancel")
        elif event.kind is EventKind.DELETE:
            self._delete(event)
        elif event.kind is EventKind.REPLACE:
            self._replace(event)
        else:
            raise BookError(f"cannot apply event kind {event.kind}")

    def apply_all(self, events: list[ItchEvent]) -> None:
        for event in events:
            self.apply(event)

    def _add(self, event: ItchEvent) -> None:
        if event.order_ref in self.orders:
            raise BookError(f"duplicate order_ref {event.order_ref}")
        if event.side is None:
            raise BookError("ADD event side is missing")
        if event.qty <= 0:
            raise BookError("ADD quantity must be greater than 0")

        self.orders[event.order_ref] = Order(
            stock_locate=event.stock_locate,
            stock=event.stock,
            side=event.side,
            qty=event.qty,
            price=event.price,
        )

    def _reduce(self, order_ref: int, qty: int, action: str) -> None:
        order = self.orders.get(order_ref)
        if order is None:
            raise BookError(f"cannot {action} unknown order_ref {order_ref}")
        if qty <= 0:
            raise BookError(f"{action} quantity must be greater than 0")
        if qty > order.qty:
            raise BookError(
                f"cannot {action} {qty} shares from order_ref {order_ref}; "
                f"only {order.qty} remain"
            )

        remaining = order.qty - qty
        if remaining == 0:
            del self.orders[order_ref]
        else:
            self.orders[order_ref] = Order(
                stock_locate=order.stock_locate,
                stock=order.stock,
                side=order.side,
                qty=remaining,
                price=order.price,
            )

    def _delete(self, event: ItchEvent) -> None:
        if event.order_ref not in self.orders:
            raise BookError(f"cannot delete unknown order_ref {event.order_ref}")
        del self.orders[event.order_ref]

    def _replace(self, event: ItchEvent) -> None:
        old = self.orders.get(event.order_ref)
        if old is None:
            raise BookError(f"cannot replace unknown order_ref {event.order_ref}")
        if event.new_order_ref in self.orders:
            raise BookError(f"replacement order_ref {event.new_order_ref} already exists")
        if event.qty <= 0:
            raise BookError("replace quantity must be greater than 0")

        del self.orders[event.order_ref]
        self.orders[event.new_order_ref] = Order(
            stock_locate=old.stock_locate,
            stock=old.stock,
            side=old.side,
            qty=event.qty,
            price=event.price,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Parse a simplified ITCH binary stream and print the same normalized "
            "event format as cpp/itch_spec.cpp."
        )
    )
    parser.add_argument("bin_file", type=Path, help="binary ITCH payload stream")
    args = parser.parse_args(argv)

    output = format_stream(args.bin_file.read_bytes())
    if output:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
