"""Compile the production pre-encoder diagnostic; run in GitHub Actions only."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'src/btstack/btstack_avdtp_source.c').read_text()
start = source.index('static void src_eld_pcm_tap_note(')
begin = source.index('{', start)
end, depth = begin + 1, 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
body = source[start:end]
fill = source[source.index('int codec_fdk_fill('):source.index('static void codec_fdk_stage_eld_packet(')]
assert fill.index('src_eld_pcm_tap_note(') < fill.index('err = aacEncEncode(')
assert 'aacinf.inputChannels==2' in fill
assert '(uint32_t)in_args.numInSamples/2u' in fill

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
volatile bool usb_pcm_tap=true;
static uint32_t now,gen=1;
static bool capture;
static uint32_t time_us_32(void){return now;}
static uint32_t aacp_mic_generation(void){return gen;}
static bool aacp_mic_capture(void){return capture;}
'''
checks = r'''
int main(void){
 int16_t left[]={-32768,0,1200,0},right[]={0,1100,0,-900};
 now=1;src_eld_pcm_tap_note(left,2);
 now=500001;src_eld_pcm_tap_note(left,2);
 assert(left[0]==-32768 && !left[1] && left[2]==1200 && !left[3]);
 capture=true;gen++;now=600001;src_eld_pcm_tap_note(right,2);
 now=1100001;src_eld_pcm_tap_note(right,2);
 capture=false;gen++;now=1200001;src_eld_pcm_tap_note(left,2);
 gen++;now=1700001;src_eld_pcm_tap_note(left,2);
 // Disabled diagnostics clear the previous window and never print.
 now=1800001;src_eld_pcm_tap_note(left,2);
 usb_pcm_tap=false;src_eld_pcm_tap_note(left,2);
 usb_pcm_tap=true;capture=true;gen++;
 now=UINT32_MAX-99u;src_eld_pcm_tap_note(right,2);
 now=500000;src_eld_pcm_tap_note(right,2);
 assert(right[1]==1100 && right[3]==-900);
}
'''
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp)
    (path / 'tap.c').write_text(fixture + body + checks)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', str(path / 'tap.c'), '-o', str(path / 'tap')], check=True)
    output = subprocess.check_output([str(path / 'tap')], text=True,
                                    env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
rows = re.findall(r'\[eld-pcm\] frames=(\d+) peak_l=(\d+) peak_r=(\d+) mic=(\w+) gen=(\d+)', output)
assert rows == [('4', '32768', '0', 'closed', '1'), ('4', '0', '1100', 'open', '2'),
                ('4', '32768', '0', 'transition', '4'), ('4', '0', '1100', 'open', '5')], rows
print('Production encoder PCM tap: channel isolation, lifecycle fencing, clock wrap and disabled reset passed')
