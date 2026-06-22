#!/usr/bin/env python3
"""Benchmark Python, C++, and RTL ITCH parsers on one shared stream."""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import gen_bench_stream
import ref_parser


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RTL_JSON = ROOT / "tmp" / "rtl_bench.json"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def parse_clock_mhz(value: str) -> list[int]:
    clocks = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not clocks or any(clock <= 0 for clock in clocks):
        raise argparse.ArgumentTypeError("--clock-mhz must contain positive integers")
    return clocks


def mb_per_sec(byte_count: int, seconds: float) -> float:
    return (byte_count / 1_000_000.0) / seconds if seconds > 0 else 0.0


def msg_per_sec(events: int, seconds: float) -> float:
    return events / seconds if seconds > 0 else 0.0


def generate_or_read_input(args: argparse.Namespace) -> tuple[Path, bytes, dict[str, Any]]:
    if args.input is not None:
        path = args.input
        stream = path.read_bytes()
        events = ref_parser.parse_stream(stream)
        metadata = {
            "bytes": len(stream),
            "messages": len(events),
            "message_mix": {},
            "seed": None,
            "output_path": str(path),
        }
        return path, stream, metadata

    path = gen_bench_stream.DEFAULT_OUT
    metadata = gen_bench_stream.write_bench_stream(
        out=path,
        messages=args.messages,
        seed=args.seed,
        stock=args.stock,
    )
    return path, path.read_bytes(), metadata


def benchmark_python(stream: bytes, repeat: int) -> dict[str, Any]:
    elapsed_ns: list[int] = []
    events = 0
    for _ in range(repeat):
        start = time.perf_counter_ns()
        parsed = ref_parser.parse_stream(stream)
        stop = time.perf_counter_ns()
        elapsed_ns.append(stop - start)
        if events == 0:
            events = len(parsed)
        elif events != len(parsed):
            raise RuntimeError("Python parser event count changed between repeats")

    median_seconds = statistics.median(elapsed_ns) / 1_000_000_000.0
    return {
        "parser": "python",
        "bytes": len(stream),
        "events": events,
        "repeat": repeat,
        "elapsed_ns": elapsed_ns,
        "median_seconds": median_seconds,
        "mb_per_sec": mb_per_sec(len(stream), median_seconds),
        "messages_per_sec": msg_per_sec(events, median_seconds),
    }


def build_cpp() -> None:
    subprocess.run(
        ["cmake", "-S", str(ROOT), "-B", str(ROOT / "build")],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["cmake", "--build", str(ROOT / "build")],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )


def benchmark_cpp(input_path: Path, repeat: int) -> dict[str, Any]:
    result = subprocess.run(
        [str(ROOT / "build" / "itch_cli"), "--bench", "--json", "--repeat", str(repeat), str(input_path)],
        check=True,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def run_rtl_benchmark(input_path: Path) -> dict[str, Any]:
    input_path = input_path.resolve()
    DEFAULT_RTL_JSON.parent.mkdir(parents=True, exist_ok=True)
    if DEFAULT_RTL_JSON.exists():
        DEFAULT_RTL_JSON.unlink()

    make_cmd = ["make"]
    if shutil.which("uv"):
        make_cmd = ["uv", "run", "make"]

    subprocess.run(
        make_cmd
        + [
            "-C",
            str(ROOT / "scripts" / "cocotb"),
            f"BENCH_STREAM={input_path}",
            f"RTL_BENCH_JSON={DEFAULT_RTL_JSON}",
            "COCOTB_TEST_MODULES=bench_itch_parser_core",
        ],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )
    return json.loads(DEFAULT_RTL_JSON.read_text(encoding="utf-8"))


def rtl_rows(rtl: dict[str, Any], clocks_mhz: list[int]) -> list[dict[str, Any]]:
    rows = []
    total_cycles = int(rtl["total_cycles"])
    bytes_accepted = int(rtl["bytes_accepted"])
    events = int(rtl["events"])
    for clock in clocks_mhz:
        clock_hz = clock * 1_000_000
        rows.append(
            {
                "parser": f"rtl @{clock}MHz",
                "cycles": total_cycles,
                "mb_per_sec": bytes_accepted / total_cycles * clock_hz / 1_000_000.0,
                "messages_per_sec": events / total_cycles * clock_hz,
                "notes": "measured cycles, ideal hardware",
            }
        )
    return rows


def fmt_float(value: float) -> str:
    return f"{value:,.2f}"


def markdown_report(dataset: dict[str, Any], python: dict[str, Any], cpp: dict[str, Any], rtl: dict[str, Any] | None, rows: list[dict[str, Any]], repeat: int) -> str:
    lines = [
        f"Dataset: {dataset['output_path']}",
        f"Messages: {dataset['messages']}",
        f"Bytes: {dataset['bytes']}",
        f"Repeats: {repeat}",
        "",
        "| Parser | Time (median) | MB/s | Msg/s | Notes |",
        "|---|---:|---:|---:|---|",
        (
            f"| Python | {python['median_seconds']:.6f}s | "
            f"{fmt_float(python['mb_per_sec'])} | {fmt_float(python['messages_per_sec'])} | "
            "ref_parser.parse_stream |"
        ),
        (
            f"| C++ | {cpp['median_seconds']:.6f}s | "
            f"{fmt_float(cpp['mb_per_sec'])} | {fmt_float(cpp['messages_per_sec'])} | "
            "ItchParser quiet mode |"
        ),
    ]
    for row in rows:
        lines.append(
            f"| {row['parser']} | {row['cycles']} cycles | "
            f"{fmt_float(row['mb_per_sec'])} | {fmt_float(row['messages_per_sec'])} | "
            f"{row['notes']} |"
        )
    if rtl is None:
        lines.append("| RTL | skipped | N | N | use without --skip-rtl to run cocotb |")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark ITCH parser implementations.")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--messages", type=_positive_int, default=gen_bench_stream.DEFAULT_MESSAGES)
    parser.add_argument("--repeat", type=_positive_int, default=5)
    parser.add_argument("--seed", type=int, default=gen_bench_stream.DEFAULT_SEED)
    parser.add_argument("--stock", default=gen_bench_stream.DEFAULT_STOCK)
    parser.add_argument("--build-cpp", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--clock-mhz", type=parse_clock_mhz, default=parse_clock_mhz("100,250"))
    parser.add_argument("--skip-rtl", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    input_path, stream, dataset = generate_or_read_input(args)

    if args.build_cpp:
        build_cpp()

    py_result = benchmark_python(stream, args.repeat)
    cpp_result = benchmark_cpp(input_path, args.repeat)

    rtl_result = None
    calculated_rows: list[dict[str, Any]] = []
    if not args.skip_rtl:
        rtl_result = run_rtl_benchmark(input_path)
        calculated_rows = rtl_rows(rtl_result, args.clock_mhz)

    result = {
        "dataset": dataset,
        "python": py_result,
        "cpp": cpp_result,
        "rtl": rtl_result,
        "rtl_rows": calculated_rows,
    }
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(markdown_report(dataset, py_result, cpp_result, rtl_result, calculated_rows, args.repeat))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
