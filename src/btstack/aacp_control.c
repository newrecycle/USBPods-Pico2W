// SPDX-License-Identifier: GPL-3.0-only
// Control identifiers/framing: vendor Full 503218b7, FUN_10016698 and
// FUN_10015dbc; independently corroborated by librepods AACPManager.
#include "aacp_control.h"
#include <string.h>
static const uint8_t ids[]={0x0b,0x0d,0x26,0x28,0x2e};
void aacp_control_reset(aacp_control *s) {
 memset(s,0,sizeof(*s)); memset(s->battery,0xff,3);
 s->pvol=s->ca=s->aa=-1;
}
static bool valid(unsigned i,uint8_t v) {
 switch(i) {
 case 0: return v==30 || v==60 || v==90 || v==150;
 case 1: return v>=1 && v<=4;
 case 2: case 3: return v==1 || v==2;
 case 4: return v<=100;
 default: return false;
 }
}
bool aacp_control_set(aacp_control *s,uint8_t id,uint8_t v) {
 for(unsigned i=0;i<sizeof(ids);i++) if(ids[i]==id && valid(i,v)) {
   s->values[i]=v; s->pending|=(uint8_t)(1u<<i); return true;
 }
 return false;
}
int aacp_control_peek(const aacp_control *s,uint8_t p[11]) {
 for(unsigned i=0;i<sizeof(ids);i++) if(s->pending&(1u<<i)) {
   const uint8_t base[]={4,0,4,0,9,0,0,0,0,0,0};
   memcpy(p,base,11); p[6]=ids[i];p[7]=s->values[i];return (int)i;
 }
 return -1;
}
void aacp_control_sent(aacp_control *s,int slot,uint8_t value) {
 if(slot>=0 && slot<5 && s->values[slot]==value)
   s->pending&=(uint8_t)~(1u<<slot);
}
bool aacp_control_receive(aacp_control *s,const uint8_t *p,size_t n) {
 if(n<6 || p[1] || p[2]!=4 || p[3] || p[5]) return false;
 if(p[0]==1) return p[4]==1; /* handshake acknowledgment */
 if(p[0]!=4) return false;
 switch(p[4]) {
 case 0x2b: return true; /* feature acknowledgment */
 case 0x06:
   if(n!=8 || p[6]>3 || p[7]>3)return false;
   s->ear_valid=true;s->worn=p[6]==0 || p[7]==0;return true;
 case 0x19:
   if(n!=8 || p[6]<5 || p[6]>7 || p[7]<1 || p[7]>2)return false;
   s->stem=p[6];s->stem_count++;return true;
 case 0x04: {
   if(n<7 || p[6]>3 || n!=7u+5u*p[6]) return false;
   uint8_t battery[3];memcpy(battery,s->battery,3);
   for(unsigned off=7;off<n;off+=5) {
     uint8_t level=p[off+2]>100?100:p[off+2];
     if(p[off+3]==1) level|=0x80;
     switch(p[off]) {
     case 1: battery[0]=battery[1]=level; break;
     case 4: battery[0]=level; break;
     case 2: battery[1]=level; break;
     case 8: battery[2]=level; break;
     default: return false;
     }
   }
   memcpy(s->battery,battery,3);return true;
 }
 case 0x09:
   if(n!=11 || p[8] || p[9] || p[10]) return false;
   for(unsigned i=0;i<sizeof(ids);i++) if(p[6]==ids[i] && valid(i,p[7])) {
     switch(i) {
     case 1: s->noise=p[7];break;
     case 2: s->pvol=p[7]==1;break;
     case 3: s->ca=p[7]==1;break;
     case 4: s->aa=p[7];break;
     default: break;
     }
     return true;
   }
   return false;
 default: return false;
 }
}
