"""Packet generator for the simplified ITCH LOB subset.

The binary layout is defined in ``localref/simp_itch_spec.md``.  This module is
intentionally small and dependency-free so cocotb tests can import it directly.
"""

from __future__ import annotations

import datetime
import enum
import random
import struct
import time
import zoneinfo
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

NS_PER_SEC = 1_000_000_000
PRICE_SCALE = 10_000
MAX_U16 = (1 << 16) - 1
MAX_U32 = (1 << 32) - 1
MAX_U48 = (1 << 48) - 1
MAX_U64 = (1 << 64) - 1


class MsgType(enum.Enum):
    ADD = "A"
    EXECUTE = "E"
    CANCEL = "X"
    DELETE = "D"
    REPLACE = "U"


MESSAGE_LENGTHS: dict[MsgType, int] = {
    MsgType.ADD: 36,
    MsgType.EXECUTE: 31,
    MsgType.CANCEL: 23,
    MsgType.DELETE: 19,
    MsgType.REPLACE: 35,
}


@dataclass(frozen=True)
class CommonHeader:
    msg_type: MsgType
    stock_locate: int
    tracking_number: int
    timestamp: int


def nsSinceMidnight(timezone: str = "Asia/Singapore") -> int:
    """Return nanoseconds elapsed since local midnight."""

    tz = zoneinfo.ZoneInfo(timezone)
    now_ns = time.time_ns()
    now_dt = datetime.datetime.fromtimestamp(time.time(), tz)
    today = now_dt.date()
    midnight_dt = datetime.datetime.combine(today, datetime.time.min, tzinfo=tz)
    midnight_ns = int(midnight_dt.timestamp()) * NS_PER_SEC
    return now_ns - midnight_ns


def _check_uint(name: str, value: int, max_value: int) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an int")
    if value < 0 or value > max_value:
        raise ValueError(f"{name} must be in range 0..{max_value}")
    return value


def _check_positive_uint32(name: str, value: int) -> int:
    _check_uint(name, value, MAX_U32)
    if value == 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def _timestamp_bytes(timestamp: int) -> bytes:
    return _check_uint("timestamp", timestamp, MAX_U48).to_bytes(6, "big")


def _price_raw(price: int | float | Decimal) -> int:
    if isinstance(price, int):
        return _check_uint("price", price, MAX_U32)

    raw = int((Decimal(str(price)) * PRICE_SCALE).to_integral_value(ROUND_HALF_UP))
    return _check_uint("price", raw, MAX_U32)


def encode_stock(stock_symbol: str | bytes) -> bytes:
    """Encode an ITCH alpha[8] stock symbol with right-side space padding."""

    if isinstance(stock_symbol, str):
        raw = stock_symbol.encode("ascii")
    else:
        raw = bytes(stock_symbol)

    if len(raw) > 8:
        raise ValueError("stock_symbol must encode to at most 8 bytes")
    if any(byte < 0x20 or byte > 0x7E for byte in raw):
        raise ValueError("stock_symbol must contain printable ASCII bytes")
    return raw.ljust(8, b" ")


def decode_stock(stock: bytes) -> str:
    if len(stock) != 8:
        raise ValueError("stock field must be exactly 8 bytes")
    return stock.rstrip(b" ").decode("ascii")


def genMsgTypeByte(msgType: MsgType) -> bytes:
    return msgType.value.encode("ascii")


def parseMsgType(msgStr: str | bytes | int) -> MsgType | None:
    if isinstance(msgStr, int):
        msgStr = bytes([msgStr])
    if isinstance(msgStr, bytes):
        msgStr = msgStr.decode("ascii")
    try:
        return MsgType(msgStr)
    except ValueError:
        return None


def pack_header(
    msg_type: MsgType,
    locate: int,
    trackN: int,
    timestamp: int,
) -> bytes:
    return struct.pack(
        ">cHH6s",
        genMsgTypeByte(msg_type),
        _check_uint("locate", locate, MAX_U16),
        _check_uint("trackN", trackN, MAX_U16),
        _timestamp_bytes(timestamp),
    )


def gen_add(
    locate: int,
    trackN: int,
    timestamp: int,
    orderref: int,
    side: str,
    shares: int,
    stockSymbol: str | bytes,
    price: int | float | Decimal,
) -> bytes:
    if side not in ("B", "S"):
        raise ValueError("side must be 'B' or 'S'")
    return (
        pack_header(MsgType.ADD, locate, trackN, timestamp)
        + struct.pack(
            ">QcI8sI",
            _check_uint("orderref", orderref, MAX_U64),
            side.encode("ascii"),
            _check_positive_uint32("shares", shares),
            encode_stock(stockSymbol),
            _price_raw(price),
        )
    )


