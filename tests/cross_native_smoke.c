/* SPDX-License-Identifier: MIT */
#include "libretro.h"
#include <assert.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static char system_path[4096], save_path[4096];
static unsigned frames, polls, ports, missing_messages;

static bool environment(unsigned command, void *data)
{
    switch (command) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
        *(const char **)data = system_path;
        return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = save_path;
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        return *(enum retro_pixel_format *)data == RETRO_PIXEL_FORMAT_XRGB8888;
    case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
        return true;
    case RETRO_ENVIRONMENT_SET_MESSAGE: {
        const char *message = ((struct retro_message *)data)->msg;
        puts(message);
        if (strstr(message, "mcpx_1.0.bin")) {
            missing_messages++;
        }
        return true;
    }
    default:
        return false;
    }
}

static void video(const void *data, unsigned width, unsigned height,
                  size_t pitch)
{
    assert(data && width && height && width <= 1920 && height <= 1080);
    assert(pitch == width * 4);
    frames++;
}

static size_t audio(const int16_t *data, size_t count)
{
    assert(data && count <= 800);
    return count;
}

static void poll_input(void)
{
    polls++;
}

static int16_t input(unsigned port, unsigned device, unsigned index,
                     unsigned id)
{
    (void)device;
    (void)index;
    (void)id;
    assert(port < 4);
    ports |= 1u << port;
    return 0;
}

static void make_file(const char *root, const char *name, off_t size,
                      bool firmware)
{
    char path[8192];
    snprintf(path, sizeof(path), "%s/xemu/%s", root, name);
    int fd = open(path, O_CREAT | O_EXCL | O_RDWR, 0600);
    assert(fd >= 0);
    assert(ftruncate(fd, size) == 0);
    if (firmware) {
        /* Original synthetic reset-vector instructions: CLI; HLT; JMP HLT. */
        const uint8_t code[] = { 0xfa, 0xf4, 0xeb, 0xfd };
        assert(pwrite(fd, code, sizeof(code), size - 16) == sizeof(code));
    }
    assert(close(fd) == 0);
}

#define LOAD(name)                                                           \
    __typeof__(&name) core_##name = (__typeof__(&name))dlsym(handle, #name); \
    assert(core_##name)

int main(int argc, char **argv)
{
    assert(argc == 4 || argc == 5);
    setbuf(stdout, NULL);
    snprintf(system_path, sizeof(system_path), "%s/system", argv[2]);
    snprintf(save_path, sizeof(save_path), "%s/saves", argv[2]);
    assert(mkdir(system_path, 0700) == 0);
    assert(mkdir(save_path, 0700) == 0);
    char path[8192];
    snprintf(path, sizeof(path), "%s/xemu", system_path);
    assert(mkdir(path, 0700) == 0);
    snprintf(path, sizeof(path), "%s/xemu", save_path);
    assert(mkdir(path, 0700) == 0);
    void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        fprintf(stderr, "dlopen: %s\n", dlerror());
        return 1;
    }
    LOAD(retro_api_version);
    LOAD(retro_get_system_info);
    LOAD(retro_set_environment);
    LOAD(retro_set_video_refresh);
    LOAD(retro_set_audio_sample_batch);
    LOAD(retro_set_input_poll);
    LOAD(retro_set_input_state);
    LOAD(retro_init);
    LOAD(retro_deinit);
    LOAD(retro_load_game);
    LOAD(retro_unload_game);
    LOAD(retro_run);
    LOAD(retro_reset);
    assert(core_retro_api_version() == 1);
    struct retro_system_info info;
    core_retro_get_system_info(&info);
    assert(strstr(info.library_name, "experimental native"));
    assert(strcmp(info.library_version, argv[3]) == 0);
    core_retro_set_environment(environment);
    core_retro_set_video_refresh(video);
    core_retro_set_audio_sample_batch(audio);
    core_retro_set_input_poll(poll_input);
    core_retro_set_input_state(input);
    core_retro_init();
    assert(!core_retro_load_game(NULL));
    assert(!core_retro_load_game(NULL));
    assert(missing_messages == 2);
    if (argc == 5) {
        make_file(system_path, "mcpx_1.0.bin", 512, true);
        make_file(system_path, "bios.bin", 256 * 1024, true);
        make_file(save_path, "eeprom.bin", 256, false);
        make_file(save_path, "xbox_hdd.qcow2", (off_t)8 * 1024 * 1024 * 1024,
                  false);
        assert(core_retro_load_game(NULL));
        for (unsigned i = 0; i < 3; i++) {
            core_retro_run();
        }
        usleep(200000);
        core_retro_run();
        core_retro_reset();
        core_retro_run();
        assert(frames == 5 && polls == 5 && ports == 15);
        core_retro_unload_game();
        assert(!core_retro_load_game(NULL));
    }
    core_retro_deinit();
    assert(dlclose(handle) == 0);
    puts("CROSS NATIVE SMOKE PASS");
    return 0;
}
