/* SPDX-License-Identifier: MIT */
#include "libretro.h"
#include "xemu-libretro-version.h"

#include <stdint.h>
#include <string.h>

#define WIDTH 640
#define HEIGHT 480
#define AUDIO_FRAMES 800
#define PORTS 4

static retro_environment_t environment;
static retro_video_refresh_t video;
static retro_audio_sample_t audio_sample;
static retro_audio_sample_batch_t audio_batch;
static retro_input_poll_t input_poll;
static retro_input_state_t input_state;
static retro_log_printf_t logger;
static bool loaded;
static bool connected[PORTS];
static uint32_t frame_number;
static uint32_t pixels[WIDTH * HEIGHT];
static const int16_t silence[AUDIO_FRAMES * 2];

static void message(const char *text)
{
    struct retro_message msg = { text, 600 };
    if (logger) {
        logger(RETRO_LOG_INFO, "%s\n", text);
    }
    if (environment) {
        environment(RETRO_ENVIRONMENT_SET_MESSAGE, &msg);
    }
}

void retro_set_environment(retro_environment_t cb)
{
    bool support_no_game = true;
    environment = cb;
    if (environment) {
        environment(RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME, &support_no_game);
    }
}

void retro_set_video_refresh(retro_video_refresh_t cb) { video = cb; }
void retro_set_audio_sample(retro_audio_sample_t cb) { audio_sample = cb; }
void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb) { audio_batch = cb; }
void retro_set_input_poll(retro_input_poll_t cb) { input_poll = cb; }
void retro_set_input_state(retro_input_state_t cb) { input_state = cb; }
unsigned retro_api_version(void) { return RETRO_API_VERSION; }

void retro_init(void)
{
    struct retro_log_callback logging = { 0 };
    unsigned port;
    logger = NULL;
    loaded = false;
    frame_number = 0;
    for (port = 0; port < PORTS; ++port) {
        connected[port] = true;
    }
    if (environment && environment(RETRO_ENVIRONMENT_GET_LOG_INTERFACE, &logging)) {
        logger = logging.log;
    }
}

void retro_unload_game(void)
{
    loaded = false;
    frame_number = 0;
}

void retro_deinit(void)
{
    retro_unload_game();
    logger = NULL;
}

void retro_get_system_info(struct retro_system_info *info)
{
    memset(info, 0, sizeof(*info));
    info->library_name = "xemu port diagnostics (no emulation)";
    info->library_version = XEMU_LIBRETRO_VERSION;
    info->valid_extensions = "iso";
    info->need_fullpath = true;
    info->block_extract = true;
}

void retro_get_system_av_info(struct retro_system_av_info *info)
{
    memset(info, 0, sizeof(*info));
    info->geometry.base_width = WIDTH;
    info->geometry.base_height = HEIGHT;
    info->geometry.max_width = WIDTH;
    info->geometry.max_height = HEIGHT;
    info->geometry.aspect_ratio = 4.0f / 3.0f;
    info->timing.fps = 60.0;
    info->timing.sample_rate = 48000.0;
}

bool retro_load_game(const struct retro_game_info *game)
{
    enum retro_pixel_format format = RETRO_PIXEL_FORMAT_XRGB8888;
    if (loaded) {
        return false;
    }
    if (game) {
        message("Xbox emulation is not integrated yet. Start this core without content for diagnostics.");
        return false;
    }
    if (!environment || !environment(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &format)) {
        message("Diagnostics require frontend support for XRGB8888 video.");
        return false;
    }
    frame_number = 0;
    loaded = true;
    message("PORT DIAGNOSTICS ONLY - no Xbox emulation. Four rows show controller buttons and sticks.");
    return true;
}

void retro_set_controller_port_device(unsigned port, unsigned device)
{
    if (port < PORTS) {
        connected[port] = (device & RETRO_DEVICE_MASK) == RETRO_DEVICE_JOYPAD;
    }
}

static void rectangle(unsigned x, unsigned y, unsigned w, unsigned h, uint32_t color)
{
    unsigned row, col;
    for (row = y; row < y + h && row < HEIGHT; ++row) {
        for (col = x; col < x + w && col < WIDTH; ++col) {
            pixels[row * WIDTH + col] = color;
        }
    }
}

void retro_run(void)
{
    unsigned port, button, stick, i;
    if (!loaded) {
        return;
    }
    if (input_poll) {
        input_poll();
    }
    for (i = 0; i < WIDTH * HEIGHT; ++i) {
        pixels[i] = 0x00131b24;
    }
    /* Moving bar proves that the frontend is advancing frames. */
    rectangle(frame_number % (WIDTH - 32), 24, 32, 8, 0x0098dc45);
    for (port = 0; port < PORTS; ++port) {
        unsigned y = 60 + port * 100;
        rectangle(16, y, 8, 72, connected[port] ? 0x0098dc45 : 0x00545c64);
        for (button = 0; button < 16; ++button) {
            bool pressed = connected[port] && input_state &&
                input_state(port, RETRO_DEVICE_JOYPAD, 0, button) != 0;
            rectangle(40 + button * 36, y, 28, 28,
                      pressed ? 0x0098dc45 : 0x00374656);
        }
        for (stick = 0; stick < 2; ++stick) {
            int x = 0, sy = 0;
            unsigned center = 100 + stick * 240;
            if (connected[port] && input_state) {
                x = input_state(port, RETRO_DEVICE_ANALOG, stick,
                                RETRO_DEVICE_ID_ANALOG_X);
                sy = input_state(port, RETRO_DEVICE_ANALOG, stick,
                                 RETRO_DEVICE_ID_ANALOG_Y);
            }
            rectangle(center - 24, y + 38, 48, 48, 0x00374656);
            rectangle((unsigned)((int)center - 3 + x * 20 / 32768),
                      (unsigned)((int)y + 59 + sy * 20 / 32768),
                      6, 6, 0x00e8eff7);
        }
    }
    if (video) {
        video(pixels, WIDTH, HEIGHT, WIDTH * sizeof(pixels[0]));
    }
    /* Silence exercises audio callbacks without a surprise test tone. There is
     * no pending sound to preserve when a frontend accepts only part of it. */
    if (audio_batch) {
        audio_batch(silence, AUDIO_FRAMES);
    } else if (audio_sample) {
        for (i = 0; i < AUDIO_FRAMES; ++i) {
            audio_sample(0, 0);
        }
    }
    ++frame_number;
}

void retro_reset(void) { frame_number = 0; }
unsigned retro_get_region(void) { return RETRO_REGION_NTSC; }
size_t retro_serialize_size(void) { return 0; }
bool retro_serialize(void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}
bool retro_unserialize(const void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}
bool retro_load_game_special(unsigned type, const struct retro_game_info *info, size_t count)
{
    (void)type;
    (void)info;
    (void)count;
    return false;
}
void retro_cheat_reset(void) { }
void retro_cheat_set(unsigned index, bool enabled, const char *code)
{
    (void)index;
    (void)enabled;
    (void)code;
}
void *retro_get_memory_data(unsigned id)
{
    (void)id;
    return NULL;
}
size_t retro_get_memory_size(unsigned id)
{
    (void)id;
    return 0;
}
