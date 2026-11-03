// SPDX-License-Identifier: GPL-3.0-only
#include "eld_encoder.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned calls,fail_at,live,peak;static bool bad_info;
static UINT parameters[32];
static int step(void){return ++calls==fail_at?AACENC_INVALID_CONFIG:AACENC_OK;}
AACENC_ERROR aacEncOpen(HANDLE_AACENCODER*h,UINT modules,UINT channels){assert(modules==3&&channels==2);int e=step();if(!e){live++;if(live>peak)peak=live;*h=(void*)(uintptr_t)live;}return e;}
AACENC_ERROR aacEncClose(HANDLE_AACENCODER*h){assert(*h&&live);live--;*h=NULL;return 0;}
AACENC_ERROR aacEncoder_SetParam(HANDLE_AACENCODER h,AACENC_PARAM p,UINT v){assert(h);assert((unsigned)p<32);parameters[p]=v;return step();}
AACENC_ERROR aacEncEncode(HANDLE_AACENCODER h,void*a,void*b,void*c,void*d){assert(h);(void)a;(void)b;(void)c;(void)d;return step();}
AACENC_ERROR aacEncInfo(HANDLE_AACENCODER h,AACENC_InfoStruct*i){assert(h);int e=step();if(!e){i->frameLength=bad_info?1024:480;i->inputChannels=2;}return e;}
int main(void){
 HANDLE_AACENCODER h=NULL;AACENC_InfoStruct info;
 for(unsigned mode=0;mode<4;mode++) {
 eld_profile p=eld_profile_select(mode?mode:3,mode==0,1,0,0,5,1);
 calls=0;fail_at=0;bad_info=false;
 assert(eld_encoder_open(&h,&info,&p)==0);unsigned steps=calls;
 assert(parameters[AACENC_BITRATE]==p.bitrate);
 assert(parameters[AACENC_PEAK_BITRATE]==(p.vbr?256000:p.bitrate));
 for(unsigned fail=1;fail<=steps;fail++){
   calls=0;fail_at=fail;assert(eld_encoder_open(&h,&info,&p)!=0);
   assert(!h&&!live&&!info.frameLength&&!info.inputChannels);
   fail_at=0;calls=0;assert(eld_encoder_open(&h,&info,&p)==0);
 }
 bad_info=true;fail_at=0;assert(eld_encoder_open(&h,&info,&p)!=0 && !h && !live);
 }
 assert(peak==1);puts("ELD encoder allocation/parameter/init/info failures close safely; no overlapping handles");
}
