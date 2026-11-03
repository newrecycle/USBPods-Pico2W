// SPDX-License-Identifier: GPL-3.0-only
#include "mic_clock.h"
#include <assert.h>
#include <stdio.h>
static void run(int ppm) {
 mic_clock clock={0};uint32_t queued=0,high=0,primed_at=0,starved=0,adjusted=0,bursts=0;
 uint64_t produced=0,consumed=0;
 int64_t next=0;
 for(uint32_t ms=0;ms<600000;ms++) {
  /* Four 480-sample AUs every nominal 30 ms; deterministic scheduling
     jitter of up to eight milliseconds around each group. */
  int32_t jitter=(int32_t)((bursts*7u)%17u)-8;
  int64_t time=(int64_t)ms*1000;
  if(time>=next+jitter*1000) {
   queued+=4*MIC_AU_SAMPLES;produced+=4*MIC_AU_SAMPLES;
   bursts++;
   next+=30000ll*1000000/(1000000+ppm);
  }
  assert(queued<=16*MIC_AU_SAMPLES);if(queued>high)high=queued;
  uint32_t n=mic_clock_packet(&clock,7,queued);
  if(n){assert(n>=63 && n<=65 && n<=queued);queued-=n;consumed+=n;if(n!=64)adjusted++;if(!primed_at)primed_at=ms+1;}
  else if(primed_at)starved++;
 }
 assert(primed_at && !starved && queued==produced-consumed);
 assert(high<16*MIC_AU_SAMPLES);
 if(ppm)assert(adjusted);
 assert(!mic_clock_packet(&clock,8,0) && !clock.primed);
 printf("Mic clock 600s: drift=%d ppm high=%u adjusted=%u missing_after_prime=%u\n",ppm,high,adjusted,starved);
}
int main(void) {
 run(-1500);run(-250);run(0);run(250);run(1500);
 mic_clock s={0};assert(!mic_clock_packet(&s,1,100));
 assert(mic_clock_packet(&s,1,MIC_PREFILL_SAMPLES)==64);
 assert(!mic_clock_packet(&s,1,0) && !s.primed);
 assert(!mic_clock_packet(&s,1,MIC_PREFILL_SAMPLES-1));assert(mic_clock_packet(&s,1,MIC_PREFILL_SAMPLES)==64);
 puts("Mic packet clock: burst buffering, drift, underrun recovery and generation reset passed");
}
