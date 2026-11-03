"""Production timer only publishes intent; button/BT operations run in main."""
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import function,ROOT

fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdio.h>
typedef struct {unsigned unused;} repeating_timer_t;
static atomic_bool bootsel_poll_pending;
static unsigned locks,polls;
static bool irq;
static void *cyw43_arch_async_context(void){return &locks;}
static void async_context_acquire_lock_blocking(void *p){assert(!irq && p==&locks && !locks);locks++;}
static void async_context_release_lock(void *p){assert(p==&locks && locks==1);locks--;}
static void check_bootsel_state(void){assert(!irq && locks==1);polls++;}
'''
tests=r'''
int main(void) {
 bootsel_main_work(false);assert(!polls);
 irq=true;for(unsigned i=0;i<100;i++)assert(bootsel_timer_callback(NULL));
 assert(!polls && !locks);irq=false;
 bootsel_main_work(false);assert(polls==1 && !locks);
 bootsel_main_work(false);assert(polls==1);
 bootsel_timer_callback(NULL);bootsel_main_work(true);assert(polls==1 && !locks);
 bootsel_timer_callback(NULL);bootsel_main_work(false);assert(polls==2);
 puts("BOOTSEL timer/main context and radio-absent gating passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp);(path/'test.c').write_text(fixture+function('src/main.c','bootsel_timer_callback')+function('src/main.c','bootsel_main_work')+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
