// SPDX-License-Identifier: GPL-3.0-only
// Production 44.1->48 kHz resampler contract: exact 441->480 output for the
// live callers, and no state corruption/OOB tap read when a block does not
// fit the caller's output cap (the old code still stepped the phase).
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "resamp44.h"
#include "resamp44_taps.h"

#define IN_FRAMES  441u
#define OUT_FRAMES 480u
#define MAX_FRAMES 8192u

static int16_t in[IN_FRAMES * 2];
static int16_t out[OUT_FRAMES * 2];
static int16_t work[MAX_FRAMES * 2];
static int16_t ref[MAX_FRAMES * 2];

static void fill_input(void) {
    for (size_t i = 0; i < IN_FRAMES; i++) {
        in[i * 2]     = (int16_t)(((int32_t)i * 7919) % 60000 - 30000);
        in[i * 2 + 1] = (int16_t)(((int32_t)i * 104729) % 50000 - 25000);
    }
}

static size_t required(int phase, size_t frames) {
    size_t n = 0;
    for (size_t i = 0; i < frames; i++) {
        while (phase < RS_L) { n++; phase += RS_M; }
        phase -= RS_L;
    }
    return n;
}

/* Same taps/arithmetic as the production loop, but with no output cap: the
 * oracle for the samples a full block must produce from a given state. */
static size_t reference_process(const resamp44_t *start, const int16_t *input,
                                size_t frames, int16_t *output) {
    resamp44_t s = *start;
    size_t oi = 0;
    for (size_t ii = 0; ii < frames; ii++) {
        for (int c = 0; c < 2; c++) {
            memmove(&s.hist[c][1], &s.hist[c][0], (RS_T - 1) * sizeof(int16_t));
            s.hist[c][0] = input[ii * 2 + c];
        }
        while (s.phase < RS_L) {
            const int16_t *h = sbc_rs_taps[s.phase];
            for (int c = 0; c < 2; c++) {
                int32_t acc = 0;
                for (int k = 0; k < RS_T; k++)
                    acc += (int32_t)s.hist[c][k] * h[k];
                acc >>= 15;
                if (acc > 32767) acc = 32767;
                if (acc < -32768) acc = -32768;
                output[oi * 2 + c] = (int16_t)acc;
            }
            oi++;
            s.phase += RS_M;
        }
        s.phase -= RS_L;
    }
    return oi;
}

static bool state_equal(const resamp44_t *a, const resamp44_t *b) {
    return a->phase == b->phase &&
           memcmp(a->hist, b->hist, sizeof(a->hist)) == 0;
}

static uint32_t fnv1a(const void *data, size_t n) {
    uint32_t h = 2166136261u;
    const uint8_t *p = data;
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 16777619u; }
    return h;
}

int main(void) {
    resamp44_t st, snap, zero;
    fill_input();

    /* The live callers (ELD 44.1 mode and the relay) rely on this exact
     * conversion: 3 filter periods in, 480 frames out, phase back at 0. */
    assert(required(0, IN_FRAMES) == OUT_FRAMES);
    memset(&zero, 0, sizeof zero);
    size_t n = reference_process(&zero, in, IN_FRAMES, ref);
    assert(n == OUT_FRAMES && zero.phase == 0);

    resamp44_reset_st(&st);
    memset(out, 0x5a, sizeof out);
    assert(resamp44_process_st(&st, in, IN_FRAMES, out, OUT_FRAMES) == OUT_FRAMES);
    assert(st.phase == 0);
    assert(memcmp(out, ref, sizeof out) == 0);
    /* Pin the exact samples the live 441->480 callers consume today. */
    assert(fnv1a(out, sizeof out) == 0x736cc560u);

    /* Undersized caps must write nothing, return 0 and leave state untouched
     * (so the caller can retry the whole block without lost/duplicated PCM). */
    for (size_t cap = 0; cap < 2; cap++) {
        resamp44_reset_st(&st);
        snap = st;
        memset(out, 0x5a, sizeof out);
        size_t bad = cap ? OUT_FRAMES - 1 : 100;
        assert(resamp44_process_st(&st, in, IN_FRAMES, out, bad) == 0);
        assert(state_equal(&st, &snap) && st.phase == 0);
        for (size_t i = 0; i < sizeof out / sizeof out[0]; i++)
            assert(out[i] == 0x5a5a);
    }
    /* The same state still produces the exact output after a refused call. */
    assert(resamp44_process_st(&st, in, IN_FRAMES, out, OUT_FRAMES) == OUT_FRAMES);
    assert(memcmp(out, ref, sizeof out) == 0);

    /* Nonzero phase: a partial block is not resumable either. Walk a prefix,
     * refuse a one-frame tail by one frame of output, then accept it and
     * compare against the oracle from the same starting state. */
    resamp44_reset_st(&st);
    size_t prefix = 100;
    assert(prefix < IN_FRAMES);
    assert(resamp44_process_st(&st, in, prefix, work, MAX_FRAMES) ==
           required(0, prefix));
    assert(st.phase >= 0);
    snap = st;
    size_t need = required(snap.phase, 3);
    assert(need >= 1);
    assert(resamp44_process_st(&st, &in[prefix * 2], 3, work, need - 1) == 0);
    assert(state_equal(&st, &snap));
    assert(resamp44_process_st(&st, &in[prefix * 2], 3, work, need) == need);
    assert(st.phase >= 0);
    size_t rn = reference_process(&snap, &in[prefix * 2], 3, ref);
    assert(rn == need);
    assert(memcmp(work, ref, need * 2 * sizeof(int16_t)) == 0);

    /* Zero-length blocks are a no-op, including an empty output cap. */
    snap = st;
    assert(resamp44_process_st(&st, in, 0, work, 0) == 0);
    assert(state_equal(&st, &snap));

    /* The legacy singleton path must behave identically. */
    resamp44_reset();
    assert(resamp44_process(in, IN_FRAMES, out, OUT_FRAMES) == OUT_FRAMES);
    memset(ref, 0, sizeof ref);
    n = reference_process(&zero, in, IN_FRAMES, ref);
    assert(n == OUT_FRAMES);
    assert(memcmp(out, ref, sizeof out) == 0);

    puts("resamp44: exact 441->480 and truncated-cap state safety passed");
    return 0;
}
