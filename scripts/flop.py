#!/usr/bin/env python3

"""Python translation of flop.pm."""

from __future__ import annotations

import argparse
import shlex
import sys
from collections.abc import Sequence

from eperl_util import vprintl


def _coerce_args(args: str | Sequence[str] | None) -> list[str]:
    if args is None:
        return []
    if isinstance(args, str):
        return shlex.split(args)
    if len(args) == 1:
        return shlex.split(args[0])
    return list(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flop",
        add_help=True,
        allow_abbrev=False,
        description="Generate Verilog flop code.",
    )
    parser.add_argument("-d", default="d")
    parser.add_argument("-q", default="q")
    parser.add_argument("-en", dest="en")
    parser.add_argument("-wid", default="1")
    parser.add_argument("-clk", default="clk")
    parser.add_argument("-rst")
    parser.add_argument("-rval", default="0")
    parser.add_argument("-indent", default="0")
    return parser


def flop(args: str | Sequence[str] | None = None) -> None:
    opts = _parser().parse_args(_coerce_args(args))

    indent = " " * int(opts.indent)
    bit_range = f"{opts.wid}-1:0"
    q_range = f"{opts.q}[{bit_range}]"
    d_range = f"{opts.d}[{bit_range}]"
    reset_value = f"{{{opts.wid}{{1'b{opts.rval}}}}}"
    unknown_value = f"{{{opts.wid}{{1'bx}}}}"

    vprintl(f"{indent}reg [{bit_range}] {opts.q};")
    if opts.rst:
        vprintl(f"{indent}always @(posedge {opts.clk} or negedge {opts.rst}) begin")
        vprintl(f"{indent}   if (!{opts.rst}) begin")
        vprintl(f"{indent}       {q_range} <= {reset_value};")
        vprintl(f"{indent}   end else begin")
    else:
        vprintl(f"{indent}always @(posedge {opts.clk}) begin")

    if opts.en is not None:
        vprintl(f"{indent}       if ({opts.en} == 1'b1) begin")
        vprintl(f"{indent}           {q_range} <= {d_range};")
        vprintl(f"{indent}       // VCS coverage off")
        vprintl(f"{indent}       end else if ({opts.en} == 1'b0) begin")
        vprintl(f"{indent}       end else begin")
        vprintl(f"{indent}           {q_range} <= {unknown_value};")
        vprintl(f"{indent}       // VCS coverage on")
        vprintl(f"{indent}       end")
    else:
        vprintl(f"{indent}       {q_range} <= {d_range};")

    if opts.rst:
        vprintl(f"{indent}   end")
    vprintl(f"{indent}end")


def main(argv: Sequence[str] | None = None) -> int:
    flop(sys.argv[1:] if argv is None else argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
