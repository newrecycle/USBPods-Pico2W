// SPDX-License-Identifier: GPL-3.0-only
#include "eld_profile.h"
eld_profile eld_profile_select(uint8_t rate,bool game,uint8_t level,bool rate44,bool relay,uint8_t vbr,uint8_t sbr) {
 eld_profile p={0};
 p.input_rate=rate44?44100:48000;p.input_frames=rate44?441:480;
 p.bitrate=game||rate==1?192000:rate==3?320000:256000;
 if(rate44 && p.bitrate>192000)p.bitrate=192000;
 if(relay && p.bitrate>164000)p.bitrate=164000;
 p.vbr=!game&&!rate44&&!relay&&rate!=1&&rate!=3?vbr:0;
 p.sbr=p.vbr?sbr:0;
 p.slots=game?(level==2?4:6):rate==3?9:6;
 p.jitter=game?(level==2?60:90):150;
 return p;
}
