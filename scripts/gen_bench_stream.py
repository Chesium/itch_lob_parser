#!/usr/bin/env python3
"""Generate deterministic valid ITCH lifecycle streams for benchmarks."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

import packet_gen


DEFAULT_MESSAGES = 100_000
DEFAULT_SEED = 1
DEFAULT_OUT = Path("tmp/bench_stream.bin")
DEFAULT_STOCK = "AAPL"


@dataclass
class ActiveOrder:
    order_ref: int
    qty: int


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def build_bench_stream(messages: int, seed: int = DEFAULT_SEED, stock: str = DEFAULT_STOCK) -> tuple[bytes, dict[str, object]]:
    """Return a deterministic valid benchmark stream and metadata."""

    if messages <= 0:
        raise ValueError("messages must be greater than 0")

    packet_gen.encode_stock(stock)
    rng = random.Random(seed)
    gen = packet_gen.PacketGenerator(locate=1, tracking_number=1, timestamp=1, rng=rng)
    active: list[ActiveOrder] = []
    packets: list[bytes] = []
    mix = {msg.value: 0 for msg in packet_gen.MsgType}

    def add_order() -> None:
        side = "B" if rng.randrange(2) == 0 else "S"
        shares = rng.randint(100, 10_000)
        price = rng.randint(1_000_000, 2_000_000)
        order_ref, packet = gen.add(side=side, shares=shares, stockSymbol=stock, price=price)
        active.append(ActiveOrder(order_ref=order_ref, qty=shares))
        packets.append(packet)
        mix[packet_gen.MsgType.ADD.value] += 1

    def pick_order() -> ActiveOrder:
        return active[rng.randrange(len(active))]

    while len(packets) < messages:
        op_index = len(packets) % 5
        if not active or op_index == 0:
            add_order()
            continue

        order = pick_order()
        if op_index == 1:
            shares = rng.randint(1, max(1, order.qty // 2))
            packets.append(gen.execute(order.order_ref, shares=shares))
            order.qty -= shares
            if order.qty == 0:
                active.remove(order)
            mix[packet_gen.MsgType.EXECUTE.value] += 1
        elif op_index == 2:
            shares = rng.randint(1, max(1, order.qty // 2))
            packets.append(gen.cancel(order.order_ref, shares=shares))
            order.qty -= shares
            if order.qty == 0:
                active.remove(order)
            mix[packet_gen.MsgType.CANCEL.value] += 1
        elif op_index == 3:
            shares = rng.randint(100, 10_000)
            price = rng.randint(1_000_000, 2_000_000)
            new_ref, packet = gen.replace(order.order_ref, shares=shares, price=price)
            active.remove(order)
            active.append(ActiveOrder(order_ref=new_ref, qty=shares))
            packets.append(packet)
            mix[packet_gen.MsgType.REPLACE.value] += 1
        else:
            packets.append(gen.delete(order.order_ref))
            active.remove(order)
            mix[packet_gen.MsgType.DELETE.value] += 1

    stream = packet_gen.gen_stream(packets)
    metadata: dict[str, object] = {
        "bytes": len(stream),
        "messages": len(packets),
        "message_mix": mix,
        "seed": seed,
        "stock": stock,
    }
    return stream, metadata


def write_bench_stream(out: Path, messages: int, seed: int, stock: str) -> dict[str, object]:
    stream, metadata = build_bench_stream(messages=messages, seed=seed, stock=stock)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(stream)
    metadata["output_path"] = out.as_posix()
    return metadata


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a deterministic ITCH benchmark stream.")
    parser.add_argument("--messages", type=_positive_int, default=DEFAULT_MESSAGES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--stock", default=DEFAULT_STOCK)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    metadata = write_bench_stream(args.out, args.messages, args.seed, args.stock)
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
