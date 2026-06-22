from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, with_timeout
from cocotbext.axi import AxiStreamBus, AxiStreamFrame, AxiStreamSource


THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parents[1]
SCRIPTS = ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))

import packet_gen  # noqa: E402
import ref_parser  # noqa: E402


CLK_PERIOD_NS = 10


@dataclass(frozen=True)
class RtlEvent:
    kind: int
    stock_locate: int
    tracking_number: int
    timestamp: int
    order_ref: int
    new_order_ref: int
    side: int
    qty: int
    price: int
    match_number: int
    stock: int
    valid_mask: int


def build_smoke_stream() -> bytes:
    gen = packet_gen.PacketGenerator(locate=1, tracking_number=1, timestamp=100)

    buy_ref, add_buy = gen.add(
        orderref=1001,
        side="B",
        shares=100,
        stockSymbol="AAPL",
        price=1_000_000,
    )
    sell_ref, add_sell = gen.add(
        orderref=1002,
        side="S",
        shares=50,
        stockSymbol="MSFT",
        price=1_010_000,
    )
    exec_buy = gen.execute(buy_ref, shares=30, matchNumber=9001)
    cancel_buy = gen.cancel(buy_ref, shares=20)
    repl_ref, replace_sell = gen.replace(
        sell_ref,
        neworderref=2002,
        shares=60,
        price=1_005_000,
    )
    delete_repl = gen.delete(repl_ref)

    return packet_gen.gen_stream(
        [add_buy, add_sell, exec_buy, cancel_buy, replace_sell, delete_repl]
    )


def build_all_message_singletons() -> list[bytes]:
    gen = packet_gen.PacketGenerator(locate=2, tracking_number=10, timestamp=1_000)
    ref, add = gen.add(
        orderref=3001,
        side="B",
        shares=250,
        stockSymbol="NVDA",
        price=12_345_600,
    )
    new_ref, replace = gen.replace(
        ref,
        neworderref=4001,
        shares=175,
        price=12_500_000,
    )
    assert new_ref == 4001

    return [
        add,
        gen.execute(ref, shares=75, matchNumber=9100),
        gen.cancel(ref, shares=25),
        gen.delete(ref),
        replace,
        packet_gen.gen_add(
            locate=packet_gen.MAX_U16,
            trackN=packet_gen.MAX_U16,
            timestamp=packet_gen.MAX_U48,
            orderref=packet_gen.MAX_U64,
            side="S",
            shares=packet_gen.MAX_U32,
            stockSymbol="MAXTEST",
            price=packet_gen.MAX_U32,
        ),
    ]


def ref_kind_value(event: ref_parser.ItchEvent) -> int:
    return event.kind.value


def ref_stock_int(event: ref_parser.ItchEvent) -> int:
    return int.from_bytes(event.stock, "big")


def expected_tuple(event: ref_parser.ItchEvent) -> RtlEvent:
    return RtlEvent(
        kind=ref_kind_value(event),
        stock_locate=event.stock_locate,
        tracking_number=event.tracking_number,
        timestamp=event.timestamp,
        order_ref=event.order_ref,
        new_order_ref=event.new_order_ref,
        side=0 if event.side is not ref_parser.Side.SELL else 1,
        qty=event.qty,
        price=event.price,
        match_number=event.match_number,
        stock=ref_stock_int(event),
        valid_mask=event.valid_mask,
    )


def rtl_event_from_dut(dut) -> RtlEvent:
    return RtlEvent(
        kind=int(dut.evt_kind.value),
        stock_locate=int(dut.stock_locate.value),
        tracking_number=int(dut.tracking_number.value),
        timestamp=int(dut.timestamp.value),
        order_ref=int(dut.order_ref.value),
        new_order_ref=int(dut.new_order_ref.value),
        side=int(dut.side.value),
        qty=int(dut.qty.value),
        price=int(dut.price.value),
        match_number=int(dut.match_number.value),
        stock=int(dut.stock.value),
        valid_mask=int(dut.valid_mask.value),
    )


