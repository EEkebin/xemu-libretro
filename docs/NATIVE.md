# Experimental native core

This target links xemu's Xbox/QEMU implementation into a libretro shared
library. It uses no standalone xemu executable. It is separate from the small
diagnostic core built by `scripts/build.py`.

## Build on Linux or Ubuntu WSL

The Linux build produces `xemu_libretro.so`. Windows x64 uses a separate native
DLL built with the toolchain described below; the two files are not interchangeable.

Dependencies used for the development build:

```sh
sudo apt-get install build-essential cmake ninja-build pkg-config python3-venv \
  python3-yaml python3-tomli libglib2.0-dev libpixman-1-dev libsdl3-dev \
  libepoxy-dev libvulkan-dev libslirp-dev libssl-dev libpcap-dev \
  libsamplerate0-dev libgtk-3-dev libcurl4-openssl-dev libpipewire-0.3-dev
```

The native build compiles a private, position-independent SDL3 from its pinned
upstream subproject. This prevents RetroArch's SDL2 symbols from intercepting
SDL3 calls, and avoids system static archives that lack PIC. Other pinned
upstream subprojects are fetched too. A C++ compiler and network access are
needed for the first build.

```sh
python3 scripts/build_native.py --build-dir "$HOME/xemu-libretro-build" --test
```

Use a build directory in WSL's Linux filesystem to reduce build I/O overhead.
The script checks out the xemu revision in `upstream.json`, applies
`patches/xemu-libretro.patch`, copies the sources from `native/ui`, and builds
the `xemu_libretro.so` Meson target. It checks existing source edits before
applying patches or replacing overlay files. Use `--reconfigure` after changing
configure options, or `--prepare-only` to inspect the patched source first.

Artifacts are copied to `build/native-dist/`. The diagnostic core remains at
`build/xemu_libretro.so`; install the native artifact when testing emulation.

## Build for Windows x64

From PowerShell in the project folder:

```powershell
.\scripts\build_windows.ps1 -Test -Synthetic
```

This requires Windows x64 Python, Ubuntu WSL, and Podman inside Ubuntu
(`sudo apt-get install podman`). The script cross-compiles using xemu's own
Windows GCC/MXE container toolchain, pinned by digest in
`scripts/windows.Containerfile`. It adds the curl package required by xemu's
dependency fetcher. The first build downloads the toolchain and dependencies;
later builds reuse them. The output is native Windows code and does not require
WSL or Podman to run.

The DLL and core information file are written to
`build/native-dist/windows-x64/`. Copy `xemu_libretro.dll` into **Windows x64**
RetroArch's cores directory, and `xemu_libretro.info` into its information
directory. Use the firmware/save layout below. The core needs an OpenGL 4.0
driver even when RetroArch uses a different video driver for presentation.

`-Distribution` chooses a WSL distribution; `-Jobs` limits build concurrency;
`-Reconfigure` reruns xemu's configuration. From Linux/WSL directly, run
`python3 scripts/build_windows.py`; it accepts `--build-dir` for a build folder
inside the Linux filesystem. The complete DLL with debugging data stays in
that build folder; the packaged DLL has debugging data stripped.

The Windows backend pins its module with `GetModuleHandleEx` during DLL loading,
including metadata-only loads, because QEMU creates a worker in a constructor.
This matches the Linux build's `NODELETE` lifetime. It wraps both direct
`exit` calls and MinGW's imported `exit` pointer. SDL3 remains private, and
xemu's standalone DXGI presentation and NVIDIA profile setup are bypassed.

## Required files

