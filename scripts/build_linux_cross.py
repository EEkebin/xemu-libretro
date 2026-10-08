"""Cross-build Linux ARM64/RISC-V64 cores in an isolated Debian 13 toolchain."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from build_native import ROOT, prepare, run

IMAGE = "localhost/xemu-libretro-linux-cross:debian13"
TARGETS = {
    "arm64": ("aarch64-linux-gnu", "aarch64-unknown-linux-gnu"),
    "riscv64": ("riscv64-linux-gnu", "riscv64gc-unknown-linux-gnu"),
}


def test_core(cache, arch, synthetic):
    triple, _ = TARGETS[arch]
    build = cache / ("linux-" + arch)
    compiler = triple + "-gcc"
    emulator = "qemu-aarch64" if arch == "arm64" else "qemu-riscv64"
    execute = [emulator, "-L", "/usr/" + triple,
               "-E", "LD_LIBRARY_PATH=/usr/lib/" + triple]
    io_test = build / "cross_io_test"
    smoke = build / "cross_native_smoke"
    run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread",
         "-I", ROOT / "native/ui", "-I", ROOT / "third_party/libretro",
         ROOT / "tests/native_io.c", ROOT / "native/ui/xemu-retro-io.c", "-o", io_test])
    run([*execute, io_test], timeout=60)
    run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
         "-I", ROOT / "third_party/libretro", ROOT / "tests/cross_native_smoke.c",
         "-ldl", "-o", smoke])
    cpus = [None]
    if arch == "riscv64" and synthetic:
        cpus += ["rv64,v=true,vlen=128", "rv64,v=true,vlen=256"]
    for cpu in cpus:
        with tempfile.TemporaryDirectory(prefix="smoke-" + arch + "-", dir=cache) as scratch:
            command = execute + (["-cpu", cpu] if cpu else [])
            command += [smoke, build / "xemu_libretro.so", scratch,
                        (ROOT / "VERSION").read_text().strip()]
            if synthetic:
                command.append("synthetic")
            print("+", " ".join(map(str, command)), flush=True)
            result = subprocess.run(list(map(str, command)), timeout=300,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            print(result.stdout, flush=True)
            result.check_returncode()
            if "CROSS NATIVE SMOKE PASS" not in result.stdout:
                raise RuntimeError("Core exited before completing the smoke test")


def build_dsp(cache, arch, jobs):
    pin = json.loads((ROOT / "upstream.json").read_text())["dsp56300"]
    source = cache / "dsp56300"
    if not source.exists():
        run(["git", "clone", "--depth", "1", "--branch", "v" + pin["version"], pin["repository"], source])
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != pin["revision"]:
        raise RuntimeError("DSP source revision differs from upstream.json; use a fresh build directory.")
    triple, rust_target = TARGETS[arch]
    env = os.environ.copy()
    env["CARGO_HOME"] = str(cache / "cargo-home")
    env["CARGO_TARGET_DIR"] = str(cache / "cargo-target")
    env["CARGO_TARGET_" + rust_target.upper().replace("-", "_") + "_LINKER"] = triple + "-gcc"
    env["CC_" + rust_target.replace("-", "_")] = triple + "-gcc"
    env["AR_" + rust_target.replace("-", "_")] = triple + "-ar"
    env["RUSTFLAGS"] = "-C relocation-model=pic"
    run(["cargo", "build", "--locked", "--release", "-p", "dsp56300-emu-ffi",
         "--target", rust_target, "-j", jobs], cwd=source, env=env)
    prefix = cache / ("dsp-" + arch)
    (prefix / "lib/pkgconfig").mkdir(parents=True, exist_ok=True)
    (prefix / "include").mkdir(exist_ok=True)
    shutil.copy2(cache / "cargo-target" / rust_target / "release/libdsp56300_emu_ffi.a", prefix / "lib")
    shutil.copy2(source / "crates/emu-ffi/include/dsp56300.h", prefix / "include")
    (prefix / "lib/pkgconfig/dsp56300-emu-ffi.pc").write_text(
        f"prefix={prefix}\nlibdir=${{prefix}}/lib\nincludedir=${{prefix}}/include\n"
        f"Name: dsp56300-emu-ffi\nDescription: xemu DSP emulator\nVersion: {pin['version']}\n"
        "Libs: -L${libdir} -ldsp56300_emu_ffi -lpthread -ldl -lm\nCflags: -I${includedir}\n")
    return prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=TARGETS, required=True)
    parser.add_argument("--build-dir", type=Path, default=Path.home() / "xemu-libretro-cross")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--reconfigure", action="store_true")
    parser.add_argument("--test", action="store_true", help="Run input/audio and core ABI checks under QEMU user emulation")
    parser.add_argument("--synthetic", action="store_true", help="Also test synthetic machine startup; requires an X11 display")
    parser.add_argument("--test-only", action="store_true", help="Test an existing build without rebuilding")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Run this developer build script inside Linux or WSL with Podman installed.")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    cache = args.build_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    if not args.inside:
        prepare(ROOT / "upstream/xemu")
        run(["podman", "build", "-t", IMAGE, "-f", ROOT / "scripts/linux-cross.Containerfile", ROOT / "scripts"])
        command = ["podman", "run", "--rm", "-v", f"{ROOT}:/src", "-v", f"{cache}:/build"]
        if args.synthetic:
            if not os.environ.get("DISPLAY"):
                parser.error("--synthetic needs DISPLAY and an accessible X11 socket")
            command += ["-v", "/tmp/.X11-unix:/tmp/.X11-unix:ro", "-e", "DISPLAY",
                        "-e", "SDL_VIDEO_DRIVER=x11", "-e", "LIBGL_ALWAYS_SOFTWARE=1"]
        command += [IMAGE, "python3", "/src/scripts/build_linux_cross.py", "--inside", "--build-dir", "/build",
                   "--arch", args.arch, "--jobs", args.jobs]
        for flag in ("reconfigure", "test", "synthetic", "test_only"):
            if getattr(args, flag):
                command.append("--" + flag.replace("_", "-"))
        run(command)
        return
    if args.test_only:
        test_core(cache, args.arch, args.synthetic)
        return
    prefix = build_dsp(cache, args.arch, args.jobs)
    triple, _ = TARGETS[args.arch]
    env = os.environ.copy()
    env["PKG_CONFIG_LIBDIR"] = f"{prefix}/lib/pkgconfig:/usr/lib/{triple}/pkgconfig:/usr/share/pkgconfig"
    env["PKG_CONFIG_PATH"] = ""
    command = [sys.executable, ROOT / "scripts/build_native.py", "--target", "linux-" + args.arch,
               "--source-dir", ROOT / "upstream/xemu", "--build-dir", cache / ("linux-" + args.arch),
               "--jobs", args.jobs]
    if args.reconfigure:
        command.append("--reconfigure")
    run(command, env=env)
    if args.test or args.synthetic:
        test_core(cache, args.arch, args.synthetic)


if __name__ == "__main__":
    main()
