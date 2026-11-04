// SPDX-License-Identifier: GPL-3.0-only
// Exercise queue ownership/epoch/error behavior with a deterministic decoder.
// This tests integration mechanics, not AAC fidelity or real FDK allocation.
#include "aacp_mic.h"
#include <aacdecoder_lib.h>
#include <assert.h>
#include <stdio.h>
uint32_t mock_time_us;
static int16_t value;
static bool fail,flush_fail,clear_fail,fill_fail,supplied;
static unsigned flush_calls,clear_calls;
static CStreamInfo info={48000,1,480};
HANDLE_AACDECODER aacDecoder_Open(int a,int b) { (void)a;(void)b;return &info; }
AAC_DECODER_ERROR aacDecoder_ConfigRaw(HANDLE_AACDECODER d,UCHAR **p,UINT *n) {
 (void)d; assert(*n==4 && p[0][0]==0xf8 && p[0][1]==0xe6); return AAC_DEC_OK;
}
void aacDecoder_Close(HANDLE_AACDECODER d) { (void)d; }
AAC_DECODER_ERROR aacDecoder_SetParam(HANDLE_AACDECODER d,int param,int v) {
 (void)d;assert(param==AAC_TPDEC_CLEAR_BUFFER && v==1);clear_calls++;
 if(clear_fail){clear_fail=false;return AAC_DEC_UNKNOWN;}
 supplied=false;return AAC_DEC_OK;
}
AAC_DECODER_ERROR aacDecoder_Fill(HANDLE_AACDECODER d,UCHAR **p,UINT *n,UINT *valid) {
 (void)d; assert(*n==1);
 if(fill_fail){fill_fail=false;return AAC_DEC_UNKNOWN;}
 value=p[0][0];supplied=true;*valid=0;return AAC_DEC_OK;
}
AAC_DECODER_ERROR aacDecoder_DecodeFrame(HANDLE_AACDECODER d,INT_PCM *p,int n,int flags) {
 (void)d; assert(n>=480 && supplied);supplied=false;
 if(flags) {
  assert(flags==(AACDEC_CLRHIST|AACDEC_INTR));
  flush_calls++;
  if(flush_fail){flush_fail=false;return AAC_DEC_UNKNOWN;}
 }
 mock_time_us+=325; /* simulated Fill+Decode duration */
 for(int i=0;i<480;i++) p[i]=value;
 return fail?AAC_DEC_UNKNOWN:AAC_DEC_OK;
}
CStreamInfo *aacDecoder_GetStreamInfo(HANDLE_AACDECODER d) { (void)d;return &info; }
static void enqueue(uint8_t v) { aacp_mic_audio_enqueue(&v,1); }
static void drain(void) { int16_t p[64]; while(aacp_mic_audio_read(p,64)) {} }
int main(void) {
 aacp_mic_audio_stats s;
 // Raw AACP timestamps are not assumed to be in samples or microseconds.
 // A 480-tick step and 7500-us arrival period are independent observations.
 for (uint32_t i=0;i<20;i++) aacp_mic_audio_note_au(i*480u,i*7500u);
 aacp_mic_audio_get_stats(&s);
 assert(s.au_observed==20 && s.arrival_intervals==19);
 assert(s.arrival_7500us==19 && s.arrival_10000us==0);
 assert(s.timestamp_step_reference==480 && s.timestamp_step_changes==0);
 // One missing timestamp interval, rapid burst, duplicate, backtrack.
 aacp_mic_audio_note_au(21u*480u,20u*7500u);
 aacp_mic_audio_note_au(22u*480u,20u*7500u+20);
 aacp_mic_audio_note_au(22u*480u,20u*7500u+40);
 aacp_mic_audio_note_au(22u*480u-1,20u*7500u+60);
 aacp_mic_audio_get_stats(&s);
 assert(s.timestamp_gap_candidates==1 && s.timestamp_step_changes>=1);
 assert(s.arrival_bursts==3 && s.timestamp_duplicates==1);
 assert(s.timestamp_backwards==1);
 uint32_t previous_generation=s.generation;
 aacp_mic_discontinuity();
 aacp_mic_audio_note_au(7,200000);
 aacp_mic_audio_note_au(487,207500);
 aacp_mic_audio_get_stats(&s);
 assert(s.generation==previous_generation+1);
 assert(s.timestamp_backwards==1); // restart is not a wrap/backtrack
 assert(s.timestamp_step_reference==480);
 int16_t p[64]; aacp_mic_audio_init(); assert(aacp_mic_audio_ready());
 enqueue(3); aacp_mic_audio_work(); assert(!aacp_mic_audio_read(p,64));
 aacp_mic_set_capture(true); enqueue(7); aacp_mic_audio_work();
 assert(aacp_mic_audio_read(p,64)==64); for(int i=0;i<64;i++) assert(p[i]==7);
 // Close/reopen must discard a partial PCM frame and pending compressed AU.
 enqueue(99); aacp_mic_set_capture(false); aacp_mic_set_capture(true);
 aacp_mic_audio_work(); assert(!aacp_mic_audio_read(p,64));
 aacp_mic_audio_get_stats(&s);
 assert(s.au_stale>=1 && s.pcm_stale>=1);
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
 aacp_mic_audio_get_stats(&s);
 assert(s.au_high_water==32 && s.au_overflows>=68);
 assert(s.pcm_high_water==16 && s.pcm_overflows>=16);
 assert(s.decode_max_us>=325 && s.decode_last_us>=325);
 assert(s.decoded_rate==48000 && s.decoded_channels==1 && s.decoded_frame_samples==480);
 while(aacp_mic_audio_read(p,64)) for(int i=0;i<64;i++) assert(p[i]==12);
 // A full queue of stale AUs must be discarded in one bounded work call.
 aacp_mic_discontinuity();
 for (unsigned i=0;i<32;i++) enqueue(45);
 aacp_mic_discontinuity();
 aacp_mic_audio_work();
 aacp_mic_audio_get_stats(&s);
 assert(s.au_depth==0 && s.au_stale>=33);
 assert(!aacp_mic_audio_read(p,64));
 enqueue(46); aacp_mic_audio_work();
 assert(aacp_mic_audio_read(p,64)==64 && p[0]==46);
 // Reset flags apply to supplied data, not an empty extra DecodeFrame call.
 // A failed first decode publishes silence, and the next AU retries reset.
 aacp_mic_discontinuity();flush_calls=0;flush_fail=true;
 enqueue(47);aacp_mic_audio_work();
 assert(flush_calls==1 && aacp_mic_audio_read(p,64)==64 && !p[0]);
 drain(); /* leave the failed-flush generation's PCM before the retry AU */
 enqueue(48);aacp_mic_audio_work();
 assert(flush_calls==2 && aacp_mic_audio_read(p,64)==64 && p[0]==48);
 drain();enqueue(49);aacp_mic_audio_work();
 assert(flush_calls==2 && aacp_mic_audio_read(p,64)==64 && p[0]==49);drain();
 // Failed transport reset or Fill cannot mark history cleared or emit old PCM.
 aacp_mic_discontinuity();unsigned clears_before=clear_calls;clear_fail=true;
 enqueue(60);aacp_mic_audio_work();assert(clear_calls==clears_before+1 && flush_calls==2);
 assert(aacp_mic_audio_read(p,64)==64 && !p[0]);drain();
 fill_fail=true;enqueue(61);aacp_mic_audio_work();
 assert(clear_calls==clears_before+2 && flush_calls==2);
 assert(aacp_mic_audio_read(p,64)==64 && !p[0]);drain();
 enqueue(62);aacp_mic_audio_work();
 assert(clear_calls==clears_before+3 && flush_calls==3);
 assert(aacp_mic_audio_read(p,64)==64 && p[0]==62);drain();
 // Decode and PCM high-water never increase past fixed queue capacities.
 aacp_mic_audio_get_stats(&s);
 assert(s.au_high_water<=32 && s.pcm_high_water<=16);
 // Packet priming must discard a FULL stale PCM ring, otherwise no fresh
 // frame can enter and startup buffering would wait forever.
 drain();
 for(unsigned i=0;i<16;i++)enqueue(50);
 aacp_mic_audio_work();aacp_mic_audio_work();
 aacp_mic_discontinuity();assert(!aacp_mic_audio_packet_samples());
 for(unsigned i=0;i<6;i++)enqueue(51);
 aacp_mic_audio_work();assert(aacp_mic_audio_packet_samples()==64);
 assert(aacp_mic_audio_read(p,64)==64 && p[0]==51);
 // Four-AU batches have a 64 kHz PCM timeline despite the 48 kHz ASC.
 aacp_mic_discontinuity();
 for(unsigned group=0;group<36;group++)for(unsigned unit=0;unit<4;unit++)
  aacp_mic_audio_note_au(group*4+unit,group*30000);
 aacp_mic_audio_get_stats(&s);assert(s.clock_windows && s.measured_sample_rate==64000);
 puts("microphone cadence, timestamp, burst, overflow and reconnect tests passed");
}

