"""Prepare pinned xemu and build the experimental desktop libretro core."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from version import version_header

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def prepare(source):
    upstream = json.loads((ROOT / "upstream.json").read_text())["xemu"]
    revision = upstream["revision"]
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "-c", "core.autocrlf=false", "clone", "--depth", "1",
             upstream["repository"], source])
    current = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if current != revision:
        dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True)
        if dirty:
            raise RuntimeError("Source checkout has changes and a different revision; use a separate --source-dir.")
        run(["git", "-C", source, "fetch", "--depth", "1", "origin", revision])
        run(["git", "-C", source, "checkout", "--detach", revision])

    patch = ROOT / "patches/xemu-libretro.patch"
    reverse = subprocess.run(["git", "-C", str(source), "apply", "--reverse", "--check", str(patch)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if reverse.returncode:
        run(["git", "-C", source, "apply", "--check", patch])
        run(["git", "-C", source, "apply", patch])

    overlays = [(p, source / p.relative_to(ROOT / "native"))
                for p in (ROOT / "native").rglob("*") if p.is_file() and p.suffix != ".info"]
    overlays.append((ROOT / "third_party/libretro/libretro.h", source / "ui/libretro.h"))
    manifest = source / ".xemu-retro-overlay.json"
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    updated = {}
    overlay_data = [(origin.read_bytes(), target) for origin, target in overlays]
    overlay_data.append((version_header(), source / "ui/xemu-libretro-version.h"))
    for data, target in overlay_data:
        key = str(target.relative_to(source))
        if target.exists() and target.read_bytes() != data:
            current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            if previous.get(key) != current_hash:
                raise RuntimeError(f"Local source edits would be overwritten: {target}. Preserve them before rebuilding.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
        updated[key] = hashlib.sha256(data).hexdigest()
    manifest.write_text(json.dumps(updated, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "upstream/xemu")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build/native")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--target", choices=("linux", "windows-x64"), default="linux")
    parser.add_argument("--cross-prefix", default="x86_64-w64-mingw32.static-")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--reconfigure", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--synthetic", action="store_true", help="Also construct an Xbox with synthetic halt-only firmware")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Run this build script inside Linux/WSL; use build_windows.ps1 for Windows.")
    windows = args.target == "windows-x64"
    if windows and (args.test or args.synthetic):
        parser.error("Test the Windows DLL using Windows Python after cross-compiling.")
    library = "xemu_libretro.dll" if windows else "xemu_libretro.so"
    source, build = args.source_dir.resolve(), args.build_dir.resolve()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    prepare(source)
    if args.prepare_only:
        return
    build.mkdir(parents=True, exist_ok=True)
    if args.reconfigure or not (build / "build.ninja").exists():
        platform_args = ["--enable-pie"]
        env = os.environ.copy()
        if windows:
            platform_args = [f"--cross-prefix={args.cross_prefix}", "--static", "--disable-pie"]
            env["AR"] = args.cross_prefix + "gcc-ar"
        run([source / "configure", "--extra-cflags=-DXBOX=1",
             "--target-list=i386-softmmu", "--disable-werror", "--disable-docs",
             "--disable-tools", "--disable-guest-agent", "--disable-plugins",
             "--disable-rust", "-Db_staticpic=true", "-Dlibretro=true", *platform_args], cwd=build, env=env)
    run(["ninja", "-C", build, f"-j{args.jobs}", library])
    if args.test or args.synthetic:
        io_test = build / "native_io_test"
        run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread",
             "-I", source / "ui", ROOT / "tests/native_io.c",
             source / "ui/xemu-retro-io.c", "-o", io_test])
        run([io_test])
        test = [sys.executable, ROOT / "tests/native_smoke.py", build / "xemu_libretro.so"]
        if args.synthetic:
            test.append("--synthetic")
        run(test)
    destination = ROOT / "build" / ("native-dist/windows-x64" if windows else "native-dist")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(build / library, destination / library)
    if windows:
        run([args.cross_prefix + "strip", "--strip-debug", destination / library])
    shutil.copy2(ROOT / "native/xemu_libretro.info", destination / "xemu_libretro.info")
    shutil.copy2(ROOT / "VERSION", destination / "VERSION")
    for notice in ("LICENSE", "COPYING", "COPYING.LIB"):
        shutil.copy2(source / notice, destination / notice)
    print(f"Native core: {destination / library}")


if __name__ == "__main__":
    main()
