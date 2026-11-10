"""Traverse the production duplex matrix with stateful host/device backends.

Exercises actual AudioSession streams, WAV writer, profile commands, ownership,
reconnects and diagnostics. No physical audio or Bluetooth claims.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import live_audio

@unittest.skipUnless(importlib.util.find_spec('numpy'),'NumPy required')
class MatrixReplay(unittest.TestCase):
    def run_case(self,external=False,reject=False,mic_fault=False,startup_pause=False,
                 external_release=False,operator_failure=False,steady_retry=False,focused=False,
                 output_stall=False, phase_stall=None, input_stall=False, channel_error=False, relay=False):
        import numpy as np
        events=[];results={};streams=[];phase_begin={}
        class Recorder:
            def __init__(self):self.control={}
            def log(self,name,obj):
                events.append((name,copy.deepcopy(obj)))
                if name=='phases.jsonl':phase_begin[obj['phase']]=clock.now
            def control_snapshot(self):return copy.deepcopy(self.control)
        recorder=Recorder()
        class Clock:
            now=0
            def monotonic(self):return self.now
            def sleep(self,seconds):
                self.now+=seconds
                for stream in list(streams):
                    kw=stream.kw
                    if kw['device']==1:
                        if output_stall or (phase_stall and next(reversed(phase_begin),None)==phase_stall and not input_stall):continue
                        buffer=bytearray(480*4);kw['callback'](buffer,480,None,'output underflow' if channel_error and next(reversed(phase_begin),None)=='mic_closed_left' else None)
                    else:
                        if phase_stall and input_stall and next(reversed(phase_begin),None)==phase_stall:continue
                        frames=480;kw['callback'](np.full(frames*kw['channels'],1200,dtype='<i2').tobytes(),frames,None,None)
                threading.Event().wait(.002) # Allow the actual bounded writer to drain.
        clock=Clock()
        class Stream:
            def __init__(self,**kw):self.kw=kw
            def __enter__(self):streams.append(self);return self
            def __exit__(self,*exc):streams.remove(self)
        sd=types.SimpleNamespace(
            query_devices=lambda device=None: [dict(name='USBPods output',hostapi=0,max_output_channels=2,max_input_channels=0,default_samplerate=48000),
                dict(name='USBPods input',hostapi=0,max_output_channels=0,max_input_channels=2,default_samplerate=48000)] if device is None else
                dict(name='USBPods input',hostapi=0,max_input_channels=2,default_samplerate=48000),
            query_hostapis=lambda index:dict(name='Windows WASAPI'),WasapiSettings=lambda **kw:kw,
            check_input_settings=lambda **kw:None,check_output_settings=lambda **kw:None,
            RawOutputStream=Stream,RawInputStream=Stream)
        def capture_active():
            return (external and (not external_release or clock.now<1)) or any(s.kw['device']==2 for s in streams)
        def refreshing():return startup_pause and 5<=clock.now<6
        class Link:
            def __init__(self):
                self.connected=True;self.failed=False;self.revision=1;self.commands=[]
                self.settings=dict(eldrate=3,gamelevel=2,usbset=33)
                self.profile=('initial',3,False,2,256000,0,0,9)
            def request(self,cmd,timeout=None):
                self.commands.append(cmd)
                if cmd=='settings':return dict(self.settings)
                if cmd.startswith('profile '):
                    assert len(streams)==2 and capture_active()
                    _,rate,game,level=cmd.split();rate,game,level=int(rate),bool(int(game)),int(level)
                    self.settings=dict(eldrate=rate,gamelevel=level,usbset=33|(128 if game else 0))
                    self.profile=next(p for p in live_audio.PROFILES if p[1:4]==(rate,game,level))
                    self.revision+=1
                    if reject:self.connected=False;self.failed=True
                    return {'kind':'ack','queued':1,'value':rate}
                if cmd=='phonepair 1':
                    self.profile=('relay',*self.profile[1:4],164000,0,0,6);return {}
                if cmd in ('phonedisc','phonepair 0'):return {}
                if cmd=='disconnect':
                    assert capture_active() and len(streams)==2
                    self.connected=False;return {}
                if cmd=='connect':self.connected=True;return {}
                if cmd=='status':return dict(connected=self.connected,confirmed=int(self.connected),streaming=int(self.connected and not refreshing()),
                    relay_connected=int(relay),relay_streaming=int(relay),
                    capture=int(capture_active()),codec=4 if self.connected else 0,fault_hold=int(self.failed),
                    mic_started=int(self.connected and capture_active()),mic_recovery_pending=0,mic_restarts=0,mic_watchdog_failures=0,
                    peer='fixture',tx_packets=int(clock.now*50)+1,send_failures=0,
                    mic_watchdog_failed=int(mic_fault and clock.now>=3),
                    mic_retry_count=3 if mic_fault else int(steady_retry and 'eld256' in phase_begin and clock.now>=phase_begin['eld256']+2))
                if cmd=='eldstatus':
                    p=self.profile
                    return dict(ready=int(self.connected),pending=int(refreshing()),transition='off' if self.failed else 'wait-start' if refreshing() else 'ready',
                        input_rate=48000,requested_revision=self.revision,built_revision=self.revision,
                        selected_rate=self.settings['eldrate'],game=int(bool(self.settings['usbset']&128)),
                        gamelevel=self.settings['gamelevel'],desired_bitrate=p[4],
                        active_bitrate=p[4],active_vbr=p[5],active_sbr=p[6],active_slots=p[7],
                        active_jitter=60 if p[2] and p[3]==2 else 90 if p[2] else 150,
                        desired_jitter=60 if p[2] and p[3]==2 else 90 if p[2] else 150,
                        negotiated_bitrate=0 if self.failed else 256000,negotiated_vbr=1,
                        error_stage=2 if self.failed else 0,last_error=263 if self.failed else 0)
                if cmd=='telemetry':
                    recorder.control=dict(micstats=dict(errors=0,au_drop=0,pcm_drop=0,capture=int(capture_active()),generation=1,
                        decoded=int(clock.now*133)+1,clock_windows=1,measured_rate=64000,coding_rate=48000,pcm_rate=64000),
                        usbcapture=dict(missing_samples=0,short_writes=0,running=int(capture_active()),pcm_samples=int(clock.now*64000)+1))
                    return {}
                raise AssertionError('Unexpected command '+cmd)
            def wait(self,predicate,timeout=45):
                deadline=clock.now+timeout
                while clock.now<deadline:
                    s=self.request('status')
                    if predicate(s):return s
                    clock.sleep(.25)
                raise TimeoutError('Stateful replay timeout')
        link=Link()
        args=types.SimpleNamespace(output_device=None,input_device=None,duration=5,soak_seconds=10,phone_relay=relay,mic_close_only=focused)
        def result(name,status,detail=None):results[name]=(status,detail)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with mock.patch.dict(sys.modules,{'sounddevice':sd}),mock.patch.object(live_audio,'time',clock):
                if reject or mic_fault:
                    with self.assertRaisesRegex(RuntimeError,'Playback failed during' if mic_fault else 'Firmware transition failed'):
                        live_audio.run_matrix(args,root,link,recorder,lambda sd,kind,x:1 if kind=='output' else 2,result,lambda message:'','fixture')
                    fault=json.loads((root/'audio-failure-state.json').read_text())
                    self.assertTrue(fault['before_stream_cleanup'])
                    self.assertTrue(fault['status']['capture'])
                    if mic_fault:
                        self.assertTrue(fault['status']['mic_watchdog_failed'])
                        self.assertTrue(fault['status']['streaming'])
                        self.assertEqual(fault['status']['mic_retry_count'],3)
                    else:self.assertEqual(fault['eldstatus']['last_error'],263)
                    self.assertLess(clock.now,10) # No 15-second convergence timeout after a known failure.
                else:
                    live_audio.run_matrix(args,root,link,recorder,lambda sd,kind,x:1 if kind=='output' else 2,result,
                        lambda message:'yes' if output_stall or channel_error or relay else 'left ear is silent' if operator_failure and 'mic_closed: tone is LEFT' in message else '',
                        'fixture')
                    if focused:
                        self.assertNotIn('duplex_soak',results)
                        self.assertNotIn('eld192',results)
                        self.assertNotIn('game_stable',results)
                        self.assertNotIn('game_latency',results)
                        self.assertNotIn('capture_reconnect_1',results)
                        self.assertEqual(results['reconnect_game_soak'][0],'SKIP')
                        self.assertEqual(results['mic_close_reopen_duplex'][0],'FAIL' if output_stall else 'PASS')
                        if output_stall:
                            # Fake firmware TX counters still advance while *no*
                            # host output callback fires. No audio PASS is valid.
                            self.assertEqual(results['restore256'][0],'FAIL')
                            self.assertIn('No host output callbacks observed',results['restore256'][1]['errors'])
                            self.assertIn('No host output callbacks observed',results['mic_close_reopen_duplex'][1]['errors'])
                            for label in ('mic_active','mic_closed','mic_reopened'):
                                for side in ('left','right'):
                                    self.assertEqual(results[label+'_'+side][0],'UNVERIFIED')
                    else:self.assertEqual(results['duplex_soak'][0],'PASS')
                    if startup_pause:
                        self.assertEqual(results['eld256'][0],'PASS')
                        self.assertIn('readiness',results['eld256'][1])
                        self.assertTrue(results['eld256'][1]['readiness']['recovery_observed'])
                        settling=[obj for name,obj in events if name=='connection-preflight.jsonl' and obj.get('phase')=='eld256_ready']
                        self.assertTrue(any(obj['eldstatus']['transition']=='wait-start' for obj in settling))
                        self.assertEqual(settling[-1]['eldstatus']['transition'],'ready')
                    if not focused:
                        self.assertEqual(results['eld320'][0],'SKIP')
                        for i in range(1,4):
                            name=f'capture_reconnect_{i}'
                            self.assertEqual(results[name][0],'FAIL' if phase_stall==name else 'PASS')
                        if phase_stall:self.assertTrue(results[phase_stall][1]['errors'])
                    if relay:self.assertEqual(results['phone_relay_duplex'][0],'FAIL' if phase_stall else 'PASS')
                    if channel_error:self.assertEqual(results['mic_closed_left'][0],'FAIL')
                    self.assertEqual(results['capture_close'][0],'SKIP' if external and not external_release else 'PASS')
                    self.assertFalse(results['capture_close'][1]['runner_exclusive_ownership_verified'])
                    if external_release:
                        self.assertTrue(results['capture_close'][1]['capture_active_before_runner'])
                        self.assertTrue(results['capture_close'][1]['firmware_capture_closed'])
                    if operator_failure:
                        self.assertEqual(results['mic_closed_left'],('FAIL','left ear is silent'))
                    if steady_retry:
                        self.assertEqual(results['eld256'][0],'FAIL')
                        self.assertTrue(any('mic_retry_count' in e for e in results['eld256'][1]['errors']))
                        fault=json.loads((root/'audio-failure-state.json').read_text())
                        self.assertTrue(fault['before_stream_cleanup'])
                    self.assertEqual(results['mic_close_reopen_duplex'][0],'FAIL' if output_stall else 'UNVERIFIED' if external and not external_release else 'PASS')
                    self.assertEqual(sum(c.startswith('profile ') for c in link.commands),1 if focused else 5)
                    self.assertTrue(list(root.glob('*.wav')))
                self.assertFalse(streams)
                self.assertTrue((root/'audio-metrics.json').exists())
                self.assertFalse(any(c.startswith(('eldrate ','gamelevel ','game ')) for c in link.commands))
        return results
    def test_complete_owned_capture_matrix(self):self.run_case()
    def test_focused_mic_close_does_not_repeat_soak_or_game_matrix(self):self.run_case(focused=True)
    def test_reconnect_output_stall_cannot_pass(self):self.run_case(phase_stall='capture_reconnect_1')
    def test_reconnect_input_stall_cannot_pass(self):self.run_case(phase_stall='capture_reconnect_1',input_stall=True)
    def test_phone_relay_with_live_callbacks(self):self.run_case(relay=True)
    def test_phone_relay_output_stall_cannot_pass(self):self.run_case(relay=True,phase_stall='phone_relay_duplex')
    def test_phone_relay_input_stall_cannot_pass(self):self.run_case(relay=True,phase_stall='phone_relay_duplex',input_stall=True)
    def test_channel_underflow_cannot_accept_yes(self):self.run_case(focused=True,channel_error=True)
    def test_fake_firmware_tx_without_output_callback_cannot_pass(self):self.run_case(focused=True,output_stall=True)
    def test_profile_measurement_waits_for_refresh_after_fixed_dwell(self):self.run_case(startup_pause=True)
    def test_external_capture_is_not_a_usb_close_failure(self):self.run_case(external=True)
    def test_recorded_start_rejection_preserved_before_cleanup(self):self.run_case(reject=True)
    def test_mic_watchdog_failure_preserved_while_playback_continues(self):self.run_case(mic_fault=True)
    def test_initial_external_use_does_not_hide_final_confirmed_closure(self):self.run_case(external=True,external_release=True)
    def test_explicit_listening_failure_is_not_unverified(self):self.run_case(operator_failure=True)
    def test_retry_during_steady_profile_is_not_clean_and_first_fault_survives(self):self.run_case(steady_retry=True)
if __name__=='__main__':unittest.main()