def gen_execute(
    locate: int,
    trackN: int,
    timestamp: int,
    orderref: int,
    shares: int,
    matchNumber: int,
) -> bytes:
    return (
        pack_header(MsgType.EXECUTE, locate, trackN, timestamp)
        + struct.pack(
            ">QIQ",
            _check_uint("orderref", orderref, MAX_U64),
            _check_positive_uint32("shares", shares),
            _check_uint("matchNumber", matchNumber, MAX_U64),
        )
    )


def gen_cancel(
    locate: int,
    trackN: int,
    timestamp: int,
    orderref: int,
    shares: int,
) -> bytes:
    return (
        pack_header(MsgType.CANCEL, locate, trackN, timestamp)
        + struct.pack(
            ">QI",
            _check_uint("orderref", orderref, MAX_U64),
            _check_positive_uint32("shares", shares),
        )
    )


def gen_delete(
    locate: int,
    trackN: int,
    timestamp: int,
    orderref: int,
) -> bytes:
    return pack_header(MsgType.DELETE, locate, trackN, timestamp) + struct.pack(
        ">Q", _check_uint("orderref", orderref, MAX_U64)
    )


def gen_replace(
    locate: int,
    trackN: int,
    timestamp: int,
    orderref: int,
    neworderref: int,
    shares: int,
    price: int | float | Decimal,
) -> bytes:
    return (
        pack_header(MsgType.REPLACE, locate, trackN, timestamp)
        + struct.pack(
            ">QQII",
            _check_uint("orderref", orderref, MAX_U64),
            _check_uint("neworderref", neworderref, MAX_U64),
            _check_positive_uint32("shares", shares),
            _price_raw(price),
        )
    )


def gen_stream(messages: Iterable[bytes]) -> bytes:
    return b"".join(messages)


class PacketGenerator:
    """Stateful convenience generator for deterministic tests."""

    def __init__(
        self,
        locate: int = 1,
        tracking_number: int = 1,
        timestamp: int = 1,
        rng: random.Random | None = None,
    ) -> None:
        self.locate = locate
        self.tracking_number = tracking_number
        self.timestamp = timestamp
        self.rng = rng or random.Random()
        self._next_order_ref = 1_000
        self._next_match_number = 50_000

    def _header_args(self) -> tuple[int, int, int]:
        args = (self.locate, self.tracking_number, self.timestamp)
        self.tracking_number = (self.tracking_number + 1) & MAX_U16
        self.timestamp += 1
        return args

    def next_order_ref(self) -> int:
        self._next_order_ref += 1
        return self._next_order_ref

    def next_match_number(self) -> int:
        self._next_match_number += 1
        return self._next_match_number

    def add(
        self,
        orderref: int | None = None,
        side: str | None = None,
        shares: int | None = None,
        stockSymbol: str = "AAPL",
        price: int | float | Decimal | None = None,
    ) -> tuple[int, bytes]:
        ref = orderref if orderref is not None else self.next_order_ref()
        side = side if side is not None else self.rng.choice(["B", "S"])
        shares = shares if shares is not None else self.rng.randint(1, 10_000)
        price = price if price is not None else self.rng.randint(1, 1_000_000)
        return ref, gen_add(*self._header_args(), ref, side, shares, stockSymbol, price)

    def execute(
        self,
        orderref: int,
        shares: int,
        matchNumber: int | None = None,
    ) -> bytes:
        matchNumber = matchNumber if matchNumber is not None else self.next_match_number()
        return gen_execute(*self._header_args(), orderref, shares, matchNumber)

    def cancel(self, orderref: int, shares: int) -> bytes:
        return gen_cancel(*self._header_args(), orderref, shares)

    def delete(self, orderref: int) -> bytes:
        return gen_delete(*self._header_args(), orderref)

    def replace(
        self,
        orderref: int,
        neworderref: int | None = None,
        shares: int | None = None,
        price: int | float | Decimal | None = None,
    ) -> tuple[int, bytes]:
        new_ref = neworderref if neworderref is not None else self.next_order_ref()
        shares = shares if shares is not None else self.rng.randint(1, 10_000)
        price = price if price is not None else self.rng.randint(1, 1_000_000)
        return new_ref, gen_replace(*self._header_args(), orderref, new_ref, shares, price)


class EventKind(enum.Enum):
    ADD = 0
    EXECUTE = 1
    CANCEL = 2
    DELETE = 3
    REPLACE = 4
    ERROR = 7


# Backwards-compatible camelCase helpers used by early experiments.
def genAdd(*args, **kwargs) -> bytes:
    return gen_add(*args, **kwargs)


def genExecute(*args, **kwargs) -> bytes:
    return gen_execute(*args, **kwargs)


def genCancel(*args, **kwargs) -> bytes:
    return gen_cancel(*args, **kwargs)


def genDelete(*args, **kwargs) -> bytes:
    return gen_delete(*args, **kwargs)


def genReplace(*args, **kwargs) -> bytes:
    return gen_replace(*args, **kwargs)
