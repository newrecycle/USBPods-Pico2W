// SPDX-License-Identifier: GPL-3.0-only
#include "control_command.h"
#include <string.h>
static bool parse(char *p,control_command *out) {
 memset(out,0,sizeof(*out));
 if(!strcmp(p,"status")){out->status=true;return true;}
 char *arg=strchr(p,' ');if(!arg)return false;*arg++=0;
 static const struct { const char *name; uint8_t id; } cmds[]={
   {"noise",0x0d},{"pvol",0x26},{"ca",0x28},{"aa",0x2e},{"jitter",0x0b}
 };
 unsigned value=0;if(!*arg)return false;
 for(;*arg;arg++) {
   if(*arg<'0'||*arg>'9')return false;
   value=value*10u+(unsigned)(*arg-'0');if(value>255)return false;
 }
 for(unsigned i=0;i<sizeof(cmds)/sizeof(cmds[0]);i++)if(!strcmp(p,cmds[i].name)) {
   out->id=cmds[i].id;out->value=(uint8_t)value;
   if(out->id==0x26 || out->id==0x28) {
     if(value>1)return false;
     out->value=value?1:2;
   }
   return true;
 }
 return false;
}
enum control_result control_input_feed(control_input *s,char c,control_command *out) {
 if(!s->active) {
   if(c!=':')return CONTROL_BYPASS;
   s->active=true;s->overflow=false;s->length=0;return CONTROL_WAIT;
 }
 if(c=='\r'||c=='\n') {
   s->line[s->length]=0;s->active=false;
   return !s->overflow && parse(s->line,out)?CONTROL_READY:CONTROL_INVALID;
 }
 if((unsigned char)c<32 || (unsigned char)c>126 || s->length==sizeof(s->line)-1) {
   s->overflow=true;return CONTROL_WAIT;
 }
 if(!s->overflow)s->line[s->length++]=c;
 return CONTROL_WAIT;
}
