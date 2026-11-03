// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
/* All operations run under the channel owner's async-context lock. */
typedef struct {
 uint8_t battery[3], noise;
 int pvol, ca, aa,allow_off;
 uint8_t pending, values[5];
 uint32_t observed[5];
 bool ear_valid,worn;
 uint32_t stem_count;uint8_t stem;
} aacp_control;
void aacp_control_reset(aacp_control *s);
/* Validates the entire notification before publishing state. */
bool aacp_control_receive(aacp_control *s,const uint8_t *p,size_t n);
bool aacp_control_set(aacp_control *s,uint8_t id,uint8_t value);
/* Peek is non-destructive. Successful sends alone commit the command. */
int aacp_control_peek(const aacp_control *s,uint8_t packet[11]);
void aacp_control_sent(aacp_control *s,int slot,uint8_t value);
/* Live channel API: false means invalid value or no open channel. */
bool aacp_control_submit(uint8_t id,uint8_t value);

/* Wire submission is distinct from a fresh peer notification. */
typedef struct {
 uint32_t transmitted, observed[5],batches,framing_errors;
 int allow_off;
 bool mic_started,mic_recovery_pending;
 uint32_t media_suppressed,media_dropped;
 uint8_t media_pending,last_id,last_value;
} aacp_control_diagnostics;
aacp_control_diagnostics aap_control_diagnostics(void);

/* Structurally validate concatenated fixed-format notifications before any
 * callbacks. Unknown standalone packets return 0 for legacy handling. No
 * header searching inside opaque or encoded audio payloads is performed. */
typedef void (*aacp_control_frame_cb)(const uint8_t*,size_t,void*);
int aacp_control_walk(const uint8_t*,size_t,aacp_control_frame_cb,void*);
