# ITCH LOB Parser

ITCH LOB Parser is a compact reference implementation of a simplified Nasdaq
ITCH order-lifecycle feed. The same generated binary stream is parsed by a
Python model, a C++20 CLI, and a SystemVerilog RTL core so behavior and
throughput can be compared directly.

## Quantifiable Results

### Protocol Slice

The project intentionally focuses on the messages that mutate a visible limit
order book: add, execute, cancel, delete, and replace. Inputs are fixed-length
ITCH payloads concatenated back-to-back; there is no SoupBinTCP, MoldUDP64,
stock-directory, trade, status, or admin framing.

![Simplified ITCH subset](assets/itch_subset.png)

### Benchmark Snapshot

`scripts/bench_parsers.py` generates one deterministic stream, runs all parser
implementations on it, and reports median software time plus idealized RTL
throughput from measured cycle counts.

```bash
uv run python scripts/bench_parsers.py --messages 10000 --repeat 5 --build-cpp
```

Example result run on a Windows 11 machine with AMD Ryzen AI 9 365:

- Dataset: `tmp\bench_stream.bin`
- Messages: 10000
- Bytes: 288000
- Repeats: 5

| Parser      | Time (median) |   MB/s |        Msg/s | Notes                           |
| ----------- | ------------: | -----: | -----------: | ------------------------------- |
| Python      |     0.035401s |   8.14 |   282,479.49 | ref_parser.parse_stream         |
| C++         |     0.001815s | 158.70 | 5,510,550.00 | ItchParser quiet mode           |
| rtl @100MHz | 298000 cycles |  96.64 | 3,355,704.70 | measured cycles, ideal hardware |
| rtl @250MHz | 298000 cycles | 241.61 | 8,389,261.74 | measured cycles, ideal hardware |

Use `--skip-rtl` to compare only the Python and C++ parsers.

## What Is Implemented

The simplified protocol is defined in `localref/simp_itch_spec.md`. All integer
fields are big-endian. `Timestamp` is a 6-byte unsigned integer representing
nanoseconds since midnight. `Price(4)` is a raw `uint32_t` fixed-point value
with four implied decimal places, so `1732500` represents `173.2500`. Stock
symbols are 8 ASCII bytes, left-aligned and padded with spaces.

### Message Types

| Type | Message        | Length | LOB meaning                                                                |
| ---- | -------------- | -----: | -------------------------------------------------------------------------- |
| `A`  | Add Order      |     36 | Insert a new visible order.                                                |
| `E`  | Order Executed |     31 | Reduce an existing order by executed shares.                               |
| `X`  | Order Cancel   |     23 | Reduce an existing order by cancelled shares.                              |
| `D`  | Order Delete   |     19 | Remove an existing order completely.                                       |
| `U`  | Order Replace  |     35 | Remove an old order ref and insert a new order ref with updated qty/price. |

Every message begins with the same 11-byte header:

| Offset | Length | Field           |
| -----: | -----: | --------------- |
|      0 |      1 | Message type    |
|      1 |      2 | Stock locate    |
|      3 |      2 | Tracking number |
|      5 |      6 | Timestamp       |

Message-specific payload fields are laid out at fixed offsets from the start of
the message:

| Type | Extra fields                                                                                 |
| ---- | -------------------------------------------------------------------------------------------- |
| `A`  | `11: order_ref u64`, `19: side char`, `20: shares u32`, `24: stock char[8]`, `32: price u32` |
| `E`  | `11: order_ref u64`, `19: executed_shares u32`, `23: match_number u64`                       |
| `X`  | `11: order_ref u64`, `19: cancelled_shares u32`                                              |
| `D`  | `11: order_ref u64`                                                                          |
| `U`  | `11: original_order_ref u64`, `19: new_order_ref u64`, `27: shares u32`, `31: price u32`     |

### Normalized Event Model

All parsers normalize binary messages into the same event shape: `kind`,
`stock_locate`, `tracking_number`, `timestamp`, `order_ref`, `new_order_ref`,
`side`, `qty`, `price`, `match_number`, `stock`, and `valid_mask`. The valid
mask records which payload fields are meaningful for each event kind.

<p align="center">
  <img src="assets/normalized_event.png" alt="Normalized event model" width="360">
</p>

| Event     | Valid payload fields                         |
| --------- | -------------------------------------------- |
| `ADD`     | `order_ref`, `side`, `qty`, `price`, `stock` |
| `EXECUTE` | `order_ref`, `qty`, `match_number`           |
| `CANCEL`  | `order_ref`, `qty`                           |
| `DELETE`  | `order_ref`                                  |
| `REPLACE` | `order_ref`, `new_order_ref`, `qty`, `price` |

### Order Lifecycle Rules

- `ADD`: require `order_ref` is new, `side` is `B` or `S`, and `qty > 0`; insert
  the order at its raw `Price(4)` value.
- `EXECUTE`: require `order_ref` exists and executed shares do not exceed the
  remaining quantity; subtract `qty`, erasing the order when it reaches zero.
  The execution message has no price, so book maintenance uses the stored price
  from the original order.
