# Experimental releases

## Download compatibility

Choose a core archive for the same OS and CPU as RetroArch. Windows x64 runs
the DLL directly; WSL and Podman are build tools and are not needed by users.

The first prerelease uses an Ubuntu 26.04 baseline for Linux x86-64 and Debian
13 for Linux ARM64/RISC-V64. These builds use system shared libraries. They are
not portable to every Linux distribution. The x86-64 core directly requires
symbols through `GLIBC_2.43`, `GLIBCXX_3.4.32`, and `CXXABI_1.3.15`; the ARM64
and RISC-V64 cores require `GLIBC_2.39`, `GLIBCXX_3.4.32`, and `CXXABI_1.3.15`.
Transitive dependencies can require newer symbols than the core itself.
Rebuilding against an older baseline is future portability work.

On the named Debian/Ubuntu baselines, install the main runtime packages:

```sh
sudo apt-get install libglib2.0-0t64 libepoxy0 libslirp0 zlib1g \
  libcurl4t64 libpcap0.8t64 libsamplerate0 libstdc++6 libgcc-s1 \
  libx11-6 libxext6 libxrandr2 libxcursor1 libxi6 libxss1 libxfixes3
```

All targets require desktop OpenGL 4.0. Linux needs a working graphics driver
and X11/XWayland display. See [cross-build details](CROSS-BUILDING.md) for the
experimental architectures. The [README status table](../README.md#platform-testing-status)
records game testing separately from emulated synthetic startup checks.

## Archive contents

Core archives contain the native core, its `.info` file, `VERSION`, setup
documentation, and component license notices. Copy the core and information
file to RetroArch's configured directories, then follow the README's Xbox
file setup. End users do not need the source archives or any launch scripts.

The companion `sources.tar.gz` archive contains this project's tracked source,
the prepared xemu source and fetched subprojects, DSP source, and vendored Rust
dependencies. The separate `windows-dependency-sources.tar.gz` contains the
MXE build recipes and downloaded dependency/compiler sources from the pinned
Windows toolchain. Both source assets belong with the binary distribution;
GitHub's automatically generated project source archive alone does not include
all dependencies. Upstream notices are preserved in these archives.

For source builds, follow [NATIVE.md](NATIVE.md) or
[CROSS-BUILDING.md](CROSS-BUILDING.md). The normal helpers fetch pinned upstream
sources and toolchains; the companion source trees also provide the files for
inspection and manual rebuilding. The source archive includes an offline Cargo
configuration for its vendored DSP dependencies. Build caches and user Xbox
assets are excluded.

## Maintainer checklist

1. Set the calendar version in `VERSION`. Preserve existing public tags; use a
   same-day suffix when needed. Rebuild all included cores with that version.
2. Run the native Windows/Linux checks and the ARM64/RISC-V64 cross checks.
   Record real-game testing and emulated synthetic checks separately.
3. Collect the pinned xemu/subproject sources, the DSP source with `cargo vendor
   --locked`, and the Windows toolchain's MXE recipes and source downloads.
4. Stage the intended repository changes, then run `scripts/package_release.py`
   under Linux/WSL with the source paths specified in its `--help`. It takes the
   project source from the Git index and creates core/source archives and hashes.
5. Verify archive members and test the extracted binaries. Keep the packaged
   tree identical to the commit: regenerate packages if staged files change.
6. Commit, push the source and annotated version tag, upload all listed assets,
   and publish an **experimental prerelease** with the platform testing table
   and known limitations. Verify uploaded asset sizes and checksums.
