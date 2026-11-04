"""Inject USB producer IRQs at queue operations during production PCM reset."""
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import function

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define AUDIO_SLOT_COUNT_MAX 9
#define AUDIO_SLOT_COUNT_SBC 6
typedef struct { uint8_t data[9],read,write,count; } queue_t;
static queue_t free_queue,ready_queue;
static struct {int16_t data[960];} slot_pool[9];
static unsigned active_slot_count,allocations,operation,interrupt_at;
static bool slot_queue_storage_ready,slot_pool_frozen,filling_slot_valid,is_streaming;
static bool irq_pending;
static uint32_t irq_mask,usb_slot_push_drops,usb_slot_ready_full_drops;
static uint8_t filling_slot_idx;
static uint16_t filling_offset,slot_frame_int16=960,usb_sw_gain_q15=32768;
void audio_slot_push_samples(const int16_t*,uint16_t);
static void deliver_irq(void) {
 if(irq_mask){irq_pending=true;return;}
 irq_pending=false;int16_t pcm[960]={0};audio_slot_push_samples(pcm,480);
}
static void after_operation(void) {
 if(++operation==interrupt_at)deliver_irq();
}
static uint32_t save_and_disable_interrupts(void) {
 uint32_t old=irq_mask;irq_mask=1;return old;
}
static void restore_interrupts(uint32_t old) {
 irq_mask=old;if(!old && irq_pending)deliver_irq();
}
static void queue_init(queue_t *q,unsigned size,unsigned cap) {
 assert(size==1 && cap==9);allocations++;memset(q,0,sizeof *q);
}
static bool queue_try_add(queue_t *q,const uint8_t *v) {
 bool ok=q->count<9;
 if(ok){q->data[q->write]=*v;q->write=(q->write+1)%9;q->count++;}
 after_operation();return ok;
}
static bool queue_try_remove(queue_t *q,uint8_t *v) {
 bool ok=q->count>0;
 if(ok){*v=q->data[q->read];q->read=(q->read+1)%9;q->count--;}
 after_operation();return ok;
}
'''
tests = r'''
static void ownership(void) {
 unsigned used[9]={0};
 queue_t *queues[]={&ready_queue,&free_queue};
 for(unsigned q=0;q<2;q++)for(unsigned n=0;n<queues[q]->count;n++) {
  unsigned idx=queues[q]->data[(queues[q]->read+n)%9];assert(idx<active_slot_count);used[idx]++;
 }
 if(filling_slot_valid){assert(filling_slot_idx<active_slot_count);used[filling_slot_idx]++;}
 for(unsigned i=0;i<active_slot_count;i++)assert(used[i]==1);
 for(unsigned i=active_slot_count;i<9;i++)assert(!used[i]);
}
int main(void) {
 // Every operation boundary, with empty, partly filled, and full ready queues.
 for(unsigned seed=0;seed<4;seed++)for(unsigned masked=0;masked<2;masked++)
 for(unsigned frozen=0;frozen<2;frozen++)for(unsigned at=1;at<=40;at++) {
  interrupt_at=0;irq_mask=0;irq_pending=false;slot_pool_frozen=false;
  audio_slot_queue_init();
  int16_t pcm[960]={0};
  const unsigned filled[]={0,1,3,6};
  for(unsigned i=0;i<filled[seed];i++)audio_slot_push_samples(pcm,480);
  if(seed&1)audio_slot_push_samples(pcm,17); // incomplete producer-owned slot
  operation=0;interrupt_at=at;irq_mask=masked;slot_pool_frozen=frozen;
  audio_slot_queue_init();
  assert(irq_mask==masked && slot_pool_frozen==frozen);
  ownership();restore_interrupts(0);ownership();
  assert(allocations==2); // repeated resets never allocate from BT callbacks
 }
 puts("PCM reset ownership: 640 IRQ/state interleavings passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)
    source='src/btstack/btstack_avdtp_source.c'
    (path/'test.c').write_text(fixture+function(source,'audio_slot_queue_init')+
                              function(source,'audio_slot_push_samples')+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1',
                    '-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
