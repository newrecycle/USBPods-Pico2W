// SPDX-License-Identifier: GPL-3.0-only
// Synthetic codec interoperability check; this is not an AirPods capture fixture.
#include <aacenc_lib.h>
#include <aacdecoder_lib.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
static void param(HANDLE_AACENCODER h,AACENC_PARAM p,UINT v) {
 assert(aacEncoder_SetParam(h,p,v)==AACENC_OK);
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
}
