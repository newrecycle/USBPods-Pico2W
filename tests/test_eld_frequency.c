// SPDX-License-Identifier: GPL-3.0-only
// Real FDK bass/stereo transfer check. Synthetic PCM, no acoustic claim.
#include "eld_encoder.h"
#include <aacdecoder_lib.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#define PI 3.14159265358979323846
static double measure(eld_profile *p,unsigned freq) {
 HANDLE_AACENCODER enc=NULL;AACENC_InfoStruct ei;
 assert(eld_encoder_open(&enc,&ei,p)==AACENC_OK);
 HANDLE_AACDECODER dec=aacDecoder_Open(TT_MP4_RAW,1);assert(dec);
 UCHAR *conf[]={ei.confBuf};UINT cn=ei.confSize;
 assert(aacDecoder_ConfigRaw(dec,conf,&cn)==AAC_DEC_OK);
 double left=0,right=0;unsigned samples=0;
 for(unsigned f=0;f<120;f++) {
  INT_PCM input[960],pcm[1920];UCHAR bytes[2048];
  for(unsigned i=0;i<480;i++) {
   input[2*i]=(INT_PCM)(12000*sin(2*PI*freq*(f*480+i)/48000));
   input[2*i+1]=0;
  }
  void *ib[]={input},*ob[]={bytes};INT iid=IN_AUDIO_DATA,oid=OUT_BITSTREAM_DATA;
  INT is=sizeof input,os=sizeof bytes,ie=sizeof(INT_PCM),oe=1;
  AACENC_BufDesc in={1,ib,&iid,&is,&ie},out={1,ob,&oid,&os,&oe};
  AACENC_InArgs args={960,0};AACENC_OutArgs result={0};
  assert(aacEncEncode(enc,&in,&out,&args,&result)==AACENC_OK);
  if(!result.numOutBytes)continue;
  UCHAR *data[]={bytes};UINT n=result.numOutBytes,valid=n;
  assert(aacDecoder_Fill(dec,data,&n,&valid)==AAC_DEC_OK && !valid);
  assert(aacDecoder_DecodeFrame(dec,pcm,1920,0)==AAC_DEC_OK);
  CStreamInfo *ci=aacDecoder_GetStreamInfo(dec);
  assert(ci && ci->frameSize==480 && ci->numChannels==2 && ci->sampleRate==48000);
  if(f>=32)for(unsigned i=0;i<480;i++) {
   left+=(double)pcm[2*i]*pcm[2*i];right+=(double)pcm[2*i+1]*pcm[2*i+1];samples++;
  }
 }
 assert(samples>40000 && left>0);
 double rms=sqrt(left/samples),leak=sqrt(right/samples);
 printf("ELD response rate=%u vbr=%u sbr=%u tone=%uHz gain=%.3fdB right_leak=%.6f\n",
  p->bitrate,p->vbr,p->sbr,freq,20*log10(rms/(12000/sqrt(2))),leak/(rms+1));
 assert(leak/(rms+1)<0.01); // Wrong-channel energy at least 40 dB lower.
 aacDecoder_Close(dec);aacEncClose(&enc);return rms;
}
int main(void) {
 const unsigned freqs[]={40,80,160,1000,6000};
 for(unsigned mode=0;mode<4;mode++) {
  eld_profile p=eld_profile_select(mode==0?1:mode==3?3:2,false,1,false,false,5,1);
  if(mode==2)p.vbr=p.sbr=0; // Exact clamped-320 profile in the physical capture.
  double levels[5];
  for(unsigned f=0;f<5;f++)levels[f]=measure(&p,freqs[f]);
  for(unsigned f=0;f<3;f++) {
   double db=20*log10(levels[f]/levels[3]);
   assert(fabs(db)<3.0); // Bass cannot disappear relative to 1 kHz reference.
  }
 }
 puts("Real FDK bass response and stereo isolation passed");
}
