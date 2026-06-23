#!/usr/bin/env python3
"""Stage-level profiling for the Python ITCH parser."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import gen_bench_stream
import ref_parser


MSG_LABELS = {
    "A": "add",
    "E": "execute",
    "X": "cancel",
    "D": "delete",
    "U": "replace",
}


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def mb_per_sec(byte_count: int, seconds: float) -> float:
    return (byte_count / 1_000_000.0) / seconds if seconds > 0 else 0.0


def median_ns(values: list[int]) -> float:
    return statistics.median(values) if values else 0.0


def message_breakdown(stream: bytes) -> dict[str, dict[str, int]]:
    offset = 0
    stats = {
        label: {"messages": 0, "bytes": 0}
        for label in MSG_LABELS
    }
    while offset < len(stream):
        msg_type = ref_parser.parseMsgType(stream[offset])
        if msg_type is None:
            raise ref_parser.ParseError(f"unknown message type at offset {offset}")
        length = ref_parser.MESSAGE_LENGTHS[msg_type]
        label = msg_type.value
        stats[label]["messages"] += 1
        stats[label]["bytes"] += length
        offset += length
    return stats


def generate_or_read_input(args: argparse.Namespace) -> tuple[Path, bytes, dict[str, Any]]:
    if args.input is not None:
        stream = args.input.read_bytes()
        events = ref_parser.parse_stream(stream)
        return args.input, stream, {
            "bytes": len(stream),
            "messages": len(events),
            "message_mix": {key: value["messages"] for key, value in message_breakdown(stream).items()},
            "seed": None,
            "stock": None,
            "output_path": str(args.input),
        }

    path = gen_bench_stream.DEFAULT_OUT
    metadata = gen_bench_stream.write_bench_stream(
        out=path,
        messages=args.messages,
        seed=args.seed,
        stock=args.stock,
    )
    return path, path.read_bytes(), metadata


def profile_python(stream: bytes, repeat: int, apply_lob: bool) -> dict[str, Any]:
    parse_elapsed_ns: list[int] = []
    lob_elapsed_ns: list[int] = []
    parse_lob_elapsed_ns: list[int] = []
    events = 0

    for _ in range(repeat):
        start = time.perf_counter_ns()
        parsed = ref_parser.parse_stream(stream)
        stop = time.perf_counter_ns()
        parse_elapsed_ns.append(stop - start)

        if apply_lob:
            lob = ref_parser.TinyLob()
            lob_start = time.perf_counter_ns()
            lob.apply_all(parsed)
            lob_stop = time.perf_counter_ns()
            lob_elapsed_ns.append(lob_stop - lob_start)
            parse_lob_elapsed_ns.append((stop - start) + (lob_stop - lob_start))

        if events == 0:
            events = len(parsed)
        elif events != len(parsed):
            raise RuntimeError("Python parser event count changed between repeats")

    parse_median = median_ns(parse_elapsed_ns)
    parse_seconds = parse_median / 1_000_000_000.0
    result: dict[str, Any] = {
        "parser": "python",
        "bytes": len(stream),
        "events": events,
        "repeat": repeat,
        "apply_lob": apply_lob,
        "elapsed_ns": parse_elapsed_ns,
        "median_parse_ns": parse_median,
        "median_parse_seconds": parse_seconds,
        "median_ns_per_message": parse_median / events if events else 0.0,
        "mb_per_sec": mb_per_sec(len(stream), parse_seconds),
        "messages_per_sec": events / parse_seconds if parse_seconds > 0 else 0.0,
        "message_types": message_breakdown(stream),
    }

    if apply_lob:
        lob_median = median_ns(lob_elapsed_ns)
        total_median = median_ns(parse_lob_elapsed_ns)
        total_seconds = total_median / 1_000_000_000.0
        result.update(
            {
                "lob_elapsed_ns": lob_elapsed_ns,
                "median_lob_apply_ns": lob_median,
                "median_parse_lob_ns": total_median,
                "median_parse_lob_seconds": total_seconds,
                "parse_lob_mb_per_sec": mb_per_sec(len(stream), total_seconds),
                "parse_lob_messages_per_sec": events / total_seconds if total_seconds > 0 else 0.0,
            }
        )

    return result


def markdown_report(dataset: dict[str, Any], profile: dict[str, Any]) -> str:
    lines = [
        f"Dataset: {dataset['output_path']}",
        f"Messages: {dataset['messages']}",
        f"Bytes: {dataset['bytes']}",
        f"Repeats: {profile['repeat']}",
        "",
        "| Stage | Median time | MB/s | Msg/s | Notes |",
        "|---|---:|---:|---:|---|",
        (
            f"| Python parse | {profile['median_parse_seconds']:.6f}s | "
            f"{profile['mb_per_sec']:,.2f} | {profile['messages_per_sec']:,.2f} | "
            "ref_parser.parse_stream |"
        ),
    ]
    if profile["apply_lob"]:
        lines.append(
            f"| Python parse+LOB | {profile['median_parse_lob_seconds']:.6f}s | "
            f"{profile['parse_lob_mb_per_sec']:,.2f} | {profile['parse_lob_messages_per_sec']:,.2f} | "
            "parse_stream plus TinyLob.apply_all |"
        )
    lines.extend(["", "| Type | Messages | Bytes |", "|---|---:|---:|"])
    for msg_type, stats in profile["message_types"].items():
        lines.append(f"| {msg_type} | {stats['messages']} | {stats['bytes']} |")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile the Python ITCH parser.")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--messages", type=_positive_int, default=gen_bench_stream.DEFAULT_MESSAGES)
    parser.add_argument("--repeat", type=_positive_int, default=5)
    parser.add_argument("--seed", type=int, default=gen_bench_stream.DEFAULT_SEED)
    parser.add_argument("--stock", default=gen_bench_stream.DEFAULT_STOCK)
    parser.add_argument("--apply-lob", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path, stream, dataset = generate_or_read_input(args)
    dataset["output_path"] = str(input_path)
    profile = profile_python(stream, args.repeat, args.apply_lob)
    payload = {"dataset": dataset, "python": profile}

    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(markdown_report(dataset, profile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
