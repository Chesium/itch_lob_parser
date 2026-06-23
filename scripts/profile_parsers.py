#!/usr/bin/env python3
"""Combined profiling wrapper for Python, C++, and RTL ITCH parsers."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import bench_parsers
import gen_bench_stream
import profile_python_parser


ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "tmp" / "profile"
PROFILE_STREAM = PROFILE_DIR / "bench_stream.bin"
PROFILE_JSON = PROFILE_DIR / "profile.json"
CALLGRIND_OUT = PROFILE_DIR / "callgrind.out"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def generate_dataset(args: argparse.Namespace) -> tuple[bytes, dict[str, Any]]:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    metadata = gen_bench_stream.write_bench_stream(
        out=PROFILE_STREAM,
        messages=args.messages,
        seed=args.seed,
        stock=args.stock,
    )
    return PROFILE_STREAM.read_bytes(), metadata


def run_cpp_breakdown(repeat: int, apply_lob: bool) -> dict[str, Any]:
    cmd = [
        str(bench_parsers.cpp_executable()),
        "--bench-breakdown",
        "--json",
        "--repeat",
        str(repeat),
    ]
    if apply_lob:
        cmd.append("--apply-lob")
    cmd.append(str(PROFILE_STREAM))

    result = subprocess.run(
        cmd,
        check=True,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def run_callgrind(repeat: int, apply_lob: bool) -> dict[str, Any]:
    if shutil.which("valgrind") is None:
        raise RuntimeError("valgrind was not found on PATH")

    if CALLGRIND_OUT.exists():
        CALLGRIND_OUT.unlink()

    cmd = [
        "valgrind",
        "--tool=callgrind",
        f"--callgrind-out-file={CALLGRIND_OUT}",
        str(bench_parsers.cpp_executable()),
        "--bench-breakdown",
        "--repeat",
        str(repeat),
    ]
    if apply_lob:
        cmd.append("--apply-lob")
    cmd.append(str(PROFILE_STREAM))

    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return {
        "tool": "callgrind",
        "output_path": str(CALLGRIND_OUT),
        "returncode": completed.returncode,
        "stderr_tail": "\n".join(completed.stderr.splitlines()[-8:]),
    }


def fmt(value: float) -> str:
    return f"{value:,.2f}"


def markdown_report(payload: dict[str, Any]) -> str:
    dataset = payload["dataset"]
    py = payload["python"]
    cpp = payload["cpp"]
    lines = [
        f"Dataset: {dataset['output_path']}",
        f"Messages: {dataset['messages']}",
        f"Bytes: {dataset['bytes']}",
        f"Repeats: {py['repeat']}",
        "",
        "| Parser/stage | Median time | MB/s | Msg/s | Notes |",
        "|---|---:|---:|---:|---|",
        (
            f"| Python parse | {py['median_parse_seconds']:.6f}s | "
            f"{fmt(py['mb_per_sec'])} | {fmt(py['messages_per_sec'])} | "
            "ref_parser.parse_stream |"
        ),
        (
            f"| C++ parse | {cpp['median_parse_seconds']:.6f}s | "
            f"{fmt(cpp['mb_per_sec'])} | {fmt(cpp['messages_per_sec'])} | "
            "ItchParser::start |"
        ),
    ]
    if py["apply_lob"]:
        lines.append(
            f"| Python parse+LOB | {py['median_parse_lob_seconds']:.6f}s | "
            f"{fmt(py['parse_lob_mb_per_sec'])} | {fmt(py['parse_lob_messages_per_sec'])} | "
            "parse_stream plus TinyLob.apply_all |"
        )
    if cpp["apply_lob"]:
        lines.append(
            f"| C++ parse+LOB | {cpp['median_parse_lob_seconds']:.6f}s | "
            f"{fmt(cpp['parse_lob_mb_per_sec'])} | {fmt(cpp['parse_lob_messages_per_sec'])} | "
            "ItchParser::start plus LOB::apply |"
        )
    if "rtl" in payload:
        rtl = payload["rtl"]
        lines.append(
            f"| RTL cycles | {rtl['total_cycles']} cycles | N/A | N/A | "
            "cocotb/Verilator measured cycles |"
        )
    if "callgrind" in payload:
        lines.extend(["", f"Callgrind output: {payload['callgrind']['output_path']}"])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run combined parser profiling.")
    parser.add_argument("--messages", type=_positive_int, default=gen_bench_stream.DEFAULT_MESSAGES)
    parser.add_argument("--repeat", type=_positive_int, default=5)
    parser.add_argument("--seed", type=int, default=gen_bench_stream.DEFAULT_SEED)
    parser.add_argument("--stock", default=gen_bench_stream.DEFAULT_STOCK)
    parser.add_argument("--build-cpp", action="store_true")
    parser.add_argument("--skip-rtl", action="store_true")
    parser.add_argument("--apply-lob", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--run-callgrind", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stream, dataset = generate_dataset(args)

    if args.build_cpp:
        bench_parsers.build_cpp()

    py_result = profile_python_parser.profile_python(stream, args.repeat, args.apply_lob)
    cpp_result = run_cpp_breakdown(args.repeat, args.apply_lob)
    payload: dict[str, Any] = {
        "dataset": dataset,
        "python": py_result,
        "cpp": cpp_result,
    }

    if not args.skip_rtl:
        payload["rtl"] = bench_parsers.run_rtl_benchmark(PROFILE_STREAM)

    if args.run_callgrind:
        payload["callgrind"] = run_callgrind(args.repeat, args.apply_lob)

    PROFILE_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(markdown_report(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
