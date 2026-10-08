/* SPDX-License-Identifier: MIT */
#include "xemu-retro-io.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int16_t buttons[16];
static int16_t axes[3][16];
static int16_t input(unsigned port, unsigned device, unsigned index, unsigned id)
{
    assert(port == 2);
    return device == RETRO_DEVICE_JOYPAD ? buttons[id] : axes[index][id];
}

int main(void)
{
    XemuRetroPad pad;
    buttons[RETRO_DEVICE_ID_JOYPAD_B] = 1;
    buttons[RETRO_DEVICE_ID_JOYPAD_X] = 1;
    buttons[RETRO_DEVICE_ID_JOYPAD_L] = 1;
    buttons[RETRO_DEVICE_ID_JOYPAD_R2] = 1;
    axes[2][RETRO_DEVICE_ID_JOYPAD_L2] = 12345;
    axes[0][RETRO_DEVICE_ID_ANALOG_X] = -32768;
    axes[0][RETRO_DEVICE_ID_ANALOG_Y] = -32768;
    axes[1][RETRO_DEVICE_ID_ANALOG_X] = 32767;
    axes[1][RETRO_DEVICE_ID_ANALOG_Y] = 32767;
    xemu_retro_map_pad(input, 2, &pad);
    assert(pad.buttons == ((1u << 0) | (1u << 3) | (1u << 10)));
    assert(pad.axis[0] == 12345 && pad.axis[1] == 32767);
    assert(pad.axis[2] == -32768 && pad.axis[3] == 32767);
    assert(pad.axis[4] == 32767 && pad.axis[5] == -32768);
    axes[2][RETRO_DEVICE_ID_JOYPAD_R2] = 15000;
    xemu_retro_map_pad(input, 2, &pad);
    assert(pad.axis[1] == 15000); /* Analog magnitude survives a digital press. */
    xemu_retro_map_pad(NULL, 2, &pad);
    assert(pad.buttons == 0);
    for (unsigned i = 0; i < 6; i++) {
        assert(pad.axis[i] == 0);
    }

    XemuRetroAudio audio = { .lock = PTHREAD_MUTEX_INITIALIZER };
    int16_t samples[XEMU_RETRO_AUDIO_CAPACITY * 2];
    int16_t output[XEMU_RETRO_AUDIO_CAPACITY * 2];
    for (unsigned i = 0; i < XEMU_RETRO_AUDIO_CAPACITY; i++) {
        samples[2 * i] = i;
        samples[2 * i + 1] = -(int)i;
    }
    assert(xemu_retro_audio_write(&audio, samples, 8000) == 8000);
    assert(xemu_retro_audio_peek(&audio, output, 800) == 800);
    assert(memcmp(output, samples, 800 * 4) == 0);
    xemu_retro_audio_consume(&audio, 400); /* Frontend accepted half the batch. */
    assert(xemu_retro_audio_peek(&audio, output, 800) == 800);
    assert(memcmp(output, samples + 800, 800 * 4) == 0);
    assert(xemu_retro_audio_write(&audio, samples, 800) == 592);
    assert(audio.dropped == 208 && audio.count == XEMU_RETRO_AUDIO_CAPACITY);
    assert(xemu_retro_audio_peek(&audio, output, XEMU_RETRO_AUDIO_CAPACITY) == 8192);
    assert(memcmp(output, samples + 800, 7600 * 4) == 0);
    assert(memcmp(output + 15200, samples, 592 * 4) == 0);
    xemu_retro_audio_consume(&audio, 8192);
    assert(xemu_retro_audio_peek(&audio, output, 1) == 0);
    assert(xemu_retro_audio_write(&audio, samples, 100) == 100);
    xemu_retro_audio_clear(&audio);
    assert(audio.count == 0);
    pthread_mutex_destroy(&audio.lock);
    puts("PASS: Xbox button mapping, trigger pressure, signed axes, audio partial consumption, wraparound and overflow");
    return 0;
}
