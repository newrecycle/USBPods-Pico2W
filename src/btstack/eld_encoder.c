// SPDX-License-Identifier: GPL-3.0-only
#include "eld_encoder.h"
#include <string.h>
AACENC_ERROR eld_encoder_open(HANDLE_AACENCODER *h,AACENC_InfoStruct *info,const eld_profile*p) {
 AACENC_ERROR e;
 if(*h)aacEncClose(h);
 *h=NULL;memset(info,0,sizeof(*info));
 if((e=aacEncOpen(h,0x03,2))!=AACENC_OK)goto failed;
#define SET(k,v) do {e=aacEncoder_SetParam(*h,k,v);if(e!=AACENC_OK)goto failed;}while(0)
 SET(AACENC_AOT,39);SET(AACENC_BITRATE,p->bitrate);SET(AACENC_SAMPLERATE,48000);
 SET(AACENC_CHANNELMODE,MODE_2);SET(AACENC_GRANULE_LENGTH,480);
 SET(AACENC_SBR_MODE,p->sbr);if(p->sbr)SET(AACENC_SBR_RATIO,1);
 SET(AACENC_BITRATEMODE,p->vbr);if(p->vbr)SET(AACENC_PEAK_BITRATE,256000);
 SET(AACENC_AFTERBURNER,0);SET(AACENC_TRANSMUX,TT_MP4_RAW);
#undef SET
 if((e=aacEncEncode(*h,NULL,NULL,NULL,NULL))!=AACENC_OK)goto failed;
 if((e=aacEncInfo(*h,info))!=AACENC_OK)goto failed;
 if(info->frameLength!=480 || info->inputChannels!=2){e=AACENC_INVALID_CONFIG;goto failed;}
 return AACENC_OK;
failed:
 if(*h)aacEncClose(h);
 *h=NULL;memset(info,0,sizeof(*info));return e;
}
