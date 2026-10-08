"""Run the native core with user-provided assets and capture diagnostic frames."""
import argparse
import ctypes as C
from pathlib import Path
import struct
import sys
import time
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from smoke import Environment, Video, AudioBatch, AudioSample, Poll, Input, GameInfo, Message


def save_png(path, data, width, height):
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = data[2::4], data[1::4], data[0::4]
    scanlines = b"".join(b"\0" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))

    def chunk(name, body):
        return struct.pack(">I", len(body)) + name + body + struct.pack(">I", zlib.crc32(name + body))

    path.write_bytes(b"\x89PNG\r\n\x1a\n" +
                     chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--save", type=Path, required=True)
    parser.add_argument("--game", type=Path)
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--capture-every", type=int, default=120)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--press-start-at", type=int, default=-1)
    parser.add_argument("--press-start-every", type=int, default=0)
    args = parser.parse_args()
    if args.frames < 1 or args.capture_every < 1:
        parser.error("Frame counts must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    core = C.CDLL(str(args.library.resolve()))
    system, save = str(args.system.resolve()).encode(), str(args.save.resolve()).encode()
    state = {"frame": 0, "video": 0, "audio": 0, "peak": 0, "shutdown": False}
    errors = []

    @Environment
    def environment(command, data):
        if command in (9, 31):
            C.cast(data, C.POINTER(C.c_char_p))[0] = system if command == 9 else save
            return True
        if command in (10, 18):
            return True
        if command == 6:
            print("CORE:", C.cast(data, C.POINTER(Message)).contents.text.decode(), flush=True)
            return True
        if command == 7:
            state["shutdown"] = True
            return True
        return False

    @Video
    def video(data, width, height, pitch):
        if not data or pitch != width * 4 or not 0 < width <= 1920 or not 0 < height <= 1080:
            errors.append("Invalid software framebuffer")
            return
        state["video"] += 1
        frame = state["frame"]
        if frame % args.capture_every == 0 or frame == args.frames - 1:
            try:
                save_png(args.output / f"frame-{frame:05d}.png", C.string_at(data, pitch * height), width, height)
            except Exception as error:
                errors.append(str(error))

    @AudioBatch
    def audio(data, frames):
        state["audio"] += frames
        if frames:
            state["peak"] = max(state["peak"], max(abs(value) for value in data[:frames * 2]))
        return frames

    @Poll
    def poll():
        pass

    @Input
    def input_state(port, device, index, button):
        offset = state["frame"] - args.press_start_at
        pressed = args.press_start_at >= 0 and offset >= 0
        pressed = pressed and (offset % args.press_start_every < 5 if args.press_start_every > 0 else offset < 5)
        return int(port == 0 and device == 1 and button == 3 and pressed)

    callbacks = {"environment": environment, "video_refresh": video,
                 "audio_sample_batch": audio, "audio_sample": AudioSample(),
                 "input_poll": poll, "input_state": input_state}
    for name, callback in callbacks.items():
        setter = getattr(core, "retro_set_" + name)
        setter.argtypes = [type(callback)]
        setter(callback)
    core.retro_load_game.argtypes = [C.POINTER(GameInfo)]
    core.retro_load_game.restype = C.c_bool
    core.retro_init()
    game = GameInfo(str(args.game.resolve()).encode(), None, 0, None) if args.game else None
    if not core.retro_load_game(C.byref(game) if game else None):
        raise RuntimeError("Native core could not load the machine")
    started = time.monotonic()
    try:
        for frame in range(args.frames):
            state["frame"] = frame
            core.retro_run()
            if state["shutdown"] or errors:
                raise RuntimeError(f"Native core stopped: {errors}")
            if frame % 60 == 0:
                print(f"frame={frame} video={state['video']} audio={state['audio']} "
                      f"peak={state['peak']} elapsed={time.monotonic()-started:.1f}s", flush=True)
    finally:
        core.retro_unload_game()
        core.retro_deinit()
    elapsed = time.monotonic() - started
    print("PROBE COMPLETE", state, f"elapsed={elapsed:.3f}s fps={state['video']/elapsed:.2f}", flush=True)


if __name__ == "__main__":
    main()
