"""Compile the production first-fault snapshot with a deterministic producer interleave.
Run in firmware CI; this is not an RP2350 scheduling or acoustic test.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'src/btstack/aacp_mic_audio.c').read_text()
start=source.index('void aacp_mic_audio_note_usb_packet(')
body=source[start:source.index('\n#else',start)]
baseline=(ROOT/'tests/fixtures/underrun-snapshot-before-8309def.c').read_text()
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#define AU_SLOTS 32u
#define PCM_SLOTS 16u
#define memory_order_acquire 0
#define memory_order_release 0
#define memory_order_relaxed 0
static uint32_t clock_us;
static uint32_t seen_admitted_au=1, seen_published_pcm=1;
static uint32_t last_admitted_au_us, last_published_pcm_us;
static uint32_t aw=1,ar,pw,pr,usb_packet_generation=1,usb_packet_available;
static uint32_t usb_postprime_underruns;
static bool usb_primed_this_generation=true,usb_first_written,usb_packet_rebuffered;
static struct { uint32_t valid,generation,at_us,requested,supplied,au_depth,pcm_depth,
 available,au_age_us,pcm_age_us,rebuffer; } first_usb_fault;
/* Simulate a producer publishing immediately before its timestamp is read.
 * All values are local: this models one legal atomic interleave without a
 * flaky host-thread schedule or changing the extracted production body. */
static uint32_t load(uint32_t *p) {
 if(p==&last_admitted_au_us || p==&last_published_pcm_us) *p=++clock_us;
 return *p;
}
#define atomic_load_explicit(p,order) load(p)
#define atomic_store_explicit(p,value,order) (*(p)=(value))
#define atomic_fetch_add_explicit(p,value,order) (*(p)+=(value))
static uint32_t time_us_32(void){return clock_us;}
'''
main=r'''
int main(int argc,char **argv) {
 clock_us=argc>1?(uint32_t)strtoul(argv[1],0,10):100;
 aacp_mic_audio_note_usb_packet(64,0);
 assert(first_usb_fault.valid && first_usb_fault.requested==64);
 assert(first_usb_fault.au_age_us<=2 && first_usb_fault.pcm_age_us<=2);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as temp:
    d=Path(temp)
    for name,implementation in [('current',body),('before',baseline)]:
        c=d/(name+'.c');exe=d/name;c.write_text(fixture+implementation+main)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(c),'-o',str(exe)],check=True)
        for clock in ('100','4294967294'):
            result=subprocess.run([str(exe),clock],capture_output=True,text=True)
            if name=='current':
                assert result.returncode==0,result.stderr
            else:
                assert result.returncode<0 and 'first_usb_fault.au_age_us<=2' in result.stderr,result.stderr
print('Producer interleave and timer-wrap ages passed; archived production body failed both controls')