- `CANCEL`: same quantity-reduction rule as execute, but for cancelled shares.
- `DELETE`: require `order_ref` exists; remove all remaining quantity and erase
  the order.
- `REPLACE`: require the original `order_ref` exists and `new_order_ref` is not
  already active; remove the original order and insert `new_order_ref` with the
  old side, old stock, old locate, new quantity, and new price.

## Project Layout

- `scripts/packet_gen.py`: binary packet and deterministic stream generator.
- `scripts/ref_parser.py`: Python reference parser and tiny order book model.
- `cpp/`: C++20 parser library plus `itch_cli` for smoke tests and benchmarks.
- `rtl/`: SystemVerilog parser cores and shared protocol package.
- `scripts/cocotb/`: cocotb/Verilator validation and RTL benchmark harness.
- `scripts/bench_parsers.py`: combined Python, C++, and RTL benchmark runner.

## Setup

Use `uv` for the Python environment on both Linux and Windows:

```bash
uv sync
```

### Linux

The original flow assumes these tools are available on `PATH`:

- `uv`
- `cmake`
- a C++20 compiler such as `g++` or `clang++`
- `make`
- `verilator`

### Windows

The Windows flow uses MSVC for both the C++ CLI and the cocotb Verilator runner.
Install these tools and make sure `uv`, `cmake`, and `verilator` are on `PATH`:

- `uv`
- `cmake`
- Verilator for Windows, tested with [withlimon/verilator-windows](https://github.com/withlimon/verilator-windows)
- MSVC Build Tools or Visual Studio with the C++ toolchain

Run Windows build, RTL, and benchmark commands from an MSVC environment:

```bat
cmd /c "call <MSVC Installation Path>\VC\Auxiliary\Build\vcvarsall.bat x64 && <command>"
```

## Build, Test, And Benchmark

### Python Reference

Run the unit tests:

```bash
uv run python -m unittest discover -s tests -p "test_*.py"
```

Generate and parse packets from Python:

```python
from scripts import packet_gen, ref_parser

stream = packet_gen.gen_stream([
    packet_gen.gen_add(1, 1, 100, 1001, "B", 100, "AAPL", 1_000_000),
    packet_gen.gen_cancel(1, 2, 101, 1001, 40),
])

events = ref_parser.parse_stream(stream)
lob = ref_parser.TinyLob()
lob.apply_all(events)

assert lob.orders[1001].qty == 60
```

For deterministic test data, use `PacketGenerator`, which auto-increments
tracking numbers and timestamps:

```python
gen = packet_gen.PacketGenerator(locate=1, timestamp=100)
order_ref, add = gen.add(side="B", shares=100, stockSymbol="AAPL", price=1_000_000)
exe = gen.execute(order_ref, shares=25)
```

### C++ CLI

Linux:

```bash
cmake -S . -B build
cmake --build build
uv run python scripts/gen_cpp_parser_fixtures.py
./build/itch_cli scripts/data/smoke_all_types.bin
./build/itch_cli scripts/data/max_width_add.bin
```

Windows:

```bat
cmd /c "call <MSVC Installation Path>\VC\Auxiliary\Build\vcvarsall.bat x64 && cmake -S . -B build-msvc && cmake --build build-msvc"
uv run python scripts/gen_cpp_parser_fixtures.py
build-msvc\itch_cli.exe scripts\data\smoke_all_types.bin
build-msvc\itch_cli.exe scripts\data\max_width_add.bin
```

### RTL Cocotb Flow

Linux:

```bash
uv run make -C scripts/cocotb
```

Windows:

```bat
cmd /c "call <MSVC Installation Path>\VC\Auxiliary\Build\vcvarsall.bat x64 && uv run make -C scripts/cocotb"
```

On Windows, `uv run make` is a project shim that invokes
`scripts/cocotb/run_verilator.py`; it still accepts Makefile-style environment
overrides such as `COCOTB_TEST_MODULES=bench_itch_parser_core`.

### Combined Benchmark

Linux:

```bash
uv run python scripts/bench_parsers.py --messages 10000 --repeat 5 --build-cpp
```

Windows:

```bat
cmd /c "call <MSVC Installation Path>\VC\Auxiliary\Build\vcvarsall.bat x64 && uv run python scripts/bench_parsers.py --messages 10000 --repeat 5 --build-cpp"
```

## RTL Core Variants

All RTL variants expose the same normalized event interface, but the default
cocotb workflow selects `rtl/itch_parser_core.sv`.

- `rtl/itch_parser_core_legacy.sv` keeps the first working parser
  microarchitecture. It decodes fields with direct byte-offset `case`
  statements and serves as a simple baseline.
- `rtl/itch_parser_core_layout.sv` is the middle-ground refactor with named
  layout constants, helper functions, and packed normalized event state.
- `rtl/itch_parser_core.sv` is the maintained parser core. It uses a static
  microcoded field table from `rtl/itch_parser_pkg.sv` to map byte offsets to
  normalized event fields while preserving the same external behavior.
