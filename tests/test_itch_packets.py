from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import packet_gen
import ref_parser


class PacketGeneratorTests(unittest.TestCase):
    def test_add_packet_matches_spec_layout(self) -> None:
        packet = packet_gen.gen_add(
            locate=0x1234,
            trackN=0xABCD,
            timestamp=0x010203040506,
            orderref=0x0102030405060708,
            side="B",
            shares=100,
            stockSymbol="AAPL",
            price=1_732_500,
        )

        self.assertEqual(len(packet), 36)
        self.assertEqual(
            packet.hex(" "),
            "41 12 34 ab cd 01 02 03 04 05 06 "
            "01 02 03 04 05 06 07 08 42 00 00 00 64 "
            "41 41 50 4c 20 20 20 20 00 1a 6f 94",
        )

    def test_each_message_length(self) -> None:
        packets = [
            packet_gen.gen_add(1, 2, 3, 1001, "S", 10, "MSFT", 250_000),
            packet_gen.gen_execute(1, 2, 3, 1001, 5, 999),
            packet_gen.gen_cancel(1, 2, 3, 1001, 4),
            packet_gen.gen_delete(1, 2, 3, 1001),
            packet_gen.gen_replace(1, 2, 3, 1001, 2001, 9, 251_000),
        ]

        for packet in packets:
            msg_type = packet_gen.parseMsgType(packet[0])
            self.assertEqual(len(packet), packet_gen.MESSAGE_LENGTHS[msg_type])

    def test_price_float_is_scaled_to_price4(self) -> None:
        packet = packet_gen.gen_add(1, 2, 3, 1001, "B", 10, "AAPL", 173.25)
        self.assertEqual(packet[-4:], (1_732_500).to_bytes(4, "big"))

    def test_generator_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            packet_gen.gen_add(1, 2, 3, 1001, "Q", 10, "AAPL", 100)
        with self.assertRaises(ValueError):
            packet_gen.gen_add(1, 2, 3, 1001, "B", 0, "AAPL", 100)
        with self.assertRaises(ValueError):
            packet_gen.gen_add(1, 2, 3, 1001, "B", 1, "TOO-LONG!", 100)
        with self.assertRaises(ValueError):
            packet_gen.gen_delete(1, 2, 1 << 48, 1001)


