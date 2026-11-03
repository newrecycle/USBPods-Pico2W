"""Execute the adapter's actual event/work bodies against mocked SDK calls."""
from pathlib import Path
import os
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
 event(A2DP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED,0x45);assert(s_avdtp_cid==0x45);
 puts("Relay stale events, STOP-over-START and signaling ownership passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    (path / 'test.c').write_text((ROOT / 'tests/relay_lifecycle_mocks.h').read_text() + function('packet_handler') + function('bt_sink_relay_work') + tests)
    subprocess.run(['cc', '-std=c11', '-O1', '-fsanitize=address,undefined', '-I', str(ROOT / 'src/btstack'), str(path / 'test.c'), str(ROOT / 'src/btstack/relay_rtp.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True, env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
