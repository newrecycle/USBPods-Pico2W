// SPDX-License-Identifier: GPL-3.0-only
#include "control_command.h"
#include <assert.h>
#include <stdio.h>
static enum control_result line(control_input *s,const char *p,control_command *cmd){
 enum control_result r=CONTROL_BYPASS;for(;*p;p++)r=control_input_feed(s,*p,cmd);return r;
}
int main(void){
 control_input s={0};control_command cmd;
 assert(control_input_feed(&s,'p',&cmd)==CONTROL_BYPASS);
 assert(line(&s,":status\n",&cmd)==CONTROL_READY && cmd.status);
 assert(line(&s,":noise 2\r",&cmd)==CONTROL_READY && cmd.id==0x0d && cmd.value==2);
 assert(control_input_feed(&s,'\n',&cmd)==CONTROL_BYPASS);
 assert(line(&s,":pvol 0\n",&cmd)==CONTROL_READY && cmd.value==2);
 assert(line(&s,":ca 1\n",&cmd)==CONTROL_READY && cmd.value==1);
 assert(line(&s,":aa -1\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":jitter 60 junk\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":pvol 2\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":noise\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":unknown 2\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":",&cmd)==CONTROL_WAIT);
 for(int i=0;i<1024;i++)assert(control_input_feed(&s,'x',&cmd)==CONTROL_WAIT);
 assert(control_input_feed(&s,'\n',&cmd)==CONTROL_INVALID);
 assert(line(&s,":status\n",&cmd)==CONTROL_READY); // overflow recovers at newline
 assert(line(&s,":aa 99999999999999999999\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":status extra\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":profile 2 0 1\n",&cmd)==CONTROL_READY && cmd.id==CONTROL_PROFILE && cmd.value==2 && !cmd.game && cmd.level==1);
 assert(line(&s,":profile 3 1 2\n",&cmd)==CONTROL_READY && cmd.game==1 && cmd.level==2);
 assert(line(&s,":profile 0 1 2\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":profile 2 2 1\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":profile 2 0 3\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":profile 2 0 1 junk\n",&cmd)==CONTROL_INVALID);
 assert(line(&s,":profile 2 0\n",&cmd)==CONTROL_INVALID);
 puts("CDC command bounds, malformed input, legacy-key coexistence and recovery passed");
}
