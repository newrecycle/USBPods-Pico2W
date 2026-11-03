"""Couple production USB capture intent, AACP commands and ELD recovery owner.

Only the SDK/peer and encoder allocation are simulated here. Real codec/audio
fidelity remains covered by the separate FDK duplex and PCM packet tests.
"""
import ast
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import ROOT, function


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


adapter = ast.parse((ROOT/'tests/test_eld_adapter.py').read_text())
values = {n.targets[0].id: ast.literal_eval(n.value) for n in adapter.body
          if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
          and n.targets[0].id in ('names', 'tests')}
mocks = (ROOT/'tests/eld_adapter_mocks.h').read_text()
mocks = replace_once(mocks, 'static struct {uint8_t eld_rate,game_level;} config;',
                     '#include "settings.h"\n#define config (*settings())\nextern bool aap_get_game(void);')
mocks = replace_once(mocks, 'config.eld_rate,game,config.game_level',
                     'config.eld_rate,aap_get_game(),config.game_level')
mocks = replace_once(mocks, 'static void aap_set_jitter_raw(uint8_t ms){jitters++;last_jitter=ms;}',
                     'extern void fixture_jitter(uint8_t);\nstatic void aap_set_jitter_raw(uint8_t ms){jitters++;last_jitter=ms;fixture_jitter(ms);}')
mocks = replace_once(mocks, ' assert(locks && (src_eld_change.phase',
                     ' extern bool fixture_in_callback;assert(!fixture_in_callback);\n assert(locks && (src_eld_change.phase')
source = mocks + '\n'.join(function('src/btstack/btstack_avdtp_source.c', n)
                            for n in values['names'])
source += values['tests'].split('static void request(')[0]
source += r'''
void fixture_source_init(void){connected();assert(src_event_matches_headset(0x42));}
uint32_t fixture_source_time(void){return now;}
void fixture_source_advance(uint32_t ms){advance(ms);}
void fixture_source_suspend(void){src_stream_suspend_accepted();}
void fixture_source_start(void){src_stream_start_accepted();}
void fixture_source_work(void){a2dp_source_main_work();}
void fixture_source_defer(void){src_eld_schedule_setup();}
void fixture_source_reject(void){assert(src_eld_signaling_rejected(AVDTP_SI_START));}
bool a2dp_source_is_playing(void){return is_streaming;}
void a2dp_source_on_aap_wake(void){}
uint32_t fixture_source_get(unsigned field){
 switch(field){
 case 0:return src_eld_change.phase;case 1:return suspends;
 case 2:return rebuild_calls;case 3:return starts;case 4:return pumps;
 case 5:return is_streaming;case 6:return disconnects;
 case 7:return src_eld_change.requested;case 8:return src_eld_change.built;
 case 9:return built_bitrate;case 10:return locks;
 default:assert(!"unknown source field");return 0;
 }
}
'''

channel = (ROOT/'tests/test_aacp_transport.c').read_text().split('int main(void){')[0]
channel = replace_once(channel, 'bool a2dp_source_is_playing(void){return true;}\nvoid a2dp_source_on_aap_wake(void){}', '')
begin = channel.index('static unsigned rate_sequence,')
end = channel.index('static btstack_packet_handler_t callback;', begin)
channel = channel[:begin] + channel[end:]
channel = replace_once(channel, 'static uint32_t now,epochs;', 'static uint32_t epochs;')
channel = replace_once(channel, 'uint32_t btstack_run_loop_get_time_ms(void){return now;}',
                       'extern uint32_t fixture_source_time(void);\nuint32_t btstack_run_loop_get_time_ms(void){return fixture_source_time();}')
channel = replace_once(channel, 'static bool capture=true;',
                       'static bool capture=true,can_send_pending;\nbool fixture_in_callback;')
