// SPDX-License-Identifier: GPL-3.0-only
#include "control_command.h"
#include <string.h>
static bool parse(char *p,control_command *out) {
 memset(out,0,sizeof(*out));
 if(!strcmp(p,"status")){out->status=true;return true;}
 static const struct { const char *name;uint8_t id; } queries[]={
   {"eldstatus",CONTROL_ELDSTATUS},{"info",CONTROL_INFO},{"scan",CONTROL_SCAN},{"scanlist",CONTROL_SCANLIST},
   {"scanstop",CONTROL_SCANSTOP},{"connect",CONTROL_CONNECT},{"disconnect",CONTROL_DISCONNECT},
   {"settings",CONTROL_SETTINGS},{"phonedisc",CONTROL_PHONEDISC},{"reboot",CONTROL_REBOOT},
   {"telemetry",CONTROL_TELEMETRY},{"savedlist",CONTROL_SAVEDLIST}
 };
 for(unsigned i=0;i<sizeof(queries)/sizeof(queries[0]);i++)if(!strcmp(p,queries[i].name)){out->id=queries[i].id;return true;}
 char *arg=strchr(p,' ');if(!arg)return false;*arg++=0;
 static const struct { const char *name; uint8_t id; } cmds[]={
   {"pair",CONTROL_PAIR},{"uart",CONTROL_UART},{"debug",CONTROL_DEBUG},
   {"game",CONTROL_GAME},{"earpause",CONTROL_EARPAUSE},{"stem",CONTROL_STEM},
   {"gamelevel",CONTROL_GAMELEVEL},{"eldrate",CONTROL_ELDRATE},
   {"usbvol",CONTROL_USBVOL},{"phvol",CONTROL_PHVOL},{"connmode",CONTROL_CONNMODE},
   {"slot",CONTROL_SLOT},{"savedconnect",CONTROL_SAVEDCONNECT},{"saveddelete",CONTROL_SAVEDDELETE},
   {"phonepair",CONTROL_PHONEPAIR},{"phoneconnect",CONTROL_PHONECONNECT},{"relayaac",CONTROL_RELAYAAC},
   {"uac1",CONTROL_UAC1},{"rate44",CONTROL_RATE44},{"bootconn",CONTROL_BOOTCONN},
   {"pausedc",CONTROL_PAUSEDC},{"swvol",CONTROL_SWVOL},{"btnmode",CONTROL_BTNMODE},
   {"ldacq",CONTROL_LDACQ},{"lhdcrate",CONTROL_LHDCRATE},
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
