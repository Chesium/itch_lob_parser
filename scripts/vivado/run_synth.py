#!/usr/bin/env python3
"""Run Vivado out-of-context synthesis for itch_parser_core."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parents[1]
RTL = ROOT / "rtl"
DEFAULT_OUT_DIR = ROOT / "tmp" / "vivado_synth"


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise SystemExit(f"{name} was not found on PATH.")
    return resolved


def parse_timing_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8", errors="ignore")
    result: dict[str, Any] = {}
    wns = re.search(r"\bWNS\(ns\)\s+([-+]?\d+(?:\.\d+)?)", text)
    if wns:
        result["wns_ns"] = float(wns.group(1))
    failing = re.search(r"\bFailing Endpoints\s+(\d+)", text)
    if failing:
        result["failing_endpoints"] = int(failing.group(1))
    return result


def run_synth(args: argparse.Namespace) -> dict[str, Any]:
    vivado = require_tool("vivado")
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(
        {
            "ITCH_ROOT": str(ROOT.resolve()),
            "ITCH_RTL_DIR": str(RTL.resolve()),
            "ITCH_SYNTH_OUT_DIR": str(out_dir),
            "ITCH_VIVADO_PART": args.part,
            "ITCH_CLOCK_MHZ": str(args.clock_mhz),
        }
    )

    log_path = out_dir / "vivado_synth.log"
    journal_path = out_dir / "vivado_synth.jou"
    subprocess.run(
        [
            vivado,
            "-mode",
            "batch",
            "-source",
            str(THIS_DIR / "synth_ooc.tcl"),
            "-log",
            str(log_path),
            "-journal",
            str(journal_path),
        ],
        cwd=ROOT,
        check=True,
        env=env,
    )

    result = {
        "part": args.part,
        "clock_mhz": args.clock_mhz,
        "clock_period_ns": 1000.0 / args.clock_mhz,
        "out_dir": str(out_dir),
        "netlist": str(out_dir / "itch_parser_core_synth.v"),
        "checkpoint": str(out_dir / "itch_parser_core_synth.dcp"),
        "sdf": str(out_dir / "itch_parser_core_synth.sdf"),
        "timing_summary": str(out_dir / "timing_summary.rpt"),
        "utilization": str(out_dir / "utilization.rpt"),
        "log": str(log_path),
    }
    result.update(parse_timing_summary(out_dir / "timing_summary.rpt"))

    result_path = out_dir / "synth_result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    result["result_json"] = str(result_path)
    return result


def print_report(result: dict[str, Any]) -> None:
    print(
        f"PASS: synthesized itch_parser_core for {result['part']} "
        f"at {result['clock_mhz']:g}MHz"
    )
    if "wns_ns" in result:
        print(f"WNS: {result['wns_ns']:.3f} ns")
    if "failing_endpoints" in result:
        print(f"Failing endpoints: {result['failing_endpoints']}")
    print(f"Netlist: {result['netlist']}")
    print(f"Timing: {result['timing_summary']}")
    print(f"Utilization: {result['utilization']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Vivado OOC synthesis for itch_parser_core.")
    parser.add_argument("--part", required=True, help="Vivado part name, e.g. xc7a35tcpg236-1")
    parser.add_argument("--clock-mhz", type=_positive_float, default=250.0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    result = run_synth(parse_args(argv))
    if "--json" in (argv or []):
        print(json.dumps(result, sort_keys=True))
    else:
        print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
