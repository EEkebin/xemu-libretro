"""Test the real xemu DSO in a subprocess; synthetic firmware only checks plumbing."""
import argparse
import ctypes as C
import ctypes.util
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from smoke import (SystemInfo, AVInfo, GameInfo, Message, Environment, Video,
                   AudioBatch, AudioSample, Poll, Input, check)


def run_child(library, synthetic, with_sdl2, expect_init_failure):
    sdl2 = None
    if with_sdl2:
        name = ctypes.util.find_library("SDL2-2.0")
        check(name is not None, "SDL2 is required for the host-interposition test")
        sdl2 = C.CDLL(name, mode=C.RTLD_GLOBAL)
        sdl2.SDL_Init.argtypes = [C.c_uint]
        sdl2.SDL_WasInit.argtypes = [C.c_uint]
        sdl2.SDL_WasInit.restype = C.c_uint
        check(sdl2.SDL_Init(0x20) == 0, "Host SDL2 video initialization failed")
    core = C.CDLL(str(Path(library).resolve()))
    for name, callback in [("environment", Environment), ("video_refresh", Video),
                           ("audio_sample_batch", AudioBatch), ("audio_sample", AudioSample),
                           ("input_poll", Poll), ("input_state", Input)]:
        getattr(core, "retro_set_" + name).argtypes = [callback]
    core.retro_load_game.argtypes = [C.POINTER(GameInfo)]
    core.retro_load_game.restype = C.c_bool
    core.retro_get_system_info.argtypes = [C.POINTER(SystemInfo)]
    core.retro_get_system_av_info.argtypes = [C.POINTER(AVInfo)]
    errors, messages, frames, ports = [], [], [], set()
    owner = threading.get_ident()
    count = {"audio": 0, "poll": 0}

    with tempfile.TemporaryDirectory(prefix="xemu-retro-test-") as temp:
        base = Path(temp)
        system, save = base / "system", base / "save"
        (system / "xemu").mkdir(parents=True)
        (save / "xemu").mkdir(parents=True)
        system_bytes, save_bytes = str(system).encode(), str(save).encode()

        def check_thread():
            if threading.get_ident() != owner:
                errors.append("Frontend callback called from emulator worker")

        @Environment
        def environment(cmd, data):
            check_thread()
            if cmd in (9, 31):
                C.cast(data, C.POINTER(C.c_char_p))[0] = system_bytes if cmd == 9 else save_bytes
                return True
            if cmd in (10, 18):
                return True
            if cmd == 6:
                messages.append(C.cast(data, C.POINTER(Message)).contents.text.decode())
                print("CORE:", messages[-1], flush=True)
                return True
            return False

        @Video
        def video(data, width, height, pitch):
            check_thread()
            if not data or not (0 < width <= 1920 and 0 < height <= 1080) or pitch != width * 4:
                errors.append(f"Invalid framebuffer {width}x{height}, pitch={pitch}")
            else:
                frames.append(C.string_at(data, pitch * height))

        @AudioBatch
        def batch(data, frames):
            check_thread()
            count["audio"] += frames
            return frames

        @Poll
        def poll():
            check_thread()
            count["poll"] += 1

        @Input
        def input_state(port, device, index, button):
            check_thread()
            ports.add(port)
            return 0

        core.retro_set_environment(environment)
        core.retro_set_video_refresh(video)
        core.retro_set_audio_sample_batch(batch)
        core.retro_set_audio_sample(AudioSample())
        core.retro_set_input_poll(poll)
        core.retro_set_input_state(input_state)
        core.retro_init()
        info = SystemInfo()
        core.retro_get_system_info(C.byref(info))
        expected_version = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip().encode()
        check(info.version == expected_version, "Core version differs from VERSION")
        check(b"experimental native" in info.name, "Loaded the diagnostic library by mistake")
        check(not core.retro_load_game(None), "Missing firmware was accepted")
        check(any("mcpx_1.0.bin" in message for message in messages), "Missing asset was not identified")
        check(not core.retro_load_game(None), "Preflight retry unexpectedly succeeded")
        if synthetic:
            # Original test instructions, not an Xbox BIOS: CLI; HLT; JMP HLT.
            # This exercises machine construction and a CPU that immediately idles.
            for name, size in [("mcpx_1.0.bin", 512), ("bios.bin", 256 * 1024)]:
                firmware = bytearray(size)
                firmware[-16:-12] = bytes.fromhex("fa f4 eb fd")
                (system / "xemu" / name).write_bytes(firmware)
            (save / "xemu/eeprom.bin").write_bytes(bytes(256))
            with (save / "xemu/xbox_hdd.qcow2").open("wb") as disk:
                # QEMU autodetects this sparse raw disk; no guest writes occur.
                if sys.platform == "win32":
                    import msvcrt
                    ioctl = C.WinDLL("kernel32", use_last_error=True).DeviceIoControl
                    ioctl.argtypes = [C.c_void_p, C.c_ulong, C.c_void_p, C.c_ulong,
                                      C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.c_void_p]
                    returned = C.c_ulong()
                    check(ioctl(msvcrt.get_osfhandle(disk.fileno()), 0x900C4,
                                None, 0, None, 0, C.byref(returned), None),
                          "Could not mark the synthetic disk as sparse")
                disk.truncate(8 * 1024**3)
            initialized = core.retro_load_game(None)
            if expect_init_failure:
                check(not initialized, "Initialization unexpectedly succeeded")
                check(not core.retro_load_game(None), "Retired instance accepted a new machine")
                core.retro_deinit()
                print("NATIVE SMOKE PASS: failed initialization preserved the host", flush=True)
                return
            check(initialized, "Synthetic machine initialization failed")
            print("MACHINE READY", flush=True)
            for _ in range(3):
                core.retro_run()
            check(len(frames) == 3, "Expected three real machine framebuffer callbacks")
            check(ports == {0, 1, 2, 3}, "Missing controller ports")
            check(count["poll"] == 3, "Missing input polling")
            time.sleep(0.2)
            core.retro_run()
            check(len(frames) == 4, "Machine failed to resume after frontend idle")
            core.retro_reset()
            core.retro_run()
            core.retro_unload_game()
            check(not core.retro_load_game(None), "Unsafe machine reinitialization was accepted")
            print(f"SYNTHETIC MACHINE STOPPED: {len(frames)} frames; {count['audio']} audio frames", flush=True)
        core.retro_deinit()
        if sys.platform == "win32":
            # Exercise a real FreeLibrary/LoadLibrary cycle after machine shutdown.
            # Pinning must preserve the retired instance and its resident workers.
            import _ctypes
            _ctypes.FreeLibrary(core._handle)
            get_module = C.WinDLL("kernel32").GetModuleHandleW
            get_module.argtypes, get_module.restype = [C.c_wchar_p], C.c_void_p
            check(get_module(str(Path(library).resolve())), "QEMU worker DLL was not pinned")
            core = C.CDLL(str(Path(library).resolve()))
            core.retro_load_game.argtypes = [C.POINTER(GameInfo)]
            core.retro_load_game.restype = C.c_bool
            if synthetic:
                check(not core.retro_load_game(None), "DLL unload bypassed the one-machine limit")
        if sdl2:
            check(sdl2.SDL_WasInit(0x20) == 0x20, "Core disrupted the host's SDL2 video subsystem")
            sdl2.SDL_Quit()
        check(not errors, "; ".join(errors))
    print("NATIVE SMOKE PASS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--with-sdl2", action="store_true")
    parser.add_argument("--expect-init-failure", action="store_true")
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args()
    if args.child:
        run_child(args.library, args.synthetic, args.with_sdl2, args.expect_init_failure)
        return
    command = [sys.executable, __file__, args.library, "--child"]
    if args.synthetic:
        command.append("--synthetic")
    if args.with_sdl2:
        command.append("--with-sdl2")
    if args.expect_init_failure:
        command.append("--expect-init-failure")
    result = subprocess.run(command, timeout=100, capture_output=True, text=True)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    check(result.returncode == 0 and "NATIVE SMOKE PASS" in result.stdout,
          f"Native test process failed or exited prematurely: {result.returncode}")


if __name__ == "__main__":
    main()
