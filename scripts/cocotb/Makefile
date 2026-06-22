COCOTB_TEST_MODULES ?= test_itch_parser_core

.PHONY: all sim clean

all: sim

sim:
	uv run python run_verilator.py

clean:
	uv run python run_verilator.py --clean
