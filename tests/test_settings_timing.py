"""Production debounce/retry paths at idle, relay and microphone loop rates."""
from pathlib import Path
import os
import subprocess
import tempfile
from test_source_boundaries import function, ROOT

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
static bool s_dirty,s_retrying,fail,change_during_commit;
static uint32_t s_dirty_ms,now,writes;
static uint32_t get_absolute_time(void){return now;}
static uint32_t to_ms_since_boot(uint32_t t){return t;}
static uint32_t save_and_disable_interrupts(void){return 0;}
static void restore_interrupts(uint32_t n){(void)n;}
static void settings_mark_dirty(void);
static bool commit_snapshot(void){
 writes++;
 if(change_during_commit){change_during_commit=false;settings_mark_dirty();}
 return !fail;
}
'''
tests = r'''
int main(void) {
 unsigned periods[]={2,10,50};
 for(unsigned p=0;p<3;p++) {
  s_dirty=s_retrying=false;now=100;writes=0;settings_mark_dirty();
  while(now<300){settings_tick();assert(!writes);now+=periods[p];}
  settings_tick();assert(writes==1 && !s_dirty);
 }
 // A second change extends debounce; real elapsed time survives timer wrap.
 now=UINT32_MAX-100;writes=0;settings_mark_dirty();now+=150;settings_mark_dirty();
 now+=199;settings_tick();assert(!writes);now++;settings_tick();assert(writes==1);
 // Failed explicit flush retains data and uses a full one-second retry delay.
 fail=true;settings_mark_dirty();assert(!settings_flush() && s_dirty && s_retrying);
 unsigned before=writes;now+=999;settings_tick();assert(writes==before);
 fail=false;now++;settings_tick();assert(writes==before+1 && !s_dirty && !s_retrying);
 // A callback update arriving during commit cannot be marked clean by success.
 change_during_commit=true;settings_mark_dirty();assert(settings_flush() && s_dirty);
 now+=200;settings_tick();assert(!s_dirty);
 puts("Settings real-time debounce, wrap, retry and concurrent-dirty retention passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)
    (path/'test.c').write_text(fixture+'\n'.join(function('src/settings.c',name) for name in ('settings_mark_dirty','settings_tick','settings_flush'))+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
