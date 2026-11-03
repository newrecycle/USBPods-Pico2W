// SPDX-License-Identifier: GPL-3.0-only
#include "eld_codec_config.h"
#include <string.h>
static bool identity(const uint8_t *p,size_t n) {
 static const uint8_t id[]={0x4c,0,0,0,1,0x80};
 return n==14 && !memcmp(p,id,sizeof id) && (p[7]&0x80) &&
        (p[9]&0x80) && (p[9]&4);
}
static uint32_t bitrate(const uint8_t *p) {
 return ((uint32_t)(p[11]&0x7f)<<16)|((uint32_t)p[12]<<8)|p[13];
}
bool eld_codec_offer(const uint8_t *p,size_t n,uint8_t out[14],eld_codec_limits *limits) {
 if(!identity(p,n))return false;
 uint32_t max=bitrate(p);
 if(!max || max>ELD_LOCAL_MAX_BITRATE)max=ELD_LOCAL_MAX_BITRATE;
 if(max<192000)return false;
 static const uint8_t base[]={0x4c,0,0,0,1,0x80,0,0x80,0,0x84,0,0,0,0};
 memcpy(out,base,sizeof base);
 out[11]=(uint8_t)((p[11]&0x80)|(max>>16));
 out[12]=(uint8_t)(max>>8);out[13]=(uint8_t)max;
 *limits=(eld_codec_limits){max,(p[11]&0x80)!=0};
 return true;
}
bool eld_codec_configuration(const uint8_t *p,size_t n,eld_codec_limits *limits) {
 if(!identity(p,n) || p[6] || p[7]!=0x80 || p[8] || p[9]!=0x84 || p[10])return false;
 uint32_t max=bitrate(p);
 if(max<192000 || max>ELD_LOCAL_MAX_BITRATE)return false;
 *limits=(eld_codec_limits){max,(p[11]&0x80)!=0};return true;
}