class ReferenceParserTests(unittest.TestCase):
    def test_parse_all_message_types_from_back_to_back_stream(self) -> None:
        packets = [
            packet_gen.gen_add(1, 10, 100, 1001, "B", 100, "AAPL", 1_000_000),
            packet_gen.gen_execute(1, 11, 101, 1001, 30, 9001),
            packet_gen.gen_cancel(1, 12, 102, 1001, 20),
            packet_gen.gen_replace(1, 13, 103, 1001, 2001, 60, 1_005_000),
            packet_gen.gen_delete(1, 14, 104, 2001),
        ]

        events = ref_parser.parse_stream(packet_gen.gen_stream(packets))

        self.assertEqual([event.kind for event in events], [
            packet_gen.EventKind.ADD,
            packet_gen.EventKind.EXECUTE,
            packet_gen.EventKind.CANCEL,
            packet_gen.EventKind.REPLACE,
            packet_gen.EventKind.DELETE,
        ])
        self.assertEqual(events[0].stock, b"AAPL    ")
        self.assertEqual(events[0].side, ref_parser.Side.BUY)
        self.assertEqual(events[0].valid_mask, ref_parser.ADD_VALID_MASK)
        self.assertEqual(events[1].match_number, 9001)
        self.assertEqual(events[1].valid_mask, ref_parser.EXEC_VALID_MASK)
        self.assertEqual(events[2].valid_mask, ref_parser.CANCEL_VALID_MASK)
        self.assertEqual(events[3].new_order_ref, 2001)
        self.assertEqual(events[3].valid_mask, ref_parser.REPLACE_VALID_MASK)
        self.assertEqual(events[4].valid_mask, ref_parser.DELETE_VALID_MASK)

    def test_format_event_matches_cpp_normalized_output(self) -> None:
        event = ref_parser.parse_packet(
            packet_gen.gen_add(1, 10, 100, 1001, "B", 100, "AAPL", 1_000_000)
        )

        self.assertEqual(
            ref_parser.format_event(event),
            "A 1 100 1001 N B 100 100.0000 N AAPL 01011101",
        )

    def test_format_stream_reads_back_to_back_binary_messages(self) -> None:
        stream = packet_gen.gen_stream(
            [
                packet_gen.gen_execute(1, 11, 101, 1001, 30, 9001),
                packet_gen.gen_delete(1, 12, 102, 1001),
            ]
        )

        self.assertEqual(
            ref_parser.format_stream(stream),
            "\n".join(
                [
                    "E 1 101 1001 N N 30 N 9001 N 00101001",
                    "D 1 102 1001 N N N N N N 00000001",
                ]
            ),
        )

    def test_smoke_sequence_leaves_expected_book_state(self) -> None:
        packets = [
            packet_gen.gen_add(1, 1, 1, 1001, "B", 100, "AAPL", 1_000_000),
            packet_gen.gen_add(1, 2, 2, 1002, "S", 50, "AAPL", 1_010_000),
            packet_gen.gen_execute(1, 3, 3, 1001, 30, 77),
            packet_gen.gen_cancel(1, 4, 4, 1001, 20),
            packet_gen.gen_replace(1, 5, 5, 1002, 2002, 60, 1_005_000),
            packet_gen.gen_delete(1, 6, 6, 2002),
        ]

        lob = ref_parser.TinyLob()
        lob.apply_all(ref_parser.parse_stream(packet_gen.gen_stream(packets)))

        self.assertEqual(set(lob.orders), {1001})
        self.assertEqual(lob.orders[1001].qty, 50)
        self.assertEqual(lob.orders[1001].price, 1_000_000)
        self.assertEqual(lob.orders[1001].side, ref_parser.Side.BUY)

    def test_partial_execute_and_cancel_to_zero_remove_order(self) -> None:
        exec_lob = ref_parser.TinyLob()
        exec_lob.apply_all(
            ref_parser.parse_stream(
                packet_gen.gen_stream(
                    [
                        packet_gen.gen_add(1, 1, 1, 10, "B", 10, "AAPL", 100),
                        packet_gen.gen_execute(1, 2, 2, 10, 4, 1),
                        packet_gen.gen_execute(1, 3, 3, 10, 6, 2),
                    ]
                )
            )
        )
        self.assertNotIn(10, exec_lob.orders)

        cancel_lob = ref_parser.TinyLob()
        cancel_lob.apply_all(
            ref_parser.parse_stream(
                packet_gen.gen_stream(
                    [
                        packet_gen.gen_add(1, 1, 1, 20, "S", 10, "MSFT", 100),
                        packet_gen.gen_cancel(1, 2, 2, 20, 7),
                        packet_gen.gen_cancel(1, 3, 3, 20, 3),
                    ]
                )
            )
        )
        self.assertNotIn(20, cancel_lob.orders)

    def test_replace_preserves_stock_locate_stock_and_side(self) -> None:
        events = ref_parser.parse_stream(
            packet_gen.gen_stream(
                [
                    packet_gen.gen_add(55, 1, 1, 100, "S", 12, "NVDA", 2_000_000),
                    packet_gen.gen_replace(55, 2, 2, 100, 101, 7, 2_100_000),
                ]
            )
        )
        lob = ref_parser.TinyLob()
        lob.apply_all(events)

        self.assertNotIn(100, lob.orders)
        self.assertEqual(lob.orders[101], ref_parser.Order(
            stock_locate=55,
            stock=b"NVDA    ",
            side=ref_parser.Side.SELL,
            qty=7,
            price=2_100_000,
        ))

    def test_parse_rejects_unknown_truncated_and_bad_side(self) -> None:
        with self.assertRaises(ref_parser.ParseError):
            ref_parser.parse_stream(b"Z")

        with self.assertRaises(ref_parser.ParseError):
            ref_parser.parse_stream(packet_gen.gen_add(1, 2, 3, 4, "B", 5, "AAPL", 6)[:-1])

        bad_side = bytearray(packet_gen.gen_add(1, 2, 3, 4, "B", 5, "AAPL", 6))
        bad_side[19] = ord("Q")
        with self.assertRaises(ref_parser.ParseError):
            ref_parser.parse_packet(bytes(bad_side))

    def test_lob_rejects_invalid_lifecycle_events(self) -> None:
        lob = ref_parser.TinyLob()
        add = ref_parser.parse_packet(packet_gen.gen_add(1, 1, 1, 100, "B", 10, "AAPL", 100))
        lob.apply(add)

        with self.assertRaises(ref_parser.BookError):
            lob.apply(add)
        with self.assertRaises(ref_parser.BookError):
            lob.apply(ref_parser.parse_packet(packet_gen.gen_execute(1, 2, 2, 999, 1, 1)))
        with self.assertRaises(ref_parser.BookError):
            lob.apply(ref_parser.parse_packet(packet_gen.gen_cancel(1, 3, 3, 100, 11)))
        with self.assertRaises(ref_parser.BookError):
            lob.apply(ref_parser.parse_packet(packet_gen.gen_replace(1, 4, 4, 999, 200, 1, 100)))

    def test_max_width_fields_round_trip(self) -> None:
        packet = packet_gen.gen_replace(
            locate=packet_gen.MAX_U16,
            trackN=packet_gen.MAX_U16,
            timestamp=packet_gen.MAX_U48,
            orderref=packet_gen.MAX_U64,
            neworderref=packet_gen.MAX_U64 - 1,
            shares=packet_gen.MAX_U32,
            price=packet_gen.MAX_U32,
        )

        event = ref_parser.parse_packet(packet)

        self.assertEqual(event.stock_locate, packet_gen.MAX_U16)
        self.assertEqual(event.tracking_number, packet_gen.MAX_U16)
        self.assertEqual(event.timestamp, packet_gen.MAX_U48)
        self.assertEqual(event.order_ref, packet_gen.MAX_U64)
        self.assertEqual(event.new_order_ref, packet_gen.MAX_U64 - 1)
        self.assertEqual(event.qty, packet_gen.MAX_U32)
        self.assertEqual(event.price, packet_gen.MAX_U32)


class CppCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(["cmake", "-S", str(ROOT), "-B", str(ROOT / "build")], check=True)
        subprocess.run(["cmake", "--build", str(ROOT / "build")], check=True)

    def test_cli_rejects_truncated_stream(self) -> None:
        packet = packet_gen.gen_add(1, 2, 3, 4, "B", 5, "AAPL", 6)

        with tempfile.NamedTemporaryFile(suffix=".bin") as tmp:
            tmp.write(packet[:-1])
            tmp.flush()

            result = subprocess.run(
                [str(ROOT / "build" / "itch_cli"), tmp.name],
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected end of stream", result.stderr)


if __name__ == "__main__":
    unittest.main()
