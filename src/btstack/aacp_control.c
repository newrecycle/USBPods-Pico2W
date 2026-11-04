// SPDX-License-Identifier: GPL-3.0-only
// Control identifiers/framing: vendor Full 503218b7, FUN_10016698 and
// FUN_10015dbc; independently corroborated by librepods AACPManager.
#include "aacp_control.h"
#include <string.h>
static const uint8_t ids[]={0x0b,0x0d,0x26,0x28,0x2e};
void aacp_control_reset(aacp_control *s) {
 memset(s,0,sizeof(*s)); memset(s->battery,0xff,3);
 s->pvol=s->ca=s->aa=s->allow_off=-1;
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
bool aacp_connection_response_success(const uint8_t *p,size_t n) {
 /* Type 1 is a Connection Response, not a Message with an opcode. Its
    14-byte payload is status, major, minor, features. Status zero succeeds. */
 return n==18 && p[0]==1 && p[1]==0 && p[2]==4 && p[3]==0 && p[4]==0 && p[5]==0;
}
bool aacp_control_receive(aacp_control *s,const uint8_t *p,size_t n) {
 if(n<6 || p[1] || p[2]!=4 || p[3] || p[5]) return false;
 if(p[0]==1) return aacp_connection_response_success(p,n);
 if(p[0]!=4) return false;
 switch(p[4]) {
 case 0x2b: return true; /* Peer information; not a validated feature acknowledgment. */
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
   if(p[6]==0x34){if(p[7]!=1&&p[7]!=2)return false;s->allow_off=p[7]==1;return true;}
   for(unsigned i=0;i<sizeof(ids);i++) if(p[6]==ids[i] && valid(i,p[7])) {
     s->observed[i]++;
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

static int control_frame_size(const uint8_t *p,size_t n) {
 if(n<6 || memcmp(p,"\x04\x00\x04\x00",4) || p[5])return 0;
 switch(p[4]) {
 case 9:return n>=11?11:-1;
 case 6:case 0x19:return n>=8?8:-1;
 case 4:
   if(n<7 || p[6]>3)return -1;
   return n>=7u+5u*p[6]?(int)(7u+5u*p[6]):-1;
 default:return 0;
 }
}
int aacp_control_walk(const uint8_t *p,size_t n,aacp_control_frame_cb cb,void *ctx) {
 if(!n)return 0;
 size_t off=0;int frames=0;
 while(off<n) {
   int len=control_frame_size(p+off,n-off);
   if(len<=0)return off || len<0?-1:0;
   off+=(size_t)len;frames++;
 }
 if(cb)for(off=0;off<n;) {
   int len=control_frame_size(p+off,n-off);
   cb(p+off,(size_t)len,ctx);off+=(size_t)len;
 }
 return frames;
}
