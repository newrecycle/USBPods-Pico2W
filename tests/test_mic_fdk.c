// SPDX-License-Identifier: GPL-3.0-only
// Synthetic codec interoperability check; this is not an AirPods capture fixture.
#include <aacenc_lib.h>
#include <aacdecoder_lib.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void param(HANDLE_AACENCODER h,AACENC_PARAM p,UINT v) {
 assert(aacEncoder_SetParam(h,p,v)==AACENC_OK);
}
static void lc_roundtrip(UINT rate) {
 HANDLE_AACENCODER enc=NULL;
 assert(aacEncOpen(&enc,0x03,2)==AACENC_OK);
 param(enc,AACENC_AOT,2);param(enc,AACENC_SAMPLERATE,rate);
 param(enc,AACENC_CHANNELMODE,MODE_2);param(enc,AACENC_BITRATE,128000);
 param(enc,AACENC_TRANSMUX,TT_MP4_LATM_MCP1);param(enc,AACENC_HEADER_PERIOD,1);
 assert(aacEncEncode(enc,NULL,NULL,NULL,NULL)==AACENC_OK);
 AACENC_InfoStruct ei;assert(aacEncInfo(enc,&ei)==AACENC_OK && ei.frameLength==1024);
 HANDLE_AACDECODER dec=aacDecoder_Open(TT_MP4_LATM_MCP1,1);assert(dec);
 unsigned count=0;
 for(unsigned f=0;f<12;f++) {
   INT_PCM in[2048],pcm[4096];UCHAR bytes[2048];
   for(unsigned i=0;i<1024;i++)in[2*i]=in[2*i+1]=(INT_PCM)(10000*sin(2*3.141592653589793*1000*(f*1024+i)/rate));
   void *ib[]={in},*ob[]={bytes};INT iid=IN_AUDIO_DATA,oid=OUT_BITSTREAM_DATA;
   INT is=sizeof(in),os=sizeof(bytes),iel=sizeof(INT_PCM),oel=1;
   AACENC_BufDesc input={1,ib,&iid,&is,&iel},output={1,ob,&oid,&os,&oel};
   AACENC_InArgs args={2048,0};AACENC_OutArgs out={0};
   assert(aacEncEncode(enc,&input,&output,&args,&out)==AACENC_OK);
   if(!out.numOutBytes)continue;
   UCHAR *b[]={bytes};UINT size=out.numOutBytes,valid=size;
   assert(aacDecoder_Fill(dec,b,&size,&valid)==AAC_DEC_OK && !valid);
   assert(aacDecoder_DecodeFrame(dec,pcm,4096,0)==AAC_DEC_OK);
   CStreamInfo *info=aacDecoder_GetStreamInfo(dec);
   assert(info && info->sampleRate==(int)rate && info->frameSize==1024 && info->numChannels==2);count++;
 }
 assert(count>=8);aacDecoder_Close(dec);aacEncClose(&enc);
 printf("FDK LATM AAC-LC after ELD: %u Hz, %u frames, 1024 samples\n",rate,count);
}
int main(void) {
 HANDLE_AACENCODER encoder=NULL;
 assert(aacEncOpen(&encoder,0x03,1)==AACENC_OK);
 param(encoder,AACENC_AOT,39); param(encoder,AACENC_SAMPLERATE,48000);
 param(encoder,AACENC_CHANNELMODE,MODE_1); param(encoder,AACENC_GRANULE_LENGTH,480);
 param(encoder,AACENC_BITRATE,64000); param(encoder,AACENC_SBR_MODE,0);
 param(encoder,AACENC_AFTERBURNER,0); param(encoder,AACENC_TRANSMUX,TT_MP4_RAW);
 assert(aacEncEncode(encoder,NULL,NULL,NULL,NULL)==AACENC_OK);
 HANDLE_AACDECODER decoder=aacDecoder_Open(TT_MP4_RAW,1); assert(decoder);
 UCHAR asc[]={0xf8,0xe6,0x30,0},*config[]={asc}; UINT config_size=sizeof(asc);
 AACENC_InfoStruct encoded_info;
 assert(aacEncInfo(encoder,&encoded_info)==AACENC_OK);
 assert(encoded_info.confSize==config_size && !memcmp(encoded_info.confBuf,asc,config_size));
 assert(aacDecoder_ConfigRaw(decoder,config,&config_size)==AAC_DEC_OK);
 unsigned count=0; int peak=0;
 for(unsigned frame=0;frame<32;frame++) {
   INT_PCM input[480],decoded[960]; UCHAR bytes[1024];
   for(unsigned i=0;i<480;i++) input[i]=(INT_PCM)(12000*sin(2*3.141592653589793*1000*(frame*480+i)/48000));
   void *ib[]={input},*ob[]={bytes}; INT iid=IN_AUDIO_DATA,oid=OUT_BITSTREAM_DATA;
   INT isize=sizeof(input),osize=sizeof(bytes),iel=sizeof(INT_PCM),oel=1;
   AACENC_BufDesc in={1,ib,&iid,&isize,&iel},out={1,ob,&oid,&osize,&oel};
   AACENC_InArgs args={480,0}; AACENC_OutArgs result={0};
   assert(aacEncEncode(encoder,&in,&out,&args,&result)==AACENC_OK);
   if (!result.numOutBytes) continue;
   assert(result.numOutBytes<=255); // AACP's one-byte AU length
   UCHAR *packet[]={bytes}; UINT size=result.numOutBytes,valid=size;
   assert(aacDecoder_Fill(decoder,packet,&size,&valid)==AAC_DEC_OK && !valid);
   assert(aacDecoder_DecodeFrame(decoder,decoded,960,0)==AAC_DEC_OK);
   CStreamInfo *info=aacDecoder_GetStreamInfo(decoder);
   assert(info && info->sampleRate==48000 && info->numChannels==1 && info->frameSize==480);
   count++;
   for(unsigned i=0;i<480;i++) { int a=abs(decoded[i]); if(a>peak) peak=a; }
 }
 assert(count>=28 && peak>1000);
 printf("Real FDK AAC-ELD round trip: %u frames, 48000 Hz ASC mono, 480 samples, peak %d\n",count,peak);
 aacDecoder_Close(decoder); aacEncClose(&encoder);
 lc_roundtrip(48000);lc_roundtrip(44100);
}

