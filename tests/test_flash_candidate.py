"""Exercise the actual flash orchestrator; subprocess and serial are simulated."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import flash_candidate as flash


class FlashTests(unittest.TestCase):
    def exercise(self,mode='running',failure=None):
        with tempfile.TemporaryDirectory(prefix='usbpods flash ') as temp:
            root=Path(temp);uf2=root/'candidate.uf2';uf2.write_bytes(b'fixture')
            manifest=dict(hardware_test_candidate=True,sha='b'*40,board='pico2_w',firmware=uf2.name,
                          firmware_sha256=hashlib.sha256(uf2.read_bytes()).hexdigest())
            (root/'candidate.json').write_text(json.dumps(manifest))
            if failure=='hash':uf2.write_bytes(b'changed')
            state={'mode':mode,'loaded':False};calls=[]
            class Clock:
                now=0
                def monotonic(self):return self.now
                def sleep(self,n):self.now+=n
            clock=Clock()
            device=types.SimpleNamespace(device='COM3',vid=0xcafe,pid=0x7215,serial_number='fixture')
            def ports():
                if state['mode']=='bootsel':return []
                port=types.SimpleNamespace(**vars(device))
                if state['loaded']:port.device='COM7'
                if failure=='unrelated':port.vid=0x1234
                return [port,port] if failure=='ambiguous' else [port]
            class Serial:
                SerialException=OSError
                class Serial:
                    def __init__(self,port,baud,**kw):
                        calls.append(('serial',port,baud))
                        if baud==1200:state['mode']='bootsel'
                    def __enter__(self):return self
                    def __exit__(self,*args):pass
                    def write(self,data):self.assertion=data==b':info\n';assert self.assertion
                    def flush(self):pass
                    def readline(self):
                        sha='a'*40 if not state['loaded'] or failure=='wrong-sha' else manifest['sha']
                        return ('[control] '+json.dumps(dict(kind='info',board='rp2350',protocol=2,sha=sha))+'\n').encode()
            def run(command,**kwargs):
                calls.append(('tool',command));action=command[1];code=0
                if action=='reboot':
                    if mode=='running':code=1 # Existing firmware needs CDC fallback.
                    else:state['mode']='bootsel'
                elif action=='info':
                    if failure=='bootsel-timeout':code=1
                    else:assert state['mode']=='bootsel'
                elif action=='load':
                    assert state['mode']=='bootsel' and '-v' in command and '-x' in command
                    assert str(uf2) in command and '--pid' in command
                    if failure=='load':code=1
                    else:state.update(mode='running',loaded=True)
                else:raise AssertionError(command)
                if failure=='tool-timeout':raise subprocess.TimeoutExpired(command,15)
                return types.SimpleNamespace(returncode=code,stdout='simulated',stderr='')
            expected={'hash':ValueError,'unrelated':RuntimeError,'ambiguous':RuntimeError,
                      'load':RuntimeError,'wrong-sha':RuntimeError,'bootsel-timeout':RuntimeError,
                      'tool-timeout':subprocess.TimeoutExpired,'missing-tool':RuntimeError}.get(failure)
            which=lambda name:None if failure=='missing-tool' else '/path with spaces/picotool.exe'
            with mock.patch.object(flash,'time',clock):
                if expected:
                    with self.assertRaises(expected):
                        flash.flash(root,'COM3',serial_module=Serial,ports=ports,run=run,which=which,clock=clock)
                else:
                    self.assertEqual(flash.flash(root,'COM3',serial_module=Serial,ports=ports,run=run,which=which,clock=clock),'COM7')
            if failure in ('hash','unrelated','ambiguous','missing-tool'):
                self.assertFalse(any(x[0]=='tool' for x in calls))
            if failure!='hash' and failure!='missing-tool':
                report=json.loads((root/'flash-log.json').read_text())
                self.assertEqual(report['complete'],not bool(failure))
            if not failure:
                self.assertEqual(report['reset_method'],{'running':'cdc-1200-fallback','compatible':'picotool','bootsel':'already-bootsel'}[mode])
                self.assertEqual(sum(x[0]=='tool' and x[1][1]=='load' for x in calls),1)
                self.assertEqual(any(x[0]=='serial' and x[2]==1200 for x in calls),mode=='running')

    def test_running_legacy_candidate(self):self.exercise()
    def test_compatible_picotool_reset(self):self.exercise('compatible')
    def test_already_bootsel(self):self.exercise('bootsel')
    def test_failures_stop_before_testing(self):
        for failure in ('hash','missing-tool','unrelated','ambiguous','load','wrong-sha','bootsel-timeout','tool-timeout'):
            with self.subTest(failure=failure):self.exercise(failure=failure)


if __name__=='__main__':unittest.main()
