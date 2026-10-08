"""Build the diagnostic core with GCC/Clang, without installing a build system."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

from version import version_header

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    (build / "xemu-libretro-version.h").write_bytes(version_header())
    suffix = ".dll" if sys.platform == "win32" else ".dylib" if sys.platform == "darwin" else ".so"
    output = build / ("xemu_libretro" + suffix)
    flags = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror"]
    flags += ["-dynamiclib"] if sys.platform == "darwin" else ["-shared"]
    if sys.platform != "win32":
        flags += ["-fPIC", "-fvisibility=hidden"]
    if sys.platform.startswith("linux"):
        flags += ["-Wl,--no-undefined"]
    subprocess.run(shlex.split(args.cc) + flags + [
        "-I", str(ROOT / "third_party/libretro"), "-I", str(build), str(ROOT / "src/core.c"),
        "-o", str(output),
    ], check=True)
    print(f"Built {output}", flush=True)
    if args.test:
        subprocess.run([sys.executable, str(ROOT / "tests/smoke.py"), str(output)], check=True)


if __name__ == "__main__":
    main()
