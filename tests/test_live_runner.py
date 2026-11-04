"""Host-side contract tests; fake serial transport, never hardware evidence."""
import importlib.util
import json
from pathlib import Path
import queue
import tempfile
import unittest
import hashlib
import sys
import subprocess
import time
import wave
import zipfile
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import live_audio

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('live_test',ROOT/'tools/live_test.py')
live=importlib.util.module_from_spec(spec);spec.loader.exec_module(live)

class FakeRecorder:
    def __init__(self):self.events=queue.Queue();self.lines=[]
    def log(self,name,obj):self.lines.append((name,obj))

class FakePort:
    def __init__(self,r,response):self.r,self.response=r,response;self.written=[]
    def write(self,data):
        self.written.append(data)
        for item in self.response:self.r.events.put(item)
    def flush(self):pass

class Contracts(unittest.TestCase):
    def test_connection_preflight_rejects_stalled_and_dropped_streams(self):
        class Link:
            def __init__(self,progress=True,connected=True):self.tx=0;self.progress=progress;self.connected=connected
            def request(self,cmd):
                if cmd=='eldstatus':return {'transition':'ready'}
                if self.progress:self.tx+=1
                return dict(connected=int(self.connected),confirmed=1,streaming=1,codec=4,tx_packets=self.tx,send_failures=0)
        class Clock:
            def __init__(self):self.now=0
            def monotonic(self):return self.now
            def sleep(self,n):self.now+=n
        for progress,connected,passes in ((True,True,True),(False,True,False),(True,False,False)):
            clock=Clock()
            with mock.patch.object(live,'time',clock):
                if passes:live.connection_preflight(Link(progress,connected),FakeRecorder(),seconds=1)
                else:
                    with self.assertRaises(RuntimeError):live.connection_preflight(Link(progress,connected),FakeRecorder(),seconds=1)
    def test_preflight_waits_for_initial_mic_recovery_before_measuring(self):
        class Clock:
            now=0
            def monotonic(self):return self.now
            def sleep(self,n):self.now+=n
        clock=Clock()
        class Link:
            def request(self,cmd):
                if cmd=='eldstatus':return dict(transition='ready' if clock.now>=2 else 'wait-suspend',pending=int(clock.now<2))
                return dict(connected=1,confirmed=1,streaming=int(clock.now>=2),codec=4,capture=1,
                            mic_started=int(clock.now>=1),mic_recovery_pending=int(clock.now<2),tx_packets=int(clock.now*50),send_failures=0)
        with mock.patch.object(live,'time',clock):
            d=live.connection_preflight(Link(),FakeRecorder(),seconds=1)
        self.assertGreaterEqual(clock.now,3)
        self.assertGreaterEqual(d['start']['tx_packets'],100)

    def test_preflight_rejects_exhausted_mic_watchdog(self):
        class Link:
            def request(self,cmd):
                if cmd=='eldstatus':return dict(transition='ready',pending=0)
                return dict(connected=1,confirmed=1,streaming=1,codec=4,capture=1,
                            mic_started=0,mic_watchdog_failed=1,mic_retry_count=3)
        with self.assertRaisesRegex(RuntimeError,'Firmware failed while settling'):
            live.connection_preflight(Link(),FakeRecorder(),seconds=1)

    def test_control_no_echo_is_unverified_and_stale_value_is_not_readback(self):
        class Link:
            def __init__(self,fresh=False):self.fresh=fresh
            def request(self,cmd):return dict(ca=0,control_rx_seq=[0,0,0,int(self.fresh),0])
        class Clock:
            def __init__(self):self.now=0
            def monotonic(self):return self.now
            def sleep(self,n):self.now+=n
        for fresh in (False,True):
            with mock.patch.object(live,'time',Clock()):
                self.assertEqual(live.observe_peer_control(Link(fresh),'ca',0,dict(control_rx_seq=[0]*5),seconds=1),fresh)
        with mock.patch.object(live,'time',Clock()):
            with self.assertRaisesRegex(RuntimeError,'differs'):
                live.observe_peer_control(Link(True),'ca',1,dict(control_rx_seq=[0]*5),seconds=1)

    def test_atomic_profile_ack_and_capture_ownership(self):
        rec=FakeRecorder();port=FakePort(rec,[dict(kind='ack',id=live.IDS['profile'],queued=1,value=2)])
        live.Link(port,rec).request('profile 2 0 1')
        self.assertEqual(port.written,[b':profile 2 0 1\n'])
        class Link:
            def request(self,cmd):return dict(capture=1)
        state,detail=live_audio.capture_close_state(Link(),True)
        self.assertEqual(state,'SKIP')

    def test_windows_capture_uses_mixer_format(self):
        class SD:
            def query_devices(self,device):
                self.device=device
                return dict(hostapi=2,default_samplerate=48000,max_input_channels=2)
            def query_hostapis(self,index):return {'name':'Windows WASAPI'}
            def WasapiSettings(self,**kw):self.extra=kw;return kw
            def check_input_settings(self,**kw):
                self.checked=kw
                if kw['samplerate']!=48000 or kw['channels']!=2:raise ValueError('Invalid sample rate')
        sd=SD();fmt=live_audio.capture_format(sd,12)
        self.assertEqual((fmt['samplerate'],fmt['channels']),(48000,2))
        self.assertEqual(sd.checked['device'],12)
        self.assertFalse(sd.extra['exclusive'])

    def test_recorded_pair_ack_with_console_indent(self):
        # Exact framing of the ACK in the failed 20261103T192956Z capture.
        line=' [control] {"kind":"ack","queued":1,"id":132,"value":0,"reboot_required":0}'
        class Port:
            def __init__(self):self.data=queue.Queue()
            def write(self,data):
                self.data.put(b'Web pair: connecting\r\n'+line[:27].encode())
                self.data.put((line[27:]+'\r\nStream started.\r\n').encode())
            def read(self,count):
                try:return self.data.get(timeout=.01)
                except queue.Empty:return b''
            def flush(self):pass
        with tempfile.TemporaryDirectory() as temp:
            rec=live.Recorder(Path(temp));port=Port();rec.serial_reader(port,'cdc.jsonl',True)
            try:
                ack=live.Link(port,rec).request('pair 0',timeout=1)
                self.assertEqual(ack['id'],132)
            finally:rec.close()
            self.assertFalse(rec.errors)
            logs=[json.loads(line)['line'] for line in (Path(temp)/'cdc.jsonl').read_text().splitlines()]
            self.assertIn('Web pair: connecting',logs)
            self.assertIn('Stream started.',logs)

    def test_boolean_control_ack_uses_wire_enum(self):
        for command in ('pvol','ca'):
            for logical,wire in ((0,2),(1,1)):
                rec=FakeRecorder();port=FakePort(rec,[{'kind':'ack','id':live.IDS[command],'queued':1,'value':wire}])
                self.assertEqual(live.Link(port,rec).request(f'{command} {logical}')['value'],wire)

    def test_telemetry_requires_all_current_replies(self):
        ack={'kind':'ack','id':live.IDS['telemetry'],'queued':1,'value':0}
        rec=FakeRecorder();port=FakePort(rec,[{'kind':k} for k in ('micstats','usbcapture','hidstats')]+[ack])
        self.assertEqual(live.Link(port,rec).request('telemetry'),ack)
        port.response=[ack,{'kind':'micstats'},{'kind':'hidstats'}]
        with self.assertRaises(TimeoutError):live.Link(port,rec).request('telemetry',timeout=.01)
        port.response=[ack]+[{'kind':k} for k in ('hidstats','usbcapture','micstats')]
        self.assertEqual(live.Link(port,rec).request('telemetry'),ack)

    def test_cleanup_only_restores_changed_settings(self):
        original=dict(usbset=33,earpause=0,stem=0,debug=0,gamelevel=2,eldrate=3,usbvol=100,phvol=100,btnmode=2,ldacq=3,lhdcrate=4)
        self.assertEqual(live.restoration_commands(original,original),[])
        self.assertEqual(live.restoration_commands(original,{**original,'eldrate':1,'usbset':161}),[('profile',(3,0,2))])
        self.assertEqual(live.restoration_commands(original,{}),[])

    def test_failure_still_bundles_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=subprocess.run([sys.executable,str(ROOT/'tools/live_test.py'),'--target-name','fixture',
                     '--manifest',str(root/'missing.json'),'--output',str(root)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2)
            archive=next(root.glob('USBPods-results-*.zip'))
            with zipfile.ZipFile(archive) as z:
                summary=json.loads(z.read('summary.json'))
                self.assertEqual(summary['tests']['run']['status'],'FAIL')
                self.assertIn('exception.txt',z.namelist())
    def test_target_identity(self):
        a={'index':1,'name':'My AirPods','mac':'AA:BB:CC:DD:EE:FF'}
        b={'index':2,'name':'Other','mac':'11:22:33:44:55:66'}
        self.assertIs(live.choose_target([a,b],name='My AirPods'),a)
        self.assertIs(live.choose_target([a,b],mac=a['mac'].lower()),a)
        with self.assertRaises(ValueError):live.choose_target([a,{**a,'index':3}],name='My AirPods')
        with self.assertRaises(ValueError):live.choose_target([a,b],name='AirPods')
        with self.assertRaises(ValueError):live.choose_target([a,b])
    def test_command_correlation(self):
        r=FakeRecorder();p=FakePort(r,[{'kind':'ack','id':11,'queued':1,'value':2},{'kind':'ack','id':13,'queued':1,'value':1},{'kind':'ack','id':13,'queued':1,'value':2}])
        live.Link(p,r).request('noise 2');self.assertEqual(p.written,[b':noise 2\n'])
        p.response=[{'kind':'ack','id':13,'queued':0,'value':2}]
        with self.assertRaises(RuntimeError):live.Link(p,r).request('noise 2')
        p.response=[]
        with self.assertRaises(TimeoutError):live.Link(p,r).request('noise 2',timeout=.01)
    def test_malformed_and_other_logs(self):
        self.assertIsNone(live.parse_control('[mic] packet'))
        with self.assertRaises(ValueError):live.parse_control('[control] broken')
        self.assertEqual(live.parse_control('[control] {"kind":"status"}')['kind'],'status')
        self.assertIsNone(live.parse_control('other [control] {"kind":"status"}'))
    def test_offline_pause_prevents_packaging_before_creating_output(self):
        from package_live_test import package
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'docs').mkdir()
            (root/'docs/validation-status.json').write_text(json.dumps(dict(live_test_authorized=False,blockers=['offline pass'])))
            out=root/'candidate'
            with self.assertRaisesRegex(ValueError,'paused'):
                package(root,root/'build',root/'evidence',out,'fixture','a'*40,1)
            self.assertFalse(out.exists())

    def test_packaging_requires_codec_heap_audit(self):
        from package_live_test import require_codec_heap_audit
        with self.assertRaises(ValueError):
            require_codec_heap_audit({}, 'USBPods_Pico2W_Lite')
        with self.assertRaises(ValueError):
            require_codec_heap_audit({'memory': {'runtime_allocation_verified': False}},
                                     'USBPods_Pico2W_Lite')
        require_codec_heap_audit({'memory': {'runtime_allocation_verified': True}},
                                 'USBPods_Pico2W_Lite')
        require_codec_heap_audit({}, 'fixture')  # non-USBPods stems unchanged
    def test_manifest_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'test.uf2').write_bytes(b'fixture')
            d={'hardware_test_candidate':True,'sha':'a'*40,'firmware':'test.uf2','firmware_sha256':hashlib.sha256(b'fixture').hexdigest()}
            self.assertEqual(live.verify_manifest(root,d),root/'test.uf2')
            with self.assertRaisesRegex(ValueError,'on hold'):
                live.verify_manifest(root,{**d,'validation_blockers':['unresolved transport']})
            (root/'test.uf2').write_bytes(b'changed')
            with self.assertRaises(ValueError):live.verify_manifest(root,d)
            d['hardware_test_candidate']=False
            with self.assertRaises(ValueError):live.verify_manifest(root,d)
    def test_cdc_command_ids_match_firmware(self):
        header=(ROOT/'src/control_command.h').read_text()
        body=header.split('CONTROL_INFO=128,',1)[1].split('};',1)[0]
        enums=['INFO']+[part.strip().removeprefix('CONTROL_') for part in body.replace('\n','').split(',') if part.strip()]
        self.assertEqual(len(enums),38)
        for offset,name in enumerate(enums):self.assertEqual(live.IDS[name.lower()],128+offset)
    def test_profile_requires_applied_state(self):
        p=live_audio.PROFILES[0]
        s=dict(ready=1,pending=0,transition='ready',input_rate=48000,requested_revision=2,built_revision=2,
               active_bitrate=256000,active_vbr=5,active_sbr=1,active_slots=6)
        self.assertTrue(live_audio.profile_matches(s,p))
        cbr={**s,'duplex_cbr':1,'active_vbr':0,'active_sbr':0}
        self.assertTrue(live_audio.profile_matches(cbr,p))
        self.assertFalse(live_audio.profile_matches({**cbr,'active_vbr':5},p))
        for change in (dict(pending=1),dict(transition='wait-start'),dict(active_bitrate=192000),dict(built_revision=1)):
            self.assertFalse(live_audio.profile_matches({**s,**change},p))
    def test_counter_wrap_and_failures(self):
        a={'micstats':dict(generation=2,capture=1,decoded=0xfffffff0,clock_windows=2,measured_rate=64000,coding_rate=48000,pcm_rate=64000),
           'usbcapture':dict(running=1,pcm_samples=10),
           'status':dict(streaming=1,codec=4,tx_packets=1),'eldstatus':dict(transition='ready')}
        b={**a,'status':dict(streaming=1,codec=4,tx_packets=2),'micstats':dict(generation=2,capture=1,decoded=10,clock_windows=3,measured_rate=64000,coding_rate=48000,pcm_rate=64000),
           'usbcapture':dict(running=1,pcm_samples=650)}
        self.assertEqual(live_audio.health(a,b),[])
        self.assertIn('No playback media packets progressed',live_audio.health(a,{**b,'status':a['status']}))
        b['micstats']['generation']=3;b['usbcapture']['missing_samples']=64
        self.assertGreaterEqual(len(live_audio.health(a,b)),2)
        self.assertTrue(live_audio.health({},{}))

    @unittest.skipUnless(importlib.util.find_spec('numpy'),'NumPy not installed in host test environment')
    def test_audio_callbacks_clip_and_close(self):
        import numpy as np
        class Stream:
            def __init__(self,**kw):self.kw=kw
            def __enter__(self):
                if self.kw['channels']==2:
                    buffer=bytearray(480*4);self.kw['callback'](buffer,480,None,None)
                    self.output=np.frombuffer(buffer,dtype='<i2');assert abs(self.output).max()<=650
                else:
                    data=np.full(13*64000,1000,dtype='<i2').tobytes()
                    self.kw['callback'](data,13*64000,None,None)
                return self
            def __exit__(self,*exc):pass
        class SD:RawOutputStream=Stream;RawInputStream=Stream
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with live_audio.AudioSession(root,FakeRecorder(),SD,np,1,2) as audio:
                end=time.monotonic()+5
                while not audio.clip_samples and time.monotonic()<end:time.sleep(.01)
            self.assertFalse(audio.thread.is_alive())
            with wave.open(str(root/'capture_open.wav')) as wav:
                self.assertEqual((wav.getnchannels(),wav.getframerate(),wav.getsampwidth()),(1,64000,2))
                self.assertEqual(wav.getnframes(),12*64000)
            metrics=json.loads((root/'audio-metrics.json').read_text())
            self.assertEqual(metrics['phases']['capture_open']['samples'],13*64000)
            self.assertEqual(metrics['collector_dropped_buffers'],0)

    @unittest.skipUnless(importlib.util.find_spec('numpy'),'NumPy not installed in host test environment')
    def test_shared_stereo_capture_metadata_and_input_only_close(self):
        import numpy as np
        opened=[]
        class Stream:
            def __init__(self,**kw):self.kw=kw
            def __enter__(self):opened.append(self);return self
            def __exit__(self,*exc):opened.remove(self)
        class SD:RawOutputStream=Stream;RawInputStream=Stream
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            fmt=dict(samplerate=48000,channels=2,extra_settings=None,mode='wasapi-shared')
            with live_audio.AudioSession(root,FakeRecorder(),SD,np,1,2,fmt) as audio:
                self.assertEqual(len(opened),2)
                data=np.tile(np.array([1200,-600],dtype='<i2'),48000).tobytes()
                audio.capture(data,48000,None,None)
                audio.set_capture(False);self.assertEqual(len(opened),1)
                self.assertEqual(opened[0].kw['device'],1)
                audio.set_capture(True);self.assertEqual(len(opened),2)
            with wave.open(str(root/'capture_open.wav')) as wav:
                self.assertEqual((wav.getnchannels(),wav.getframerate(),wav.getnframes()),(2,48000,48000))
                self.assertEqual(wav.readframes(1),np.array([1200,-600],dtype='<i2').tobytes())
            self.assertFalse(opened)

    @unittest.skipUnless(importlib.util.find_spec('numpy'),'NumPy not installed in host test environment')
    def test_audio_open_failure_cleans_up(self):
        import numpy as np
        class Stream:
            def __init__(self,**kw):pass
            def __enter__(self):raise RuntimeError('simulated device error')
            def __exit__(self,*exc):pass
        class SD:RawOutputStream=Stream;RawInputStream=Stream
        with tempfile.TemporaryDirectory() as temp:
            audio=live_audio.AudioSession(Path(temp),FakeRecorder(),SD,np,1,2)
            with self.assertRaises(RuntimeError):audio.__enter__()
            self.assertFalse(audio.thread.is_alive())
            self.assertTrue((Path(temp)/'audio-metrics.json').exists())

if __name__=='__main__':unittest.main()