channel = replace_once(channel, 'uint8_t l2cap_request_can_send_now_event(uint16_t cid){assert(cid==0x42);return request_rc;}',
                       'uint8_t l2cap_request_can_send_now_event(uint16_t cid){assert(cid==0x42);can_send_pending=!request_rc;return request_rc;}')
channel = replace_once(channel, 'static void send_now(void){aacp_mic_poll();event(L2CAP_EVENT_CAN_SEND_NOW,0x42);}',
                       'static void send_now(void){aacp_mic_poll();if(can_send_pending){can_send_pending=false;fixture_in_callback=true;event(L2CAP_EVENT_CAN_SEND_NOW,0x42);fixture_in_callback=false;}}')
channel += r'''
#include "eld_transition.h"
#include "usb_capture_lifecycle.h"
enum {PHASE,SUSPENDS,BUILDS,STARTS,PUMPS,STREAMING,DROPS,REQUESTED,BUILT,BITRATE,LOCKS};
void fixture_source_init(void);
void fixture_source_advance(uint32_t);
void fixture_source_suspend(void);
void fixture_source_start(void);
void fixture_source_work(void);
void fixture_source_defer(void);
void fixture_source_reject(void);
uint32_t fixture_source_get(unsigned);
void fixture_jitter(uint8_t v){aap_set_jitter_raw(v);}
void aacp_mic_set_capture(bool on){capture=on;}
static uint32_t get(unsigned field){return fixture_source_get(field);}
static void tick(uint32_t ms){fixture_source_advance(ms);aacp_mic_poll();}
static void usb_alt(bool on){
 unsigned before=get(SUSPENDS),built=get(BUILDS);
 fixture_in_callback=true;usb_capture_set_alt(on);fixture_in_callback=false;
 assert(get(SUSPENDS)==before && get(BUILDS)==built); // IRQ publishes intent only.
}
static void setup(void){
 aap_disconnect();memset(&config,0,sizeof config);fixture_source_init();
 usb_capture_mount();assert(!capture);send_rc=request_rc=0;can_send_pending=false;
 bd_addr_t addr={1,2,3,4,5,6};aap_connect(addr);tick(1500);
 event(L2CAP_EVENT_CHANNEL_OPENED,0x42);
 send_now();send_now();send_now();
 uint8_t ack[]={1,0,4,0,1,0};callback(L2CAP_DATA_PACKET,0x42,ack,sizeof ack);
 assert(aap_protocol_seen() && get(STREAMING) && !get(SUSPENDS));
}
static void start_mic(void){usb_alt(true);send_now();assert(last_len==19);}
static void finish_recovery(void){
 assert(get(PHASE)==ELD_WAIT_SUSPEND);unsigned built=get(BUILDS);
 fixture_in_callback=true;fixture_source_suspend();fixture_in_callback=false;
 assert(get(BUILDS)==built && get(PHASE)==ELD_REBUILD);
 fixture_source_work();assert(get(BUILDS)==built+1 && get(PHASE)==ELD_WAIT_START);
 fixture_source_start();assert(get(STREAMING) && get(PHASE)==ELD_READY);
 assert(get(REQUESTED)==get(BUILT) && !get(DROPS) && !get(LOCKS));
}
int main(void){
 aacp_mic_init();
 // Normal duplex start/stop drives real SUSPEND/build/START, not a call counter.
 setup();start_mic();assert(aap_control_diagnostics().mic_recovery_pending);
 tick(799);assert(!get(SUSPENDS));tick(1);assert(get(SUSPENDS)==1);
 finish_recovery();assert(aap_control_diagnostics().mic_started);
 usb_alt(false);send_now();assert(last_len==12 && get(SUSPENDS)==1);
 aacp_mic_poll();assert(get(SUSPENDS)==2);finish_recovery();
 assert(!aap_control_diagnostics().mic_started && !capture);
 tick(1000);assert(get(SUSPENDS)==2);

 // A late STOP supersedes a not-yet-due START recovery.
 setup();start_mic();tick(400);usb_alt(false);send_now();
 aacp_mic_poll();assert(get(SUSPENDS)==1);finish_recovery();
 tick(1000);assert(get(SUSPENDS)==1 && !capture);

 // No old recovery while the most recent command failed on the wire.
 setup();start_mic();tick(400);usb_alt(false);send_rc=1;send_now();
 tick(800);assert(!get(SUSPENDS));send_rc=0;send_now();aacp_mic_poll();
 assert(get(SUSPENDS)==1);finish_recovery();

 // Recovery coalesces into a profile change still awaiting SUSPEND.
 setup();start_mic();tick(400);assert(aap_set_eld_profile(1,true,2));
 assert(get(SUSPENDS)==1);tick(400);assert(get(SUSPENDS)==1);
 finish_recovery();assert(get(BUILDS)==1 && get(BITRATE)==192000);

 // If START is already in flight, the recovery needs one later reset.
 setup();start_mic();tick(400);assert(aap_set_eld_profile(1,true,2));
 fixture_source_suspend();fixture_source_work();assert(get(PHASE)==ELD_WAIT_START);
 tick(400);assert(get(SUSPENDS)==1);
 fixture_source_start();assert(get(SUSPENDS)==2 && !get(STREAMING));
 finish_recovery();assert(get(BUILDS)==2 && get(BITRATE)==192000);

 // Initial deferred allocation is still owned by main, with mic START active.
 setup();fixture_source_defer();start_mic();fixture_source_work();
 assert(get(BUILDS)==1 && get(PHASE)==ELD_WAIT_START);tick(800);
 fixture_source_start();assert(get(SUSPENDS)==1);finish_recovery();

 // A rejected recovery START enters fault hold rather than resuming the pump.
 setup();start_mic();tick(800);fixture_source_suspend();fixture_source_work();
 fixture_source_reject();assert(get(DROPS)==1 && !get(STREAMING));
 usb_alt(false);send_now();aacp_mic_poll();tick(1000);
 assert(get(DROPS)==1 && !get(STREAMING) && get(BUILDS)==1);

 // Endpoint bounce before sending does not send an obsolete STOP.
 setup();start_mic();tick(800);finish_recovery();unsigned before=get(SUSPENDS);
 usb_alt(false);aacp_mic_poll();usb_alt(true);send_now();
 tick(1000);assert(get(SUSPENDS)==before && capture);

 // Channel teardown cancels the delayed recovery and stale send-now event.
 setup();start_mic();tick(400);aap_disconnect();tick(1000);
 event(L2CAP_EVENT_CAN_SEND_NOW,0x42);assert(!get(SUSPENDS) && get(STREAMING));
 assert(!aap_control_diagnostics().mic_recovery_pending && locks==0);
 puts("Coupled USB/AACP/ELD recovery: START/STOP, wire retries, profile races and teardown passed");
}
'''

with tempfile.TemporaryDirectory() as temp:
    out = Path(temp)
    (out/'source.c').write_text(source)
    (out/'channel.c').write_text(channel)
    args = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1',
            '-fsanitize=address,undefined']
    for inc in ('tests/encoder_mocks', 'tests/transport_mocks', 'tests', 'src/btstack', 'src/tinyusb', 'src'):
        args += ['-I', str(ROOT/inc)]
    args += [str(out/'source.c'), str(out/'channel.c')]
    for file in ('aacp_mic.c', 'aacp_control.c', 'aacp_mic_protocol.c', 'media_input.c', 'eld_transition.c', 'eld_profile.c'):
        args.append(str(ROOT/'src/btstack'/file))
    args += [str(ROOT/'src/tinyusb/usb_capture_lifecycle.c'), '-o', str(out/'test')]
    subprocess.run(args, check=True)
    result = subprocess.run([str(out/'test')], capture_output=True, text=True,
                            env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
    if result.returncode:
        print(result.stdout[-3000:] + result.stderr[-3000:])
        raise SystemExit(result.returncode)
    print(result.stdout.splitlines()[-1])
