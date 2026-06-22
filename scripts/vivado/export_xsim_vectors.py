#!/usr/bin/env python3
"""Export deterministic ITCH parser vectors for Vivado xsim testbenches."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parents[1]
SCRIPTS = ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))

import gen_bench_stream  # noqa: E402
import ref_parser  # noqa: E402


PACKED_EVENT_BITS = 412
PACKED_EVENT_HEX_DIGITS = (PACKED_EVENT_BITS + 3) // 4


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def side_value(event: ref_parser.ItchEvent) -> int:
    return 1 if event.side is ref_parser.Side.SELL else 0


def stock_value(event: ref_parser.ItchEvent) -> int:
    return int.from_bytes(event.stock, "big")


def pack_event(event: ref_parser.ItchEvent) -> int:
    """Pack an event in the same order as itch_parser_core output ports."""

    fields = [
        (event.kind.value, 3),
        (event.stock_locate, 16),
        (event.tracking_number, 16),
        (event.timestamp, 48),
        (event.order_ref, 64),
        (event.new_order_ref, 64),
        (side_value(event), 1),
        (event.qty, 32),
        (event.price, 32),
        (event.match_number, 64),
        (stock_value(event), 64),
        (event.valid_mask, 8),
    ]

    packed = 0
    total_width = 0
    for value, width in fields:
        if value < 0 or value >= (1 << width):
            raise ValueError(f"value {value} does not fit in {width} bits")
        packed = (packed << width) | value
        total_width += width

    if total_width != PACKED_EVENT_BITS:
        raise AssertionError(f"packed event width is {total_width}, expected {PACKED_EVENT_BITS}")
    return packed


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def generate_or_read_stream(args: argparse.Namespace) -> tuple[bytes, dict[str, Any]]:
    if args.input is not None:
        stream = args.input.read_bytes()
        metadata: dict[str, Any] = {
            "bytes": len(stream),
            "messages": len(ref_parser.parse_stream(stream)),
            "message_mix": {},
            "seed": None,
            "stock": None,
            "input_path": str(args.input),
        }
        return stream, metadata

    stream, metadata = gen_bench_stream.build_bench_stream(
        messages=args.messages,
        seed=args.seed,
        stock=args.stock,
    )
    return stream, metadata


def export_vectors(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stream, metadata = generate_or_read_stream(args)
    events = ref_parser.parse_stream(stream)

    stream_bin = out_dir / "stream.bin"
    stream_mem = out_dir / "stream.mem"
    expected_mem = out_dir / "expected_events.mem"
    expected_txt = out_dir / "expected_events.txt"
    metadata_json = out_dir / "metadata.json"

    stream_bin.write_bytes(stream)
    write_lines(stream_mem, [f"{byte:02x}" for byte in stream])
    write_lines(
        expected_mem,
        [f"{pack_event(event):0{PACKED_EVENT_HEX_DIGITS}x}" for event in events],
    )
    write_lines(expected_txt, [ref_parser.format_event(event) for event in events])

    metadata.update(
        {
            "bytes": len(stream),
            "messages": len(events),
            "output_dir": str(out_dir),
            "stream_bin": str(stream_bin),
            "stream_mem": str(stream_mem),
            "expected_events_mem": str(expected_mem),
            "expected_events_txt": str(expected_txt),
            "packed_event_bits": PACKED_EVENT_BITS,
            "packed_event_hex_digits": PACKED_EVENT_HEX_DIGITS,
        }
    )
    metadata_json.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return metadata


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Vivado xsim ITCH parser vectors.")
    parser.add_argument("--input", type=Path, help="existing binary stream to export")
    parser.add_argument("--messages", type=_positive_int, default=gen_bench_stream.DEFAULT_MESSAGES)
    parser.add_argument("--seed", type=int, default=gen_bench_stream.DEFAULT_SEED)
    parser.add_argument("--stock", default=gen_bench_stream.DEFAULT_STOCK)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "tmp" / "vivado_xsim" / "vectors")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    metadata = export_vectors(parse_args(argv))
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
