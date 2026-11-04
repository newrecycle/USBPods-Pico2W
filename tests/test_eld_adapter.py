"""Run production transition adapters/callbacks with deterministic SDK transport.

Actual FDK fidelity/allocation is checked separately by test_eld_duplex_fdk.c.
This fixture executes production function bodies, not a duplicate state model.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'src/btstack/btstack_avdtp_source.c').read_text()

def function(name):
    match = re.search(r'^(?:static )?(?:void|bool|uint8_t) ' + re.escape(name) + r'\([^;]*?\)\s*\{', source, re.M)
    assert match, name
    begin = source.index('{', match.start())
    depth, end = 1, begin + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]

tests = r'''
static void advance(uint32_t ms) {
 uint32_t target=now+ms;
 for(unsigned budget=0;budget<20;budget++) {
   btstack_timer_source_t *next=NULL,*timers[]={&src_eld_change_timer,&src_jitter_timer};
   for(unsigned i=0;i<2;i++)if(timers[i]->active && (int32_t)(target-timers[i]->deadline)>=0 &&
       (!next || (int32_t)(timers[i]->deadline-next->deadline)<0))next=timers[i];
   if(!next){now=target;return;}
   now=next->deadline;next->active=false;next->handler(next);
 }
 assert(!"unbounded timer loop");
}
static void connected(void) {
 memset(&media_tracker,0,sizeof(media_tracker));media_tracker.avdtp_cid=0x42;media_tracker.local_seid=1;
 memset(&src_eld_change_timer,0,sizeof(src_eld_change_timer));memset(&src_jitter_timer,0,sizeof(src_jitter_timer));
 src_eld_timer_armed=false;src_eld_reset_pending=src_codec_release_pending=false;src_requested_eld_valid=false;
 is_streaming=false;a2dp_is_connected_flag=finish_scan_avdtp_codec=true;
 src_fault_hold=src_user_dc_hold=src_auto_kick_pending=false;src_con_handle=0x123;cur_codec=4;
 src_eld_failures=src_eld_rebuilds=src_eld_last_error=src_eld_max_rebuild_us=0;src_eld_error_stage=0;
 src_suspend_ms=0;src_pending_jitter=150;src_session_streamed=false;core1_encoder_active=false;
 suspends=starts=pumps=disconnects=rebuild_calls=jitters=leds=0;
 suspend_rc=start_rc=encode_rc=0;locks=0;game=relay=false;config.eld_rate=2;config.game_level=1;now=100;
 src_stream_established=true;src_eld_setup_pending=src_eld_early_start=false;opens=open_rc=0;
 registry_releases=0;
 handleAAC=(void*)1;active_slot_count=6;eld_transition_configured(&src_eld_change);
 src_start_stream(0x42,1);src_stream_start_accepted();assert(is_streaming&&pumps==1);
 advance(500);assert(jitters==1);jitters=0;
}
static void request(uint8_t rate,bool gaming,unsigned level) {
 config.eld_rate=rate;game=gaming;config.game_level=level;a2dp_source_apply_eld_rate();
}
int main(void) {
 connected();request(3,true,2);unsigned before=pumps;
 a2dp_source_main_work();assert(!rebuild_calls && starts==1 && suspends==1);
 advance(200);request(1,false,1);assert(suspends==1); // One SUSPEND, latest policy.
 src_stream_start_accepted();assert(pumps==before); // Old START cannot run pump.
 src_stream_suspend_accepted();assert(!is_streaming && !rebuild_calls);
 a2dp_source_main_work();assert(rebuild_calls==1 && starts==2 && built_bitrate==192000);
 assert(pumps==before && !jitters && src_eld_change.phase==ELD_WAIT_START);
 src_stream_start_accepted();assert(is_streaming && pumps==before+1);
 advance(499);assert(!jitters);advance(1);assert(jitters==1 && last_jitter==150);
 src_stream_start_accepted();assert(pumps==before+1); // Duplicate ignored.

 // A request during START waits for acceptance and performs another suspend.
 connected();request(3,false,1);src_stream_suspend_accepted();a2dp_source_main_work();
 request(2,true,2);a2dp_source_main_work();assert(rebuild_calls==1 && starts==2);
 src_stream_start_accepted();assert(suspends==2 && pumps==1 && !jitters);
 src_stream_suspend_accepted();a2dp_source_main_work();assert(rebuild_calls==2 && starts==3);
 assert(built_bitrate==192000 && active_slot_count==4);
 src_stream_start_accepted();advance(500);assert(last_jitter==60 && jitters==1);

 // A SUSPEND accepted while a managed rebuild's START is still outstanding
 // must cancel that START into one bounded rebuild. Waiting for the 3 s
 // deadline would abort and drop the ACL (old ELD_NOTHING behaviour).
 connected();request(3,false,1);src_stream_suspend_accepted();a2dp_source_main_work();
 assert(rebuild_calls==1 && starts==2 && src_eld_change.phase==ELD_WAIT_START);
 unsigned f2_starts=starts,f2_rebuilds=rebuild_calls;
 src_stream_suspend_accepted();
 assert(src_eld_change.phase==ELD_REBUILD && !disconnects);
 a2dp_source_main_work();
 assert(rebuild_calls==f2_rebuilds+1 && starts==f2_starts+1 && !disconnects);
 assert(src_eld_change.phase==ELD_WAIT_START && !is_streaming);
 src_stream_start_accepted();
 assert(is_streaming && !disconnects && src_eld_change.phase==ELD_READY);
 advance(500);assert(jitters==1 && last_jitter==150);

 // Captured 220546: rate=2 builds, then gamelevel 2->1 while game is OFF.
 // The effective profile is identical; accepting the first START must RUN,
 // not immediately issue a second SUSPEND/rebuild/START.
 connected();config.eld_rate=3;config.game_level=2;
 request(2,false,2);src_stream_suspend_accepted();a2dp_source_main_work();
 advance(100);request(2,false,1);src_stream_start_accepted();
 assert(suspends==1 && rebuild_calls==1 && is_streaming);
 uint32_t revision=src_eld_change.requested;
 request(2,false,1);assert(suspends==1 && src_eld_change.requested==revision);
 a2dp_source_recover_eld_stream();assert(suspends==2);
 src_stream_suspend_accepted();a2dp_source_main_work();src_stream_start_accepted();
 assert(is_streaming && rebuild_calls==2 && !disconnects);

 // Rejected/failed SUSPEND never restarts a live pump or opens a new encoder.
 connected();suspend_rc=12;request(3,false,1);a2dp_source_main_work();
 assert(disconnects==1 && pumps==1 && !is_streaming && !rebuild_calls);
 assert(src_user_dc_hold && src_eld_error_stage==1 && src_eld_last_error==12);
 assert(!src_eld_change_timer.active && !src_jitter_timer.active);
 src_stream_start_accepted();assert(pumps==1);request(1,false,1);assert(disconnects==1);
 connected();request(3,false,1);assert(src_eld_signaling_rejected(AVDTP_SI_SUSPEND));
 assert(disconnects==1 && !rebuild_calls);

 // No SUSPEND response: repeated settings cannot move the original deadline.
 connected();request(1,true,1);uint32_t deadline=src_eld_change_timer.deadline;
 advance(2500);request(3,true,2);assert(src_eld_change_timer.deadline==deadline);
 advance(500);assert(disconnects==1 && src_eld_error_stage==4 && !rebuild_calls);

 // Encoder failure does not issue START, send jitter or report streaming.
 connected();request(3,false,1);src_stream_suspend_accepted();encode_rc=33;
 a2dp_source_main_work();assert(!handleAAC && disconnects==1 && starts==1 && pumps==1 && !jitters);
 assert(!src_eld_reset_pending && src_eld_error_stage==3 && src_eld_last_error==33);

 // START immediate failure, rejection and missing response each fail boundedly.
 for(unsigned failure=0;failure<3;failure++) {
   connected();request(3,false,1);src_stream_suspend_accepted();if(failure==0)start_rc=12;
   a2dp_source_main_work();
   if(failure==1)assert(src_eld_signaling_rejected(AVDTP_SI_START));
   if(failure==2)advance(3000);
   assert(disconnects==1 && !is_streaming && !jitters && pumps==1);
 }

 // Channel-late jitter reapply and new requests supersede old settle timers.
 connected();a2dp_source_queue_jitter(90);advance(200);request(3,true,2);advance(500);
 assert(!jitters);src_stream_suspend_accepted();a2dp_source_main_work();src_stream_start_accepted();
 advance(500);assert(jitters==1 && last_jitter==60);
 a2dp_source_queue_jitter(60);advance(500);assert(jitters==2);

 // Disconnect invalidates a queued rebuild; a new session can start cleanly.
 connected();request(3,false,1);src_stream_suspend_accepted();
 src_eld_link_reset();
 a2dp_is_connected_flag=false;a2dp_source_main_work();advance(5000);
 assert(!rebuild_calls && starts==1 && !jitters);
 connected();assert(is_streaming && !src_user_dc_hold && locks==0);
 assert(src_event_matches_headset(0x42));phone_cid=0x43;
 assert(!src_event_matches_headset(0) && !src_event_matches_headset(0x41) && !src_event_matches_headset(0x43));

 // A setting before initial START does not rebuild while that START is pending.
 connected();src_eld_link_reset();is_streaming=false;eld_transition_configured(&src_eld_change);
 request(1,true,2);a2dp_source_main_work();assert(!rebuild_calls && !suspends);
 src_start_stream(0x42,1);src_stream_start_accepted();assert(suspends==1);
 src_stream_suspend_accepted();a2dp_source_main_work();src_stream_start_accepted();
 advance(500);assert(last_jitter==60 && built_bitrate==192000);

 // Initial START silence cannot leave an in-flight gate stuck forever.
 connected();src_eld_link_reset();is_streaming=false;eld_transition_configured(&src_eld_change);
 src_start_stream(0x42,1);advance(3000);
 assert(src_eld_change.phase==ELD_READY && src_suspend_ms && !disconnects);
 // SDK timer arithmetic and phase deadline remain bounded across tick wrap.
 connected();now=UINT32_MAX-100;request(3,false,1);advance(3000);assert(disconnects==1);

 // Configuration callback schedules only; main owns the initial FDK open.
 connected();src_stream_established=false;src_eld_schedule_setup();unsigned old_starts=starts;
 src_codec_release_pending=true;config.eld_rate=1;game=true;config.game_level=2;
 assert(!rebuild_calls && src_eld_setup_pending && !is_streaming);
 src_start_stream(0x42,1);assert(starts==old_starts);
 a2dp_source_main_work();assert(rebuild_calls==1 && opens==1 && starts==old_starts);
 assert(registry_releases==1 && built_bitrate==192000 && active_slot_count==4);
 assert(!src_eld_setup_pending && src_eld_change.phase==ELD_WAIT_START);
 src_stream_established=true;src_start_stream(0x42,1);src_stream_start_accepted();assert(is_streaming);

 // Peer media/START can race deferred initialization without a premature pump.
 connected();src_eld_schedule_setup();before=pumps;old_starts=starts;
 src_stream_start_accepted();assert(pumps==before && src_eld_early_start);
 a2dp_source_main_work();assert(pumps==before+1 && starts==old_starts && !opens);
 connected();src_eld_schedule_setup();before=pumps;old_starts=starts;
 src_stream_start_accepted();src_stream_suspend_accepted();a2dp_source_main_work();
 assert(pumps==before && starts==old_starts+1 && !src_eld_early_start);
 src_stream_start_accepted();assert(pumps==before+1);
 connected();src_codec_release_pending=true;a2dp_source_main_work();
 assert(!registry_releases && handleAAC && is_streaming); // Never free a fresh active encoder.

 connected();src_eld_schedule_setup();src_eld_link_reset();a2dp_is_connected_flag=false;
 a2dp_source_main_work();assert(!rebuild_calls);
 connected();src_eld_schedule_setup();encode_rc=33;a2dp_source_main_work();
 assert(disconnects==1 && src_eld_error_stage==5 && !opens);
 connected();src_stream_established=false;src_eld_schedule_setup();open_rc=12;a2dp_source_main_work();
 assert(disconnects==1 && src_eld_error_stage==6);
 connected();src_stream_established=false;src_eld_schedule_setup();a2dp_source_main_work();advance(3000);
 assert(disconnects==1 && src_eld_error_stage==6);
 // Early START is deferred until the scan completes, then consumed once.
 connected();finish_scan_avdtp_codec=false;is_streaming=false;
 eld_transition_configured(&src_eld_change);before=pumps;
 src_stream_start_accepted();assert(src_start_accepted_pending && pumps==before);
 assert(!src_pump_start_pending());finish_scan_avdtp_codec=true;
 assert(src_pump_start_pending());src_pump_start();
 assert(is_streaming && pumps==before+1 && !src_start_accepted_pending);
 assert(!src_pump_start_pending());
 // A crossed SUSPEND invalidates the old permission before scan completion.
 connected();finish_scan_avdtp_codec=false;is_streaming=false;
 eld_transition_configured(&src_eld_change);src_stream_start_accepted();before=pumps;
 src_stream_suspend_accepted();assert(src_eld_change.phase==ELD_REBUILD);
 finish_scan_avdtp_codec=true;
 assert(!src_start_accepted_pending && !src_pump_start_pending() && pumps==before);
 // Even a surviving flag cannot bypass the current owner or session gates.
 src_start_accepted_pending=true;assert(!src_pump_start_pending());
 src_eld_change.phase=ELD_READY;assert(src_pump_start_pending());
 src_fault_hold=true;assert(!src_pump_start_pending());src_fault_hold=false;
 src_user_dc_hold=true;assert(!src_pump_start_pending());src_user_dc_hold=false;
 a2dp_is_connected_flag=false;assert(!src_pump_start_pending());a2dp_is_connected_flag=true;
 src_stream_established=false;assert(!src_pump_start_pending());src_stream_established=true;
 src_codec_setup_pending=true;assert(!src_pump_start_pending());src_codec_setup_pending=false;
 src_eld_setup_pending=true;assert(!src_pump_start_pending());src_eld_setup_pending=false;
 // SBC still honors a current START and also cancels it on SUSPEND.
 cur_codec=1;src_eld_change.phase=ELD_REBUILD;assert(src_pump_start_pending());
 src_stream_suspend_accepted();assert(!src_pump_start_pending() && !src_start_accepted_pending);
 puts("Production ELD adapter: suspend/build/START/jitter, coalescing, deadlines and failure teardown passed");
}
'''

names = ['a2dp_demo_timer_stop', 'a2dp_demo_timer_pause', 'src_eld_cancel_timer',
         'src_eld_link_reset', 'src_eld_schedule_setup', 'src_event_matches_headset',
         'src_eld_change_timeout', 'src_eld_arm_timer', 'src_eld_abort',
         'src_start_stream', 'src_eld_execute', 'src_eld_signaling_rejected',
         'src_jitter_handler', 'a2dp_source_queue_jitter', 'src_request_eld_change', 'a2dp_source_apply_eld_rate', 'a2dp_source_recover_eld_stream',
         'src_eld_initialize', 'a2dp_source_main_work', 'src_pump_start', 'src_pump_start_pending', 'src_stream_start_accepted', 'src_stream_suspend_accepted']
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    (path / 'test.c').write_text((ROOT / 'tests/eld_adapter_mocks.h').read_text() + '\n' + '\n'.join(function(n) for n in names) + tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O1', '-fsanitize=address,undefined',
                    '-I', str(ROOT / 'tests/encoder_mocks'), '-I', str(ROOT / 'src/btstack'),
                    str(path / 'test.c'), str(ROOT / 'src/btstack/eld_transition.c'),
                    str(ROOT / 'src/btstack/eld_profile.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True, env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
