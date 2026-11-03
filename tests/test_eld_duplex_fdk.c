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
int main(void){
 mic_fixture();aacp_mic_audio_init();assert(aacp_mic_audio_ready());aacp_mic_set_capture(true);
 uint32_t generation=aacp_mic_generation();HANDLE_AACENCODER encoder=NULL;AACENC_InfoStruct ei;
 const struct {uint8_t rate,game,level,r44,relay;} modes[]={
   {1,0,1,0,0},{2,0,1,0,0},{3,0,1,0,0},{3,1,1,0,0},
   {3,1,2,0,0},{2,0,1,1,0},{2,0,1,0,1},{2,0,1,0,0}
 };
 unsigned all_frames=0;int mic_peak=0;
 for(unsigned mode=0;mode<sizeof(modes)/sizeof(modes[0]);mode++){
   eld_profile p=eld_profile_select(modes[mode].rate,modes[mode].game,modes[mode].level,modes[mode].r44,modes[mode].relay,5,1);
   assert(eld_encoder_open(&encoder,&ei,&p)==AACENC_OK);
   assert(aacp_mic_audio_ready() && aacp_mic_generation()==generation);
   HANDLE_AACDECODER decoder=aacDecoder_Open(TT_MP4_RAW,1);assert(decoder);
   UCHAR*conf[]={ei.confBuf};UINT size=ei.confSize;assert(aacDecoder_ConfigRaw(decoder,conf,&size)==AAC_DEC_OK);
   resamp44_t rs;resamp44_reset_st(&rs);unsigned frames=0,max_au=0;
   for(unsigned frame=0;frame<64;frame++){
     INT_PCM input[960],resampled[960],decoded[1920],mic[480];UCHAR bytes[2048];
     for(unsigned i=0;i<p.input_frames;i++){
       double t=(frame*p.input_frames+i)/(double)p.input_rate;
       input[2*i]=(INT_PCM)(10000*sin(2*3.141592653589793*440*t));
       input[2*i+1]=(INT_PCM)(9000*sin(2*3.141592653589793*880*t));
     }
     void*pcm=input;
     if(p.input_rate==44100){assert(resamp44_process_st(&rs,input,441,resampled,480)==480);pcm=resampled;}
     void*ib[]={pcm},*ob[]={bytes};INT iid=IN_AUDIO_DATA,oid=OUT_BITSTREAM_DATA,is=960*sizeof(INT_PCM),os=sizeof(bytes),ie=sizeof(INT_PCM),oe=1;
     AACENC_BufDesc in={1,ib,&iid,&is,&ie},out={1,ob,&oid,&os,&oe};AACENC_InArgs args={960,0};AACENC_OutArgs result={0};
     assert(aacEncEncode(encoder,&in,&out,&args,&result)==AACENC_OK);
     if(result.numOutBytes){
       unsigned n=(unsigned)result.numOutBytes;assert(n<=p.bitrate/800+64);if(n>max_au)max_au=n;
       UCHAR*b[]={bytes};UINT length=n,valid=n;assert(aacDecoder_Fill(decoder,b,&length,&valid)==AAC_DEC_OK&&!valid);
       assert(aacDecoder_DecodeFrame(decoder,decoded,1920,0)==AAC_DEC_OK);
       CStreamInfo *info=aacDecoder_GetStreamInfo(decoder);assert(info&&info->frameSize==480&&info->numChannels==2&&info->sampleRate==48000);frames++;
     }
     unsigned m=frame%mic_count;aacp_mic_audio_enqueue(mic_au[m],(uint8_t)mic_len[m]);aacp_mic_audio_work();
     assert(aacp_mic_audio_read(mic,480)==480);
     for(unsigned i=0;i<480;i++)if(abs(mic[i])>mic_peak)mic_peak=abs(mic[i]);
     assert(aacp_mic_generation()==generation);
   }
   assert(frames>=60);all_frames+=frames;aacDecoder_Close(decoder);
   printf("ELD duplex profile %u: rate=%u vbr=%u sbr=%u slots=%u input=%u frames=%u max_au=%u mic_generation=%u\n",mode,p.bitrate,p.vbr,p.sbr,p.slots,p.input_rate,frames,max_au,generation);
 }
 assert(mic_peak>1000);aacEncClose(&encoder);aacp_mic_set_capture(false);
 printf("ELD rate/game transitions with active mic queue: %u playback frames, mic peak=%d\n",all_frames,mic_peak);
}