For the complete menu-by-menu setup and folder example, follow the
[README installation guide](../README.md#installation). Its
[troubleshooting section](../README.md#troubleshooting) covers missing-file
errors, save sorting, and selecting the game ISO.

Set RetroArch's System/BIOS and Save Files directories, then provide:

| Location | File | Purpose |
| --- | --- | --- |
| `<system>/xemu/` | `mcpx_1.0.bin` | User-supplied 512-byte MCPX ROM |
| `<system>/xemu/` | `bios.bin` | User-supplied Xbox flash BIOS |
| `<save>/xemu/` | `eeprom.bin` | Writable 256-byte EEPROM; xemu generates one if absent |
| `<save>/xemu/` | `xbox_hdd.qcow2` | Writable copy of a working xemu HDD image |

Use copies of your HDD and EEPROM for this prototype; guest writes go to those
files. Do not point them at your standalone xemu files via symlinks. The core
does not bundle assets, search your standalone configuration, or copy disks
automatically. It loads default settings in memory and does not save an xemu
configuration file.

Copy `build/native-dist/xemu_libretro.so` to Linux RetroArch's cores directory
and its accompanying `.info` to RetroArch's core information directory. Load an
Xbox-compatible disc image using the core, or select Start Core without content
to boot the BIOS/dashboard. Only the boot/menu path of Fuzion Frenzy has been
tested so far; full gameplay and other titles remain unverified.

For the simple directory layout above, disable RetroArch's save-file sorting by
core/content and the options to use the content directory for saves/system
files. Select the parent directories in Settings > Directory, not their `xemu`
subfolders: the core appends `xemu`. Otherwise `<save>` means the effective
directory returned by RetroArch, which the core names in its missing-file error.
Loading a core does not configure these paths.

## Implemented integration

- The shared library includes the real xemu device model and CPU emulator.
- A presentation worker owns private, hidden SDL3/OpenGL contexts. Finished
  GPU textures or the VGA fallback are read back as XRGB8888 frames. RetroArch
  receives software frames and can apply its normal presentation/shader path.
- Four RetroPads feed xemu's existing `ControllerState` and USB controller
  implementation. Face buttons follow physical positions, L/R map to
  White/Black, and triggers use analog pressure with a digital fallback. Stick
  Y axes follow xemu's conversion. Rumble is delivered on the frontend thread.
- The APU's 48 kHz signed 16-bit stereo output enters a bounded audio queue.
  Audio callbacks run on the frontend thread and retain unconsumed samples.
  Delivery is capped at 800 frames per `retro_run()` for the declared 60 Hz.
  APU throttling uses this queue's occupancy and remains interruptible by VM
  pause/shutdown. The queue itself drops overflow rather than blocking a writer.
- The guest runs continuously across normal `retro_run()` calls. A monotonic
  60 Hz deadline includes capture and frontend overhead, avoiding an extra
  full-frame delay on every call. If the frontend stops requesting frames for
  100 ms, the worker pauses the guest until the next request. Pause timing is
  approximate; this is not deterministic, frame-exact stepping. Fast-forward
  beyond the internal 60 Hz limit is not implemented.
- QEMU's generic audio backend is set to `none`; the Xbox APU monitor feeds
  libretro audio callbacks, and RetroArch owns the output device.
- Missing assets fail before machine creation. Direct QEMU `exit()` calls in
  the linked image are intercepted so they do not intentionally exit RetroArch.

## Current limits

Only **one machine lifetime per RetroArch process** is supported. After closing
content or a failure during machine initialization, restart RetroArch before
loading again. Missing-file preflight failures are retryable. The library is
marked `NODELETE` on Linux or pinned on Windows because QEMU owns global threads/state that are not yet fully
destroyed; closing a core does not reclaim all its resources. This is a concrete
embedding limitation, not a claim that QEMU is safely reloadable.

The exit interceptor does not catch assertions, crashes, or exits from external
libraries. A failed initialization retires the instance rather than attempting
to reuse partially initialized global state. Worker waits have timeouts.

Presentation is fixed at 60 Hz / 4:3, supports up to 1920x1080 output, and uses
GPU readback. PAL timing, widescreen negotiation, GPU-native frontend rendering,
performance tuning, and accurate guest-frame synchronization remain work.
Controllers remain physically attached as four virtual controllers; disabling
a frontend port currently neutralizes its input. Save states, rewind, runahead,
netplay, cheats, and exported RAM are unsupported.

## Tests

`--test` runs controller/audio unit tests and a subprocess test of the compiled
core's metadata and retryable missing-asset handling. To also test the machine:

```sh
SDL_VIDEO_DRIVER=x11 python3 scripts/build_native.py \
  --build-dir "$HOME/xemu-libretro-build" --test --synthetic
```

The synthetic test creates temporary, original halt-only ROM bytes, a dummy
EEPROM, and a sparse raw test disk. It checks native machine construction,
video callbacks, frontend callback thread ownership, controller polling, reset,
shutdown, and rejection of unsafe machine reinitialization. It does not contain
Microsoft firmware and does not test dashboard boot or game compatibility.
It requires a working OpenGL-capable display. WSLg's X11 display worked in the
development environment; its Xvfb display failed SDL's GLX visual selection.

Additional regression checks used in development:

```sh
SDL_VIDEO_DRIVER=x11 python3 tests/native_smoke.py \
  "$HOME/xemu-libretro-build/xemu_libretro.so" --synthetic --with-sdl2
SDL_VIDEO_DRIVER=unavailable_test_driver python3 tests/native_smoke.py \
  "$HOME/xemu-libretro-build/xemu_libretro.so" --synthetic --expect-init-failure
```

These check that a host's globally loaded SDL2 does not interfere with the
private SDL3, that its video subsystem survives core shutdown, and that a
deliberate SDL initialization failure does not terminate the host process.

With user-provided MCPX, Complex 4627 v1.03 BIOS, a copied HDD, and Fuzion Frenzy
(USA), `scripts/probe_native.py` reached player selection through scripted
Start-button input. A 3,600-frame run delivered 2,850,048 stereo audio frames
with nonzero samples and shut down cleanly. This verifies the callback path;
audio quality, physical controllers, rumble, and minigame gameplay still need
manual validation. The environment was Linux x86-64 in Ubuntu WSL, using WSLg
and Mesa llvmpipe OpenGL 4.5; it is not a hardware-GPU performance benchmark.

RetroArch 1.22.2 also loaded the native core and Fuzion Frenzy for 2,200 frames,
captured the game's animated intro, and unloaded with exit status 0. That test
used the SDL2 input driver and null frontend video/audio drivers; it validates
actual host integration and screenshot delivery, not audible playback or an
interactive display. Local evidence is in `build/retroarch-native.log` and
`build/retroarch-fuzion.png` (ignored development artifacts).

Windows x64 validation used the native DLL, Windows Python, an RTX 4090, and
RetroArch 1.22.2. Controller/audio helper tests, missing-file retries, synthetic
boot, idle/resume, reset, shutdown, and DLL release/reload protection passed.
An intentional SDL startup failure also preserved the host process. The DLL
imports Windows system libraries; SDL3 and compiler runtimes are linked into
the core.

The initial Windows scheduler rendered about 48 frames/second, and audible
stuttering was reported. After replacing per-frame pause/sleep with continuous
emulation and cumulative deadlines, a Fuzion Frenzy probe delivered 2,400
frames in 40.032 seconds (59.95 FPS), 1,869,824 stereo audio frames, and nonzero
audio samples. It reached player selection through libretro Start input and
exited cleanly. This measures host callback pacing, not guest-frame accuracy
or subjective audio quality.

A Windows RetroArch run with null video and WASAPI audio also completed 2,400
frames and exited cleanly. Interactive testing uses OpenGL video, WASAPI audio,
XInput, video/audio synchronization, and pause on loss of focus. The local
`build/Play-Fuzion-Frenzy.cmd` launcher uses the prepared asset copies and the
separate portable RetroArch under `build/tools/`; it contains this machine's
game path and is not a portable distribution script.

The user confirmed that the visible Windows game window displayed correctly
and the audio played smoothly after the timing change. RetroArch detected and
configured their Xbox One controller. Full minigame compatibility and physical
controller/rumble coverage remain unverified.

For actual hardware/game validation, compare a controller and audio homebrew
test disc with standalone xemu and, where available, a real Xbox. Verify every
button, analog trigger/stick range, rumble motor, stereo channel, and pause/reset.

## Source and licensing

Edit files under `native/ui/` for the overlay implementation. Changes to existing
xemu files live in `patches/xemu-libretro.patch`; `upstream/xemu` is an ignored
working checkout, not the only copy of the integration. Preserve the native
sources and patch together when sharing the project.

The native core incorporates xemu/QEMU and is subject to their applicable GPL
and other component licenses. The GPL text is in `LICENSE`; `LICENSES/MIT.txt` preserves the license of the
separately written diagnostic foundation and marked helpers. See `NOTICE.md`
for component scope and attribution. Upstream license notices remain in the
source checkout. No firmware or game is included.
