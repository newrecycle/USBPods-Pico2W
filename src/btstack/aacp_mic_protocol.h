// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef void (*aacp_mic_au_cb)(const uint8_t *, uint8_t, uint32_t, void *);
/* 0: other control; -1: malformed audio; >0: fully validated AU count.
 * No callback runs until the ENTIRE SDU has passed validation. */
int aacp_mic_parse(const uint8_t *p, size_t n, aacp_mic_au_cb cb, void *ctx);
typedef struct { uint8_t init_sent; bool confirmed, started; } aacp_mic_session;
/* Returns 0..4 for handshake/features/notifications/start/stop; -1 idle. */
int aacp_mic_next(const aacp_mic_session *s, bool wanted);
void aacp_mic_sent(aacp_mic_session *s, int command);
const uint8_t *aacp_mic_command(int command, uint16_t *size);
