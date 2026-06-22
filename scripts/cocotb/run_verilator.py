from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import cocotb_tools.config
import find_libpython
from cocotb_tools.runner import get_runner


THIS_DIR = Path(__file__).resolve().parent
ROOT_DIR = THIS_DIR.parents[1]
RTL_DIR = ROOT_DIR / "rtl"
BUILD_DIR = THIS_DIR / "sim_build"
COCOTB_VERSION = "2.0.1"
COCOTB_SRC_DIR = ROOT_DIR / ".tmp" / f"cocotb-{COCOTB_VERSION}"


def run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def ensure_cocotb_source() -> Path:
    if COCOTB_SRC_DIR.exists():
        return COCOTB_SRC_DIR

    archive = ROOT_DIR / ".tmp" / f"cocotb-{COCOTB_VERSION}.tar.gz"
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        url = f"https://files.pythonhosted.org/packages/source/c/cocotb/cocotb-{COCOTB_VERSION}.tar.gz"
        urllib.request.urlretrieve(url, archive)

    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(archive.parent)
    return COCOTB_SRC_DIR


def write_patched_vpi_impl(cocotb_src: Path) -> Path:
    source = cocotb_src / "src/cocotb/share/lib/vpi/VpiImpl.cpp"
    patched = BUILD_DIR / "VpiImpl_verilator.cpp"
    text = source.read_text()
    text = text.replace(
        '#include "VpiImpl.h"',
        '#define vlog_startup_routines cocotb_hidden_vlog_startup_routines_decl\n#include "VpiImpl.h"',
        1,
    )
    text = text.replace(
        "#define CASE_STR",
        "#undef vlog_startup_routines\n#define CASE_STR",
        1,
    )
    patched.write_text(text)
    return patched


def write_patched_verilator_cpp() -> Path:
    source = Path(cocotb_tools.config.share_dir) / "lib/verilator/verilator.cpp"
    patched = BUILD_DIR / "verilator_msvc.cpp"
    text = source.read_text()
    text = text.replace('#include <libgen.h>  // basename\n', "")
    text = text.replace(
        '#include <string>  // std::string\n',
        "#include <cstring>  // strrchr\n"
        '#include <string>  // std::string\n'
        "\n"
        "static const char *basename(const char *path) {\n"
        "    const char *last_slash = strrchr(path, '/');\n"
        "    const char *last_backslash = strrchr(path, '\\\\');\n"
        "    const char *base = last_slash > last_backslash ? last_slash : last_backslash;\n"
        "    return base ? base + 1 : path;\n"
        "}\n",
        1,
    )
    patched.write_text(text)
    return patched


def write_patched_vpi_signal(cocotb_src: Path) -> Path:
    source = cocotb_src / "src/cocotb/share/lib/vpi/VpiSignal.cpp"
    patched = BUILD_DIR / "VpiSignal_msvc.cpp"
    patched.write_text(source.read_text().replace("leftRange != NULL and rightRange != NULL", "leftRange != NULL && rightRange != NULL"))
    return patched


