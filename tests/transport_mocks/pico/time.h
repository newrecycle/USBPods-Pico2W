#pragma once
#include <stdint.h>
/* Transport mock: AU cadence is exercised with explicit times in the audio test. */
static inline uint32_t time_us_32(void) { return 0; }
