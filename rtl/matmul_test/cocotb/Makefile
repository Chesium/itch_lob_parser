SIM ?= verilator
TOPLEVEL_LANG := verilog

RTL_DIR := $(abspath ..)

VERILOG_SOURCES := \
	$(RTL_DIR)/myip_v1_0.v \
	$(RTL_DIR)/matrix_multiply.v \
	$(RTL_DIR)/memory_RAM.v

TOPLEVEL := myip_v1_0
MODULE := test_myip_v1_0

EXTRA_ARGS += -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-WIDTH

include $(shell cocotb-config --makefiles)/Makefile.sim
