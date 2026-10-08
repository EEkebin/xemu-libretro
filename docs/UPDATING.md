# Updating the xemu version

The native build uses the exact xemu commit in `upstream.json`. A new xemu
release does not silently change an existing build, and updating standalone
xemu does not update this RetroArch core. The Windows compiler container and
vendored libretro header are pinned separately. Linux cross builds also pin
their container base and DSP source. Keep the DSP version in `upstream.json`
aligned with the dependency required by the selected xemu revision.

## Maintainer workflow

Use calendar versioning (CalVer): `YYYY.MM.DD`, with zero-padded month and day.
The first release on a date has no suffix; further releases use `.1`, `.2`, etc.
For example, `2026.10.08` is tagged `v2026.10.08`. This is a date scheme, not
SemVer's major/minor/patch compatibility promise. Set `VERSION` before building
a release, and keep the tag identical except for its `v` prefix. Build scripts
generate the version header from this file; native packages include `VERSION`.

1. Create a working branch and a separate checkout of the proposed xemu commit.
   Keep the current working emulator checkout and tested core available.
2. Review upstream changes, especially startup/shutdown, SDL and graphics,
   the Xbox APU, controller state, threading, and the build system.
3. Apply `patches/xemu-libretro.patch` to the new baseline and copy the overlay
   files from `native/ui/` plus `third_party/libretro/libretro.h` into its `ui/`
   directory. Resolve conflicts deliberately; a successful patch application
   does not establish runtime compatibility.
4. Update `upstream.json` and regenerate the patch against that new baseline.
   Preserve changes to overlay files in `native/ui/`, not only in the ignored
   `upstream/xemu` checkout. Keep the patch and overlay synchronized.
5. Use a fresh build directory for each platform. Verify the source preparation
   script works against a clean checkout of the new pin.
6. Run input/audio tests, native metadata and missing-file checks, synthetic
   boot/reset/idle-resume/shutdown checks, and failure handling. On Windows,
   verify the DLL remains safe through frontend release/reload attempts. On
   Linux, check coexistence with a host that loads SDL2 globally.
   For ARM64/RISC-V64, run the cross checks in [CROSS-BUILDING.md](CROSS-BUILDING.md)
   and record emulated results separately from native hardware testing.
7. Test actual games in Windows and Linux RetroArch with separately supplied
   assets. Compare with standalone xemu from the same revision. Check graphics,
   audio pacing, controller input, idle/resume, and clean shutdown; a synthetic
   halt-only ROM cannot verify these.
8. Record the upstream revision, toolchain, test environment, results, and known
   regressions. Publish a tagged core update only after those checks succeed.
   Package the applicable notices and corresponding source with binary releases.

The preparation script intentionally refuses to replace an edited checkout
at a different revision. Use a separate checkout for upgrade work instead of
forcing it over local changes. `scripts/build_native.py --source-dir ...`
supports an alternate source directory; the standard Windows wrapper uses
`upstream/xemu`, so preserve the existing checkout when preparing a new one there.

Users then install the new core file for their platform. Keep BIOS files and
game images separate, back up writable HDD/EEPROM data before testing an upgrade,
and fully exit RetroArch before replacing a loaded core.