def format_rtl_event(event: RtlEvent) -> str:
    kind = {
        0: "A",
        1: "E",
        2: "X",
        3: "D",
        4: "U",
        7: "*",
    }.get(event.kind, "*")

    order_ref = str(event.order_ref) if event.valid_mask & ref_parser.VALID_ORDER_REF else "N"
    new_order_ref = (
        str(event.new_order_ref)
        if event.valid_mask & ref_parser.VALID_NEW_ORDER_REF
        else "N"
    )
    side = "N"
    if event.valid_mask & ref_parser.VALID_SIDE:
        side = "S" if event.side else "B"
    qty = str(event.qty) if event.valid_mask & ref_parser.VALID_QTY else "N"
    price = "N"
    if event.valid_mask & ref_parser.VALID_PRICE:
        price = f"{event.price / 10_000:.4f}"
    match_number = (
        str(event.match_number)
        if event.valid_mask & ref_parser.VALID_MATCH_NUMBER
        else "N"
    )
    stock = "N"
    if event.valid_mask & ref_parser.VALID_STOCK:
        stock_bytes = event.stock.to_bytes(8, "big")
        chars = []
        for byte in stock_bytes:
            if ord("A") <= byte <= ord("Z"):
                chars.append(chr(byte))
            else:
                break
        stock = "".join(chars)

    return " ".join(
        [
            kind,
            str(event.stock_locate),
            str(event.timestamp),
            order_ref,
            new_order_ref,
            side,
            qty,
            price,
            match_number,
            stock,
            f"{event.valid_mask:08b}",
        ]
    )


async def reset_dut(dut) -> None:
    dut.rst_n.value = 0
    dut.evt_ready.value = 0
    await ClockCycles(dut.clk, 3)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def collect_events(dut, count: int) -> list[RtlEvent]:
    events = []
    dut.evt_ready.value = 1

    while len(events) < count:
        await RisingEdge(dut.clk)
        if int(dut.evt_valid.value) and int(dut.evt_ready.value):
            events.append(rtl_event_from_dut(dut))

    return events


async def drive_stream(dut, stream: bytes) -> None:
    source = AxiStreamSource(
        AxiStreamBus.from_prefix(dut, "s_axis"),
        dut.clk,
        dut.rst_n,
        reset_active_level=False,
        byte_lanes=1,
    )
    await source.send(AxiStreamFrame(stream))


def cpp_reference_lines(stream: bytes) -> list[str]:
    default_build_dir = ROOT / ("build-msvc" if os.name == "nt" else "build")
    build_dir = Path(os.environ.get("ITCH_CPP_BUILD_DIR", default_build_dir))
    cli = build_dir / ("itch_cli.exe" if os.name == "nt" else "itch_cli")
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp.write(stream)
            tmp.flush()
            tmp_path = Path(tmp.name)

        subprocess.run(
            ["cmake", "-S", str(ROOT), "-B", str(build_dir)],
            check=True,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["cmake", "--build", str(build_dir)],
            check=True,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
        )
        result = subprocess.run(
            [str(cli), str(tmp_path)],
            check=True,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    return result.stdout.splitlines()


async def run_stream_test(dut, stream: bytes) -> list[RtlEvent]:
    expected = ref_parser.parse_stream(stream)
    collector = cocotb.start_soon(collect_events(dut, len(expected)))

    await drive_stream(dut, stream)
    rtl_events = await with_timeout(collector, 20_000, "ns")

    assert rtl_events == [expected_tuple(event) for event in expected]
    assert [format_rtl_event(event) for event in rtl_events] == [
        ref_parser.format_event(event) for event in expected
    ]
    return rtl_events


@cocotb.test()
async def itch_parser_smoke_matches_python_and_cpp(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    stream = build_smoke_stream()
    rtl_events = await run_stream_test(dut, stream)

    assert [format_rtl_event(event) for event in rtl_events] == cpp_reference_lines(stream)


@cocotb.test()
async def itch_parser_single_message_streams_match_python(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())

    for message in build_all_message_singletons():
        await reset_dut(dut)
        await run_stream_test(dut, message)


@cocotb.test()
async def itch_parser_applies_output_backpressure(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await reset_dut(dut)

    stream = build_smoke_stream()
    expected = ref_parser.parse_stream(stream)

    source = AxiStreamSource(
        AxiStreamBus.from_prefix(dut, "s_axis"),
        dut.clk,
        dut.rst_n,
        reset_active_level=False,
        byte_lanes=1,
    )

    await source.send(AxiStreamFrame(stream))

    rtl_events = []
    dut.evt_ready.value = 0

    while len(rtl_events) < len(expected):
        await RisingEdge(dut.clk)
        if int(dut.evt_valid.value):
            held = rtl_event_from_dut(dut)
            await ClockCycles(dut.clk, 3)
            assert rtl_event_from_dut(dut) == held
            dut.evt_ready.value = 1
            await RisingEdge(dut.clk)
            rtl_events.append(held)
            dut.evt_ready.value = 0

    assert rtl_events == [expected_tuple(event) for event in expected]
