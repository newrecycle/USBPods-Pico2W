"""Execute production encoder scheduling with deterministic IRQ/foreground calls."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source-file',type=Path,default=ROOT/'src/btstack/btstack_avdtp_source.c')
args=p.parse_args()
source=args.source_file.read_text()
def function(name):
    m=re.search(r'^(?:static )?(?:void|bool) '+name+r'\([^;]*?\)\s*\{',source,re.M)
    assert m,name
    begin=source.index('{',m.start());end=begin+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[m.start():end]

fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#define CODEC_ID_AACELD 4
#define ELD_READY 1
typedef struct {uint32_t samples_ready;bool codec_ready_to_send;unsigned frames;} a2dp_media_sending_context_t;
static a2dp_media_sending_context_t media_tracker;
static volatile bool src_eld_encode_requested;
static bool is_streaming=true,src_fault_hold,src_user_dc_hold,src_eld_reset_pending,in_irq;
static unsigned cur_codec=4,acc_num_simples=480,locks,encoded,mic_passes;
static struct {unsigned phase;} src_eld_change={ELD_READY};
static void *cyw43_arch_async_context(void){return &locks;}
static void async_context_acquire_lock_blocking(void *p){assert(p==&locks);locks++;}
static void async_context_release_lock(void *p){assert(p==&locks && locks);locks--;}
static void codec_fdk_stage_eld_packet(a2dp_media_sending_context_t *c){
 assert(!in_irq && locks); /* the old production timer call fails here */
 if(c->codec_ready_to_send || c->samples_ready<480)return;
 c->samples_ready-=480;c->frames++;encoded++;
 if(c->frames==2)c->codec_ready_to_send=true;
}
'''
if 'static void codec_fdk_request_eld_packet(' in source:
    bodies='\n'.join(function(n) for n in ('codec_fdk_request_eld_packet','src_eld_encode_work','a2dp_source_main_pending'))
else:
    # Preserve the archived timer's actual case body for the negative control.
    begin=source.index('        case 4:   /* Apple AAC-ELD: encode on Core 0')
    end=source.index('            break;',begin)
    bodies='static void codec_fdk_request_eld_packet(a2dp_media_sending_context_t *context){'+source[source.index('\n',begin)+1:end]+'}\n'
    bodies+='static void src_eld_encode_work(void){(void)src_eld_encode_requested;}\n'
    bodies+='bool a2dp_source_main_pending(void){return false;}\n'

tests=r'''
int main(void){
 (void)cyw43_arch_async_context;(void)async_context_acquire_lock_blocking;(void)async_context_release_lock;(void)acc_num_simples;
 media_tracker.samples_ready=1440;
 in_irq=true;codec_fdk_request_eld_packet(&media_tracker);codec_fdk_request_eld_packet(&media_tracker);in_irq=false;
 assert(!encoded && a2dp_source_main_pending());
 mic_passes++;src_eld_encode_work();assert(encoded==1 && media_tracker.frames==1 && !locks);
 assert(a2dp_source_main_pending());
 mic_passes++;src_eld_encode_work();assert(encoded==2 && media_tracker.codec_ready_to_send && mic_passes==2);
 assert(!a2dp_source_main_pending());
 // Pending grants freeze packet contents, including a repeated timer tick.
 in_irq=true;codec_fdk_request_eld_packet(&media_tracker);in_irq=false;src_eld_encode_work();assert(encoded==2);
 // A grant releases the packet; remaining credit is serviced by the next tick.
 media_tracker.frames=0;media_tracker.codec_ready_to_send=false;
 codec_fdk_request_eld_packet(&media_tracker);src_eld_encode_work();assert(encoded==3 && !a2dp_source_main_pending());
 // Empty input cannot create an unbounded foreground spin.
 media_tracker.samples_ready=0;codec_fdk_request_eld_packet(&media_tracker);src_eld_encode_work();
 assert(encoded==3 && !a2dp_source_main_pending() && !locks);
 // Obsolete requests cannot revive a suspended, torn-down or rebuilding owner.
 for(unsigned gate=0;gate<6;gate++){
  media_tracker.samples_ready=480;codec_fdk_request_eld_packet(&media_tracker);
  switch(gate){case 0:is_streaming=false;break;case 1:src_fault_hold=true;break;
   case 2:src_user_dc_hold=true;break;case 3:src_eld_reset_pending=true;break;
   case 4:src_eld_change.phase=0;break;default:cur_codec=1;break;}
  src_eld_encode_work();assert(encoded==3 && !a2dp_source_main_pending() && !locks);
  is_streaming=true;src_fault_hold=src_user_dc_hold=src_eld_reset_pending=false;
  src_eld_change.phase=ELD_READY;cur_codec=4;
 }
 puts("Production foreground ELD: no IRQ encoding, one AU per mic pass, bounded catch-up and lifecycle gates passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    out=Path(temp);(out/'test.c').write_text(fixture+bodies+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-DUSBPODS_MIC_DECODE=1',
                    '-fsanitize=address,undefined',str(out/'test.c'),'-o',str(out/'test')],check=True)
    subprocess.run([str(out/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
