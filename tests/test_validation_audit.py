"""Pinned validation-audit regressions exercising production runner code.

No physical device, OS microphone, raw captures or firmware flash is simulated
as hardware acceptance. Run with python3 tests/test_validation_audit.py.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import live_audio
import live_test
from package_live_test import package


class Clock:
    def __init__(self):self.now=0
    def monotonic(self):return self.now
    def sleep(self,seconds):self.now+=seconds


class RunnerAudit(unittest.TestCase):
    def test_free_text_reports_remain_verbatim_and_do_not_turn_into_passes(self):
        checks=[
            ('left ear is silent','channel','left','FAIL'),
            ('Only the right bud played','channel','left','FAIL'),
            ('right ear only','channel','right','PASS'),
            ('only left','channel','left','PASS'),
            ('both ears played','channel','left','FAIL'),
            ('nothing happened','channel','right','UNVERIFIED'),
            ('not silent','channel','left','UNVERIFIED'),
            ('no, the left is gone','channel','left','FAIL'),
            ('high pitched','quality',None,'UNVERIFIED'),
            ('too high-pitched','quality',None,'FAIL'),
            ('sounds distorted','quality',None,'FAIL'),
            ('no distortion','quality',None,'UNVERIFIED'),
            ('no problems','quality',None,'UNVERIFIED'),
            ('yes','quality',None,'PASS'),
            ('double press did nothing','gestures',None,'FAIL'),
            ('all AVRCP attempts appeared as PLAY','gestures',None,'UNVERIFIED'),
            ('yes','gestures',None,'UNVERIFIED'),
            ('','channel','left','UNVERIFIED'),
        ]
        for raw,category,expected,want in checks:
            with self.subTest(raw=raw):
                self.assertEqual(live_audio.observation_status(raw,category,expected),want)
                self.assertEqual(raw,raw)  # Caller stores untouched text, not a normalized copy.

    def test_initial_ownership_does_not_erase_confirmed_final_capture_close(self):
        class Link:
            def __init__(self,values):self.states=iter(values);self.last={}
            def request(self,command):
                self.assertion=command=='status';assert self.assertion
                self.last=next(self.states,self.last)
                return self.last
        for before,states,want,closed in [
            (True,[{'capture':1},{'capture':0}],'PASS',True),
            (False,[{'capture':1},{'capture':0}],'PASS',True),
            (True,[{'capture':1}],'SKIP',False),
            (False,[{'capture':1}],'UNVERIFIED',False),
            (True,[{}],'UNVERIFIED',False),
        ]:
            with self.subTest(before=before,states=states):
                clock=Clock()
                with mock.patch.object(live_audio,'time',clock):
                    outcome,details=live_audio.capture_close_state(Link(states),before,seconds=.5)
                self.assertEqual(outcome,want)
                self.assertEqual(details['capture_active_before_runner'],before)
                self.assertEqual(details['firmware_capture_closed'],closed)
                self.assertFalse(details['runner_exclusive_ownership_verified'])

    def test_pre_measure_retry_wait_must_resettle_and_remain_visible(self):
        profile=live_audio.PROFILES[-1]
        clock=Clock()
        class Link:
            def request(self,name):
                if name=='status':
                    return dict(connected=1,confirmed=1,streaming=int(clock.now>=1.5),
                        capture=1,mic_started=1,codec=4,tx_packets=int(clock.now*50),
                        mic_retry_count=int(clock.now>=3),mic_recovery_pending=int(clock.now<1.5))
                if name=='eldstatus':
                    return dict(ready=1,pending=int(clock.now<1.5),
                        transition='wait-start' if clock.now<1.5 else 'ready',
                        input_rate=48000,requested_revision=1,built_revision=1,
                        active_bitrate=256000,active_vbr=0,active_sbr=0,
                        active_slots=6,duplex_cbr=1)
                raise AssertionError(name)
        class Recorder:
            def __init__(self):self.records=[]
            def log(self,name,item):self.records.append(item)
        recorder=Recorder()
        with mock.patch.object(live_audio,'time',clock):
            outcome=live_audio.await_duplex_ready(Link(),recorder,profile,'ready',timeout=12)
        self.assertGreaterEqual(clock.now,5)
        self.assertTrue(outcome['readiness']['recovery_observed'])
        self.assertEqual(outcome['readiness']['continuous_ready_seconds'],2)
        self.assertTrue(any(x['eldstatus']['transition']=='wait-start' for x in recorder.records))

    def test_recovery_during_steady_interval_is_a_failure(self):
        base={'micstats':dict(generation=3,capture=1,decoded=80,clock_windows=4,
                measured_rate=64000,coding_rate=48000,pcm_rate=64000),
              'usbcapture':dict(running=1,pcm_samples=10000,missing_samples=0),
              'status':dict(streaming=1,codec=4,capture=1,mic_started=1,
                mic_audio_seen=1,mic_retry_count=0,mic_restarts=0,
                mic_watchdog_failures=0,tx_packets=150,send_failures=0),
              'eldstatus':dict(transition='ready')}
        after=json.loads(json.dumps(base))
        after['micstats']['decoded']=180
        after['usbcapture']['pcm_samples']=20000
        after['status']['tx_packets']=250
        self.assertEqual(live_audio.health(base,after),[])
        for key in ('mic_retry_count','mic_restarts','mic_watchdog_failures'):
            change=json.loads(json.dumps(after));change['status'][key]=1
            self.assertTrue(any(key in item for item in live_audio.health(base,change)),key)
        change=json.loads(json.dumps(after));change['status']['mic_audio_seen']=0
        self.assertTrue(any('framed audio' in item for item in live_audio.health(base,change)))
        change=json.loads(json.dumps(after));change['status']['mic_recovery_pending']=1
        self.assertTrue(any('recovery was active' in item for item in live_audio.health(base,change)))

    def test_first_fault_file_is_not_replaced_by_later_cleanup_state(self):
        class Link:
            def __init__(self):self.fault=True
            def request(self,command,timeout=2):
                if command=='status':return {'capture':int(self.fault),'mic_watchdog_failed':int(self.fault)}
                if command=='eldstatus':return {'transition':'failed' if self.fault else 'off'}
                if command=='telemetry':return {'queued':1}
                raise AssertionError(command)
        class Recorder:
            def control_snapshot(self):return {'micstats':{'decoded':1}}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);link=Link()
            live_audio.preserve_audio_failure(root,link,Recorder(),RuntimeError('first-fault'),True)
            link.fault=False
            live_audio.preserve_audio_failure(root,link,Recorder(),RuntimeError('cleanup fault'),False)
            data=json.loads((root/'audio-failure-state.json').read_text())
            self.assertEqual(data['error'],'first-fault')
            self.assertTrue(data['before_stream_cleanup'])
            self.assertEqual(data['status']['mic_watchdog_failed'],1)

    def test_hash_check_detects_changed_packaged_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fw=root/'test.uf2';fw.write_bytes(b'uf2 fixture')
            script=root/'live_test.py';script.write_bytes(b'known runner')
            manifest=dict(hardware_test_candidate=True,sha='b'*40,firmware=fw.name,
                firmware_sha256=hashlib.sha256(fw.read_bytes()).hexdigest(),
                runner_files={'live_test.py':hashlib.sha256(script.read_bytes()).hexdigest()})
            self.assertEqual(live_test.verify_manifest(root,manifest),fw)
            script.write_text('tampered script')
            with self.assertRaisesRegex(ValueError,'Bundle file'):
                live_test.verify_manifest(root,manifest)

    def test_production_packager_refuses_missing_build_and_codec_heap_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'docs').mkdir();(root/'evidence').mkdir()
            (root/'docs/validation-status.json').write_text(json.dumps(
                {'live_test_authorized':True,'blockers':[]}))
            evidence=root/'evidence';out=root/'candidate'
            def check(report,pattern):
                (evidence/'verification.json').write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError,pattern):
                    package(root,root/'build',evidence,out,'USBPods_Pico2W_Lite','a'*40,123)
                self.assertFalse(out.exists())
            check({'build_verified':False,'memory':{'runtime_allocation_verified':True}},
                  'Build verification')
            check({'build_verified':True,'memory':{'runtime_allocation_verified':False}},
                  'codec-heap32')


if __name__=='__main__':
    unittest.main()
