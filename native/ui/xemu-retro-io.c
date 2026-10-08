/* SPDX-License-Identifier: MIT */
#include "xemu-retro-io.h"
#include <string.h>

void xemu_retro_map_pad(retro_input_state_t input, unsigned port,
                        XemuRetroPad *pad)
{
    /* Match ui/xemu-input.h's ControllerState bit and axis ordering. */
    static const unsigned buttons[] = {
        RETRO_DEVICE_ID_JOYPAD_B,      RETRO_DEVICE_ID_JOYPAD_A,
        RETRO_DEVICE_ID_JOYPAD_Y,      RETRO_DEVICE_ID_JOYPAD_X,
        RETRO_DEVICE_ID_JOYPAD_LEFT,   RETRO_DEVICE_ID_JOYPAD_UP,
        RETRO_DEVICE_ID_JOYPAD_RIGHT,  RETRO_DEVICE_ID_JOYPAD_DOWN,
        RETRO_DEVICE_ID_JOYPAD_SELECT, RETRO_DEVICE_ID_JOYPAD_START,
        RETRO_DEVICE_ID_JOYPAD_L,      RETRO_DEVICE_ID_JOYPAD_R,
        RETRO_DEVICE_ID_JOYPAD_L3,     RETRO_DEVICE_ID_JOYPAD_R3,
    };
    memset(pad, 0, sizeof(*pad));
    if (!input) {
        return;
    }
    for (unsigned i = 0; i < sizeof(buttons) / sizeof(buttons[0]); i++) {
        if (input(port, RETRO_DEVICE_JOYPAD, 0, buttons[i])) {
            pad->buttons |= 1u << i;
        }
    }
    for (unsigned i = 0; i < 2; i++) {
        unsigned trigger =
            i ? RETRO_DEVICE_ID_JOYPAD_R2 : RETRO_DEVICE_ID_JOYPAD_L2;
        int16_t value = input(port, RETRO_DEVICE_ANALOG,
                              RETRO_DEVICE_INDEX_ANALOG_BUTTON, trigger);
        pad->axis[i] = value > 0                                    ? value :
                       input(port, RETRO_DEVICE_JOYPAD, 0, trigger) ? 32767 :
                                                                      0;
        pad->axis[2 + i * 2] =
            input(port, RETRO_DEVICE_ANALOG, i, RETRO_DEVICE_ID_ANALOG_X);
        /* Match xemu's SDL conversion, including both signed endpoints. */
        pad->axis[3 + i * 2] =
            -1 - input(port, RETRO_DEVICE_ANALOG, i, RETRO_DEVICE_ID_ANALOG_Y);
    }
}

size_t xemu_retro_audio_write(XemuRetroAudio *audio, const int16_t *data,
                              size_t frames)
{
    pthread_mutex_lock(&audio->lock);
    size_t accepted = frames;
    if (accepted > XEMU_RETRO_AUDIO_CAPACITY - audio->count) {
        accepted = XEMU_RETRO_AUDIO_CAPACITY - audio->count;
    }
    for (size_t i = 0; i < accepted; i++) {
        size_t pos =
            (audio->read + audio->count + i) % XEMU_RETRO_AUDIO_CAPACITY;
        memcpy(&audio->samples[2 * pos], &data[2 * i], 2 * sizeof(int16_t));
    }
    audio->count += accepted;
    audio->dropped += frames - accepted;
    pthread_mutex_unlock(&audio->lock);
    return accepted;
}

size_t xemu_retro_audio_peek(XemuRetroAudio *audio, int16_t *data,
                             size_t frames)
{
    pthread_mutex_lock(&audio->lock);
    if (frames > audio->count) {
        frames = audio->count;
    }
    for (size_t i = 0; i < frames; i++) {
        size_t pos = (audio->read + i) % XEMU_RETRO_AUDIO_CAPACITY;
        memcpy(&data[2 * i], &audio->samples[2 * pos], 2 * sizeof(int16_t));
    }
    pthread_mutex_unlock(&audio->lock);
    return frames;
}

void xemu_retro_audio_consume(XemuRetroAudio *audio, size_t frames)
{
    pthread_mutex_lock(&audio->lock);
    if (frames > audio->count) {
        frames = audio->count;
    }
    audio->read = (audio->read + frames) % XEMU_RETRO_AUDIO_CAPACITY;
    audio->count -= frames;
    pthread_mutex_unlock(&audio->lock);
}

void xemu_retro_audio_clear(XemuRetroAudio *audio)
{
    pthread_mutex_lock(&audio->lock);
    audio->read = audio->count = 0;
    pthread_mutex_unlock(&audio->lock);
}
