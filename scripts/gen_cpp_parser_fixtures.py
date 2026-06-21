#!/usr/bin/env python3
"""Generate binary ITCH fixture files for the C++ parser.

The messages are encoded with scripts/packet_gen.py and follow the simplified
payload-only format documented in localref/simp_itch_spec.md:

  [message type][common header][message-specific fields]

There is no SoupBinTCP/MoldUDP framing here. Each .bin file is just one or more
fixed-length ITCH payload messages concatenated back-to-back, exactly what the
C++ parser expects to walk through.
"""

from __future__ import annotations

from pathlib import Path

from packet_gen import (
    MAX_U16,
    MAX_U32,
    MAX_U48,
    MAX_U64,
    PacketGenerator,
    gen_add,
    gen_cancel,
    gen_delete,
    gen_execute,
    gen_replace,
    gen_stream,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = SCRIPT_DIR / "data"


def write_fixture(out_dir: Path, name: str, messages: list[bytes], note: str) -> None:
    """Write one concatenated binary stream and add a short manifest entry."""

    stream = gen_stream(messages)
    path = out_dir / name
    path.write_bytes(stream)

    lengths = ", ".join(str(len(message)) for message in messages)
    MANIFEST_LINES.append(
        f"- {name}: {len(messages)} messages, {len(stream)} bytes "
        f"(message lengths: {lengths})\n  {note}"
    )


MANIFEST_LINES: list[str] = []


def build_fixtures(out_dir: Path) -> None:
    """Create a small suite of deterministic parser test streams."""

    out_dir.mkdir(parents=True, exist_ok=True)
    MANIFEST_LINES.clear()

    # Smoke test from localref/simp_itch_spec.md section 9. This exercises all
    # five message types in one back-to-back stream: A, A, E, X, U, D.
    smoke = PacketGenerator(locate=1, tracking_number=1, timestamp=100)
    buy_ref, add_buy = smoke.add(
        orderref=1001,
        side="B",
        shares=100,
        stockSymbol="AAPL",
        price=1_000_000,  # raw Price(4): 100.0000
    )
    sell_ref, add_sell = smoke.add(
        orderref=1002,
        side="S",
        shares=50,
        stockSymbol="MSFT",
        price=1_010_000,  # raw Price(4): 101.0000
    )
    exec_buy = smoke.execute(buy_ref, shares=30, matchNumber=9001)
    cancel_buy = smoke.cancel(buy_ref, shares=20)
    repl_ref, replace_sell = smoke.replace(
        sell_ref,
        neworderref=2002,
        shares=60,
        price=1_005_000,  # raw Price(4): 100.5000
    )
    delete_repl = smoke.delete(repl_ref)
    write_fixture(
        out_dir,
        "smoke_all_types.bin",
        [add_buy, add_sell, exec_buy, cancel_buy, replace_sell, delete_repl],
        "Spec smoke flow. After book semantics, order 1001 remains with qty=50.",
    )

    # One message per file is useful when debugging byte offsets or stepping
    # through ItchParser::parseAdd/parseExecute/etc. in isolation.
    single = PacketGenerator(locate=2, tracking_number=10, timestamp=1_000)
    ref, add = single.add(
        orderref=3001,
        side="B",
        shares=250,
        stockSymbol="NVDA",
        price=12_345_600,
    )
    write_fixture(out_dir, "single_add.bin", [add], "One ADD message.")
    write_fixture(
        out_dir,
        "single_execute.bin",
        [single.execute(ref, shares=75, matchNumber=9100)],
        "One EXECUTE message for order_ref=3001.",
    )
    write_fixture(
        out_dir,
        "single_cancel.bin",
        [single.cancel(ref, shares=25)],
        "One CANCEL message for order_ref=3001.",
    )
    write_fixture(
        out_dir,
        "single_delete.bin",
        [single.delete(ref)],
        "One DELETE message for order_ref=3001.",
    )
    new_ref, replace = single.replace(
        ref,
        neworderref=4001,
        shares=175,
        price=12_500_000,
    )
    write_fixture(
        out_dir,
        "single_replace.bin",
        [replace],
        f"One REPLACE message from order_ref=3001 to new_order_ref={new_ref}.",
    )

    # A lifecycle stream focused on repeated modifications to one order. This is
    # handy for checking that a downstream book model handles cumulative events.
    lifecycle = PacketGenerator(locate=3, tracking_number=100, timestamp=10_000)
    life_ref, life_add = lifecycle.add(
        orderref=5001,
        side="S",
        shares=1_000,
        stockSymbol="TSLA",
        price=2_500_000,
    )
    life_repl_ref, life_replace = lifecycle.replace(
        life_ref,
        neworderref=5002,
        shares=800,
        price=2_490_000,
    )
    write_fixture(
        out_dir,
        "replace_then_execute.bin",
        [
            life_add,
            lifecycle.cancel(life_ref, shares=100),
            life_replace,
            lifecycle.execute(life_repl_ref, shares=300, matchNumber=9200),
            lifecycle.delete(life_repl_ref),
        ],
        "ADD, partial CANCEL, REPLACE, EXECUTE on new ref, then DELETE.",
    )

    # Max-width values catch truncation and endian mistakes. The C++ parser
    # should read these as unsigned fields in big-endian order.
    write_fixture(
        out_dir,
        "max_width_add.bin",
        [
            gen_add(
                locate=MAX_U16,
                trackN=MAX_U16,
                timestamp=MAX_U48,
                orderref=MAX_U64,
                side="S",
                shares=MAX_U32,
                stockSymbol="MAXTEST",
                price=MAX_U32,
            )
        ],
        "ADD message with max uint16/uint32/uint48/uint64 field values.",
    )

    manifest = [
        "# Generated ITCH Parser Fixtures",
        "",
        "Regenerate with:",
        "",
        "```sh",
        "python3 scripts/gen_cpp_parser_fixtures.py",
        "```",
        "",
        "Files:",
        "",
        *MANIFEST_LINES,
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(manifest), encoding="utf-8")


def main() -> None:
    build_fixtures(DEFAULT_OUT_DIR)
    print(f"Wrote {len(MANIFEST_LINES)} fixture files to {DEFAULT_OUT_DIR}")


if __name__ == "__main__":
    main()
