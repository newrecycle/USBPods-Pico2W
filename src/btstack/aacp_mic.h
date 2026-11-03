// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#include <stdint.h>
void aacp_mic_init(void);             /* BT context, after sdp_init */
void aacp_mic_poll(void);             /* main, with BT async lock held */
void aacp_mic_set_capture(bool on);   /* USB IRQ: atomic publication only */
bool aacp_mic_capture(void);
uint32_t aacp_mic_generation(void);
void aacp_mic_discontinuity(void); /* invalidate queued audio, preserve USB intent */
void aacp_mic_audio_init(void);       /* plain main context, before BT starts */
void aacp_mic_audio_work(void);       /* bounded main-context decode */
void aacp_mic_audio_enqueue(const uint8_t *au, uint8_t len);
uint32_t aacp_mic_audio_read(int16_t *dst, uint32_t samples); /* USB IRQ */
bool aacp_mic_audio_ready(void);
void aacp_mic_audio_report(void);
