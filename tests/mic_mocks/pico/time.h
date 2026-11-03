#pragma once
#include <stdint.h>
extern uint32_t mock_time_us;
static inline uint32_t time_us_32(void) { return mock_time_us; }
static inline uint64_t get_absolute_time(void) { return 0; }
static inline uint32_t to_ms_since_boot(uint64_t t) { return t/1000; }
