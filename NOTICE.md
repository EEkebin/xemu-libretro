# Component licenses and attribution

This repository contains a libretro integration for xemu, not a replacement
license for xemu or its dependencies.

- `native/ui/xemu-libretro.inc.c` and `native/ui/xemu-libretro.h` are marked
  GPL-2.0-or-later. `LICENSE` contains the GNU GPL version 2 text.
- `patches/xemu-libretro.patch` modifies xemu/QEMU files; the respective upstream
  file licenses and copyright notices continue to apply.
- `src/core.c`, `native/ui/xemu-retro-io.c`, `native/ui/xemu-retro-io.h`, and
  `tests/native_io.c` retain their SPDX MIT markings and the notice preserved
  in `LICENSES/MIT.txt`.
- The separately written build scripts, tests, diagnostic build configuration,
  and documentation retain the original foundation's MIT terms, unless marked
  otherwise.
- `third_party/libretro/libretro.h` retains its own MIT notice and attribution.
  Its source revision and checksum are in `third_party/libretro/README.md`.

The built native core incorporates xemu/QEMU and its dependencies under their
applicable licenses. The foundation's MIT license does not relicense those
components. Preserve their notices and provide corresponding source as required
when distributing binaries; the source pins, patch, and overlay in this
repository document this integration but do not replace dependency source and
license obligations.

The initial integration and build tooling were developed with assistance from
OpenAI Codex (GPT-6). Validation and known limitations are recorded in
`docs/NATIVE.md`. This is an independent project, not an official xemu or
libretro release. No Xbox firmware, games, or writable disk images are included.
