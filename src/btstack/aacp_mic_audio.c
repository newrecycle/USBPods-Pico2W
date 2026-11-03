// SPDX-License-Identifier: GPL-3.0-only
// ASC/stream parameters from han-um / librepods; new bounded queues use
// C11 release/acquire publication across BT, main and USB contexts.
#include "aacp_mic.h"
#include <stdatomic.h>
#include <string.h>
#include <stdio.h>
#include "pico/time.h"
static _Atomic bool capture;
static _Atomic uint32_t generation;
void aacp_mic_set_capture(bool on) {
 if (atomic_exchange(&capture,on) != on) atomic_fetch_add(&generation,1);
}
void aacp_mic_discontinuity(void) { atomic_fetch_add(&generation,1); }
bool aacp_mic_capture(void) { return atomic_load(&capture); }
uint32_t aacp_mic_generation(void) { return atomic_load(&generation); }
#ifdef USBPODS_MIC_DECODE
#include <aacdecoder_lib.h>
#include <malloc.h>
#define AU_SLOTS 32u
#define PCM_SLOTS 16u
#define FRAME 480u
static struct { uint32_t epoch; uint8_t len, data[255]; } aus[AU_SLOTS];
static struct { uint32_t epoch; int16_t data[FRAME]; } pcm[PCM_SLOTS];
static _Atomic uint32_t aw, ar, pw, pr;
static _Atomic uint32_t queue_drops;
static uint32_t pcm_offset; /* USB consumer only */
static HANDLE_AACDECODER decoder;
static INT_PCM scratch[960];
static uint32_t decoded, errors, pcm_drops, max_us, last_epoch=UINT32_MAX;
static int last_rate, last_channels, last_frame;
void aacp_mic_audio_init(void) {
 /* Inherited AirPods ASC encodes 48kHz; the measured fork transports
  * 480 decoded samples per 7.5ms and exposes them at 64kHz. Keep these
  * rates distinct until physical timestamp/cadence validation. */
 UCHAR asc[]={0xf8,0xe6,0x30,0}; UCHAR *config[]={asc}; UINT length=sizeof(asc);
 decoder=aacDecoder_Open(TT_MP4_RAW,1);
 if (decoder && aacDecoder_ConfigRaw(decoder,config,&length) != AAC_DEC_OK) {
   aacDecoder_Close(decoder); decoder=NULL;
 }
#ifdef __GLIBC__
 struct mallinfo2 heap=mallinfo2();
#else
 struct mallinfo heap=mallinfo();
#endif
 printf("[mic] heap inuse=%lu free_in_arena=%lu (excludes unclaimed heap)\n",
        (unsigned long)heap.uordblks,(unsigned long)heap.fordblks);
 printf("[mic] AAC-ELD decoder %s (48kHz ASC, 64kHz USB clock, experimental)\n",decoder?"ready":"allocation/configuration FAILED");
}
bool aacp_mic_audio_ready(void) { return decoder != NULL; }
void aacp_mic_audio_enqueue(const uint8_t *au, uint8_t len) {
 if (!aacp_mic_capture() || !decoder) return;
 uint32_t w=atomic_load_explicit(&aw,memory_order_relaxed);
 if (w-atomic_load_explicit(&ar,memory_order_acquire) == AU_SLOTS) {
   atomic_fetch_add(&queue_drops,1); return;
 }
 aus[w%AU_SLOTS].epoch=aacp_mic_generation(); aus[w%AU_SLOTS].len=len;
 memcpy(aus[w%AU_SLOTS].data,au,len);
 atomic_store_explicit(&aw,w+1,memory_order_release);
}
void aacp_mic_audio_work(void) {
 static uint32_t report_ms;
 uint32_t now=to_ms_since_boot(get_absolute_time());
 if (now-report_ms>=2000 && aacp_mic_capture()) { report_ms=now; aacp_mic_audio_report(); }
 if (!decoder) return;
 for (unsigned budget=0; budget<8; budget++) {
   uint32_t r=atomic_load_explicit(&ar,memory_order_relaxed);
   if (r == atomic_load_explicit(&aw,memory_order_acquire)) break;
   uint32_t epoch=aus[r%AU_SLOTS].epoch;
   if (epoch != aacp_mic_generation() || !aacp_mic_capture()) {
     atomic_store_explicit(&ar,r+1,memory_order_release); continue;
   }
   /* Decoder state belongs to main only; reset at a new USB session. */
   if (last_epoch != epoch) {
     aacDecoder_DecodeFrame(decoder,scratch,960,AACDEC_CLRHIST|AACDEC_INTR);
     last_epoch=epoch;
   }
   UCHAR *input[]={aus[r%AU_SLOTS].data}; UINT size=aus[r%AU_SLOTS].len, valid=size;
   AAC_DECODER_ERROR err=aacDecoder_Fill(decoder,input,&size,&valid);
   uint32_t t=time_us_32();
   if (err == AAC_DEC_OK && !valid) err=aacDecoder_DecodeFrame(decoder,scratch,960,0);
   else err=AAC_DEC_UNKNOWN;
   uint32_t dt=time_us_32()-t; if (dt>max_us) max_us=dt;
   atomic_store_explicit(&ar,r+1,memory_order_release);
   CStreamInfo *info=aacDecoder_GetStreamInfo(decoder);
   if (info) { last_rate=info->sampleRate; last_channels=info->numChannels; last_frame=info->frameSize; }
   bool ok=err==AAC_DEC_OK && info && info->sampleRate==48000 &&
           info->numChannels==1 && info->frameSize==FRAME;
   if (ok) decoded++; else errors++;
   if (epoch != aacp_mic_generation() || !aacp_mic_capture()) continue;
   uint32_t w=atomic_load_explicit(&pw,memory_order_relaxed);
   if (w-atomic_load_explicit(&pr,memory_order_acquire)==PCM_SLOTS) { pcm_drops++; continue; }
   pcm[w%PCM_SLOTS].epoch=epoch;
   if (ok) memcpy(pcm[w%PCM_SLOTS].data,scratch,sizeof(pcm[0].data));
   else memset(pcm[w%PCM_SLOTS].data,0,sizeof(pcm[0].data));
   atomic_store_explicit(&pw,w+1,memory_order_release);
 }
}
uint32_t aacp_mic_audio_read(int16_t *dst,uint32_t count) {
 uint32_t done=0, epoch=aacp_mic_generation();
 if (!aacp_mic_capture()) return 0;
 /* At most PCM_SLOTS stale frames are discarded; never wait in USB IRQ. */
 for (unsigned budget=0; done<count && budget<=PCM_SLOTS; budget++) {
   uint32_t r=atomic_load_explicit(&pr,memory_order_relaxed);
   if (r==atomic_load_explicit(&pw,memory_order_acquire)) break;
   if (pcm[r%PCM_SLOTS].epoch != epoch) {
     pcm_offset=0; atomic_store_explicit(&pr,r+1,memory_order_release); continue;
   }
   uint32_t n=FRAME-pcm_offset; if (n>count-done) n=count-done;
   memcpy(dst+done,pcm[r%PCM_SLOTS].data+pcm_offset,n*sizeof(*dst));
   done+=n; pcm_offset+=n;
   if (pcm_offset==FRAME) { pcm_offset=0; atomic_store_explicit(&pr,r+1,memory_order_release); }
 }
 return done;
}
void aacp_mic_audio_report(void) {
 printf("[mic-dec] ok=%lu errors=%lu au_drop=%lu pcm_drop=%lu max_us=%lu asc_format=%dHz/%dch/%d\n",
 (unsigned long)decoded,(unsigned long)errors,(unsigned long)atomic_load(&queue_drops),
 (unsigned long)pcm_drops,(unsigned long)max_us,last_rate,last_channels,last_frame);
}
#else
void aacp_mic_audio_init(void) { printf("[mic] transport diagnostics: USB microphone sends silence\n"); }
bool aacp_mic_audio_ready(void) { return true; }
void aacp_mic_audio_enqueue(const uint8_t *au,uint8_t len) { (void)au; (void)len; }
void aacp_mic_audio_work(void) {}
uint32_t aacp_mic_audio_read(int16_t *dst,uint32_t count) { (void)dst; (void)count; return 0; }
void aacp_mic_audio_report(void) {}
#endif
