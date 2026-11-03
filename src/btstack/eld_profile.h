// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct {
 uint32_t bitrate;
 uint16_t input_rate,input_frames;
 uint8_t vbr,sbr,slots,jitter;
} eld_profile;
eld_profile eld_profile_select(uint8_t rate,bool game,uint8_t level,bool rate44,bool relay,uint8_t vbr,uint8_t sbr);
typedef struct { eld_profile desired,active; bool ready,pending;uint32_t failures,rebuilds; } eld_runtime_status;
void a2dp_source_eld_status(eld_runtime_status*);
