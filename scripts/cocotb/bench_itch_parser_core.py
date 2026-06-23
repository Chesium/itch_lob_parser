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
MSG_LABELS = {
    "A": "add",
    "E": "execute",
    "X": "cancel",
    "D": "delete",
    "U": "replace",
}


async def reset_dut(dut) -> None:
    dut.rst_n.value = 0
    dut.evt_ready.value = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


def stream_messages(stream: bytes) -> list[dict[str, int | str]]:
    messages: list[dict[str, int | str]] = []
    offset = 0
    while offset < len(stream):
        msg_type = ref_parser.parseMsgType(stream[offset])
        if msg_type is None:
            raise ValueError(f"unknown message type at offset {offset}")
        length = ref_parser.MESSAGE_LENGTHS[msg_type]
        messages.append({"type": msg_type.value, "offset": offset, "bytes": length})
        offset += length
    return messages


@cocotb.test()
async def benchmark_itch_parser_core_cycles(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    stream_path = Path(os.environ.get("BENCH_STREAM", ROOT / "tmp" / "bench_stream.bin"))
    out_path = Path(os.environ.get("RTL_BENCH_JSON", ROOT / "tmp" / "rtl_bench.json"))
    stream = stream_path.read_bytes()
    expected_messages = stream_messages(stream)
    expected_events = len(ref_parser.parse_stream(stream))

    dut.evt_ready.value = 1

    byte_index = 0
    bytes_accepted = 0
    accepted_byte_cycles = 0
    events = 0
    total_cycles = 0
    started = False
    state_cycles = {"idle": 0, "read": 0, "output": 0}
    input_stall_cycles = 0
    output_stall_cycles = 0
    type_stats = {
        key: {"name": MSG_LABELS[key], "messages": 0, "bytes": 0, "cycles": 0, "latency_cycles": []}
        for key in MSG_LABELS
    }
    active_msg_index = 0
    active_msg_type = ""
    active_msg_start_cycle = 0

    while events < expected_events:
        dut.s_axis_tvalid.value = 1 if byte_index < len(stream) else 0
        dut.s_axis_tdata.value = stream[byte_index] if byte_index < len(stream) else 0
        dut.s_axis_tlast.value = 0

        await ReadOnly()
        tvalid_now = int(dut.s_axis_tvalid.value)
        tready_now = int(dut.s_axis_tready.value)
        evt_valid_now = int(dut.evt_valid.value)
        evt_ready_now = int(dut.evt_ready.value)
        will_accept = byte_index < len(stream) and tready_now
        will_emit = evt_valid_now and evt_ready_now
        input_stall = byte_index < len(stream) and tvalid_now and not tready_now
        output_stall = evt_valid_now and not evt_ready_now

        await RisingEdge(dut.clk)

        counted_cycle = started or will_accept
        if counted_cycle:
            if evt_valid_now:
                state_cycles["output"] += 1
            elif will_accept:
                state_cycles["read"] += 1
            else:
                state_cycles["idle"] += 1
        if input_stall and counted_cycle:
            input_stall_cycles += 1
        if output_stall and counted_cycle:
            output_stall_cycles += 1

        if will_accept:
            if active_msg_start_cycle == 0 and active_msg_index < len(expected_messages):
                active_msg = expected_messages[active_msg_index]
                active_msg_type = str(active_msg["type"])
                active_msg_start_cycle = total_cycles + 1
            byte_index += 1
            bytes_accepted += 1
            accepted_byte_cycles += 1
            started = True
        if started:
            total_cycles += 1
        if will_emit:
            if active_msg_start_cycle and active_msg_type in type_stats:
                latency = total_cycles - active_msg_start_cycle + 1
                stats = type_stats[active_msg_type]
                stats["messages"] += 1
                stats["bytes"] += int(expected_messages[active_msg_index]["bytes"])
                stats["cycles"] += latency
                if len(stats["latency_cycles"]) < 16:
                    stats["latency_cycles"].append(latency)
            active_msg_index += 1
            active_msg_start_cycle = 0
            active_msg_type = ""
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
        "state_cycles": state_cycles,
        "input_stall_cycles": input_stall_cycles,
        "output_stall_cycles": output_stall_cycles,
        "message_types": type_stats,
        "clock_period_ns": CLK_PERIOD_NS,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")

    assert bytes_accepted == len(stream)
    assert events == expected_events
