from __future__ import annotations

import os
import pathlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import packet_gen
import ref_parser
import gen_bench_stream


CPP_BUILD = ROOT / "build"


def cpp_cli() -> pathlib.Path:
    candidates = [
        CPP_BUILD / "itch_cli.exe",
        CPP_BUILD / "itch_cli",
        CPP_BUILD / "Release" / "itch_cli.exe",
        CPP_BUILD / "Debug" / "itch_cli.exe",
        CPP_BUILD / "RelWithDebInfo" / "itch_cli.exe",
        CPP_BUILD / "MinSizeRel" / "itch_cli.exe",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def cpp_build_env() -> dict[str, str]:
    env = os.environ.copy()
    gcc16_root = pathlib.Path.home() / "opt" / "gcc-16.1.0"
    gcc16_bin = gcc16_root / "bin"
    if gcc16_bin.exists():
        env["PATH"] = f"{gcc16_bin}{os.pathsep}{env.get('PATH', '')}"
        lib_paths = [str(gcc16_root / "lib64"), str(gcc16_root / "lib")]
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = os.pathsep.join(lib_paths + ([existing] if existing else []))
    cmake_bin = pathlib.Path.home() / ".local" / "bin"
    if (cmake_bin / "cmake").exists():
        env["PATH"] = f"{cmake_bin}{os.pathsep}{env.get('PATH', '')}"
    return env


def write_temp_bin(payload: bytes) -> pathlib.Path:
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        tmp.write(payload)
        return pathlib.Path(tmp.name)


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

    def test_benchmark_stream_generation_is_valid_and_deterministic(self) -> None:
        stream_a, meta_a = gen_bench_stream.build_bench_stream(messages=100, seed=7)
        stream_b, meta_b = gen_bench_stream.build_bench_stream(messages=100, seed=7)

        events = ref_parser.parse_stream(stream_a)

        self.assertEqual(stream_a, stream_b)
        self.assertEqual(meta_a["bytes"], len(stream_a))
        self.assertEqual(meta_a["messages"], 100)
        self.assertEqual(meta_b["messages"], 100)
        self.assertEqual(len(events), 100)
        self.assertEqual(sum(meta_a["message_mix"].values()), 100)


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
        cmake_cmd = [
            "cmake",
            "-S",
            str(ROOT),
            "-B",
            str(CPP_BUILD),
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_CXX_COMPILER=g++-16.1",
        ]
        subprocess.run(cmake_cmd, check=True, env=cpp_build_env())
        subprocess.run(["cmake", "--build", str(CPP_BUILD)], check=True, env=cpp_build_env())

    def test_cli_rejects_truncated_stream(self) -> None:
        packet = packet_gen.gen_add(1, 2, 3, 4, "B", 5, "AAPL", 6)
        tmp_path = write_temp_bin(packet[:-1])
        try:

            result = subprocess.run(
                [str(cpp_cli()), str(tmp_path)],
                text=True,
                capture_output=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected end of stream", result.stderr)
        self.assertIn("parse error at byte", result.stderr)

    def test_cli_rejects_unknown_message_type(self) -> None:
        tmp_path = write_temp_bin(b"Z")
        try:
            result = subprocess.run(
                [str(cpp_cli()), str(tmp_path)],
                text=True,
                capture_output=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown MsgType", result.stderr)
        self.assertIn("parse error at byte 0", result.stderr)

    def test_cli_rejects_bad_add_side(self) -> None:
        bad_side = bytearray(packet_gen.gen_add(1, 2, 3, 4, "B", 5, "AAPL", 6))
        bad_side[19] = ord("Q")
        tmp_path = write_temp_bin(bytes(bad_side))
        try:
            result = subprocess.run(
                [str(cpp_cli()), str(tmp_path)],
                text=True,
                capture_output=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown Add-Messgae Side Symbol", result.stderr)
        self.assertIn("parse error at byte 19", result.stderr)

    def test_cli_output_matches_reference_parser(self) -> None:
        stream = packet_gen.gen_stream(
            [
                packet_gen.gen_add(1, 1, 100, 1001, "B", 100, "AAPL", 1_000_000),
                packet_gen.gen_add(1, 2, 101, 1002, "S", 50, "MSFT", 1_010_000),
                packet_gen.gen_execute(1, 3, 102, 1001, 30, 9001),
                packet_gen.gen_cancel(1, 4, 103, 1001, 20),
                packet_gen.gen_replace(1, 5, 104, 1002, 2002, 60, 1_005_000),
                packet_gen.gen_delete(1, 6, 105, 2002),
            ]
        )

        tmp_path = write_temp_bin(stream)
        try:

            result = subprocess.run(
                [str(cpp_cli()), str(tmp_path)],
                text=True,
                capture_output=True,
                check=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        self.assertEqual(result.stdout.rstrip("\n"), ref_parser.format_stream(stream))
        self.assertEqual(result.stderr, "")

    def test_cli_debug_lob_applies_lifecycle_like_reference_model(self) -> None:
        stream = packet_gen.gen_stream(
            [
                packet_gen.gen_add(1, 1, 100, 1001, "B", 100, "AAPL", 1_000_000),
                packet_gen.gen_add(1, 2, 101, 1002, "S", 50, "MSFT", 1_010_000),
                packet_gen.gen_execute(1, 3, 102, 1001, 30, 9001),
                packet_gen.gen_cancel(1, 4, 103, 1001, 20),
                packet_gen.gen_replace(1, 5, 104, 1002, 2002, 60, 1_005_000),
                packet_gen.gen_delete(1, 6, 105, 2002),
            ]
        )

        tmp_path = write_temp_bin(stream)
        try:

            result = subprocess.run(
                [str(cpp_cli()), "--debug-lob", str(tmp_path)],
                text=True,
                capture_output=True,
                check=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        lob = ref_parser.TinyLob()
        lob.apply_all(ref_parser.parse_stream(stream))

        self.assertEqual(set(lob.orders), {1001})
        self.assertEqual(result.stdout.rstrip("\n"), ref_parser.format_stream(stream))
        self.assertEqual(
            result.stderr.splitlines()[-3:],
            [
                "[lob] applied D 1 105 2002 N N N N N N 00000001",
                "[lob] active_orders=1",
                "[lob] order 1001 1 AAPL B 50 100.0000",
            ],
        )

    def test_cli_benchmark_json_reports_event_count(self) -> None:
        stream, _ = gen_bench_stream.build_bench_stream(messages=50, seed=11)

        tmp_path = write_temp_bin(stream)
        try:

            result = subprocess.run(
                [str(cpp_cli()), "--bench", "--json", "--repeat", "2", str(tmp_path)],
                text=True,
                capture_output=True,
                check=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        payload = json.loads(result.stdout)
        self.assertEqual(payload["parser"], "cpp")
        self.assertEqual(payload["bytes"], len(stream))
        self.assertEqual(payload["events"], len(ref_parser.parse_stream(stream)))
        self.assertEqual(payload["repeat"], 2)
        self.assertEqual(len(payload["elapsed_ns"]), 2)
        self.assertGreater(payload["messages_per_sec"], 0)

    def test_cli_benchmark_breakdown_json_reports_stage_timings(self) -> None:
        stream, _ = gen_bench_stream.build_bench_stream(messages=50, seed=12)

        tmp_path = write_temp_bin(stream)
        try:
            result = subprocess.run(
                [
                    str(cpp_cli()),
                    "--bench-breakdown",
                    "--json",
                    "--repeat",
                    "2",
                    str(tmp_path),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        payload = json.loads(result.stdout)
        self.assertEqual(payload["parser"], "cpp_breakdown")
        self.assertEqual(payload["bytes"], len(stream))
        self.assertEqual(payload["events"], len(ref_parser.parse_stream(stream)))
        self.assertEqual(payload["repeat"], 2)
        self.assertEqual(len(payload["parse_ns"]), 2)
        self.assertGreater(payload["median_parse_ns"], 0)
        self.assertEqual(sum(row["messages"] for row in payload["message_types"].values()), 50)

    def test_python_profile_script_json_reports_event_count(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "profile_python_parser.py"),
                "--messages",
                "50",
                "--repeat",
                "2",
                "--json",
            ],
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["dataset"]["messages"], 50)
        self.assertEqual(payload["python"]["events"], 50)
        self.assertEqual(payload["python"]["repeat"], 2)
        self.assertGreater(payload["python"]["median_parse_ns"], 0)

    def test_profile_parsers_smoke_without_rtl(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "profile_parsers.py"),
                "--messages",
                "50",
                "--repeat",
                "2",
                "--skip-rtl",
                "--build-cpp",
                "--json",
            ],
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["dataset"]["messages"], 50)
        self.assertEqual(payload["python"]["events"], 50)
        self.assertEqual(payload["cpp"]["events"], 50)
        self.assertNotIn("rtl", payload)
        self.assertGreater(payload["cpp"]["median_parse_ns"], 0)

    def test_benchmark_script_smoke_without_rtl(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "bench_parsers.py"),
                "--messages",
                "100",
                "--repeat",
                "2",
                "--skip-rtl",
                "--build-cpp",
            ],
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )

        self.assertIn("| Python |", result.stdout)
        self.assertIn("| C++ |", result.stdout)
        self.assertIn("Dataset: tmp/bench_stream.bin", result.stdout)

    @unittest.skipUnless(
        shutil.which("make") and shutil.which("verilator") and (shutil.which("cocotb-config") or shutil.which("uv")),
        "RTL benchmark smoke requires make, verilator, and cocotb via PATH or uv",
    )
    def test_rtl_benchmark_smoke_writes_cycle_json(self) -> None:
        stream, _ = gen_bench_stream.build_bench_stream(messages=25, seed=13)
        with tempfile.TemporaryDirectory() as td:
            stream_path = pathlib.Path(td) / "rtl_bench.bin"
            out_path = pathlib.Path(td) / "rtl_bench.json"
            stream_path.write_bytes(stream)

            make_cmd = ["make"]
            if shutil.which("uv") and not shutil.which("cocotb-config"):
                make_cmd = ["uv", "run", "make"]

            subprocess.run(
                make_cmd
                + [
                    "-C",
                    str(ROOT / "scripts" / "cocotb"),
                    f"BENCH_STREAM={stream_path}",
                    f"RTL_BENCH_JSON={out_path}",
                    "COCOTB_TEST_MODULES=bench_itch_parser_core",
                ],
                check=True,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
            )

            payload = json.loads(out_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["bytes"], len(stream))
        self.assertEqual(payload["bytes_accepted"], len(stream))
        self.assertEqual(payload["events"], len(ref_parser.parse_stream(stream)))
        self.assertGreaterEqual(payload["total_cycles"], payload["accepted_byte_cycles"])
        self.assertIn("state_cycles", payload)
        self.assertIn("message_types", payload)
        self.assertIn("input_stall_cycles", payload)
        self.assertIn("output_stall_cycles", payload)


if __name__ == "__main__":
    unittest.main()
