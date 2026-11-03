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
    def run_case(self,external=False,reject=False):
        import numpy as np
        events=[];results={};streams=[]
        class Recorder:
            def __init__(self):self.control={}
            def log(self,name,obj):events.append((name,copy.deepcopy(obj)))
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
                        buffer=bytearray(480*4);kw['callback'](buffer,480,None,None)
                    else:
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
        def capture_active():return external or any(s.kw['device']==2 for s in streams)
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
                if cmd=='disconnect':
                    assert capture_active() and len(streams)==2
                    self.connected=False;return {}
                if cmd=='connect':self.connected=True;return {}
                if cmd=='status':return dict(connected=self.connected,confirmed=int(self.connected),streaming=int(self.connected),
                    capture=int(capture_active()),codec=4 if self.connected else 0,fault_hold=int(self.failed),
                    peer='fixture',tx_packets=int(clock.now*50)+1,send_failures=0)
                if cmd=='eldstatus':
                    p=self.profile
                    return dict(ready=int(self.connected),pending=0,transition='off' if self.failed else 'ready',
                        input_rate=48000,requested_revision=self.revision,built_revision=self.revision,
                        active_bitrate=p[4],active_vbr=p[5],active_sbr=p[6],active_slots=p[7],
                        negotiated_bitrate=0 if self.failed else 256000,negotiated_vbr=1,
                        error_stage=2 if self.failed else 0,last_error=263 if self.failed else 0)
                if cmd=='telemetry':
                    recorder.control=dict(micstats=dict(capture=int(capture_active()),generation=1,
                        decoded=int(clock.now*133)+1,clock_windows=1,measured_rate=64000,coding_rate=48000,pcm_rate=64000),
                        usbcapture=dict(running=int(capture_active()),pcm_samples=int(clock.now*64000)+1))
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
        args=types.SimpleNamespace(output_device=None,input_device=None,duration=5,soak_seconds=10,phone_relay=False)
        def result(name,status,detail=None):results[name]=(status,detail)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with mock.patch.dict(sys.modules,{'sounddevice':sd}),mock.patch.object(live_audio,'time',clock):
                if reject:
                    with self.assertRaisesRegex(RuntimeError,'Firmware transition failed'):
                        live_audio.run_matrix(args,root,link,recorder,lambda sd,kind,x:1 if kind=='output' else 2,result,lambda message:'','fixture')
                    fault=json.loads((root/'audio-failure-state.json').read_text())
                    self.assertTrue(fault['before_stream_cleanup'])
                    self.assertTrue(fault['status']['capture'])
                    self.assertEqual(fault['eldstatus']['last_error'],263)
                    self.assertLess(clock.now,10) # No 15-second convergence timeout after a known failure.
                else:
                    live_audio.run_matrix(args,root,link,recorder,lambda sd,kind,x:1 if kind=='output' else 2,result,lambda message:'','fixture')
                    self.assertEqual(results['duplex_soak'][0],'PASS')
                    self.assertEqual(results['eld320'][0],'SKIP')
                    for i in range(1,4):self.assertEqual(results[f'capture_reconnect_{i}'][0],'PASS')
                    self.assertEqual(results['capture_close'][0],'SKIP' if external else 'PASS')
                    self.assertEqual(results['mic_close_reopen_duplex'][0],'UNVERIFIED' if external else 'PASS')
                    self.assertEqual(sum(c.startswith('profile ') for c in link.commands),5)
                    self.assertTrue(list(root.glob('*.wav')))
                self.assertFalse(streams)
                self.assertTrue((root/'audio-metrics.json').exists())
                self.assertFalse(any(c.startswith(('eldrate ','gamelevel ','game ')) for c in link.commands))
        return results
    def test_complete_owned_capture_matrix(self):self.run_case()
    def test_external_capture_is_not_a_usb_close_failure(self):self.run_case(external=True)
    def test_recorded_start_rejection_preserved_before_cleanup(self):self.run_case(reject=True)
if __name__=='__main__':unittest.main()
