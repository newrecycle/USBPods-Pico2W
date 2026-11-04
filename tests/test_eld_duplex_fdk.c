// SPDX-License-Identifier: GPL-3.0-only
// Exact playback configuration + actual mic queues/decoder; synthetic data.
#include "eld_encoder.h"
#include "aacp_mic.h"
#include "../src/resamp44.h"
#include <aacdecoder_lib.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef USBPODS_MIC_PARALLEL_HOST
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
static _Atomic bool parallel_mic_run;
static pthread_t parallel_mic_thread;
static void *parallel_mic_decoder(void *unused) {
 (void)unused;
 while(atomic_load_explicit(&parallel_mic_run,memory_order_acquire)){
  aacp_mic_audio_work();
  if(!aacp_mic_audio_pending())sched_yield();
 }
 return NULL;
}
static void parallel_mic_read(INT_PCM *dst, unsigned count) {
 unsigned offset=0;
 for(unsigned polls=0;offset<count&&polls<1000000;polls++) {
  offset+=aacp_mic_audio_read(dst+offset,count-offset);
  if(offset<count)sched_yield();
 }
 assert(offset==count);
}
#endif
#ifdef USBPODS_ALLOC_AUDIT
#include "fdk_alloc_tracker.h"
#else
#define fdk_alloc_begin() ((void)0)
#define fdk_alloc_end() ((void)0)
#define fdk_alloc_report() ((void)0)
#endif
#ifdef __GLIBC__
#include <malloc.h>
#endif
static UCHAR mic_au[32][255];static unsigned mic_len[32],mic_count;
static void set(HANDLE_AACENCODER h,AACENC_PARAM k,UINT v){assert(aacEncoder_SetParam(h,k,v)==AACENC_OK);}
static void mic_fixture(void) {
 HANDLE_AACENCODER h=NULL;assert(aacEncOpen(&h,0x03,1)==AACENC_OK);
 set(h,AACENC_AOT,39);set(h,AACENC_SAMPLERATE,48000);set(h,AACENC_CHANNELMODE,MODE_1);
 set(h,AACENC_GRANULE_LENGTH,480);set(h,AACENC_BITRATE,64000);set(h,AACENC_SBR_MODE,0);
 set(h,AACENC_TRANSMUX,TT_MP4_RAW);assert(aacEncEncode(h,NULL,NULL,NULL,NULL)==AACENC_OK);
 for(unsigned f=0;f<32;f++){
   INT_PCM pcm[480];UCHAR data[1024];for(unsigned i=0;i<480;i++)pcm[i]=(INT_PCM)(12000*sin(2*3.141592653589793*1000*(f*480+i)/48000));
   void*ib[]={pcm},*ob[]={data};INT iid=IN_AUDIO_DATA,oid=OUT_BITSTREAM_DATA,is=sizeof(pcm),os=sizeof(data),ie=2,oe=1;
   AACENC_BufDesc in={1,ib,&iid,&is,&ie},out={1,ob,&oid,&os,&oe};AACENC_InArgs args={480,0};AACENC_OutArgs result={0};
   assert(aacEncEncode(h,&in,&out,&args,&result)==AACENC_OK);
   if(result.numOutBytes){assert(result.numOutBytes<=255);memcpy(mic_au[mic_count],data,result.numOutBytes);mic_len[mic_count++]=result.numOutBytes;}
 }
 assert(mic_count>=28);aacEncClose(&h);
}
static void mic_burst_check(void) {
 HANDLE_AACDECODER fresh=aacDecoder_Open(TT_MP4_RAW,1);assert(fresh);
 UCHAR asc[]={0xf8,0xe6,0x30,0},*conf[]={asc};UINT size=sizeof asc;
 assert(aacDecoder_ConfigRaw(fresh,conf,&size)==AAC_DEC_OK);
 INT_PCM expected[32][480],scratch[960],actual[480];
 for(unsigned i=0;i<mic_count;i++) {
   UCHAR *data[]={mic_au[i]};UINT n=mic_len[i],valid=n;
   assert(aacDecoder_Fill(fresh,data,&n,&valid)==AAC_DEC_OK && !valid);
   assert(aacDecoder_DecodeFrame(fresh,scratch,960,0)==AAC_DEC_OK);
   memcpy(expected[i],scratch,sizeof expected[i]);
 }
 aacDecoder_Close(fresh);aacp_mic_discontinuity();
 assert(!aacp_mic_audio_read(actual,480));aacp_mic_audio_work();
 for(unsigned i=0;i<mic_count;i++)aacp_mic_audio_enqueue(mic_au[i],(uint8_t)mic_len[i]);
 for(unsigned i=0;i<5;i++){fdk_alloc_begin();aacp_mic_audio_work();fdk_alloc_end();}
 aacp_mic_audio_stats s;aacp_mic_audio_get_stats(&s);
 assert(s.pcm_depth==16 && s.au_depth==mic_count-16 && !s.pcm_overflows);
 assert(!aacp_mic_audio_pending());
 for(unsigned i=0;i<mic_count;i++) {
   assert(aacp_mic_audio_read(actual,480)==480 && !memcmp(expected[i],actual,sizeof actual));
   fdk_alloc_begin();aacp_mic_audio_work();fdk_alloc_end();
 }
 aacp_mic_audio_get_stats(&s);assert(!s.au_depth && !s.pcm_depth && !s.pcm_overflows);
 puts("Real FDK mic burst: 32 queued AUs retained across full PCM backpressure, in order");
}
static void mic_restart_check(void) {
 // A fresh reference decoder must match every generation of the production
 // decoder exactly; otherwise old overlap/concealment history has leaked.
 for(unsigned cycle=0;cycle<12;cycle++) {
   if(cycle&1)aacp_mic_discontinuity(); // AACP reconnect/wire transition
   else {aacp_mic_set_capture(false);aacp_mic_set_capture(true);} // USB STOP/START
   HANDLE_AACDECODER fresh=aacDecoder_Open(TT_MP4_RAW,1);assert(fresh);
   UCHAR asc[]={0xf8,0xe6,0x30,0},*conf[]={asc};UINT size=sizeof asc;
   assert(aacDecoder_ConfigRaw(fresh,conf,&size)==AAC_DEC_OK);
   INT_PCM expected[32][480];
   // Generate reference PCM before measuring production allocations, so the
   // extra host-only decoder is excluded from the target heap estimate.
   for(unsigned frame=0;frame<mic_count;frame++) {
     unsigned m=(frame+cycle*3)%mic_count;
     INT_PCM scratch[960];UCHAR *au[]={mic_au[m]};
     UINT length=mic_len[m],valid=length;
     assert(aacDecoder_Fill(fresh,au,&length,&valid)==AAC_DEC_OK && !valid);
     assert(aacDecoder_DecodeFrame(fresh,scratch,960,0)==AAC_DEC_OK);
     memcpy(expected[frame],scratch,sizeof expected[frame]);
   }
   aacDecoder_Close(fresh);
   for(unsigned frame=0;frame<mic_count;frame++) {
     unsigned m=(frame+cycle*3)%mic_count;INT_PCM actual[480];
     aacp_mic_audio_enqueue(mic_au[m],(uint8_t)mic_len[m]);
     fdk_alloc_begin();aacp_mic_audio_work();fdk_alloc_end();
     assert(aacp_mic_audio_read(actual,480)==480);
     assert(!memcmp(expected[frame],actual,sizeof actual));
   }
   // Leave PCM and a queued AU behind so the next epoch must discard both.
   unsigned m=(cycle+9)%mic_count;
   aacp_mic_audio_enqueue(mic_au[m],(uint8_t)mic_len[m]);
   fdk_alloc_begin();aacp_mic_audio_work();fdk_alloc_end();
   aacp_mic_audio_enqueue(mic_au[m],(uint8_t)mic_len[m]);
 }
 aacp_mic_audio_stats s;aacp_mic_audio_get_stats(&s);
 assert(!s.decode_errors && s.au_stale>=11 && s.pcm_stale>=11);
 puts("Real FDK mic reset: 12 capture/reconnect generations match fresh decoder PCM");
}
int main(void){
 setvbuf(stdout,NULL,_IONBF,0);
 mic_fixture();aacp_mic_audio_init();assert(aacp_mic_audio_ready());aacp_mic_set_capture(true);
#ifdef USBPODS_MIC_PARALLEL_HOST
 atomic_store_explicit(&parallel_mic_run,true,memory_order_release);
 assert(pthread_create(&parallel_mic_thread,NULL,parallel_mic_decoder,NULL)==0);
#endif
 uint32_t generation=aacp_mic_generation();HANDLE_AACENCODER encoder=NULL;AACENC_InfoStruct ei;
 const struct {uint8_t rate,game,level,r44,relay;} modes[]={
   {1,0,1,0,0},{2,0,1,0,0},{3,0,1,0,0},{3,1,1,0,0},
   {3,1,2,0,0},{2,0,1,1,0},{2,0,1,0,1},{2,0,1,0,0}
 };
 unsigned all_frames=0;int mic_peak=0;uint32_t noise=1;
 for(unsigned transition=0;transition<3*sizeof(modes)/sizeof(modes[0]);transition++){
   unsigned mode=transition%(sizeof(modes)/sizeof(modes[0]));
   eld_profile p=eld_profile_select(modes[mode].rate,modes[mode].game,modes[mode].level,modes[mode].r44,modes[mode].relay,5,1);
   fdk_alloc_begin();
   assert(eld_encoder_open(&encoder,&ei,&p)==AACENC_OK);
   assert(aacp_mic_audio_ready() && aacp_mic_generation()==generation);
   fdk_alloc_end(); /* Reference playback decoder below is host-only. */
#ifdef __GLIBC__
   struct mallinfo2 heap=mallinfo2();
   printf("ELD host heap mic+encoder profile %u: inuse=%zu free_arena=%zu (not target RAM measurement)\n",mode,(size_t)heap.uordblks,(size_t)heap.fordblks);
#endif
   HANDLE_AACDECODER decoder=aacDecoder_Open(TT_MP4_RAW,1);assert(decoder);
   UCHAR*conf[]={ei.confBuf};UINT size=ei.confSize;assert(aacDecoder_ConfigRaw(decoder,conf,&size)==AAC_DEC_OK);
   resamp44_t rs;resamp44_reset_st(&rs);unsigned frames=0,max_au=0;
   for(unsigned frame=0;frame<128;frame++){
     INT_PCM input[960],resampled[960],decoded[1920],mic[480];UCHAR bytes[2048];
#ifdef USBPODS_MIC_PARALLEL_HOST
     /* Producer queues a real mic AU before playback work. This forces the
        independent FDK microphone decoder to run while FDK playback encodes. */
     unsigned m=frame%mic_count;
     aacp_mic_audio_enqueue(mic_au[m],(uint8_t)mic_len[m]);
#endif
     for(unsigned i=0;i<p.input_frames;i++){
       double t=(frame*p.input_frames+i)/(double)p.input_rate;
       switch((frame/16)%4) {
       case 0:
         input[2*i]=(INT_PCM)(10000*sin(2*3.141592653589793*440*t));
         input[2*i+1]=(INT_PCM)(9000*sin(2*3.141592653589793*880*t));break;
       case 1:
         noise=noise*1664525u+1013904223u;input[2*i]=(INT_PCM)(noise>>16);
         noise=noise*1664525u+1013904223u;input[2*i+1]=(INT_PCM)(noise>>16);break;
       case 2:input[2*i]=input[2*i+1]=0;break;
       default:
         input[2*i]=i==0?30000:0;input[2*i+1]=i==1?-30000:0;break;
       }
     }
     void*pcm=input;
     if(p.input_rate==44100){assert(resamp44_process_st(&rs,input,441,resampled,480)==480);pcm=resampled;}
     void*ib[]={pcm},*ob[]={bytes};INT iid=IN_AUDIO_DATA,oid=OUT_BITSTREAM_DATA,is=960*sizeof(INT_PCM),os=sizeof(bytes),ie=sizeof(INT_PCM),oe=1;
     AACENC_BufDesc in={1,ib,&iid,&is,&ie},out={1,ob,&oid,&os,&oe};AACENC_InArgs args={960,0};AACENC_OutArgs result={0};
     assert(aacEncEncode(encoder,&in,&out,&args,&result)==AACENC_OK);
     if(result.numOutBytes){
       unsigned n=(unsigned)result.numOutBytes;
       if(n>p.bitrate/800+64)fprintf(stderr,"ELD budget violation: mode=%u frame=%u bytes=%u budget=%u rate=%u vbr=%u sbr=%u\n",mode,frame,n,p.bitrate/800+64,p.bitrate,p.vbr,p.sbr);
       assert(n<=p.bitrate/800+64);if(n>max_au)max_au=n;
       UCHAR*b[]={bytes};UINT length=n,valid=n;assert(aacDecoder_Fill(decoder,b,&length,&valid)==AAC_DEC_OK&&!valid);
       assert(aacDecoder_DecodeFrame(decoder,decoded,1920,0)==AAC_DEC_OK);
       CStreamInfo *info=aacDecoder_GetStreamInfo(decoder);assert(info&&info->frameSize==480&&info->numChannels==2&&info->sampleRate==48000);frames++;
     }
#ifdef USBPODS_MIC_PARALLEL_HOST
     parallel_mic_read(mic,480);
#else
     unsigned m=frame%mic_count;aacp_mic_audio_enqueue(mic_au[m],(uint8_t)mic_len[m]);aacp_mic_audio_work();
     assert(aacp_mic_audio_read(mic,480)==480);
#endif
     for(unsigned i=0;i<480;i++)if(abs(mic[i])>mic_peak)mic_peak=abs(mic[i]);
     assert(aacp_mic_generation()==generation);
   }
   assert(frames>=124);all_frames+=frames;aacDecoder_Close(decoder);
   fdk_alloc_begin();fdk_alloc_end(); /* Include any lazy mic allocation. */
   printf("ELD duplex transition %u: rate=%u vbr=%u sbr=%u slots=%u input=%u frames=%u max_au=%u mic_generation=%u\n",transition,p.bitrate,p.vbr,p.sbr,p.slots,p.input_rate,frames,max_au,generation);
 }
#ifdef USBPODS_MIC_PARALLEL_HOST
 atomic_store_explicit(&parallel_mic_run,false,memory_order_release);
 assert(pthread_join(parallel_mic_thread,NULL)==0);
 puts("Real FDK parallel: microphone decode concurrent with stereo ELD encode and 24 profile rebuilds");
#endif
 assert(mic_peak>1000);mic_restart_check();mic_burst_check();fdk_alloc_report();aacEncClose(&encoder);aacp_mic_set_capture(false);
 printf("ELD rate/game transitions with active mic queue: %u playback frames, mic peak=%d\n",all_frames,mic_peak);
}
