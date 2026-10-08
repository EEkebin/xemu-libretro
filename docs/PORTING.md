# Native xemu integration plan

This document records the initial architecture review. An experimental desktop
implementation now lives in `native/ui/` and `patches/xemu-libretro.patch`.
See [current native build and validation details](NATIVE.md) for implemented
behavior and remaining limits; the original milestones below are not a current
feature checklist.

## Scope and evidence

Target: an in-process libretro library that runs xemu's Xbox emulation and sends
video/audio to RetroArch while accepting its controller input. Initial target:
x86-64 desktop, with Linux as the first integration platform and Windows next.
This is a proposed development sequence, not a completed or tested emulator port.

Source review baseline:
[`478b4f496102379c7eaa7f3ec10e714a703c4300`](https://github.com/xemu-project/xemu/tree/478b4f496102379c7eaa7f3ec10e714a703c4300).
Recheck upstream changes before implementing patches. Source review found:

| Area | Upstream source | Integration work |
| --- | --- | --- |
| Startup and display loop | [`ui/xemu.c`](https://github.com/xemu-project/xemu/blob/478b4f496102379c7eaa7f3ec10e714a703c4300/ui/xemu.c) | This contains the Xbox `main()`, SDL window/context ownership, a QEMU worker, and display shutdown synchronization. Extract an embeddable lifecycle. |
| Shared library build | [`meson.build`](https://github.com/xemu-project/xemu/blob/478b4f496102379c7eaa7f3ec10e714a703c4300/meson.build) | Add a libretro target using the complete configured emulator dependency graph and generated sources. Audit PIC and exported symbols. |
| GPU presentation | [`ui/xemu.c`](https://github.com/xemu-project/xemu/blob/478b4f496102379c7eaa7f3ec10e714a703c4300/ui/xemu.c), [`hw/xbox/nv2a/pgraph/gl/display.c`](https://github.com/xemu-project/xemu/blob/478b4f496102379c7eaa7f3ec10e714a703c4300/hw/xbox/nv2a/pgraph/gl/display.c) | The display path reads an NV2A framebuffer surface. Integrate frontend hardware contexts, texture ownership, synchronization, and presentation. |
| Audio output | [`hw/xbox/mcpx/apu/monitor.c`](https://github.com/xemu-project/xemu/blob/478b4f496102379c7eaa7f3ec10e714a703c4300/hw/xbox/mcpx/apu/monitor.c) | This path opens an SDL audio stream and pushes the monitor frame buffer into it. Introduce a PCM sink for libretro. |
| Audio pacing | [`hw/xbox/mcpx/apu/apu.c`](https://github.com/xemu-project/xemu/blob/478b4f496102379c7eaa7f3ec10e714a703c4300/hw/xbox/mcpx/apu/apu.c) | Queue occupancy participates in throttling. Replacing the output sink also requires replacing its pacing feedback. |
| Controllers | [`ui/xemu-input.h`](https://github.com/xemu-project/xemu/blob/478b4f496102379c7eaa7f3ec10e714a703c4300/ui/xemu-input.h) | Supply controller state through a frontend-independent provider; support four ports and rumble. |

The generic `system/main.c` is guarded out for Xbox builds; wrapping that entry
point would miss the actual xemu startup path. Replacing only QEMU's generic
SDL audio driver would likewise miss the Xbox APU monitor path reviewed above.

An existing [experimental xemu-libretro repository](https://github.com/paulo101977/xemu-libretro)
is worth monitoring. At review, its `XemuLibretro/main.c` had an empty
`retro_run()`, incomplete callback registration, and empty AV metadata. Its
README describes a Python module build. No working RetroArch core was verified
from it, and none of its code was copied here. The upstream open-PR search for
`libretro` returned zero results at review; this is not an exhaustive claim that
no other port exists.

## Milestones and acceptance gates

1. **Libretro foundation — implemented here.** Compile a shared library and
   exercise callbacks using a mock frontend. A real RetroArch launch remains a
   manual validation step.
2. **Embeddable xemu — next.** Check out the pinned source, retain its Meson
   dependency graph, and introduce explicit start/stop/error handling. Eliminate
   host-process exits from reachable error paths. Audit process globals, signal
   handlers, `atexit` registrations, timers, worker threads, and configuration
   writes. Passing gate: initialize and shut down without terminating or hanging
   the host, including startup failures, and prove what reload behavior is safe.
3. **First boot/frame.** Supply a user's MCPX ROM, BIOS, HDD, and EEPROM through
   explicit paths; initialize the machine and deliver actual framebuffer output
   inside RetroArch. Begin with OpenGL if its context model proves workable.
   Hardware API/version negotiation must follow xemu's actual requirements.
   Handle context reset/destruction. A diagnostic frame is not a boot test.
4. **Playable loop.** Connect controllers and APU audio. Run one known working
   test title, compare it with standalone xemu, measure queue occupancy, and
   validate pause/resume/reset/quit. Use a user-supplied Xbox-compatible disc
   image; the diagnostic core's `iso` extension is only a future association.
5. **Distribution.** Validate Windows builds and dependencies; verify clean
   profile behavior, missing assets, GPU failure, repeated loads, and graceful
   errors. Add CI and a supported-platform matrix before claiming a usable port.

## Proposed runtime contract

Keep libretro callbacks and the frontend's active graphics context on the
thread calling `retro_run()`. QEMU workers must communicate through bounded
queues and explicit synchronization; do not call frontend callbacks arbitrarily
from those threads. Scheduling must account for guest vblank, QEMU timers, audio
pacing, and locks. Calling `qemu_main_loop()` directly from `retro_run()` would
block the frontend rather than produce a frame.

The initial video implementation needs to establish whether the NV2A renderer
can use an appropriate shared graphics context or requires further separation.
A texture from an unrelated SDL context cannot simply be handed to RetroArch.
Libretro hardware rendering uses its supplied framebuffer and the hardware-frame
sentinel, with correct orientation, dimensions, and context lifetime handling.
Do not assume context sharing or assume framebuffer zero is the output target.

Use a bounded audio queue. Convert to interleaved signed 16-bit stereo at the
negotiated rate if needed. Preserve unconsumed samples when the batch callback
accepts fewer frames; define underflow/overflow behavior and avoid deadlock when
RetroArch pauses. The diagnostic's fixed 800 silent frames per run does not
implement this queue or emulate the APU.

Proposed controller mapping follows physical face-button positions: RetroPad B
to Xbox A, A to B, Y to X, X to Y; L/R to White/Black; L2/R2 to triggers;
Select to Back; Start and stick clicks directly. Validate analog ranges and Y
axis direction against the existing xemu controller conversion. Support analog
trigger values with a digital fallback. These mappings are not implemented by
the diagnostic's raw input display.

Keep firmware in a frontend system subdirectory and writable HDD/EEPROM state
under an explicit save directory. Avoid silently reusing or modifying a user's
standalone xemu disks and settings. Prefer a per-core writable HDD overlay where
the backend supports it. Do not package firmware or games.

Save states, rewind, runahead, and netplay need separate investigations. QEMU
snapshots do not automatically satisfy libretro serialization semantics,
especially when block-device state is involved. Keep these unsupported until
correctness and lifetime tests exist.

## Building upstream and contributing

Follow [xemu's build instructions](https://xemu.app/docs/dev/building-from-source/)
for the full emulator. The small foundation's CMake file cannot compile xemu;
do not add a handful of Xbox source files to it and expect a complete emulator.
The documented upstream Windows route uses cross-compilation from Linux.

Before working in an upstream checkout, read its `AGENTS.md` and
`CONTRIBUTING.md`, check related PRs again, and preserve all license notices.
Upstream asks contributors to discuss major changes with maintainers before
submission. No messages or pull requests have been sent as part of this setup.

Libretro references: [core development overview](https://docs.libretro.com/development/cores/developing-cores/)
and the [pinned canonical header](https://github.com/libretro/libretro-common/blob/2b96a82bd8479bb3547d271e1eefadc82dd2161e/include/libretro.h).
