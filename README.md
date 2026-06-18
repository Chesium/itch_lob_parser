# ITCH LOB Parser

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
