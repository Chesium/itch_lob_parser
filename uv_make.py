import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def external_tool(name: str) -> str | None:
    current = Path(sys.argv[0]).resolve()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        candidate = shutil.which(name, path=entry)
        if candidate is None:
            continue
        if Path(candidate).resolve() == current:
            continue
        return candidate
    return None


def is_cocotb_make_dir(value: str) -> bool:
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve() == (ROOT / "scripts/cocotb").resolve()


def run_cocotb_make(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    script_args: list[str] = []
    for arg in args:
        if arg in {"all", "sim"}:
            continue
        if arg == "clean":
            script_args.append("--clean")
            continue
        if "=" in arg and not arg.startswith("-"):
            key, value = arg.split("=", 1)
            env[key] = value
            continue
        script_args.append(arg)

    script = ROOT / "scripts/cocotb/run_verilator.py"
    return subprocess.run([sys.executable, str(script), *script_args], env=env)


def main() -> None:
    if os.name == "nt" and len(sys.argv) >= 3 and sys.argv[1] == "-C" and is_cocotb_make_dir(sys.argv[2]):
        completed = run_cocotb_make(sys.argv[3:])
        sys.exit(completed.returncode)

    make = "mingw32-make" if os.name == "nt" else "make"
    make_path = external_tool(make)
    if make_path is None:
        sys.exit(f"{make} was not found on PATH.")
    completed = subprocess.run([make_path, *sys.argv[1:]])
    sys.exit(completed.returncode)
