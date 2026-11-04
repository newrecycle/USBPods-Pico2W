"""Couple production USB capture intent, AACP commands and ELD recovery owner.

Only the SDK/peer and encoder allocation are simulated here. Real codec/audio
fidelity remains covered by the separate FDK duplex and PCM packet tests.
"""
import ast
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import ROOT, function

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--channel-source',type=Path,default=ROOT/'src/btstack/aacp_mic.c')
parser.add_argument('--probe',action='store_true',help='Only reproduce an ignored initial START')
options=parser.parse_args()


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
void fixture_source_force(void){a2dp_source_recover_eld_stream();}
void fixture_source_early_start(void){
 is_streaming=false;finish_scan_avdtp_codec=false;
 eld_transition_configured(&src_eld_change);src_stream_start_accepted();
 assert(src_start_accepted_pending && !src_pump_start_pending());
}
void fixture_source_finish_scan(void){
 finish_scan_avdtp_codec=true;if(src_pump_start_pending())src_pump_start();
}
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
void fixture_source_force(void);
void fixture_source_early_start(void);
void fixture_source_finish_scan(void);
uint32_t fixture_source_get(unsigned);
void fixture_jitter(uint8_t v){aap_set_jitter_raw(v);}
void aacp_mic_set_capture(bool on){if(capture!=on)epochs++;capture=on;}
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
static void audio_packet(uint16_t channel,bool valid){
 uint8_t data[28]={4,0,4,0,0x58,0,1,0};data[26]=1;data[27]=0xaa;
 callback(L2CAP_DATA_PACKET,channel,data,valid?sizeof data:sizeof data-1);
}
static void audio(void){audio_packet(0x42,true);}
static void playback_untouched(void){assert(!get(SUSPENDS) && !get(BUILDS) && get(STREAMING) && !get(DROPS));}
int main(int argc,char **argv){
 (void)argv;
 aacp_mic_init();
 if(argc>1){
   setup();start_mic();tick(2000);send_now();
   assert(last_len==12 && aap_control_diagnostics().mic_retry_count==1);
   playback_untouched();puts("Ignored initial START: bounded AACP retry with uninterrupted playback passed");return 0;
 }
 // Opening/closing capture never pauses, rebuilds or restarts playback.
 setup();start_mic();assert(aap_control_diagnostics().mic_recovery_pending);
 audio();assert(aap_control_diagnostics().mic_audio_seen);
 assert(!aap_control_diagnostics().mic_recovery_pending);
 for(unsigned i=0;i<10;i++){tick(500);audio();send_now();}
 assert(!aap_control_diagnostics().mic_retry_count);playback_untouched();
 usb_alt(false);send_now();assert(last_len==12);tick(1000);playback_untouched();
 assert(!aap_control_diagnostics().mic_started && !capture);

 // An ignored first START is retried, without touching AVDTP.
 setup();start_mic();tick(1999);assert(!aap_control_diagnostics().mic_retry_count);
 tick(1);send_now();assert(last_len==12 && aap_control_diagnostics().mic_retry_count==1);
 assert(!aap_control_diagnostics().mic_started);send_now();assert(last_len==19);
 audio();assert(aap_control_diagnostics().mic_audio_seen);playback_untouched();

 // Only framed audio from this channel satisfies the watchdog.
 setup();start_mic();audio_packet(0x41,true);audio_packet(0x42,false);
 assert(!aap_control_diagnostics().mic_audio_seen);tick(2000);send_now();assert(last_len==12);
 send_now();assert(last_len==19);audio();playback_untouched();

 // Failed retry STOP must not commit the retry or allow a replacement START.
 setup();start_mic();tick(2000);send_rc=1;send_now();
 assert(last_len==12 && !aap_control_diagnostics().mic_retry_count);
 send_rc=0;send_now();assert(last_len==12 && aap_control_diagnostics().mic_retry_count==1);
 send_rc=1;send_now();assert(last_len==19 && !aap_control_diagnostics().mic_started);
 send_rc=0;send_now();assert(last_len==19 && aap_control_diagnostics().mic_started);
 audio();playback_untouched();

 // A valid AU arriving before a queued STOP cancels that unsent retry.
 setup();start_mic();tick(2000);audio();send_now();
 assert(!aap_control_diagnostics().mic_retry_count && aap_control_diagnostics().mic_audio_seen);
 playback_untouched();

 // Three retries, then one final STOP and an observable, held capture fault.
 setup();start_mic();
 for(unsigned i=1;i<=3;i++){
   tick(2000);send_now();assert(last_len==12 && aap_control_diagnostics().mic_retry_count==i);
   send_now();assert(last_len==19);
 }
 tick(2000);assert(aap_control_diagnostics().mic_watchdog_failed);
 send_now();assert(last_len==12 && !aap_control_diagnostics().mic_started);
 tick(1000);send_now();assert(!aap_control_diagnostics().mic_started);
 assert(aap_control_diagnostics().mic_restarts==3 && aap_control_diagnostics().mic_watchdog_failures==1);
 playback_untouched();
 // A new capture generation clears the held fault and gets a fresh budget.
 usb_alt(false);usb_alt(true);send_now();assert(last_len==19);
 assert(!aap_control_diagnostics().mic_watchdog_failed && !aap_control_diagnostics().mic_retry_count);
 audio();playback_untouched();
 // A channel teardown also clears the held fault: a reconnect after the peer
 // drops the channel must be allowed to retry. The counters describe one
 // channel attempt, not the whole boot.
 setup();start_mic();
 for(unsigned i=1;i<=3;i++){tick(2000);send_now();send_now();}
 tick(2000);send_now();assert(aap_control_diagnostics().mic_watchdog_failed);
 aap_disconnect();
 assert(!aap_control_diagnostics().mic_watchdog_failed &&
        !aap_control_diagnostics().mic_retry_count &&
        !aap_control_diagnostics().mic_restarts &&
        !aap_control_diagnostics().mic_watchdog_failures);

 // A close while retry STOP is queued cannot be followed by stale START.
 setup();start_mic();tick(2000);usb_alt(false);send_now();assert(last_len==12);
 tick(1000);send_now();assert(!aap_control_diagnostics().mic_started);playback_untouched();

 // Capture bounce before sending cancels the obsolete STOP.
 setup();start_mic();audio();usb_alt(false);aacp_mic_poll();usb_alt(true);send_now();
 audio();assert(aap_control_diagnostics().mic_started);playback_untouched();

 // A mic retry crosses a profile transition without requesting another rebuild.
 setup();start_mic();assert(aap_set_eld_profile(1,true,2));
 tick(2000);send_now();send_now();assert(get(SUSPENDS)==1);
 finish_recovery();audio();assert(get(BUILDS)==1 && get(BITRATE)==192000);
 // Also cover retry while the profile's START acceptance is outstanding.
 setup();start_mic();assert(aap_set_eld_profile(1,true,2));
 fixture_source_suspend();fixture_source_work();assert(get(PHASE)==ELD_WAIT_START);
 tick(2000);send_now();send_now();audio();fixture_source_start();
 assert(get(SUSPENDS)==1 && get(BUILDS)==1 && get(STREAMING));

 // Main owns initial allocation; mic START does not schedule a second rebuild.
 setup();fixture_source_defer();start_mic();audio();fixture_source_work();fixture_source_start();
 assert(get(BUILDS)==1 && !get(SUSPENDS) && get(STREAMING));
 // Active mic traffic cannot revive a pre-scan START canceled by SUSPEND.
 setup();start_mic();audio();fixture_source_early_start();unsigned before_pumps=get(PUMPS);
 fixture_source_suspend();fixture_source_finish_scan();audio();
 assert(!get(STREAMING) && get(PUMPS)==before_pumps && get(PHASE)==ELD_REBUILD);
 fixture_source_work();fixture_source_start();
 assert(get(STREAMING) && get(PUMPS)==before_pumps+1 && get(BUILDS)==1);
 // Explicit playback recovery remains available, independently of capture.
 setup();start_mic();audio();fixture_source_force();finish_recovery();
 assert(get(SUSPENDS)==1 && get(BUILDS)==1);

 // A failed profile START is not revived by mic STOP or watchdog activity.
 setup();start_mic();assert(aap_set_eld_profile(1,true,2));
 fixture_source_suspend();fixture_source_work();fixture_source_reject();
 assert(get(DROPS)==1 && !get(STREAMING));usb_alt(false);send_now();tick(1000);
 assert(get(DROPS)==1 && !get(STREAMING) && get(BUILDS)==1);

 // Disconnect cancels queued retries and stale CAN_SEND_NOW callbacks.
 setup();start_mic();tick(2000);aap_disconnect();tick(1000);
 event(L2CAP_EVENT_CAN_SEND_NOW,0x42);playback_untouched();
 assert(!aap_control_diagnostics().mic_recovery_pending && locks==0);
 puts("Coupled USB/AACP/ELD: bounded received-audio retries, capture isolation, profile races and teardown passed");
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
    args.append(str(options.channel_source.resolve()))
    for file in ('aacp_control.c', 'aacp_mic_protocol.c', 'media_input.c', 'eld_transition.c', 'eld_profile.c'):
        args.append(str(ROOT/'src/btstack'/file))
    args += [str(ROOT/'src/tinyusb/usb_capture_lifecycle.c'), '-o', str(out/'test')]
    subprocess.run(args, check=True)
    result = subprocess.run([str(out/'test')]+(['probe'] if options.probe else []), capture_output=True, text=True,
                            env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
    if result.returncode:
        print(result.stdout[-3000:] + result.stderr[-3000:])
        raise SystemExit(result.returncode)
    print(result.stdout.splitlines()[-1])
