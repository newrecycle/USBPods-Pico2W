// SPDX-License-Identifier: GPL-3.0-only
// Exercise the actual AU/PCM SPSC production queues with three host threads.
// Not a proof of target FDK reentrancy or multicore flash safety.
#include "aacp_mic.h"
#include <aacdecoder_lib.h>
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>

enum { FRAME_SAMPLES = 480, TEST_FRAMES = 512 };
_Atomic uint32_t mock_time_us; /* decoder advances; producer samples enqueue time */
static _Atomic bool done;
static CStreamInfo stream_info={48000,1,480};
static uint8_t next_value; /* decoder-thread private */
HANDLE_AACDECODER aacDecoder_Open(int t,int n) {
    assert(t==TT_MP4_RAW && n==1);
    return &stream_info;
}
AAC_DECODER_ERROR aacDecoder_ConfigRaw(HANDLE_AACDECODER d,UCHAR **p,UINT *n) {
    assert(d==&stream_info && *n==4 && p[0][0]==0xf8 && p[0][1]==0xe6);
    return AAC_DEC_OK;
}
void aacDecoder_Close(HANDLE_AACDECODER d) { assert(d==&stream_info); }
AAC_DECODER_ERROR aacDecoder_SetParam(HANDLE_AACDECODER d,int p,int v) {
    assert(d==&stream_info && p==AAC_TPDEC_CLEAR_BUFFER && v==1);
    return AAC_DEC_OK;
}
AAC_DECODER_ERROR aacDecoder_Fill(HANDLE_AACDECODER d,UCHAR **p,UINT *size,UINT *valid) {
    assert(d==&stream_info && *size==1 && *valid==1);
    next_value=p[0][0];*valid=0;
    return AAC_DEC_OK;
}
AAC_DECODER_ERROR aacDecoder_DecodeFrame(HANDLE_AACDECODER d,INT_PCM *out,int cap,int flags) {
    assert(d==&stream_info && cap>=FRAME_SAMPLES);
    assert(flags==0 || flags==(AACDEC_CLRHIST|AACDEC_INTR));
    for(int i=0;i<FRAME_SAMPLES;i++)out[i]=next_value;
    mock_time_us+=275;
    return AAC_DEC_OK;
}
CStreamInfo *aacDecoder_GetStreamInfo(HANDLE_AACDECODER d) {
    assert(d==&stream_info);
    return &stream_info;
}
static void *decoder_thread(void *unused) {
    (void)unused;
    while(!atomic_load_explicit(&done,memory_order_acquire)) {
        aacp_mic_audio_work();
        if(!aacp_mic_audio_pending())sched_yield();
    }
    return NULL;
}
static void *producer_thread(void *unused) {
    (void)unused;
    for(unsigned i=0;i<TEST_FRAMES;i++) {
        aacp_mic_audio_stats stats;
        do {
            aacp_mic_audio_get_stats(&stats);
            if(stats.au_depth<20)break;
            sched_yield();
        }while(1);
        const uint8_t value=(uint8_t)(1+(i%200));
        aacp_mic_audio_enqueue(&value,1);
    }
    return NULL;
}
static void *consumer_thread(void *unused) {
    (void)unused;
    int16_t samples[64];
    unsigned received=0;
    while(received<TEST_FRAMES*FRAME_SAMPLES) {
        const uint32_t n=aacp_mic_audio_read(samples,64);
        if(!n) {sched_yield();continue;}
        for(uint32_t j=0;j<n;j++) {
            const unsigned frame=(received+j)/FRAME_SAMPLES;
            assert(samples[j]==(int16_t)(1+(frame%200)));
        }
        received+=n;
    }
    atomic_store_explicit(&done,true,memory_order_release);
    return NULL;
}
int main(void) {
    alarm(15); /* fail a real deadlock instead of occupying the CI runner */
    aacp_mic_audio_init();
    assert(aacp_mic_audio_ready());
    aacp_mic_set_capture(true);
    pthread_t producer,decoder,consumer;
    assert(pthread_create(&decoder,NULL,decoder_thread,NULL)==0);
    assert(pthread_create(&producer,NULL,producer_thread,NULL)==0);
    assert(pthread_create(&consumer,NULL,consumer_thread,NULL)==0);
    assert(pthread_join(producer,NULL)==0);
    assert(pthread_join(consumer,NULL)==0);
    assert(pthread_join(decoder,NULL)==0);
    aacp_mic_audio_stats stats;
    aacp_mic_audio_get_stats(&stats);
    assert(stats.au_depth==0 && stats.pcm_depth==0);
    assert(stats.decoded==TEST_FRAMES && stats.decode_errors==0);
    assert(stats.au_overflows==0 && stats.pcm_overflows==0);
    puts("three-thread AACP AU -> decoder -> USB PCM queue test passed");
    return 0;
}
