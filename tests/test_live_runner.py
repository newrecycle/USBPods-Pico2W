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
    def test_manifest_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'test.uf2').write_bytes(b'fixture')
            d={'hardware_test_candidate':True,'sha':'a'*40,'firmware':'test.uf2','firmware_sha256':hashlib.sha256(b'fixture').hexdigest()}
            self.assertEqual(live.verify_manifest(root,d),root/'test.uf2')
            (root/'test.uf2').write_bytes(b'changed')
            with self.assertRaises(ValueError):live.verify_manifest(root,d)
            d['hardware_test_candidate']=False
            with self.assertRaises(ValueError):live.verify_manifest(root,d)
    def test_cdc_command_ids_match_firmware(self):
        header=(ROOT/'src/control_command.h').read_text()
        body=header.split('CONTROL_INFO=128,',1)[1].split('};',1)[0]
        enums=['INFO']+[part.strip().removeprefix('CONTROL_') for part in body.replace('\n','').split(',') if part.strip()]
        self.assertEqual(len(enums),37)
        for offset,name in enumerate(enums):self.assertEqual(live.IDS[name.lower()],128+offset)
    def test_profile_requires_applied_state(self):
        p=live_audio.PROFILES[0]
        s=dict(ready=1,pending=0,transition='ready',input_rate=48000,requested_revision=2,built_revision=2,
               active_bitrate=256000,active_vbr=5,active_sbr=1,active_slots=6)
        self.assertTrue(live_audio.profile_matches(s,p))
        for change in (dict(pending=1),dict(transition='wait-start'),dict(active_bitrate=192000),dict(built_revision=1)):
            self.assertFalse(live_audio.profile_matches({**s,**change},p))
    def test_counter_wrap_and_failures(self):
        a={'micstats':dict(generation=2,capture=1,decoded=0xfffffff0),
           'usbcapture':dict(running=1,pcm_samples=10),
           'status':dict(streaming=1,codec=4),'eldstatus':dict(transition='ready')}
        b={**a,'micstats':dict(generation=2,capture=1,decoded=10),
           'usbcapture':dict(running=1,pcm_samples=650)}
        self.assertEqual(live_audio.health(a,b),[])
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