def build_windows_msvc() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    verilator = shutil.which("verilator")
    if verilator is None:
        raise SystemExit("verilator was not found on PATH.")
    if shutil.which("cl") is None or shutil.which("nmake") is None:
        raise SystemExit("MSVC cl.exe and nmake.exe must be on PATH. Run vcvarsall.bat x64 first.")

    if "VERILATOR_ROOT" not in os.environ:
        os.environ["VERILATOR_ROOT"] = str(Path(verilator).resolve().parents[1])
    os.environ["VERILATOR_ROOT"] = os.environ["VERILATOR_ROOT"].replace("\\", "/")

    cocotb_src = ensure_cocotb_source()
    share_lib = cocotb_src / "src/cocotb/share/lib"
    include_dirs = [
        BUILD_DIR,
        Path(os.environ["VERILATOR_ROOT"]) / "include",
        Path(os.environ["VERILATOR_ROOT"]) / "include/vltstd",
        cocotb_src / "src/cocotb/share/include",
        cocotb_src / "src/cocotb",
        share_lib / "vpi",
        share_lib / "gpi",
        share_lib / "utils",
        share_lib / "gpi_log",
        Path(sysconfig.get_paths()["include"]),
    ]
    libs_dir = Path(cocotb_tools.config.libs_dir)
    python_lib_dir = Path(sys.base_prefix) / "libs"
    patched_vpi_impl = write_patched_vpi_impl(cocotb_src)
    patched_vpi_signal = write_patched_vpi_signal(cocotb_src)

    verilator_cpp = write_patched_verilator_cpp()
    run(
        [
            verilator,
            "-cc",
            "--exe",
            "-Mdir",
            str(BUILD_DIR),
            "--top-module",
            "itch_parser_core",
            "--vpi",
            "--public-flat-rw",
            "--prefix",
            "Vtop",
            "-o",
            "itch_parser_core",
            "-Wall",
            "-Wno-fatal",
            "--timescale",
            "1ns/1ps",
            str(verilator_cpp),
            str(patched_vpi_impl),
            str(share_lib / "vpi/VpiCbHdl.cpp"),
            str(share_lib / "vpi/VpiObj.cpp"),
            str(share_lib / "vpi/VpiIterator.cpp"),
            str(patched_vpi_signal),
            str(RTL_DIR / "itch_parser_pkg.sv"),
            str(RTL_DIR / "itch_parser_core.sv"),
        ]
    )
    with (BUILD_DIR / "Vtop__ALL.cpp").open("w") as included:
        subprocess.run(
            [
                str(Path(os.environ["VERILATOR_ROOT"]) / "bin/verilator_includer.bat"),
                "-DVL_INCLUDE_OPT=include",
                "Vtop.cpp",
                "Vtop___024root__0.cpp",
                "Vtop__Dpi.cpp",
                "Vtop__ConstPool__0__Slow.cpp",
                "Vtop___024root__Slow.cpp",
                "Vtop___024root__0__Slow.cpp",
                "Vtop_itch_parser_pkg__Slow.cpp",
                "Vtop__Syms__Slow.cpp",
            ],
            cwd=BUILD_DIR,
            check=True,
            stdout=included,
        )

    cmake_lists = BUILD_DIR / "CMakeLists.txt"
    sources = [
        str(verilator_cpp),
        "VpiImpl_verilator.cpp",
        str(share_lib / "vpi/VpiCbHdl.cpp"),
        str(share_lib / "vpi/VpiObj.cpp"),
        str(share_lib / "vpi/VpiIterator.cpp"),
        "VpiSignal_msvc.cpp",
        "Vtop__ALL.cpp",
        str(Path(os.environ["VERILATOR_ROOT"]) / "include/verilated.cpp"),
        str(Path(os.environ["VERILATOR_ROOT"]) / "include/verilated_dpi.cpp"),
        str(Path(os.environ["VERILATOR_ROOT"]) / "include/verilated_vpi.cpp"),
        str(Path(os.environ["VERILATOR_ROOT"]) / "include/verilated_threads.cpp"),
    ]
    cmake_lists.write_text(
        "\n".join(
            [
                "cmake_minimum_required(VERSION 3.20)",
                "project(itch_parser_core_sim LANGUAGES CXX)",
                "add_executable(itch_parser_core",
                *[f"  {Path(source).as_posix()}" for source in sources],
                ")",
                "target_compile_features(itch_parser_core PRIVATE cxx_std_20)",
                "target_compile_definitions(itch_parser_core PRIVATE VERILATOR=1 VM_COVERAGE=0 VM_SC=0 VM_TIMING=0 VM_TRACE=0 VM_TRACE_FST=0 VM_TRACE_VCD=0 VM_TRACE_SAIF=0 COCOTBVPI_EXPORTS VERILATOR __STDC_FORMAT_MACROS PLI_DLLISPEC=)",
                "target_include_directories(itch_parser_core PRIVATE",
                *[f"  {include_dir.as_posix()}" for include_dir in include_dirs],
                ")",
                f"target_link_directories(itch_parser_core PRIVATE {libs_dir.as_posix()})",
                f"target_link_directories(itch_parser_core PRIVATE {python_lib_dir.as_posix()})",
                "target_link_libraries(itch_parser_core PRIVATE gpi gpilog)",
                "",
            ]
        )
    )
    cmake_build = BUILD_DIR / "cmake-build"
    env = os.environ.copy()
    env["CMAKE_GENERATOR"] = "NMake Makefiles"
    subprocess.run(["cmake", "-S", str(BUILD_DIR), "-B", str(cmake_build), "-DCMAKE_BUILD_TYPE=Release"], check=True, env=env)
    subprocess.run(["cmake", "--build", str(cmake_build)], check=True, env=env)

    test_env = os.environ.copy()
    test_env.update(
        {
            "COCOTB_TEST_MODULES": os.environ.get("COCOTB_TEST_MODULES", "test_itch_parser_core"),
            "COCOTB_TOPLEVEL": "itch_parser_core",
            "TOPLEVEL_LANG": "verilog",
            "COCOTB_RESULTS_FILE": str(THIS_DIR / "results.xml"),
            "LIBPYTHON_LOC": find_libpython.find_libpython() or "",
            "PYTHONPATH": os.pathsep.join(sys.path),
            "PYGPI_PYTHON_BIN": sys.executable,
            "PATH": f"{libs_dir}{os.pathsep}{Path(sys.base_prefix)}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{test_env['PATH']}",
            "CMAKE_GENERATOR": os.environ.get("CMAKE_GENERATOR", "NMake Makefiles"),
            "ITCH_CPP_BUILD_DIR": str(ROOT_DIR / "build-msvc"),
        }
    )
    results_xml = THIS_DIR / "results.xml"
    if results_xml.exists():
        results_xml.unlink()
    subprocess.run(
        [str(cmake_build / "itch_parser_core.exe")],
        cwd=THIS_DIR,
        check=True,
        env=test_env,
    )
    if not results_xml.exists():
        raise SystemExit("Simulation exited without producing results.xml.")
    results = ET.parse(results_xml).getroot()
    failures = sum(int(node.attrib.get("failures", "0")) for node in results.iter())
    failures += sum(1 for _ in results.iter("failure"))
    errors = sum(int(node.attrib.get("errors", "0")) for node in results.iter())
    errors += sum(1 for _ in results.iter("error"))
    if failures or errors:
        raise SystemExit(
            f"cocotb reported {failures} failures and {errors} errors; see {results_xml}."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    if args.clean:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
        results = THIS_DIR / "results.xml"
        if results.exists():
            results.unlink()
        return

    if os.name == "nt":
        build_windows_msvc()
        return

    runner = get_runner("verilator")
    test_modules = os.environ.get("COCOTB_TEST_MODULES", "test_itch_parser_core")

    runner.build(
        sources=[
            RTL_DIR / "itch_parser_pkg.sv",
            RTL_DIR / "itch_parser_core.sv",
        ],
        hdl_toplevel="itch_parser_core",
        build_args=["-Wall", "-Wno-fatal"],
        build_dir=BUILD_DIR,
        timescale=("1ns", "1ps"),
        always=True,
    )
    runner.test(
        test_module=test_modules,
        hdl_toplevel="itch_parser_core",
        hdl_toplevel_lang="verilog",
        build_dir=BUILD_DIR,
        test_dir=THIS_DIR,
        results_xml="results.xml",
        extra_env={
            "CMAKE_GENERATOR": os.environ.get("CMAKE_GENERATOR", "MinGW Makefiles"),
        },
    )


if __name__ == "__main__":
    main()
