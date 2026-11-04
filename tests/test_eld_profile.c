// SPDX-License-Identifier: GPL-3.0-only
#include "eld_profile.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 unsigned count=0;
 for(int rate=0;rate<=3;rate++)for(int game=0;game<2;game++)for(int level=1;level<=2;level++)for(int r44=0;r44<2;r44++)for(int relay=0;relay<2;relay++) {
   eld_profile p=eld_profile_select(rate,game,level,r44,relay,5,1);
   assert(p.input_rate==(r44?44100:48000)&&p.input_frames==(r44?441:480));
   assert(p.bitrate==(relay?164000:r44||game||rate==1?192000:rate==3?320000:256000));
#ifdef USBPODS_MIC_DECODE
   assert(!p.vbr && !p.sbr);
#else
   assert(p.vbr==(!relay&&!r44&&!game&&rate!=1&&rate!=3?5:0));
#endif
   assert(p.sbr==(p.vbr?1:0));assert(p.slots==(game?(level==2?4:6):rate==3?9:6));
   assert(p.jitter==(game?(level==2?60:90):150));count++;
 }
 eld_profile p=eld_profile_select(2,0,1,0,0,0,1);assert(!p.vbr&&!p.sbr);
 puts("ELD rate/game/rate44/relay policy: 64 combinations passed");assert(count==64);
}
