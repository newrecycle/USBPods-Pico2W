// SPDX-License-Identifier: GPL-3.0-only
#include "media_input.h"
#include <string.h>
void media_input_reset(media_input *s){memset(s,0,sizeof(*s));}
void media_input_avrcp(media_input *s,uint16_t usage,uint32_t now) {
 if(s->typed_valid && now-s->typed_at<MEDIA_INPUT_WINDOW_MS){s->suppressed++;return;}
 if(s->count==MEDIA_INPUT_QUEUE){s->dropped++;return;}
 unsigned w=(s->read+s->count)%MEDIA_INPUT_QUEUE;
 s->pending[w].when=now;s->pending[w].usage=usage;s->count++;
}
uint16_t media_input_poll(media_input *s,uint32_t now) {
 if(!s->count || now-s->pending[s->read].when<MEDIA_INPUT_WINDOW_MS)return 0;
 uint16_t usage=s->pending[s->read].usage;s->read=(s->read+1)%MEDIA_INPUT_QUEUE;s->count--;return usage;
}
void media_input_typed(media_input *s,uint32_t now) {
 /* Only unexpired events remain after the caller's bounded drain. */
 s->suppressed+=s->count;s->count=0;s->read=0;s->typed_at=now;s->typed_valid=true;
}
