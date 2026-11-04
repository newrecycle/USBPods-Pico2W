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

enum { AACP_MIC_SILENCE_MS=2000, AACP_MIC_MAX_RETRIES=3 };
typedef enum { AACP_MIC_RETRY_NONE,AACP_MIC_RETRY_STOP,AACP_MIC_RETRY_START } aacp_mic_retry_phase;
typedef struct {
 uint32_t generation,due,last_audio,restarts,failures;
 uint8_t retries;
 bool enabled,armed,seen,failed;
 aacp_mic_retry_phase retry;
} aacp_mic_watch;
/* Channel owner only. Target is recomputed before requesting/sending a command.
 * Capture generations reset the retry budget; successful sends alone advance
 * STOP -> START. Received, fully framed audio establishes liveness. */
void aacp_mic_watch_reset(aacp_mic_watch *w);
bool aacp_mic_watch_target(aacp_mic_watch *w,bool wanted,bool started,uint32_t generation,uint32_t now);
void aacp_mic_watch_sent(aacp_mic_watch *w,int command,uint32_t now);
void aacp_mic_watch_audio(aacp_mic_watch *w,uint32_t now);

