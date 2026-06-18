## Instructions

```bash
cd rtl/matmul_test

verilator --binary --timing -Wall -Wno-fatal \
  -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-BLKSEQ \
  --top-module tb_myip_v1_0 \
  tb_myip_v1_0.v myip_v1_0.v matrix_multiply.v memory_RAM.v

./obj_dir/Vtb_myip_v1_0
```

## Explanation

- The `cd rtl/matmul_test` matters because the testbench uses relative $readmemh paths:

- You need `--timing` because the testbench uses Verilog delays like `#50`, `#100`, etc. Verilator’s `--binary` mode is convenient here because it can build and run a Verilog testbench directly, without you writing a C++ harness.
- There are warnings, but they are not blockers. They are mostly width issues: 8-bit matrix data being assigned through 32-bit AXI stream signals, and wider counters being assigned into narrower RAM addresses. Verilator treats warnings as fatal by default, so `-Wno-fatal` is what lets this Vivado-style code run unchanged.