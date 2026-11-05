// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef enum {
 ELD_OFF,ELD_READY,ELD_WAIT_SUSPEND,ELD_REBUILD,ELD_WAIT_START,ELD_FAILED
} eld_phase;
enum eld_action {
 ELD_NOTHING=0,ELD_STOP=1,ELD_SUSPEND=2,ELD_BUILD=4,
 ELD_START=8,ELD_RUN=16,ELD_SETTLE=32,ELD_DROP=64
};
typedef struct {
 eld_phase phase;
 uint32_t requested,built;
 bool managed,start_inflight;
 uint8_t start_retries;
} eld_transition;
void eld_transition_reset(eld_transition*);
void eld_transition_configured(eld_transition*);
unsigned eld_transition_request(eld_transition*,bool streaming);
unsigned eld_transition_suspended(eld_transition*);
unsigned eld_transition_started(eld_transition*);
unsigned eld_transition_built(eld_transition*,bool success);
unsigned eld_transition_failed(eld_transition*);
unsigned eld_transition_rejected(eld_transition*);
bool eld_transition_begin_start(eld_transition*);
unsigned eld_transition_retry_start(eld_transition*);
bool eld_transition_busy(const eld_transition*);
const char *eld_transition_phase_name(eld_phase);
