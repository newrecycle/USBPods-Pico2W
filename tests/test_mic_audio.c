// SPDX-License-Identifier: GPL-3.0-only
// Exercise queue ownership/epoch/error behavior with a deterministic decoder.
// This tests integration mechanics, not AAC fidelity or real FDK allocation.
#include "aacp_mic.h"
#include <aacdecoder_lib.h>
#include <assert.h>
#include <stdio.h>
static int16_t value;
static bool fail;
static CStreamInfo info={48000,1,480};
HANDLE_AACDECODER aacDecoder_Open(int a,int b) { (void)a;(void)b;return &info; }
AAC_DECODER_ERROR aacDecoder_ConfigRaw(HANDLE_AACDECODER d,UCHAR **p,UINT *n) {
 (void)d; assert(*n==4 && p[0][0]==0xf8 && p[0][1]==0xe6); return AAC_DEC_OK;
}
void aacDecoder_Close(HANDLE_AACDECODER d) { (void)d; }
AAC_DECODER_ERROR aacDecoder_Fill(HANDLE_AACDECODER d,UCHAR **p,UINT *n,UINT *valid) {
 (void)d; assert(*n==1); value=p[0][0]; *valid=0; return AAC_DEC_OK;
}
AAC_DECODER_ERROR aacDecoder_DecodeFrame(HANDLE_AACDECODER d,INT_PCM *p,int n,int flags) {
 (void)d; assert(n>=480); if(flags) return AAC_DEC_OK;
 for(int i=0;i<480;i++) p[i]=value;
 return fail?AAC_DEC_UNKNOWN:AAC_DEC_OK;
}
CStreamInfo *aacDecoder_GetStreamInfo(HANDLE_AACDECODER d) { (void)d;return &info; }
static void enqueue(uint8_t v) { aacp_mic_audio_enqueue(&v,1); }
static void drain(void) { int16_t p[64]; while(aacp_mic_audio_read(p,64)) {} }
int main(void) {
 int16_t p[64]; aacp_mic_audio_init(); assert(aacp_mic_audio_ready());
 enqueue(3); aacp_mic_audio_work(); assert(!aacp_mic_audio_read(p,64));
 aacp_mic_set_capture(true); enqueue(7); aacp_mic_audio_work();
 assert(aacp_mic_audio_read(p,64)==64); for(int i=0;i<64;i++) assert(p[i]==7);
 // Close/reopen must discard a partial PCM frame and pending compressed AU.
 enqueue(99); aacp_mic_set_capture(false); aacp_mic_set_capture(true);
 aacp_mic_audio_work(); assert(!aacp_mic_audio_read(p,64));
 enqueue(8); aacp_mic_audio_work(); assert(aacp_mic_audio_read(p,64)==64 && p[0]==8);
 aacp_mic_discontinuity(); assert(aacp_mic_capture() && !aacp_mic_audio_read(p,64));
 // Unexpected format is rejected instead of copying stereo/other rate PCM.
 info.sampleRate=32000; enqueue(10); aacp_mic_audio_work();
 assert(aacp_mic_audio_read(p,64)==64); for(int i=0;i<64;i++) assert(!p[i]); drain();
 info.sampleRate=48000; fail=true; enqueue(10); aacp_mic_audio_work();
 assert(aacp_mic_audio_read(p,64)==64 && !p[0]); drain(); fail=false;
 // Fill both queues past capacity; bounded dropping must preserve valid data.
 for(int i=0;i<100;i++) enqueue(12);
 for(int i=0;i<5;i++) aacp_mic_audio_work();
 while(aacp_mic_audio_read(p,64)) for(int i=0;i<64;i++) assert(p[i]==12);
 puts("microphone queue, generation and decode-error integration tests passed");
}
