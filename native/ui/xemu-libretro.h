/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef XEMU_LIBRETRO_H
#define XEMU_LIBRETRO_H

#include <stddef.h>
#include <stdint.h>

void xemu_retro_audio_push(const int16_t *samples, size_t frames);
size_t xemu_retro_audio_queued(void);
void xemu_retro_report_error(const char *message);

#endif
