// SPDX-License-Identifier: GPL-3.0-only
// Production AU/PCM queues, microphone clock and USB accounting under
// deterministic 1ms host schedules. This is NOT physical timing evidence.
// Each scenario runs in its own process to avoid leaking static queue state.
#include "aacp_mic.h"
#include "mic_clock.h"
#include "usb_capture_lifecycle.h"
#include <aacdecoder_lib.h>
#include <assert.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

_Atomic uint32_t mock_time_us;
static CStreamInfo stream_info={48000,1,480};
static uint8_t next_sample;
static bool has_au;
static unsigned received_au;

HANDLE_AACDECODER aacDecoder_Open(int transport,int layers) {
    assert(transport==TT_MP4_RAW && layers==1);
    return &stream_info;
}
AAC_DECODER_ERROR aacDecoder_ConfigRaw(HANDLE_AACDECODER d,UCHAR **p,UINT *n) {
    assert(d==&stream_info && *n==4 && p[0][0]==0xf8 && p[0][1]==0xe6);
    return AAC_DEC_OK;
}
void aacDecoder_Close(HANDLE_AACDECODER d) { assert(d==&stream_info); }
AAC_DECODER_ERROR aacDecoder_SetParam(HANDLE_AACDECODER d,int param,int v) {
    assert(d==&stream_info && param==AAC_TPDEC_CLEAR_BUFFER && v==1);
    return AAC_DEC_OK;
}
AAC_DECODER_ERROR aacDecoder_Fill(HANDLE_AACDECODER d,UCHAR **p,UINT *size,UINT *valid) {
    assert(d==&stream_info && *size==1 && *valid==1 && !has_au);
    next_sample=p[0][0];*valid=0;has_au=true;
    return AAC_DEC_OK;
}
AAC_DECODER_ERROR aacDecoder_DecodeFrame(HANDLE_AACDECODER d,INT_PCM *samples,int cap,int flags) {
    assert(d==&stream_info && cap>=480 && has_au);
    assert(flags==0 || flags==(AACDEC_CLRHIST|AACDEC_INTR));
    has_au=false;
    for(unsigned i=0;i<480;i++)samples[i]=next_sample;
    received_au++;
    atomic_fetch_add_explicit(&mock_time_us,300,memory_order_relaxed);
    return AAC_DEC_OK;
}
CStreamInfo *aacDecoder_GetStreamInfo(HANDLE_AACDECODER d) {
    assert(d==&stream_info);
    return &stream_info;
}
static void start_session(void) {
    aacp_mic_audio_init();
    assert(aacp_mic_audio_ready());
    usb_capture_mount();
    assert(!usb_capture_running());
    usb_capture_set_alt(true);
    assert(usb_capture_running() && aacp_mic_capture());
}
static unsigned next_au;
static void publish_group(void) {
    for(unsigned n=0;n<4;n++) {
        uint8_t value=(uint8_t)(1+((next_au++)%200));
        aacp_mic_audio_note_au(next_au*180,atomic_load(&mock_time_us));
        aacp_mic_audio_enqueue(&value,1);
    }
}
static void capture_epoch(void) {
    start_session();
    // Fill all sixteen actual PCM frames without an intervening USB callback.
    for(unsigned i=0;i<16;i++) {
        const uint8_t old=19;
        aacp_mic_audio_enqueue(&old,1);
        aacp_mic_audio_work();
    }
    assert(aacp_mic_audio_packet_samples()==64);
    int16_t pcm[65];
    assert(aacp_mic_audio_read(pcm,64)==64 && pcm[0]==19);
    const unsigned epoch=aacp_mic_generation();
    usb_capture_close();
    assert(!aacp_mic_capture());
    usb_capture_set_alt(true);
    assert(aacp_mic_generation()==epoch+2);
    // Current AUs are retained (at most 32), not overwritten by stale PCM.
    for(unsigned i=0;i<10;i++) {
        const uint8_t fresh=73;
        aacp_mic_audio_enqueue(&fresh,1);
    }
    aacp_mic_audio_work(); // blocked by the old full PCM ring
    // Only production USB consumer may retire stale frames/partial offsets.
    assert(aacp_mic_audio_packet_samples()==0);
    aacp_mic_audio_work();
    assert(aacp_mic_audio_packet_samples()==0); // eight frames < 4800
    aacp_mic_audio_work();
    uint32_t count=aacp_mic_audio_packet_samples();
    assert(count>=63 && count<=65);
    assert(aacp_mic_audio_read(pcm,count)==count);
    for(unsigned j=0;j<count;j++)assert(pcm[j]==73);
    aacp_mic_audio_stats stat;
    aacp_mic_audio_get_stats(&stat);
    assert(stat.pcm_stale>=16 && stat.au_overflows==0 && stat.decode_errors==0);
    assert(stat.pcm_blocked>0 && stat.decoded==26);
    printf("PASS capture-epoch: stale full ring, partial offset and fresh PCM; generation=%u\n",stat.generation);
}
static void schedule(const char *which) {
    const bool producer_gap=strcmp(which,"producer-gap")==0;
    const bool worker_delay=strcmp(which,"worker-delay")==0 ||
                            strcmp(which,"negative-worker-no-loss")==0;
    const bool consumer_hold=strcmp(which,"consumer-hold")==0;
    const bool baseline=strcmp(which,"on-time")==0;
    assert(producer_gap || worker_delay || consumer_hold || baseline);
    start_session();
    uint32_t held_groups=0,missing_after_prime=0,miss_with_au=0,miss_no_au=0;
    bool primed_once=false;
    const uint32_t final_ms=3000;
    for(uint32_t ms=0;ms<final_ms;ms++) {
        atomic_store_explicit(&mock_time_us,ms*1000,memory_order_relaxed);
        if(ms%30u==0) {
            if(producer_gap && ms>=1200 && ms<1350)held_groups++;
            else {
                for(uint32_t n=0;n<1+held_groups;n++)publish_group();
                held_groups=0;
            }
        }
        if(!worker_delay || ms<1200 || ms>=1360)
            aacp_mic_audio_work();
        if(consumer_hold && ms>=1200 && ms<1700) continue;
        uint32_t want=aacp_mic_audio_packet_samples();
        uint32_t got=0;
        int16_t pcm[65]={0};
        if(want) {
            assert(want>=63 && want<=65);
            got=aacp_mic_audio_read(pcm,want);
            assert(got==want); // any unexpected partial read is a real failure
            primed_once=true;
        } else {
            want=64; // actual UAC callback substitutes a 64-sample zero frame
            if(primed_once) {
                missing_after_prime+=64;
                aacp_mic_audio_stats st;
                aacp_mic_audio_get_stats(&st);
                if(st.au_depth)miss_with_au++;
                else miss_no_au++;
            }
        }
        usb_capture_note_tx(want,got,2*want);
    }
    aacp_mic_audio_stats st;
    aacp_mic_audio_get_stats(&st);
    usb_capture_snapshot_t usb=usb_capture_snapshot();
    assert(primed_once && st.decoder_ready && st.capture);
    assert(st.decode_errors==0 && st.pcm_overflows==0);
    assert(usb.short_writes==0 && usb.expected_samples==usb.pcm_samples+usb.missing_samples);
    assert(usb.usb_packets>0 && usb.packets_63+usb.packets_65<=usb.usb_packets);
    assert(usb.expected_samples>=63u*usb.usb_packets &&
           usb.expected_samples<=65u*usb.usb_packets);
    assert(st.decoded==received_au);
    if(!consumer_hold) {
        assert(st.au_overflows==0);
        assert((uint64_t)st.decoded*480u>=usb.pcm_samples);
        assert((uint64_t)st.decoded*480u-usb.pcm_samples<=16u*480u);
    }
    if(baseline)assert(missing_after_prime==0 && st.au_overflows==0);
    if(producer_gap) {
        assert(missing_after_prime>0 && miss_no_au>0);
        assert(st.au_overflows==0 && st.au_depth<=32);
    }
    if(worker_delay) {
        assert(missing_after_prime>0 && miss_with_au>0);
        assert(st.au_overflows==0 && st.au_depth<=32);
    }
    if(consumer_hold) {
        assert(st.pcm_blocked>0 && st.au_overflows>0);
        assert(st.au_high_water==32 && st.pcm_high_water==16);
    }
    if(strcmp(which,"negative-worker-no-loss")==0) {
        // Deliberately wrong strict-pass claim must be rejected by production
        // USB accounting; CI requires this executable to fail as a control.
        fprintf(stderr,"EXPECTED_NEGATIVE_CONTROL: deliberately false zero-loss claim\n");
        fflush(stderr);
        assert(usb.missing_samples==0);
    }
    printf("PASS %s: decoded=%u AU_drop=%u PCM_full=%u USB_missing=%u missing_after_prime=%u empty_AU=%u queued_AU=%u\n",
           which,st.decoded,st.au_overflows,st.pcm_blocked,usb.missing_samples,
           missing_after_prime,miss_no_au,miss_with_au);
}
int main(int argc,char **argv) {
    assert(argc==2);
    if(strcmp(argv[1],"capture-epoch")==0)capture_epoch();
    else schedule(argv[1]);
    return 0;
}
