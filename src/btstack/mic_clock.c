// SPDX-License-Identifier: GPL-3.0-only
#include "mic_clock.h"
uint32_t mic_clock_packet(mic_clock *s,uint32_t generation,uint32_t available) {
 if(generation!=s->generation){*s=(mic_clock){.generation=generation};}
 if(!s->primed) {
  if(available<MIC_PREFILL_SAMPLES)return 0;
  s->primed=true;s->level_q8=MIC_PREFILL_SAMPLES*256;s->correction=0;
 }
 /* Smooth SDU batches (typically 4 AUs / 30 ms) over ~256 ms. The bounded
    proportional correction is at most 2000 ppm, accumulated fractionally;
    it never changes the number of PCM samples in a frame or resamples voice. */
 int32_t level=(int32_t)(available>7680?7680:available)*256;
 s->level_q8+=(level-s->level_q8)/256;
 int32_t ppm=((s->level_q8/256)-MIC_PREFILL_SAMPLES)*2;
 if(ppm>2000)ppm=2000;
 if(ppm< -2000)ppm= -2000;
 s->correction+=ppm*MIC_USB_NOMINAL_SAMPLES;
 uint32_t n=MIC_USB_NOMINAL_SAMPLES;
 if(s->correction>=1000000){n++;s->correction-=1000000;}
 else if(s->correction<= -1000000){n--;s->correction+=1000000;}
 if(available<n){s->primed=false;return 0;}
 return n;
}
