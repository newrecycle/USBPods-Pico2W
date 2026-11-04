#!/usr/bin/env python3
"""Independent regressions for main 6be2889. The reviewed tree fails all three.

Linux/WSL: python3 tools/review_regressions_6be2889.py --fdk-lib PATH
Exit 1 means an invariant failed; compilation failures are recorded separately.
Generated C fixtures and logs are retained in --output (ignored build directory).
No hardware, network, flashing or production source mutation is performed.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_source_boundaries import function

QUEUE_FIXTURE=r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#define AUDIO_SLOT_COUNT_MAX 6
#define AUDIO_SLOT_COUNT_SBC 6
typedef struct{uint8_t data[6],read,write,count;} queue_t;
static queue_t free_queue,ready_queue;
static struct{int16_t data[960];} slot_pool[6];
static unsigned active_slot_count;
static bool slot_queue_storage_ready,slot_pool_frozen,filling_slot_valid,is_streaming;
static uint8_t filling_slot_idx;
static uint16_t filling_offset,slot_frame_int16=960,usb_sw_gain_q15=32768;
static uint32_t usb_slot_push_drops,usb_slot_ready_full_drops;
static bool inject;
void audio_slot_push_samples(const int16_t*,uint16_t);
static void queue_init(queue_t*q,unsigned size,unsigned cap){assert(size==1&&cap==6);memset(q,0,sizeof *q);}
static bool queue_try_add(queue_t*q,const uint8_t*v){if(q->count==6)return false;q->data[q->write]=*v;q->write=(q->write+1)%6;q->count++;return true;}
static bool queue_try_remove(queue_t*q,uint8_t*v){
 if(!q->count)return false;
 *v=q->data[q->read];q->read=(q->read+1)%6;q->count--;
 // Interrupt after the queue operation, when its per-operation lock is released.
 if(q==&free_queue && inject){
   inject=false;
   int16_t host_pcm[960]={0};audio_slot_push_samples(host_pcm,480);
 }
 return true;
}
'''
QUEUE_TEST=r'''
int main(void){
 audio_slot_queue_init();inject=true;audio_slot_queue_init();
 unsigned used[6]={0};
 for(unsigned i=0;i<ready_queue.count;i++)used[ready_queue.data[(ready_queue.read+i)%6]]++;
 for(unsigned i=0;i<free_queue.count;i++)used[free_queue.data[(free_queue.read+i)%6]]++;
 for(unsigned i=0;i<6;i++)if(used[i]!=1)printf("slot %u has %u owners after USB interrupt during reset\n",i,used[i]);
 fflush(stdout);for(unsigned i=0;i<6;i++)assert(used[i]==1);
}
'''
PENDING_TEST=r'''
 connected();finish_scan_avdtp_codec=false;is_streaming=false;
 eld_transition_configured(&src_eld_change);src_stream_start_accepted();
 assert(src_start_accepted_pending);src_stream_suspend_accepted();
 assert(src_eld_change.phase==ELD_REBUILD);finish_scan_avdtp_codec=true;
 assert(!src_pump_start_pending());
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fdk-lib',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'build-independent-review')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
    results=[]
    def execute(name,cmd,timeout=120):
        r=subprocess.run(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
        (out/(name+'.txt')).write_text(r.stdout)
        return r
    def compile_run(name,cmd,binary):
        r=execute(name+'-compile',cmd)
        if r.returncode:
            results.append(dict(name=name,status='COMPILE_FAILED',returncode=r.returncode));return
        r=execute(name,[str(binary)])
        results.append(dict(name=name,status='PASS' if not r.returncode else 'FAIL',returncode=r.returncode,log=name+'.txt'))
    flags=['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined']
    src='src/btstack/btstack_avdtp_source.c'
    c=out/'queue-reset.c'
    c.write_text(QUEUE_FIXTURE+function(src,'audio_slot_queue_init')+function(src,'audio_slot_push_samples')+QUEUE_TEST)
    compile_run('queue-reset',flags+[str(c),'-o',str(out/'queue-reset')],out/'queue-reset')

    tree=ast.parse((ROOT/'tests/test_eld_adapter.py').read_text());v={}
    for n in tree.body:
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('tests','names'):
            v[n.targets[0].id]=ast.literal_eval(n.value)
    tests=v['tests'].replace(' puts("Production ELD adapter:',PENDING_TEST+' puts("Production ELD adapter:')
    assert tests!=v['tests'],'Adapter test anchor changed; update the review fixture'
    c=out/'pending-start.c'
    c.write_text((ROOT/'tests/eld_adapter_mocks.h').read_text()+'\n#define CODEC_ID_NONE 0\n'+
                 '\n'.join(function(src,n) for n in v['names']+['src_pump_start_pending'])+tests)
    cmd=flags+['-O1','-I','tests/encoder_mocks','-I','src/btstack',str(c),
               'src/btstack/eld_transition.c','src/btstack/eld_profile.c','-o',str(out/'pending-start')]
    compile_run('pending-start',cmd,out/'pending-start')

    if a.fdk_lib:
        # Include the actual module unchanged, adding only read-only inspection
        # of its private clear-history epoch. All decode calls are production.
        wrapper=out/'mic-history-module.c'
        wrapper.write_text('#include '+json.dumps(str(ROOT/'src/btstack/aacp_mic_audio.c'))+
                           '\nuint32_t review_cleared_epoch(void){return last_epoch;}\n')
        s=(ROOT/'tests/test_eld_duplex_fdk.c').read_text()
        s=s.replace('int main(void){','uint32_t review_cleared_epoch(void);\nint main(void){')
        needle='fdk_alloc_report();aacEncClose';assert needle in s
        s=s.replace(needle,'aacp_mic_audio_report();printf("[review] cleared_epoch=%u active_epoch=%u\\n",review_cleared_epoch(),aacp_mic_generation());assert(review_cleared_epoch()==aacp_mic_generation());'+needle)
        c=out/'mic-history.c';c.write_text(s)
        cmd=next(x['argv'] for x in json.loads((ROOT/'tests/offline-commands.json').read_text()) if x['name']=='compile eld-duplex')
        cmd=[x.replace('{FDK}',str(a.fdk_lib.resolve())).replace('{TMP}',str(out)).replace('tests/test_eld_duplex_fdk.c',str(c)).replace('src/btstack/aacp_mic_audio.c',str(wrapper)) for x in cmd]
        binary=out/'eld-duplex';compile_run('mic-history',cmd,binary)
    else:results.append(dict(name='mic-history',status='SKIP',reason='Supply an ASan-instrumented native FDK archive'))
    summary={'reviewed_commit':'6be28899efba385d805e1c7c7cd3c3041b562b5b','hardware_run':False,'results':results}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    for r in results:print(r['status']+' '+r['name'])
    print(out/'summary.json')
    return int(any(r['status'] in ('FAIL','COMPILE_FAILED') for r in results))


if __name__=='__main__':raise SystemExit(main())
