"""Execute the adapter's actual event/work bodies against mocked SDK calls."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'src/btstack/btstack_sink_relay.c').read_text()

def function(name):
    start = source.index('static void ' + name + '(') if 'static void ' + name + '(' in source else source.index('bool ' + name + '(')
    begin = source.index('{', start)
    depth, end = 1, begin + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

tests = r'''
static void event(uint8_t type,uint8_t cid){uint8_t p[]={HCI_EVENT_A2DP_META,0,type,cid,0};packet_handler(HCI_EVENT_PACKET,0,p,sizeof p);}
static uint8_t s_headset_mac[6]={3,3,3,3,3,3};
/* Real 14-byte A2DP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED layout. */
static void sig_established(uint16_t cid,const uint8_t*mac,uint8_t status){
 uint8_t p[14]={HCI_EVENT_A2DP_META,12,A2DP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED,
                (uint8_t)(cid&0xff),(uint8_t)(cid>>8)};
 for(int i=0;i<6;i++)p[5+i]=mac[5-i];   /* accessor byte-reverses [5..10] */
 p[13]=status;
 packet_handler(HCI_EVENT_PACKET,0,p,sizeof p);
}
int main(void){
 s_connected=true;s_avdtp_cid=0x42;
 event(A2DP_SUBEVENT_STREAM_STARTED,0x42);
 event(A2DP_SUBEVENT_STREAM_SUSPENDED,0x42);
 bt_sink_relay_work();assert(!s_streaming);
 event(A2DP_SUBEVENT_STREAM_STARTED,0x42);
 event(A2DP_SUBEVENT_SIGNALING_CONNECTION_RELEASED,0x41);
 assert(s_connected && s_avdtp_cid==0x42);bt_sink_relay_work();assert(s_streaming);
 event(A2DP_SUBEVENT_STREAM_RELEASED,0x42);bt_sink_relay_work();
 assert(!s_streaming && s_avdtp_cid==0x42);
 event(A2DP_SUBEVENT_SIGNALING_CONNECTION_RELEASED,0x42);bt_sink_relay_work();
 assert(!s_streaming && !s_avdtp_cid);
 // A signaling-established event must carry the real 14-byte shape and the
 // address decides ownership: a headset address is never adopted as the phone,
 // a failed status is ignored, and a mismatching cid cannot steal a live link.
 sig_established(0x46,s_headset_mac,0);assert(!s_avdtp_cid);
 sig_established(0x46,s_phone_mac,1);assert(!s_avdtp_cid);
 sig_established(0x46,s_phone_mac,0);assert(s_avdtp_cid==0x46);
 sig_established(0x47,s_phone_mac,0);assert(s_avdtp_cid==0x46);
 puts("Relay stale events, STOP-over-START and signaling ownership passed");
}
'''
# The mock ring depth must track production, not a stale copy.
prod_n = int(re.search(r'#define RELAY_PKT_N\s+(\d+)', source).group(1))
mock_src = (ROOT / 'tests/relay_lifecycle_mocks.h').read_text()
mock_n = int(re.search(r'#define RELAY_PKT_N\s+(\d+)', mock_src).group(1))
assert prod_n == mock_n, f'relay mock ring depth {mock_n} != production {prod_n}'
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    (path / 'test.c').write_text(mock_src + function('packet_handler') + function('bt_sink_relay_work') + tests)
    subprocess.run(['cc', '-std=c11', '-O1', '-fsanitize=address,undefined', '-I', str(ROOT / 'src/btstack'), str(path / 'test.c'), str(ROOT / 'src/btstack/relay_rtp.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True, env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
