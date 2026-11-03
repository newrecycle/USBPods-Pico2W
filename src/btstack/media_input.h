// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#include <stdint.h>
#define MEDIA_INPUT_WINDOW_MS 250u
#define MEDIA_INPUT_QUEUE 4u
typedef struct {
 struct {uint32_t when;uint16_t usage;} pending[MEDIA_INPUT_QUEUE];
 uint32_t typed_at,suppressed,dropped;
 uint8_t read,count;
 bool typed_valid;
} media_input;
void media_input_reset(media_input*);
void media_input_avrcp(media_input*,uint16_t usage,uint32_t now);
/* Flush expired native events before committing a new typed gesture. */
uint16_t media_input_poll(media_input*,uint32_t now);
void media_input_typed(media_input*,uint32_t now);
