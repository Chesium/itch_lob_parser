#!/usr/bin/env python3
"""Run Vivado xsim against a synthesized itch_parser_core functional netlist."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parents[1]
RTL = ROOT / "rtl"
DEFAULT_BUILD_DIR = ROOT / "tmp" / "vivado_xsim" / "post_synth"
DEFAULT_VECTOR_DIR = ROOT / "tmp" / "vivado_xsim" / "post_synth_vectors"
DEFAULT_RESULT_JSON = DEFAULT_BUILD_DIR / "xsim_post_synth.json"
DEFAULT_NETLIST = ROOT / "tmp" / "vivado_synth" / "itch_parser_core_synth.v"

sys.path.insert(0, str(THIS_DIR))

import export_xsim_vectors  # noqa: E402
from run_xsim import parse_clock_mhz, throughput_rows  # noqa: E402


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise SystemExit(f"{name} was not found on PATH.")
    return resolved


def posix(path: Path) -> str:
    return path.resolve().as_posix()


def vivado_root_from_tool(tool_path: str) -> Path | None:
    path = Path(tool_path).resolve()
    for parent in path.parents:
        if (parent / "data" / "verilog" / "src" / "glbl.v").exists():
            return parent
    return None


def generate_vectors(args: argparse.Namespace) -> dict[str, Any]:
    vector_args = argparse.Namespace(
        input=args.input,
        messages=args.messages,
        seed=args.seed,
        stock=args.stock,
        out_dir=args.vector_dir,
    )
    return export_xsim_vectors.export_vectors(vector_args)


def run_post_synth_xsim(args: argparse.Namespace, metadata: dict[str, Any]) -> dict[str, Any]:
    xvlog = require_tool("xvlog")
    xelab = require_tool("xelab")
    xsim = require_tool("xsim")

    netlist = args.netlist.resolve()
    if not netlist.exists():
        raise SystemExit(f"netlist does not exist: {netlist}")

    build_dir = args.build_dir.resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    args.result_json.parent.mkdir(parents=True, exist_ok=True)
    sim_result_json = build_dir / "xsim_bench.json"
    if args.result_json.exists():
        args.result_json.unlink()
    if sim_result_json.exists():
        sim_result_json.unlink()

    shutil.copyfile(metadata["stream_mem"], build_dir / "stream.mem")
    shutil.copyfile(metadata["expected_events_mem"], build_dir / "expected_events.mem")

    sources = [posix(netlist), posix(RTL / "tb_itch_parser_core_xsim.sv")]
    vivado_root = vivado_root_from_tool(xvlog)
    if vivado_root is not None:
        sources.append(posix(vivado_root / "data" / "verilog" / "src" / "glbl.v"))
    subprocess.run([xvlog, "-sv", *sources], cwd=build_dir, check=True)

    snapshot = args.snapshot
    verify = "1" if args.mode == "verify" or args.verify_events else "0"
    xelab_args = build_dir / "xelab_post_synth.args"
    xelab_args.write_text(
        "\n".join(
            [
                "tb_itch_parser_core_xsim glbl",
                "--timescale 1ns/1ps",
                f"--generic_top STREAM_BYTES={metadata['bytes']}",
                f"--generic_top EXPECTED_EVENTS={metadata['messages']}",
                f"--generic_top VERIFY_EVENTS={verify}",
                f"--generic_top INPUT_STALL_PERIOD={args.input_stall_period}",
                f"--generic_top OUTPUT_STALL_PERIOD={args.output_stall_period}",
                "-L unisims_ver",
                "-L unimacro_ver",
                "-L secureip",
                f"-s {snapshot}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run([xelab, "-f", str(xelab_args)], cwd=build_dir, check=True)

    subprocess.run(
        [
            xsim,
            snapshot,
            "--R",
            "--log",
            "xsim_post_synth.log",
        ],
        cwd=build_dir,
        check=True,
    )

    if not sim_result_json.exists():
        raise SystemExit(f"xsim completed without writing {sim_result_json}")
    if args.result_json.resolve() != sim_result_json.resolve():
        shutil.copyfile(sim_result_json, args.result_json)
    return json.loads(args.result_json.read_text(encoding="utf-8"))


def print_report(result: dict[str, Any], clocks_mhz: list[int]) -> None:
    status = "PASS" if result.get("passed") else "FAIL"
    print(
        f"{status}: post-synthesis xsim accepted {result['bytes_accepted']} bytes, "
        f"emitted {result['events']} events in {result['total_cycles']} cycles"
    )
    print("")
    print("| Parser | Cycles | MB/s | Msg/s | Notes |")
    print("|---|---:|---:|---:|---|")
    for row in throughput_rows(result, clocks_mhz):
        print(
            f"| post-synth xsim @{row['clock_mhz']}MHz | {row['cycles']} | "
            f"{row['mb_per_sec']:,.2f} | {row['messages_per_sec']:,.2f} | "
            "functional synthesized netlist, ideal hardware |"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run xsim for synthesized itch_parser_core netlist.")
    parser.add_argument("--mode", choices=["verify", "bench"], default="verify")
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--input", type=Path, help="existing binary stream to run")
    parser.add_argument("--messages", type=_positive_int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--stock", default="AAPL")
    parser.add_argument("--clock-mhz", type=parse_clock_mhz, default=parse_clock_mhz("100,250"))
    parser.add_argument("--vector-dir", type=Path, default=DEFAULT_VECTOR_DIR)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument("--result-json", type=Path, default=DEFAULT_RESULT_JSON)
    parser.add_argument("--snapshot", default="tb_itch_parser_core_post_synth_snapshot")
    parser.add_argument("--input-stall-period", type=int, default=0)
    parser.add_argument("--output-stall-period", type=int, default=0)
    parser.add_argument("--verify-events", action="store_true", help="also compare event payloads in bench mode")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    metadata = generate_vectors(args)
    result = run_post_synth_xsim(args, metadata)
    rows = throughput_rows(result, args.clock_mhz)
    combined = {"vectors": metadata, "xsim": result, "throughput": rows, "netlist": str(args.netlist)}
    if args.json:
        print(json.dumps(combined, sort_keys=True))
    else:
        print_report(result, args.clock_mhz)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
