"""Cross-compile the Windows x64 core using xemu's pinned container toolchain."""
import argparse
from pathlib import Path
import subprocess
import sys

from build_native import ROOT, prepare

TOOLCHAIN = "localhost/xemu-retro-win64-toolchain:2881edd"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=Path.home() / "xemu-retro-win64")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--reconfigure", action="store_true")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Run through build_windows.ps1 or inside Linux/WSL with Podman installed.")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    prepare(ROOT / "upstream/xemu")
    subprocess.run(["podman", "build", "-t", TOOLCHAIN, "-f",
                    str(ROOT / "scripts/windows.Containerfile"), str(ROOT / "scripts")], check=True)
    build = args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    command = ["podman", "run", "--rm", "-v", f"{ROOT}:/src", "-v", f"{build}:/build",
               "-w", "/build", TOOLCHAIN, "python3", "/src/scripts/build_native.py",
               "--target", "windows-x64", "--source-dir", "/src/upstream/xemu",
               "--build-dir", "/build", "--jobs", str(args.jobs)]
    if args.reconfigure:
        command.append("--reconfigure")
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
