// SPDX-License-Identifier: GPL-3.0-only
#include "aacp_control.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
int main(void) {
 aacp_control s; aacp_control_reset(&s);
 assert(s.battery[0]==255 && s.pvol==-1);
 uint8_t p[22]={4,0,4,0,4,0,3,1,0,87,1,0,2,0,101,0,0,8,0,50,0,0};
 aacp_control before=s;
 for(size_t n=0;n<22;n++) { assert(!aacp_control_receive(&s,p,n));assert(!memcmp(&s,&before,sizeof s)); }
 assert(aacp_control_receive(&s,p,22));
 assert(s.battery[0]==(87|128) && s.battery[1]==100 && s.battery[2]==50);
 before=s;p[17]=0xff;assert(!aacp_control_receive(&s,p,22));assert(!memcmp(&s,&before,sizeof s));
 uint8_t c[]={4,0,4,0,9,0,0x26,1,0,0,0};
 c[0]=0xff;assert(!aacp_control_receive(&s,c,11));c[0]=4;
 assert(!aacp_control_receive(&s,c,8));
 assert(aacp_control_receive(&s,c,11) && s.pvol==1);
 c[7]=2;assert(aacp_control_receive(&s,c,11) && s.pvol==0);
 c[7]=3;assert(!aacp_control_receive(&s,c,11) && s.pvol==0);
 c[6]=0x2e;c[7]=101;assert(!aacp_control_receive(&s,c,11));
 assert(!aacp_control_set(&s,3,1));assert(!aacp_control_set(&s,0x0d,0));
 assert(!aacp_control_set(&s,0x2e,101));
 assert(aacp_control_set(&s,0x0d,2));assert(s.noise==0); // intent is not peer state
 uint8_t tx[11]; int slot=aacp_control_peek(&s,tx);assert(slot==1);
 const uint8_t expected[]={4,0,4,0,9,0,0x0d,2,0,0,0};assert(!memcmp(tx,expected,11));
 assert(aacp_control_peek(&s,tx)==slot); // failed send retains command
 assert(aacp_control_set(&s,0x0d,4)); // latest intent wins
 aacp_control_sent(&s,slot,2);assert(aacp_control_peek(&s,tx)==slot && tx[7]==4);
 aacp_control_sent(&s,slot,4);assert(aacp_control_peek(&s,tx)==-1);
 assert(aacp_control_set(&s,0x0b,90));aacp_control_reset(&s);
 assert(!s.pending && s.pvol==-1 && s.battery[0]==255);
 puts("AACP control validation, observed state and send retry tests passed");
}
