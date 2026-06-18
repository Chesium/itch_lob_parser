from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, with_timeout
from cocotbext.axi import AxiStreamBus, AxiStreamFrame, AxiStreamSink, AxiStreamSource


THIS_DIR = Path(__file__).resolve().parent
RTL_DIR = THIS_DIR.parent

NUMBER_OF_INPUT_WORDS = 520
NUMBER_OF_OUTPUT_WORDS = 64


def load_mem_words(path):
    words = []

    with path.open() as mem_file:
        for line in mem_file:
            line = line.split("//", 1)[0].strip()
            if line:
                words.append(int(line, 16))

    return words


async def reset_dut(dut):
    dut.ARESETN.value = 0
    await ClockCycles(dut.ACLK, 2)
    dut.ARESETN.value = 1
    await ClockCycles(dut.ACLK, 2)


@cocotb.test()
async def matrix_multiply_axi_stream_vectors(dut):
    cocotb.start_soon(Clock(dut.ACLK, 100, units="ns").start())

    source = AxiStreamSource(
        AxiStreamBus.from_prefix(dut, "S_AXIS"),
        dut.ACLK,
        dut.ARESETN,
        reset_active_level=False,
        byte_lanes=1,
    )
    sink = AxiStreamSink(
        AxiStreamBus.from_prefix(dut, "M_AXIS"),
        dut.ACLK,
        dut.ARESETN,
        reset_active_level=False,
        byte_lanes=1,
    )

    input_words = load_mem_words(RTL_DIR / "test_64x8_input.mem")
    expected_words = load_mem_words(RTL_DIR / "test_64x8_expected.mem")

    assert len(input_words) == NUMBER_OF_INPUT_WORDS
    assert len(expected_words) == NUMBER_OF_OUTPUT_WORDS

    await reset_dut(dut)

    await source.send(AxiStreamFrame(input_words))
    frame = await with_timeout(sink.recv(), 200_000, "ns")

    received_words = list(frame.tdata)

    assert len(received_words) == NUMBER_OF_OUTPUT_WORDS
    assert received_words == expected_words
