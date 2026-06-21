SIM ?= verilator
TOPLEVEL_LANG := verilog

ROOT_DIR := $(abspath ../..)
RTL_DIR := $(ROOT_DIR)/rtl

VERILOG_SOURCES := $(RTL_DIR)/itch_parser_core.sv

TOPLEVEL := itch_parser_core
COCOTB_TEST_MODULES := test_itch_parser_core

EXTRA_ARGS += -Wall -Wno-fatal

include $(shell cocotb-config --makefiles)/Makefile.sim
