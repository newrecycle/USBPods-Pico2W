// SPDX-License-Identifier: GPL-3.0-only
#include "aacp_mic_protocol.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned callbacks;
static void frame(const uint8_t *p,uint8_t n,uint32_t ts,void *ctx) {
 (void)ctx; assert(n==2 && p[0]==0xaa && p[1]==0xbb && ts==0x12345678); callbacks++;
}
int main(void) {
 uint8_t p[40]={4,0,4,0,0x58,0,1,0};
 p[22]=0x78; p[23]=0x56; p[24]=0x34; p[25]=0x12; p[26]=2; p[27]=0xaa; p[28]=0xbb;
 assert(aacp_mic_parse(p,29,frame,NULL)==1 && callbacks==1);
 memcpy(p+29,p+22,7); callbacks=0;
 assert(aacp_mic_parse(p,36,frame,NULL)==2 && callbacks==2);
 for (unsigned n=8;n<29;n++) assert(aacp_mic_parse(p,n,NULL,NULL)==-1);
 callbacks=0;
 assert(aacp_mic_parse(p,35,frame,NULL)==-1 && callbacks==0); // no partial delivery
 assert(aacp_mic_parse(p,37,frame,NULL)==-1 && callbacks==0); // trailing byte
 p[33]=0; assert(aacp_mic_parse(p,34,frame,NULL)==-1 && callbacks==0);
 p[1]=1; assert(aacp_mic_parse(p,29,frame,NULL)==-1);
 p[1]=0; p[4]=0x0f; assert(aacp_mic_parse(p,29,frame,NULL)==0);
 // Exhaust every possible AU length against the boundary.
 p[4]=0x58;
 for (unsigned n=0;n<256;n++) { p[26]=n; assert(aacp_mic_parse(p,29,NULL,NULL)==(n==2?1:-1)); }
 aacp_mic_session s={0};
 for (int i=0;i<3;i++) {
   assert(aacp_mic_next(&s,true)==i);
   assert(aacp_mic_next(&s,false)==i); // failed send doesn't advance
   aacp_mic_sent(&s,i);
 }
 assert(aacp_mic_next(&s,true)==-1); // wait for response
 s.confirmed=true;
 assert(aacp_mic_next(&s,true)==3);
 assert(aacp_mic_next(&s,false)==-1); // close before can-send: cancel START
 aacp_mic_sent(&s,3);
 assert(aacp_mic_next(&s,false)==4);
 assert(aacp_mic_next(&s,true)==-1); // reopen before can-send: cancel STOP
 aacp_mic_sent(&s,4); assert(!s.started);
 static const uint16_t lengths[]={16,14,10,19,12};
 for (int i=0;i<5;i++) { uint16_t n; assert(aacp_mic_command(i,&n) && n==lengths[i]); }
 uint16_t n; assert(!aacp_mic_command(5,&n) && !n);
 puts("AACP transactional parser and session tests passed");
}
