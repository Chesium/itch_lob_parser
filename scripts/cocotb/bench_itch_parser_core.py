from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge


THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parents[1]
SCRIPTS = ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))

import ref_parser  # noqa: E402


CLK_PERIOD_NS = 10


async def reset_dut(dut) -> None:
    dut.rst_n.value = 0
    dut.evt_ready.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


@cocotb.test()
async def benchmark_itch_parser_core_cycles(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    stream_path = Path(os.environ.get("BENCH_STREAM", ROOT / "tmp" / "bench_stream.bin"))
    out_path = Path(os.environ.get("RTL_BENCH_JSON", ROOT / "tmp" / "rtl_bench.json"))
    stream = stream_path.read_bytes()
    expected_events = len(ref_parser.parse_stream(stream))

    dut.evt_ready.value = 1

    byte_index = 0
    bytes_accepted = 0
    accepted_byte_cycles = 0
    events = 0
    total_cycles = 0
    started = False

    while events < expected_events:
        dut.s_axis_tvalid.value = 1 if byte_index < len(stream) else 0
        dut.s_axis_tdata.value = stream[byte_index] if byte_index < len(stream) else 0
        dut.s_axis_tlast.value = 0

        await ReadOnly()
        will_accept = byte_index < len(stream) and int(dut.s_axis_tready.value)
        will_emit = int(dut.evt_valid.value) and int(dut.evt_ready.value)

        await RisingEdge(dut.clk)

        if will_accept:
            byte_index += 1
            bytes_accepted += 1
            accepted_byte_cycles += 1
            started = True
        if started:
            total_cycles += 1
        if will_emit:
            events += 1

    dut.s_axis_tvalid.value = 0

    result = {
        "parser": "rtl",
        "stream": str(stream_path),
        "bytes": len(stream),
        "bytes_accepted": bytes_accepted,
        "events": events,
        "accepted_byte_cycles": accepted_byte_cycles,
        "total_cycles": total_cycles,
        "clock_period_ns": CLK_PERIOD_NS,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")

    assert bytes_accepted == len(stream)
    assert events == expected_events
