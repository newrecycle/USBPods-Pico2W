// SPDX-License-Identifier: GPL-3.0-only
// Protocol sequences/layout adapted from han-um's USBPods fork (2026),
// derived there from librepods (GPL-3.0). See docs/AACP-MIC.md.
#include "aacp_mic_protocol.h"
#include <string.h>
static const uint8_t commands[][19] = {
 {0,0,4,0,1,0,2,0,0,0,0,0,0,0,0,0},
 {4,0,4,0,0x4d,0,0xff,0,0,0,0,0,0,0},
 {4,0,4,0,0x0f,0,0xff,0xff,0xff,0xff},
 {4,0,4,0,0x58,0,0,0,9,0,0,1,0x82,0,0,0,4,0x96,0},
 {4,0,4,0,0x58,0,0,0,2,0,3,1}
};
const uint8_t *aacp_mic_command(int command, uint16_t *size) {
 static const uint8_t sizes[] = {16,14,10,19,12};
 if (command < 0 || command > 4) { *size=0; return NULL; }
 *size=sizes[command]; return commands[command];
}
int aacp_mic_next(const aacp_mic_session *s, bool wanted) {
 if (s->init_sent < 3) return s->init_sent;
 if (!s->confirmed || wanted == s->started) return -1;
 return wanted ? 3 : 4;
}
void aacp_mic_sent(aacp_mic_session *s, int c) {
 if (c >= 0 && c < 3 && c == s->init_sent) s->init_sent++;
 if (c == 3) s->started=true;
 if (c == 4) s->started=false;
}
void aacp_mic_watch_reset(aacp_mic_watch *w){memset(w,0,sizeof(*w));}
bool aacp_mic_watch_target(aacp_mic_watch *w,bool want,bool started,uint32_t generation,uint32_t now) {
 if(w->enabled!=want || w->generation!=generation) {
   uint32_t restarts=w->restarts,failures=w->failures;
   *w=(aacp_mic_watch){.enabled=want,.generation=generation,.armed=want&&started,
       .due=now+AACP_MIC_SILENCE_MS,.restarts=restarts,.failures=failures};
 }
 if(w->enabled && w->armed && started && !w->failed &&
    w->retry==AACP_MIC_RETRY_NONE && (int32_t)(now-w->due)>=0) {
   if(w->retries==AACP_MIC_MAX_RETRIES){w->failed=true;w->failures++;}
   else w->retry=AACP_MIC_RETRY_STOP;
 }
 return want && !w->failed && w->retry!=AACP_MIC_RETRY_STOP;
}
void aacp_mic_watch_sent(aacp_mic_watch *w,int command,uint32_t now) {
 if(command==3) {
   w->armed=true;w->seen=false;w->due=now+AACP_MIC_SILENCE_MS;
   w->retry=AACP_MIC_RETRY_NONE;
 }else if(command==4) {
   w->armed=false;w->seen=false;
   if(w->retry==AACP_MIC_RETRY_STOP && !w->failed) {
     w->retries++;w->restarts++;w->retry=AACP_MIC_RETRY_START;
   }else w->retry=AACP_MIC_RETRY_NONE;
 }
}
void aacp_mic_watch_audio(aacp_mic_watch *w,uint32_t now) {
 if(!w->enabled || !w->armed || w->failed)return;
 w->seen=true;w->last_audio=now;w->due=now+AACP_MIC_SILENCE_MS;
 if(w->retry==AACP_MIC_RETRY_STOP)w->retry=AACP_MIC_RETRY_NONE;
}
int aacp_mic_parse(const uint8_t *p, size_t n, aacp_mic_au_cb cb, void *ctx) {
 if (n < 8 || p[4] != 0x58 || p[5] || p[6] != 1 || p[7]) return 0;
 if (memcmp(p, "\x04\x00\x04\x00",4) || n < 28) return -1;
 size_t off=22; int frames=0;
 while (off < n) {
   if (n-off < 5 || !p[off+4] || (size_t)p[off+4] > n-off-5) return -1;
   off += 5+p[off+4]; frames++;
 }
 if (cb) for (off=22; off<n; off+=5+p[off+4]) {
   uint32_t ts=(uint32_t)p[off] | (uint32_t)p[off+1]<<8 |
               (uint32_t)p[off+2]<<16 | (uint32_t)p[off+3]<<24;
   cb(p+off+5,p[off+4],ts,ctx);
 }
 return frames;
}

