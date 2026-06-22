# ITCH LOB Parser

## Simplified ITCH Subset and LOB Semantics

This repository implements the simplified ITCH payload subset described in
`localref/simp_itch_spec.md`. It is not a full Nasdaq ITCH feed handler: there
is no SoupBinTCP or MoldUDP64 framing, no stock-directory handling, and no
trade/status/admin messages. The input stream is simply fixed-length ITCH
payload messages concatenated back-to-back.

Supported order-lifecycle messages:

| Type | Message        | Length | LOB meaning |
| ---- | -------------- | -----: | ----------- |
| `A`  | Add Order      |     36 | Insert a new visible order. |
| `E`  | Order Executed |     31 | Reduce an existing order by executed shares. |
| `X`  | Order Cancel   |     23 | Reduce an existing order by cancelled shares. |
| `D`  | Order Delete   |     19 | Remove an existing order completely. |
| `U`  | Order Replace  |     35 | Remove an old order ref and insert a new order ref with updated qty/price. |

All integer fields are big-endian. `Timestamp` is a 6-byte unsigned integer
representing nanoseconds since midnight. `Price(4)` is a raw `uint32_t`
fixed-point value with four implied decimal places, so `1732500` represents
`173.2500`. Stock symbols are 8 ASCII bytes, left-aligned and padded on the
right with spaces.

Every message begins with the same 11-byte header:

| Offset | Length | Field |
| -----: | -----: | ----- |
|      0 |      1 | Message type |
|      1 |      2 | Stock locate |
|      3 |      2 | Tracking number |
|      5 |      6 | Timestamp |

Message-specific payload fields are laid out at fixed offsets from the start of
the message:

| Type | Extra fields |
| ---- | ------------ |
| `A` | `11: order_ref u64`, `19: side char`, `20: shares u32`, `24: stock char[8]`, `32: price u32` |
| `E` | `11: order_ref u64`, `19: executed_shares u32`, `23: match_number u64` |
| `X` | `11: order_ref u64`, `19: cancelled_shares u32` |
| `D` | `11: order_ref u64` |
| `U` | `11: original_order_ref u64`, `19: new_order_ref u64`, `27: shares u32`, `31: price u32` |

The parser normalizes each binary message into an `ItchEvent` with common
fields: `kind`, `stock_locate`, `tracking_number`, `timestamp`, `order_ref`,
`new_order_ref`, `side`, `qty`, `price`, `match_number`, `stock`, and
`valid_mask`. The valid mask tells downstream code which payload fields are
meaningful for that event:

| Event | Valid payload fields |
| ----- | -------------------- |
| `ADD` | `order_ref`, `side`, `qty`, `price`, `stock` |
| `EXECUTE` | `order_ref`, `qty`, `match_number` |
| `CANCEL` | `order_ref`, `qty` |
| `DELETE` | `order_ref` |
| `REPLACE` | `order_ref`, `new_order_ref`, `qty`, `price` |

The core order lifecycle rules are:

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
  old side, old stock, old locate, new quantity, and new price. The replace
  message intentionally does not carry side or stock because those do not
  change.

## Python Reference Scripts

The helper scripts in `scripts/` implement the simplified ITCH subset described
in `localref/simp_itch_spec.md`.

### `scripts/packet_gen.py`

Generates binary ITCH payload messages for `A`, `E`, `X`, `D`, and `U`.
Fields are packed big-endian, timestamps are 6-byte `uint48`, prices are raw
`Price(4)` integers, and stock symbols are ASCII space-padded to 8 bytes.

```python
from scripts import packet_gen

add = packet_gen.gen_add(1, 1, 100, 1001, "B", 100, "AAPL", 1_000_000)
exe = packet_gen.gen_execute(1, 2, 101, 1001, 30, 9001)
stream = packet_gen.gen_stream([add, exe])
```

For deterministic test data, use `PacketGenerator`, which auto-increments
tracking numbers and timestamps:

```python
gen = packet_gen.PacketGenerator(locate=1, timestamp=100)
order_ref, add = gen.add(side="B", shares=100, stockSymbol="AAPL", price=1_000_000)
exe = gen.execute(order_ref, shares=25)
```

### `scripts/ref_parser.py`

Parses one packet with `parse_packet()` or a concatenated byte stream with
`parse_stream()`, returning normalized `ItchEvent` objects with spec-defined
valid masks. `TinyLob` applies those events as a reference order-lifecycle
model.

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

Run the Python checks with:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

## CPP Build

```bash
cmake -S . -B build
cmake --build build
```

```bash
python3 scripts/gen_cpp_parser_fixtures.py
./build/itch_cli scripts/data/smoke_all_types.bin
./build/itch_cli scripts/data/max_width_add.bin
```

## RTL Parser Cores

`rtl/itch_parser_core_legacy.sv` keeps the first working parser
microarchitecture. It decodes fields with direct byte-offset `case` statements,
which is useful as a simple baseline for later design comparisons.

`rtl/itch_parser_core_layout.sv` keeps the middle-ground refactor. It uses named
layout constants, helper functions, and packed normalized event state while
still spelling out each message type's field updates in the core.

`rtl/itch_parser_core.sv` is the maintained public parser core. It uses a static
microcoded field table from `rtl/itch_parser_pkg.sv` to map byte offsets to
normalized event fields, giving the most abstract protocol layout description
while preserving the same external interface and behavior.

All three cores expose the same normalized event interface, but the default
cocotb workflow selects only `itch_parser_core`.

Run the RTL validation workflow with:

```bash
uv run make -C scripts/cocotb
```
