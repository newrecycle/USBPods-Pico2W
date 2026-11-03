// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
enum { ELD_CODEC_CONFIG_SIZE=14, ELD_LOCAL_MAX_BITRATE=320000 };
typedef struct {uint32_t max_bitrate;bool vbr;} eld_codec_limits;
/* The supported 48 kHz stereo vendor layout; zero capability bitrate means
 * unspecified, whereas a configuration must name an explicit ceiling. */
bool eld_codec_offer(const uint8_t *caps,size_t len,uint8_t out[14],eld_codec_limits *limits);
bool eld_codec_configuration(const uint8_t *config,size_t len,eld_codec_limits *limits);
