#!/usr/bin/env python3

"""Python translation of pipe.pm."""

from __future__ import annotations

import argparse
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field

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
        prog="pipe",
        add_help=True,
        allow_abbrev=False,
        description="Generate Verilog ready/valid pipe code.",
    )
    parser.add_argument("-prefix", default="pipe")
    parser.add_argument("-is", dest="input_skid", action="store_true")
    parser.add_argument("-os", dest="output_skid", action="store_true")
    parser.add_argument("-wid", default="1")
    parser.add_argument("-module", "-m", dest="module")
    parser.add_argument("-clk", default="clk")
    parser.add_argument("-rst", default="rst")
    parser.add_argument("-indent", default="0")
    return parser


@dataclass
class PipeGenerator:
    clk: str = "clk"
    rst: str = "rst"
    indent: int = 0
    code: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    regs: list[str] = field(default_factory=list)
    wires: list[str] = field(default_factory=list)

    @property
    def ind(self) -> str:
        return " " * self.indent

    def generate(
        self,
        *,
        prefix: str = "pipe",
        width: str = "1",
        module: str | None = None,
        input_skid: bool = False,
        output_skid: bool = False,
    ) -> None:
        vi = f"{prefix}_vi"
        ro = f"{prefix}_ro"
        di = f"{prefix}_di"
        vo = f"{prefix}_vo"
        ri = f"{prefix}_ri"
        do = f"{prefix}_do"
        bit_range = f"{width}-1:0"

        self.ports.append(f"{self.ind}input  {self.clk};")
        self.ports.append(f"{self.ind}input  {self.rst};")
        self.ports.append(f"{self.ind}input  {vi};")
        self.ports.append(f"{self.ind}output {ro};")
        self.ports.append(f"{self.ind}input  [{bit_range}] {di};")
        self.ports.append(f"{self.ind}output {vo};")
        self.ports.append(f"{self.ind}input  {ri};")
        self.ports.append(f"{self.ind}output [{bit_range}] {do};")

        pins = [vi, di, ro, vo, do, ri]

        if input_skid:
            vi, di, ro = self._skid(vi, di, ro, bit_range)

        vi, di, ro = self._pipe(vi, di, ro, bit_range)

        if output_skid:
            vi, di, ro = self._skid(vi, di, ro, bit_range)

        self.code.append("// PIPE OUTPUT")
        self.code.append(f"{self.ind}assign {ro} = {ri};")
        self.code.append(f"{self.ind}assign {vo} = {vi};")
        self.code.append(f"{self.ind}assign {do} = {di};")

        if module:
            vprintl(f"{self.ind}module {module} (")
            vprintl(f"\n{self.ind}  ,".join(pins))
            vprintl(f"{self.ind}  );")
            vprintl("// Port")
            vprintl("\n".join(self.ports))

        vprintl("// Reg")
        vprintl("\n".join(self.regs))
        vprintl("// Wire")
        vprintl("\n".join(self.wires))
        vprintl("// Code")
        vprintl("\n".join(self.code))

        if module:
            vprintl(f"{self.ind}endmodule")

    def _pipe(self, vi: str, di: str, ro: str, bit_range: str) -> tuple[str, str, str]:
        vo = f"pipe_{vi}"
        do = f"pipe_{di}"
        ri = f"pipe_{ro}"
        data_in = f"{di}[{bit_range}]"
        data_out = f"{do}[{bit_range}]"

        self.code.append("// PIPE READY")
        self.regs.append(f"reg    {vo};")
        self.wires.append(f"wire   {ro};")
        self.code.append(f"{self.ind}assign {ro} = {ri} || !{vo};")
        self.code.append("")

        self.code.append("// PIPE VALID")
        self.code.append(f"{self.ind}always @(posedge {self.clk} or negedge {self.rst}) begin")
        self.code.append(f"{self.ind}    if (!{self.rst}) begin")
        self.code.append(f"{self.ind}        {vo} <= 1'b0;")
        self.code.append(f"{self.ind}    end else begin")
        self.code.append(f"{self.ind}        if ({ro}) begin")
        self.code.append(f"{self.ind}            {vo} <= {vi};")
        self.code.append(f"{self.ind}        end")
        self.code.append(f"{self.ind}    end")
        self.code.append(f"{self.ind}end")
        self.code.append("")

        self.code.append("// PIPE DATA")
        self.regs.append(f"reg    [{bit_range}] {do};")
        self.code.append(f"{self.ind}always @(posedge {self.clk}) begin")
        self.code.append(f"{self.ind}    if ({ro} && {vi}) begin")
        self.code.append(f"{self.ind}        {data_out} <= {data_in};")
        self.code.append(f"{self.ind}    end")
        self.code.append(f"{self.ind}end")
        self.code.append("\n")

        return vo, do, ri

    def _skid(self, vi: str, di: str, ro: str, bit_range: str) -> tuple[str, str, str]:
        vs = f"skid_flop_{vi}"
        ds = f"skid_flop_{di}"
        rs = f"skid_flop_{ro}"
        vo = f"skid_{vi}"
        do = f"skid_{di}"
        ri = f"skid_{ro}"
        data_in = f"{di}[{bit_range}]"
        skid_data = f"{ds}[{bit_range}]"
        data_out = f"{do}[{bit_range}]"

        self.code.append("// SKID READY")
        self.regs.append(f"reg    {ro};")
        self.regs.append(f"reg    {rs};")
        self.code.append(f"{self.ind}always @(posedge {self.clk} or negedge {self.rst}) begin")
        self.code.append(f"{self.ind}   if (!{self.rst}) begin")
        self.code.append(f"{self.ind}       {ro} <= 1'b1;")
        self.code.append(f"{self.ind}       {rs} <= 1'b1;")
        self.code.append(f"{self.ind}   end else begin")
        self.code.append(f"{self.ind}       {ro} <= {ri};")
        self.code.append(f"{self.ind}       {rs} <= {ri};")
        self.code.append(f"{self.ind}   end")
        self.code.append(f"{self.ind}end")
        self.code.append("")

        self.code.append("// SKID VALID")
        self.regs.append(f"reg    {vs};")
        self.code.append(f"{self.ind}always @(posedge {self.clk} or negedge {self.rst}) begin")
        self.code.append(f"{self.ind}    if (!{self.rst}) begin")
        self.code.append(f"{self.ind}        {vs} <= 1'b0;")
        self.code.append(f"{self.ind}    end else begin")
        self.code.append(f"{self.ind}        if ({rs}) begin")
        self.code.append(f"{self.ind}            {vs} <= {vi};")
        self.code.append(f"{self.ind}        end")
        self.code.append(f"{self.ind}   end")
        self.code.append(f"{self.ind}end")
        self.code.append(f"{self.ind}assign {vo} = ({rs}) ? {vi} : {vs};")
        self.code.append("")

        self.code.append("// SKID DATA")
        self.regs.append(f"reg    [{bit_range}] {ds};")
        self.code.append(f"{self.ind}always @(posedge {self.clk}) begin")
        self.code.append(f"{self.ind}    if ({rs} & {vi}) begin")
        self.code.append(f"{self.ind}        {skid_data} <= {data_in};")
        self.code.append(f"{self.ind}    end")
        self.code.append(f"{self.ind}end")
        self.code.append(f"{self.ind}assign {data_out} = ({rs}) ? {data_in} : {skid_data};")
        self.code.append("\n")

        return vo, do, ri


def pipe(args: str | Sequence[str] | None = None) -> None:
    opts = _parser().parse_args(_coerce_args(args))
    PipeGenerator(clk=opts.clk, rst=opts.rst, indent=int(opts.indent)).generate(
        prefix=opts.prefix,
        width=opts.wid,
        module=opts.module,
        input_skid=opts.input_skid,
        output_skid=opts.output_skid,
    )


def main(argv: Sequence[str] | None = None) -> int:
    pipe(sys.argv[1:] if argv is None else argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
