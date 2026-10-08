"""Exercise the compiled shared library through the actual libretro C ABI."""
import ctypes as C
from pathlib import Path
import sys


class SystemInfo(C.Structure):
    _fields_ = [("name", C.c_char_p), ("version", C.c_char_p),
                ("extensions", C.c_char_p), ("fullpath", C.c_bool),
                ("block_extract", C.c_bool)]


class Geometry(C.Structure):
    _fields_ = [("width", C.c_uint), ("height", C.c_uint),
                ("max_width", C.c_uint), ("max_height", C.c_uint),
                ("aspect", C.c_float)]


class Timing(C.Structure):
    _fields_ = [("fps", C.c_double), ("sample_rate", C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p),
                ("size", C.c_size_t), ("meta", C.c_char_p)]


class Message(C.Structure):
    _fields_ = [("text", C.c_char_p), ("frames", C.c_uint)]


Environment = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
Video = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AudioBatch = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
AudioSample = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
Poll = C.CFUNCTYPE(None)
Input = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    core = C.CDLL(str(Path(sys.argv[1]).resolve()))
    signatures = {
        "api_version": (C.c_uint, []),
        "init": (None, []), "deinit": (None, []),
        "get_system_info": (None, [C.POINTER(SystemInfo)]),
        "get_system_av_info": (None, [C.POINTER(AVInfo)]),
        "set_environment": (None, [Environment]),
        "set_video_refresh": (None, [Video]),
        "set_audio_sample": (None, [AudioSample]),
        "set_audio_sample_batch": (None, [AudioBatch]),
        "set_input_poll": (None, [Poll]),
        "set_input_state": (None, [Input]),
        "set_controller_port_device": (None, [C.c_uint, C.c_uint]),
        "load_game": (C.c_bool, [C.POINTER(GameInfo)]),
        "load_game_special": (C.c_bool, [C.c_uint, C.POINTER(GameInfo), C.c_size_t]),
        "unload_game": (None, []), "run": (None, []), "reset": (None, []),
        "serialize_size": (C.c_size_t, []),
        "serialize": (C.c_bool, [C.c_void_p, C.c_size_t]),
        "unserialize": (C.c_bool, [C.c_void_p, C.c_size_t]),
        "get_region": (C.c_uint, []), "cheat_reset": (None, []),
        "cheat_set": (None, [C.c_uint, C.c_bool, C.c_char_p]),
        "get_memory_data": (C.c_void_p, [C.c_uint]),
        "get_memory_size": (C.c_size_t, [C.c_uint]),
    }
    for name, (result, args) in signatures.items():
        function = getattr(core, "retro_" + name)
        function.restype, function.argtypes = result, args

    state = {"accept_pixel_format": True, "no_game": False,
             "polls": 0, "audio_frames": 0, "samples": 0}
    messages, frames, errors, input_ports = [], [], [], set()

    @Environment
    def environment(command, data):
        if command == 18:  # SET_SUPPORT_NO_GAME
            state["no_game"] = C.cast(data, C.POINTER(C.c_bool))[0]
            return True
        if command == 10:  # SET_PIXEL_FORMAT
            if C.cast(data, C.POINTER(C.c_int))[0] != 1:
                errors.append("Expected XRGB8888")
            return state["accept_pixel_format"]
        if command == 6:  # SET_MESSAGE
            messages.append(C.cast(data, C.POINTER(Message)).contents.text.decode())
            return True
        return False

    @Video
    def video(data, width, height, pitch):
        if not data or (width, height, pitch) != (640, 480, 2560):
            errors.append("Bad video buffer geometry")
            return
        frames.append(C.string_at(data, pitch * height))

    @AudioBatch
    def audio(data, count):
        if count != 800 or any(data[i] for i in range(count * 2)):
            errors.append("Bad diagnostic audio")
        state["audio_frames"] += count
        return count

    @AudioSample
    def sample(left, right):
        if left or right:
            errors.append("Non-silent sample")
        state["samples"] += 1

    @Poll
    def poll():
        state["polls"] += 1

    @Input
    def input_state(port, device, index, button):
        input_ports.add(port)
        if device == 1:
            return int(port == 0 and button == 0)
        # Exercise both signed extremes of the analog range.
        return -32768 if button == 0 else 32767

    core.retro_set_environment(environment)
    core.retro_set_video_refresh(video)
    core.retro_set_audio_sample(sample)
    core.retro_set_audio_sample_batch(audio)
    core.retro_set_input_poll(poll)
    core.retro_set_input_state(input_state)
    core.retro_init()
    check(core.retro_api_version() == 1, "API version")
    check(state["no_game"], "No-content support was not advertised")
    info, av = SystemInfo(), AVInfo()
    core.retro_get_system_info(C.byref(info))
    expected_version = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip().encode()
    check(info.version == expected_version, "Core version differs from VERSION")
    core.retro_get_system_av_info(C.byref(av))
    check(b"no emulation" in info.name and info.fullpath, "Honest metadata")
    check((av.geometry.width, av.geometry.height) == (640, 480), "AV geometry")
    check((av.timing.fps, av.timing.sample_rate) == (60, 48000), "AV timing")
    core.retro_run()
    check(not frames, "Unloaded core emitted a frame")

    game = GameInfo(b"example.iso", None, 0, None)
    check(not core.retro_load_game(C.byref(game)), "Unimplemented emulation accepted content")
    check("not integrated" in messages[-1], "Missing content error")
    state["accept_pixel_format"] = False
    check(not core.retro_load_game(None), "Unsupported pixel format accepted")
    state["accept_pixel_format"] = True
    check(core.retro_load_game(None), "No-content load failed")
    for _ in range(3):
        core.retro_run()
    check(state["polls"] == 3 and state["audio_frames"] == 2400, "Callback counts")
    check(state["samples"] == 0, "Both audio interfaces were used")
    check(input_ports == {0, 1, 2, 3}, "Four-port polling")
    check(len(frames) == 3 and frames[0] != frames[1], "Frames did not advance")
    first = (C.c_uint32 * (640 * 480)).from_buffer_copy(frames[0])
    check(first[60 * 640 + 40] == 0x98dc45, "Pressed button not drawn")
    check(first[60 * 640 + 76] == 0x374656, "Released button not drawn")
    core.retro_reset()
    core.retro_run()
    check(frames[-1] == frames[0], "Reset did not restore the first frame")
    core.retro_set_controller_port_device(0, 0)
    input_ports.clear()
    core.retro_run()
    check(input_ports == {1, 2, 3}, "Disabled controller still polled")
    core.retro_set_audio_sample_batch(AudioBatch())
    core.retro_run()
    check(state["samples"] == 800, "Sample audio fallback")

    check(core.retro_serialize_size() == 0, "Unexpected save-state support")
    check(not core.retro_serialize(None, 0), "Serialize falsely succeeded")
    check(not core.retro_unserialize(None, 0), "Unserialize falsely succeeded")
    check(not core.retro_load_game_special(0, None, 0), "Special load falsely succeeded")
    check(not core.retro_get_memory_data(0) and core.retro_get_memory_size(0) == 0,
          "Unexpected memory exposure")
    core.retro_unload_game()
    count = len(frames)
    core.retro_run()
    check(len(frames) == count, "Unloaded core is still running")
    for _ in range(3):
        check(core.retro_load_game(None), "Reload failed")
        core.retro_run()
        core.retro_unload_game()
    core.retro_deinit()
    core.retro_init()
    check(core.retro_load_game(None), "Reinitialization failed")
    core.retro_run()
    core.retro_deinit()
    check(not errors, "; ".join(errors))
    print(f"PASS: {len(signatures)} ABI exports; metadata; load failures; video; audio; "
          "four controllers; reset; unload/reload; reinitialization; unsupported features")


if __name__ == "__main__":
    main()
