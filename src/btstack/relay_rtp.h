// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
typedef struct { uint8_t data[2048]; uint16_t length,sequence; uint32_t timestamp,source; bool active,complete,seen; } relay_rtp_assembly;
bool relay_rtp_payload(const uint8_t*,size_t,const uint8_t**,size_t*);
void relay_rtp_reset(relay_rtp_assembly*);
/* LATM fragments share a timestamp, consecutive sequence and final marker. */
int relay_rtp_assemble(relay_rtp_assembly*,const uint8_t*,size_t);
