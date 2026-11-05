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
void aacp_mic_audio_work(void);       /* bounded decode: core0 default, core1 experimental */
bool aacp_mic_audio_pending(void);   /* runnable AU: avoid sleeping behind it */
void aacp_mic_audio_enqueue(const uint8_t *au, uint8_t len);
uint32_t aacp_mic_audio_read(int16_t *dst, uint32_t samples); /* USB IRQ */
uint32_t aacp_mic_audio_packet_samples(void); /* USB IRQ, once per 1 ms IN packet */
bool aacp_mic_audio_ready(void);
void aacp_mic_audio_report(void);
/* Metadata only: no microphone content, device addresses or key payloads. */
typedef struct {
    uint32_t age_ms, init_mask, rx_packets, rx_unhandled, logged_headers;
    uint32_t last_rx_age_ms, last_tx_age_ms;
    uint16_t cid, last_opcode, last_length;
    uint8_t init_sent, peer_seen, handshake_ack, last_tx_command;
    bool open;
} aacp_mic_session_diagnostics;
void aacp_mic_get_session_diagnostics(aacp_mic_session_diagnostics *out);

/* Best-effort, allocation-free telemetry snapshot. Counters are lifetime
 * totals (uint32_t wrapping naturally); depth is a point-in-time estimate.
 * Microsecond arrival values are wrapping 32-bit clock deltas, while AACP
 * timestamps are raw peer units: no timestamp clock is assumed. */
typedef struct {
    uint32_t generation, capture, decoder_ready;
    uint32_t au_observed, arrival_intervals, arrival_bursts;
    uint32_t arrival_7500us, arrival_10000us, arrival_other, arrival_gaps;
    uint32_t arrival_last_us, arrival_min_us, arrival_max_us;
    uint32_t timestamp_last, timestamp_step_reference;
    uint32_t timestamp_step_last, timestamp_step_min, timestamp_step_max;
    uint32_t timestamp_duplicates, timestamp_backwards;
    uint32_t timestamp_step_changes, timestamp_gap_candidates;
    uint32_t au_depth, au_high_water, au_overflows, au_stale, au_inactive;
    uint32_t pcm_depth, pcm_high_water, pcm_overflows, pcm_stale;
    uint32_t decoded, decode_errors, decode_last_us, decode_max_us, decode_ema_us;
    uint32_t decoded_rate, decoded_channels, decoded_frame_samples;
    uint32_t measured_sample_rate,clock_windows,pcm_primed;
} aacp_mic_audio_stats;

/* Called once for each validated AACP audio AU, including diagnostic-only
 * builds and AUs received while capture is not requested. arrival_us must
 * be a monotonically wrapping microsecond clock (time_us_32()). */
void aacp_mic_audio_note_au(uint32_t timestamp, uint32_t arrival_us);
void aacp_mic_audio_get_stats(aacp_mic_audio_stats *out);
