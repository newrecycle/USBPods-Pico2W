// SPDX-License-Identifier: GPL-3.0-only
// Diagnostic-only build must preserve AU timing even without FDK.
#include "aacp_mic.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    aacp_mic_audio_stats s;
    aacp_mic_audio_init();
    assert(aacp_mic_audio_ready());
    aacp_mic_set_capture(true);
    aacp_mic_audio_note_au(0xfffffff0u,0xfffffff0u);
    aacp_mic_audio_note_au(464,7484); /* both counters wrap by +480/+7500 */
    aacp_mic_audio_get_stats(&s);
    assert(s.capture && !s.decoder_ready);
    assert(s.au_observed==2 && s.arrival_7500us==1);
    assert(s.timestamp_step_reference==480 && s.timestamp_backwards==0);
    assert(s.au_depth==0 && s.pcm_depth==0 && s.decode_max_us==0);
    aacp_mic_discontinuity();
    aacp_mic_audio_note_au(0,0);
    aacp_mic_audio_note_au(480,10000);
    aacp_mic_audio_get_stats(&s);
    assert(s.au_observed==4 && s.arrival_10000us==1);
    assert(s.timestamp_backwards==0 && s.timestamp_step_reference==480);
    puts("transport-only cadence, wrap and generation tests passed");
}
