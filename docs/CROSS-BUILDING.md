# Linux ARM64 and RISC-V64

These experimental targets produce a separate `xemu_libretro.so` for each CPU
architecture. Use a RetroArch build for the same operating system and CPU.
An ARM64 Linux core is not an Android, macOS, or Windows ARM64 core.

## Build

Use an x86-64 Linux machine, or Ubuntu WSL on Windows, with Python 3, Git, and
Podman installed. Run from this repository:

```sh
python3 scripts/build_linux_cross.py --arch arm64 --test
python3 scripts/build_linux_cross.py --arch riscv64 --test
```

The first build downloads the toolchain and source dependencies. Compilation
runs inside the container defined by `scripts/linux-cross.Containerfile`;
Podman is only a build dependency. The default cache is
`$HOME/xemu-libretro-cross`. Keep it on the Linux filesystem when using WSL.
Use `--build-dir` to change it, `--jobs` to limit compiler concurrency, and
`--reconfigure` after changing build configuration.

| Target | Core output |
| --- | --- |
| Linux ARM64 / AArch64 | `build/native-dist/linux-arm64/xemu_libretro.so` |
| Linux RISC-V64 / RV64GC, LP64D | `build/native-dist/linux-riscv64/xemu_libretro.so` |

Each directory also contains the core information file, version, and upstream
license notices. Install the matching core using the normal
[RetroArch setup instructions](../README.md#installation). Xbox file locations
are identical across architectures; no launcher or standalone xemu is required.

The helper builds the DSP emulator from the pinned source in `upstream.json`,
using its locked Rust dependencies. This supplies the same DSP version required
by the pinned xemu source without relying on prebuilt DSP archives for each CPU.

The integration patch also adapts the RISC-V TCG backend to xemu's additional
scalar floating-point type entries. Vector sizing uses byte-size exponents
instead of enum ordinals. The unsupported scalar FP emitter follows xemu's
existing ARM64 guard; the guest translator enables that optimized FP path only
on x86-64 and uses its helper path on these targets.

## Linux compatibility

These are development builds using **Debian 13** libraries. The container's
Rust base image is pinned by digest; Debian packages come from its configured
repositories, so package updates can still change subsequent builds.

The core includes its private SDL3 and DSP implementation. It still links to
Linux shared libraries, including GLib, libepoxy, libslirp, zlib, libcurl,
libpcap, libsamplerate, and compiler/system runtimes. It is not a self-contained
binary that works on every Linux distribution. An older glibc or missing
dependency can prevent RetroArch from loading it. Matching CPU architecture
alone is insufficient.

On a Debian 13 target, the main runtime packages are:

```sh
sudo apt-get install libglib2.0-0t64 libepoxy0 libslirp0 zlib1g \
  libcurl4t64 libpcap0.8t64 libsamplerate0 libstdc++6 libgcc-s1
```

The current cross builds use X11 for their private graphics contexts. Supply
an X11 display (or XWayland) and a working **desktop OpenGL 4.0** driver.
OpenGL ES alone does not meet this requirement. A device running RetroArch
is not proof that its GPU or CPU can run Xbox emulation adequately.

## Tests

`--test` compiles and executes controller/audio helper tests and a minimal
libretro host under QEMU user emulation. The host loads the actual foreign
architecture core, checks its version/API, and checks retryable missing-file
handling. This does not boot an Xbox or test a game.

To test an existing build and attempt synthetic machine startup:

```sh
python3 scripts/build_linux_cross.py --arch arm64 --test-only --synthetic
python3 scripts/build_linux_cross.py --arch riscv64 --test-only --synthetic
```

This needs `DISPLAY` and an accessible `/tmp/.X11-unix` socket. The container
uses software OpenGL for this check. On some desktops, X11 authentication may
require additional container configuration. The synthetic check creates
temporary original halt-only ROMs, a dummy EEPROM, and a sparse raw disk;
it does not use Xbox firmware or games. It checks machine creation, video
callbacks, controller polling, idle/resume, reset, and shutdown.
On RISC-V it repeats startup with emulated 128-bit and 256-bit vector registers
in addition to the default CPU. These checks cover initialization and lifecycle,
not comprehensive guest SIMD instruction correctness.

CPU emulation and software rendering cannot establish native hardware
performance or game compatibility. Real ARM64 and RISC-V64 hardware testing
is required before these targets should be called game-tested.

## Recorded validation

Version `2026.10.08` built successfully for both targets using GCC 14.2 and
Rust 1.96.0 in the Debian 13 container. Both passed controller/audio helper
tests, core loading and missing-file retries, and synthetic startup through
QEMU user emulation with WSLg X11 and Mesa llvmpipe OpenGL 4.5. The RISC-V
synthetic check also passed with 128-bit and 256-bit vector registers enabled.
The full integration patch was replayed against pristine files from the pinned
xemu revision and reproduced the prepared source.

ELF inspection identified AArch64 and RISC-V binaries respectively. Both cores
directly reference symbols through `GLIBC_2.39`, `GLIBCXX_3.4.32`, and
`CXXABI_1.3.15`. These are direct symbol requirements, not a promise that all
transitive Debian 13 dependencies will work on an older distribution.

No actual Xbox firmware, dashboard, or game was tested on these architectures.
No native ARM64/RISC-V64 device was used, and these results do not establish
playable speed. Public binary release packaging remains separate work.
