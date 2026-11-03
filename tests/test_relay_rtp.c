// SPDX-License-Identifier: GPL-3.0-only
#include "relay_rtp.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void){
 uint8_t p[32]={0x80,0xe0,0,1};p[12]=0x55;
 const uint8_t*out;size_t n;
 for(size_t size=0;size<13;size++)assert(!relay_rtp_payload(p,size,&out,&n));
 assert(relay_rtp_payload(p,13,&out,&n)&&n==1&&out[0]==0x55);
 p[0]=0x90;p[14]=0x40;assert(!relay_rtp_payload(p,20,&out,&n)); // old 16-bit wrap
 p[14]=0;p[15]=1;assert(relay_rtp_payload(p,24,&out,&n)&&n==4);
 p[0]=0xa0;p[31]=0;assert(!relay_rtp_payload(p,32,&out,&n));
 p[31]=20;assert(!relay_rtp_payload(p,32,&out,&n));
 p[31]=3;assert(relay_rtp_payload(p,32,&out,&n)&&n==17);
 relay_rtp_assembly s;relay_rtp_reset(&s);p[0]=0x80;p[1]=0x60;
 assert(relay_rtp_assemble(&s,p,13)==0);p[3]=2;p[1]|=128;
 assert(relay_rtp_assemble(&s,p,13)==1&&s.length==2);
 p[3]=3;p[1]=0x60;assert(relay_rtp_assemble(&s,p,13)==0);
 p[3]=5;assert(relay_rtp_assemble(&s,p,13)==-1&&!s.length);
 for(unsigned i=0;i<2100;i++) {p[2]=i>>8;p[3]=i;int r=relay_rtp_assemble(&s,p,13);if(r<0)break;}
 assert(!s.length);puts("Relay RTP bounds, fragmentation, sequence and overflow passed");
}
