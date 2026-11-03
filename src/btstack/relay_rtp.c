// SPDX-License-Identifier: GPL-3.0-only
#include "relay_rtp.h"
#include <string.h>
bool relay_rtp_payload(const uint8_t*p,size_t n,const uint8_t**out,size_t*len) {
 *out=NULL;*len=0;
 if(n<12 || (p[0]>>6)!=2)return false;
 size_t off=12+4u*(p[0]&15);
 if(off>n)return false;
 if(p[0]&16) {
   if(n-off<4)return false;
   size_t ext=4u*(256u*p[off+2]+p[off+3]);
   off+=4;if(ext>n-off)return false;off+=ext;
 }
 if(p[0]&32) {size_t pad=p[n-1];if(!pad || pad>n-off)return false;n-=pad;}
 if(off>=n)return false;
 *out=p+off;*len=n-off;return true;
}
void relay_rtp_reset(relay_rtp_assembly*s){memset(s,0,sizeof(*s));}
int relay_rtp_assemble(relay_rtp_assembly*s,const uint8_t*p,size_t n) {
 const uint8_t*data;size_t len;
 if(!relay_rtp_payload(p,n,&data,&len)){relay_rtp_reset(s);return -1;}
 uint16_t seq=(uint16_t)(256u*p[2]+p[3]);
 if(s->complete){s->length=0;s->complete=false;}
 uint32_t stamp=(uint32_t)p[4]<<24|(uint32_t)p[5]<<16|(uint32_t)p[6]<<8|p[7];
 uint32_t source=(uint32_t)p[8]<<24|(uint32_t)p[9]<<16|(uint32_t)p[10]<<8|p[11];
 if((s->seen && seq!=(uint16_t)(s->sequence+1)) ||
    (s->active && (stamp!=s->timestamp || source!=s->source))){relay_rtp_reset(s);return -1;}
 s->timestamp=stamp;s->source=source;s->seen=true;
 if(len>sizeof(s->data)-s->length){relay_rtp_reset(s);return -1;}
 memcpy(s->data+s->length,data,len);s->length+=(uint16_t)len;s->sequence=seq;
 s->active=(p[1]&128)==0;s->complete=!s->active;
 return s->complete?1:0;
}
