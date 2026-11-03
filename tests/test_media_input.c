// SPDX-License-Identifier: GPL-3.0-only
#include "media_input.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
 media_input s;media_input_reset(&s);
 media_input_avrcp(&s,0xcd,100);assert(!media_input_poll(&s,349));
 assert(media_input_poll(&s,350)==0xcd && !media_input_poll(&s,1000));
 // Native PLAY then explicit double press: only typed NEXT is forwarded.
 media_input_avrcp(&s,0xcd,1100);assert(!media_input_poll(&s,1150));
 media_input_typed(&s,1150);assert(!media_input_poll(&s,1400) && s.suppressed==1);
 // Opposite arrival order: typed PREVIOUS suppresses its native companion.
 media_input_typed(&s,1500);media_input_avrcp(&s,0xcd,1510);
 assert(!media_input_poll(&s,2000) && s.suppressed==2);
 // Genuine later native commands preserve order and semantics, never inferred counts.
 media_input_avrcp(&s,0xb5,2000);media_input_avrcp(&s,0xb6,2010);
 assert(media_input_poll(&s,2250)==0xb5 && !media_input_poll(&s,2250));
 assert(media_input_poll(&s,2260)==0xb6);
 for(unsigned i=0;i<5;i++)media_input_avrcp(&s,0xcd,3000+i);
 assert(s.count==4 && s.dropped==1);
 media_input_reset(&s);assert(!media_input_poll(&s,4000)); // Stale peer/session cancelled.
 media_input_avrcp(&s,0xcd,0xffffff80u);
 assert(!media_input_poll(&s,0x00000020u));
 assert(media_input_poll(&s,0x00000080u)==0xcd);
 puts("Media input ordering, typed-event precedence, native fallback, overflow and wrap passed");
}
