# Diagnostic core (developer tool)

This is the original callback test. It does not emulate an Xbox. For the real
emulator core, follow [the native build guide](NATIVE.md).

## Build and test the diagnostic target

The dependency-free build script requires Python 3 and GCC or Clang:

```sh
python3 scripts/build.py --test
```

This produces `build/xemu_libretro.so` for **Linux RetroArch**. A WSL Linux
library cannot be loaded by Windows RetroArch.

For native Windows, install a C compiler and CMake, then use, for example,
the Visual Studio developer terminal:

```powershell
cmake -S . -B build/windows -A x64
cmake --build build/windows --config Release
ctest --test-dir build/windows -C Release --output-on-failure
```

The expected Windows artifact is `build/windows/Release/xemu_libretro.dll`.
The Windows/CMake route is provided but has not been validated in this workspace.
The equivalent CMake build on Linux/macOS is:

```sh
cmake -S . -B build/cmake
cmake --build build/cmake
ctest --test-dir build/cmake --output-on-failure
```

## Try the diagnostic core

Copy the library into the matching platform's RetroArch cores directory and
`xemu_libretro.info` into its core information directory. Load the core and
choose **Start Core**, without selecting a game. Alternatively:

```sh
retroarch -L build/xemu_libretro.so
```

The display contains a moving green bar and four controller rows. Each row
shows 16 digital buttons in libretro ID order and two stick indicators.
Pressed buttons turn green. Audio is intentionally silent. No firmware or
game files are needed for diagnostics.

## Validation

`tests/smoke.py` loads the actual compiled library using Python ctypes and checks
all API exports, metadata, rejected content, rejected pixel formats, advancing
frames, visible input responses, analog extremes, controller disconnect,
batch/sample audio callbacks, reset, unload/reload, and reinitialization.

Diagnostic checks passed with GCC 15.2 on x86-64 Ubuntu under WSL, with warnings
treated as errors. These checks do not exercise xemu; see the native guide for
the separate emulator validation and limits.
