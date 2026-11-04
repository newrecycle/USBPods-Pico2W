// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdint.h>
#include <stdbool.h>
/* 75 ms target/prefill (previously 45 ms): absorb service gaps without
 * changing the 64 kHz clock or enlarging the existing sixteen-frame ring. */
enum {MIC_CODING_RATE=48000,MIC_PCM_RATE=64000,MIC_AU_SAMPLES=480,
      MIC_USB_NOMINAL_SAMPLES=64,MIC_USB_MAX_SAMPLES=65,MIC_PREFILL_SAMPLES=4800};
typedef struct {uint32_t generation;int32_t level_q8,correction;bool primed;} mic_clock;
/* One call per USB millisecond. Zero means startup/rebuffering silence; PCM
 * stays queued. Async IN packets use 63/64/65 samples to follow source drift. */
uint32_t mic_clock_packet(mic_clock *state,uint32_t generation,uint32_t available);
