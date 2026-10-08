/* SPDX-License-Identifier: MIT */
#ifndef XEMU_RETRO_IO_H
#define XEMU_RETRO_IO_H
#include "libretro.h"
#include <pthread.h>

#define XEMU_RETRO_AUDIO_CAPACITY 8192
typedef struct XemuRetroPad {
    uint16_t buttons;
    int16_t axis[6];
} XemuRetroPad;

typedef struct XemuRetroAudio {
    pthread_mutex_t lock;
    int16_t samples[XEMU_RETRO_AUDIO_CAPACITY * 2];
    size_t read, count;
    uint64_t dropped;
} XemuRetroAudio;

void xemu_retro_map_pad(retro_input_state_t input, unsigned port,
                        XemuRetroPad *pad);
size_t xemu_retro_audio_write(XemuRetroAudio *audio, const int16_t *data,
                              size_t frames);
size_t xemu_retro_audio_peek(XemuRetroAudio *audio, int16_t *data,
                             size_t frames);
void xemu_retro_audio_consume(XemuRetroAudio *audio, size_t frames);
void xemu_retro_audio_clear(XemuRetroAudio *audio);
#endif
