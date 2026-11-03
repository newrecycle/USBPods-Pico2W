// SPDX-License-Identifier: GPL-3.0-only
#include "eld_codec_config.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
 uint8_t caps[]={0x4c,0,0,0,1,0x80,0,0x80,0,0x8c,0,0x84,0xe2,0},out[14];
 eld_codec_limits p;
 assert(eld_codec_offer(caps,sizeof caps,out,&p));
 assert(p.max_bitrate==320000 && p.vbr && out[9]==0x84);
 assert(eld_codec_configuration(out,sizeof out,&p) && p.max_bitrate==320000);
 caps[11]=0x83;caps[12]=0xe8;caps[13]=0;
 assert(eld_codec_offer(caps,14,out,&p) && p.max_bitrate==256000);
 caps[11]=2;caps[12]=0xee;caps[13]=0;
 assert(eld_codec_offer(caps,14,out,&p) && p.max_bitrate==192000 && !p.vbr);
 caps[11]=caps[12]=caps[13]=0;
 assert(eld_codec_offer(caps,14,out,&p) && p.max_bitrate==320000 && !p.vbr);
 for(unsigned i=0;i<14;i++) {
  uint8_t before[14];memcpy(before,out,14);
  assert(!eld_codec_offer(caps,i,out,&p));assert(!memcmp(before,out,14));
 }
 caps[0]=0;assert(!eld_codec_offer(caps,14,out,&p));caps[0]=0x4c;
 caps[9]=0x88;assert(!eld_codec_offer(caps,14,out,&p));caps[9]=0x84;
 caps[11]=1;caps[12]=caps[13]=0;assert(!eld_codec_offer(caps,14,out,&p));
 out[11]=0x87;out[12]=0x53;out[13]=0;assert(!eld_codec_configuration(out,14,&p));
 out[11]=0x84;out[12]=0xe2;out[13]=0;out[9]=0x8c;
 assert(!eld_codec_configuration(out,14,&p));
 puts("ELD negotiated ceilings, VBR capability, geometry and malformed layouts passed");
}
