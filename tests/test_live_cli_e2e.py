"""Run the actual live CLI through simulated CDC/HID/audio backends.

The C command parser and ELD profile policy are production code. Bluetooth,
USB hardware, Windows drivers, counters and speech are simulated. This is
runner integration evidence, never physical device acceptance.
Use --candidate PATH to exercise an extracted, hash-verified live package.
"""
import argparse
import contextlib
import ctypes
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import types
import wave
import zipfile
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
REAL_TIME=time
PEER='AA:BB:CC:DD:EE:01'
SHIM=r'''
#include "control_command.h"
#include "eld_profile.h"
int parse_wire(const char *s,unsigned n,uint8_t out[5]) {
 control_input input={0};control_command c={0};enum control_result result=CONTROL_WAIT;
 for(unsigned i=0;i<n;i++)result=control_input_feed(&input,s[i],&c);
 if(result!=CONTROL_READY)return 0;
 out[0]=c.id;out[1]=c.value;out[2]=c.game;out[3]=c.level;out[4]=c.status;return 1;
}
void profile_wire(unsigned rate,unsigned game,unsigned level,unsigned vbr,uint32_t out[5]) {
 eld_profile p=eld_profile_select(rate,game,level,false,false,vbr,1);
 out[0]=p.bitrate;out[1]=p.vbr;out[2]=p.sbr;out[3]=p.slots;out[4]=p.input_rate;
}
'''


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def run_case(live,audio,manifest_path,manifest,parser,profile,output,case,ceiling=256000):
    import numpy as np
    streams=[];ports=[];handles=[];commands=[]
    class Clock:
        now=0
        def monotonic(self):return self.now+REAL_TIME.monotonic()-wall_start
        def monotonic_ns(self):return int(self.monotonic()*1e9)
        def sleep(self,seconds):
            self.now+=seconds
            for stream in list(streams):
                kw=stream.kw
                if stream.is_input:
                    data=np.tile(np.array([1200,-600],dtype='<i2'),480).tobytes()
                    kw['callback'](data,480,None,None)
                else:kw['callback'](bytearray(480*4),480,None,None)
            threading.Event().wait(.002) # Real reader and WAV worker scheduling.
    wall_start=REAL_TIME.monotonic();clock=Clock()
    class Device:
        connected=False;failed=False;generation=0;was_capture=False;tx=0;revision=1
        control_tx=0;last_id=0;last_value=0
        connect_calls=0
        def __init__(self):
            self.settings=dict(usbset=33,slot=1,connmode=1,usbvol=100,phvol=100,
                gamelevel=1,eldrate=2,earpause=0,stem=0,debug=0,btnmode=1,ldacq=2,lhdcrate=2)
            self.original=dict(self.settings);self.controls=dict(noise=2,pvol=1,ca=1,aa=50)
            self.sequences=[0]*5;self.opened_at=None
        def capture(self):
            active=case=='external-capture' or any(s.is_input for s in streams)
            if active!=self.was_capture:self.generation+=1;self.was_capture=active
            return active
        def mic_fault(self):
            return case=='mic-watchdog' and self.opened_at is not None and clock.now-self.opened_at>=3
        def status(self):
            if case=='session-peer-timeout' and self.opened_at is not None and clock.now-self.opened_at>=30:self.connected=False
            self.tx+=int(self.connected)
            return dict(kind='status',connected=int(self.connected),confirmed=int(self.connected),
                streaming=int(self.connected),codec=4 if self.connected else 0,peer=PEER,
                capture=int(self.capture()),decoder_ready=1,tx_packets=self.tx,send_failures=0,
                fault_hold=int(self.failed),mic_started=int(self.connected and self.capture()),
                mic_recovery_pending=0,mic_watchdog_failed=int(self.mic_fault()),mic_retry_count=3 if self.mic_fault() else 0,
                relay_connected=0,relay_streaming=0,control_tx=self.control_tx,
                control_last_id=self.last_id,control_last_value=self.last_value,
                control_rx_seq=list(self.sequences),allow_off=-1 if case=='off-unavailable' else 1,**self.controls)
        def eld(self):
            p=(ctypes.c_uint32*5)();s=self.settings
            profile(s['eldrate'],int(bool(s['usbset']&128)),s['gamelevel'],5,p)
            game=bool(s['usbset']&128)
            jitter=60 if game and s['gamelevel']==2 else 90 if game else 150
            return dict(kind='eldstatus',ready=int(self.connected),pending=0,
                transition='failed' if self.failed else 'ready',requested_revision=self.revision,
                built_revision=self.revision,active_bitrate=p[0],active_vbr=0,active_sbr=0,
                active_slots=p[3],input_rate=p[4],negotiated_bitrate=ceiling,negotiated_vbr=1,duplex_cbr=1,
                selected_rate=s['eldrate'],game=int(game),gamelevel=s['gamelevel'],
                desired_bitrate=p[0],active_jitter=jitter,desired_jitter=jitter,
                error_stage=(6 if case=='reconnect-fault' else 2) if self.failed else 0,
                last_error=(518 if case=='reconnect-fault' else 263) if self.failed else 0)
        def reply(self,raw):
            c=(ctypes.c_uint8*5)();assert parser(raw,len(raw),c),'Production C parser rejected '+repr(raw)
            command=raw.decode().strip()[1:];commands.append(command);name=command.split()[0]
            if c[4]:return [self.status()]
            assert c[0]==live.IDS[name],(name,c[0],live.IDS[name])
            if name=='info':return [dict(kind='info',protocol=2,sha='b'*40 if case=='identity-mismatch' else manifest['sha'],mic_decode=True,uac1=case=='normalize')]
            if name=='settings':return [dict(kind='settings',**self.settings)]
            if name=='status':return [self.status()]
            if name=='eldstatus':return [self.eld()]
            if name=='savedlist':return [dict(kind='savedlist',items=[])]
            if name=='scanlist':return [dict(kind='scanlist',items=[dict(index=0,mac=PEER,name='Simulated AirPods',rssi=-20)])]
            if name=='pair' and case=='pair-rejected':return [dict(kind='error',error='simulated pair rejection')]
            if name in ('pair','connect'):
                self.connected=True;self.failed=False;self.generation+=1
                if name=='connect':
                    self.connect_calls+=1
                    if case=='reconnect-fault' and self.connect_calls==2:self.connected=False;self.failed=True
            elif name=='disconnect':self.connected=False;self.generation+=1
            elif name=='profile':
                assert len(streams)==2 or not streams # Matrix or cleanup.
                self.settings.update(eldrate=c[1],gamelevel=c[3],usbset=(self.settings['usbset']&~128)|(128 if c[2] else 0))
                self.revision+=1
                if case=='start-rejected' and streams:self.connected=False;self.failed=True
            elif name in ('noise','pvol','ca','aa','jitter'):
                self.control_tx+=1;self.last_id=c[0];self.last_value=c[1]
                if name!='jitter':
                    self.controls[name]=(1 if c[1]==1 else 0) if name in ('pvol','ca') else c[1]
                    if case!='no-control-echo':self.sequences[dict(noise=1,pvol=2,ca=3,aa=4)[name]]+=1
            elif name in self.settings:self.settings[name]=c[1]
            elif name=='uac1':pass
            elif name=='rate44':self.settings['usbset']&=~8
            elif name=='reboot':self.connected=False
            ack=dict(kind='ack',id=c[0],value=c[1],queued=1,reboot_required=0)
            if name!='telemetry':return [ack]
            active=int(self.capture());n=int(clock.now*133)+1
            data=[dict(kind='aacpsession',open=int(self.connected),init_sent=3,init_mask=7,handshake_ack=int(case!='session-no-ack'),peer_seen=int(self.connected)),
                  dict(kind='micstats',generation=self.generation,capture=active,decoded=n,
                       clock_windows=1,measured_rate=64000,coding_rate=48000,pcm_rate=64000),
                  dict(kind='usbcapture',running=active,pcm_samples=int(clock.now*64000)+1),
                  dict(kind='hidstats',presses=1,releases=1)]
            return [ack]+data if len(commands)%2 else data+[ack]
    device=Device()
    class Port:
        def __init__(self,*args,**kwargs):self.rx=queue.Queue();self.closed=False;ports.append(self)
        def write(self,raw):
            if case=='usb-lost' and device.opened_at is not None and clock.now-device.opened_at>=5:
                raise OSError('simulated USB device removed')
            objects=device.reply(raw)
            data=b'[diag] simulated application/AACP/HID log\r\n'+b''.join((' [control] '+json.dumps(o)+'\r\n').encode() for o in objects)
            for off in range(0,len(data),37):self.rx.put(data[off:off+37])
        def read(self,count):
            try:return self.rx.get(timeout=.01)
            except queue.Empty:return b''
        def flush(self):pass
        def close(self):self.closed=True
    class Hid:
        closed=False;reads=0
        def __init__(self):handles.append(self)
        def open_path(self,path):assert path==b'correct-hid'
        def read(self,*args):
            self.reads+=1;threading.Event().wait(.002)
            return [1,0,0] if self.reads==1 else []
        def close(self):self.closed=True
    class Stream:
        def __init__(self,**kw):self.kw=kw;self.is_input=kw['device']==1
        def __enter__(self):
            streams.append(self)
            if self.is_input and device.opened_at is None:device.opened_at=clock.now
            device.capture();return self
        def __exit__(self,*args):streams.remove(self);device.capture()
    devices=[dict(name='USBPods simulated output',hostapi=0,max_input_channels=0,max_output_channels=2,default_samplerate=48000),
             dict(name='USBPods simulated input',hostapi=0,max_input_channels=2,max_output_channels=0,default_samplerate=48000)]
    sd=types.SimpleNamespace(query_devices=lambda index=None:devices if index is None else devices[index],
        query_hostapis=lambda index:dict(name='Windows WASAPI'),WasapiSettings=lambda **kw:kw,
        check_input_settings=lambda **kw:None,check_output_settings=lambda **kw:None,
        RawInputStream=Stream,RawOutputStream=Stream)
    cdc=types.SimpleNamespace(device='COM_SIM',vid=0xcafe,pid=1,serial_number='correct',description='simulation')
    list_ports=types.ModuleType('serial.tools.list_ports');list_ports.comports=lambda:[cdc]
    serial=types.ModuleType('serial');serial.Serial=Port
    serial_tools=types.ModuleType('serial.tools');serial_tools.list_ports=list_ports
    hid=types.SimpleNamespace(device=Hid,enumerate=lambda *args:[dict(path=b'wrong-hid',serial_number='other'),dict(path=b'correct-hid',serial_number='correct')])
    modules={'serial':serial,'serial.tools':serial_tools,'serial.tools.list_ports':list_ports,'hid':hid,'sounddevice':sd,'live_audio':audio}
    args=['live_test.py','--manifest',str(manifest_path),'--cdc','COM_SIM','--duration','5','--soak-seconds','10','--output',str(output)]
    session_case=case in ('session-only','session-peer-timeout','session-no-ack')
    if session_case:args+=['--session-only']
    def answer(message):return '0' if 'Enter the index' in message else ''
    log=io.StringIO()
    with mock.patch.dict(sys.modules,modules),mock.patch.object(sys,'argv',args),mock.patch('builtins.input',answer),mock.patch.object(live,'time',clock),mock.patch.object(audio,'time',clock),contextlib.redirect_stdout(log):
        code=live.main()
    root=next(output.glob('USBPods-results-*'))
    if root.suffix=='.zip':root=root.with_suffix('')
    summary=json.loads((root/'summary.json').read_text());tests=summary['tests']
    failed=case in ('identity-mismatch','pair-rejected','start-rejected','mic-watchdog','normalize','usb-lost','reconnect-fault','session-peer-timeout')
    assert code==(2 if failed else 0),(case,code,log.getvalue()[-1200:])
    assert summary['automated_pass']==(not failed)
    assert not summary['complete'] # Physical observations remain UNVERIFIED.
    if case=='usb-lost':
        assert summary.get('restore_errors') and tests['run']['status']=='FAIL'
        assert all('simulated USB device removed' in e for e in summary['collector_errors'])
    else:assert not summary['collector_errors'] and not summary.get('restore_errors')
    assert all(p.closed for p in ports) and all(h.closed for h in handles) and not streams
    if not failed and not session_case:
        for key in ('eld256','eld192','game_stable','game_latency','restore256','duplex_soak','capture_reconnect_1','capture_reconnect_2','capture_reconnect_3'):
            assert tests[key]['status']=='PASS',(case,key,tests[key])
        assert tests['eld320']['status']==('PASS' if ceiling>=320000 else 'SKIP')
        assert tests['mic_close_reopen_duplex']['status']==('UNVERIFIED' if case=='external-capture' else 'PASS')
        assert device.settings==device.original,(case,device.settings,device.original)
        assert device.controls==dict(noise=2,pvol=1,ca=1,aa=50)
        assert tests['noise']['status']==('UNVERIFIED' if case=='no-control-echo' else 'PASS')
        if case=='off-unavailable':
            assert 'noise 1' not in commands and tests['noise_off']['status']=='SKIP'
        for wav in root.glob('*.wav'):
            with wave.open(str(wav)) as f:assert (f.getframerate(),f.getnchannels(),f.getsampwidth())==(48000,2,2)
        assert list(root.glob('*.wav'))
    if session_case:
        assert not any(k in tests for k in ('eld192','game_stable','duplex_soak','noise','ear_and_stem'))
        assert device.connect_calls==0
        if case in ('session-only','session-no-ack'):
            assert tests['session_probe']['status']=='PASS' and tests['full_feature_matrix']['status']=='SKIP'
            assert tests['post_audio_controls']['status']=='SKIP' and tests['capture_close']['status']=='PASS'
            assert tests['aacp_handshake']['status']==('UNVERIFIED' if case=='session-no-ack' else 'PASS')
        else:
            fault=json.loads((root/'audio-failure-state.json').read_text())
            assert fault['before_stream_cleanup'] and fault['status']['capture'] and not fault['status']['connected']
            assert 'Playback failed during session_probe' in tests['simultaneous_audio']['detail']
    if case in ('start-rejected','mic-watchdog'):
        fault=json.loads((root/'audio-failure-state.json').read_text())
        assert fault['before_stream_cleanup'] and fault['status']['capture']
        if case=='mic-watchdog':assert fault['status']['mic_watchdog_failed'] and fault['status']['streaming']
        else:assert fault['eldstatus']['last_error']==263
    if case=='reconnect-fault':
        fault=json.loads((root/'audio-failure-state.json').read_text())
        assert fault['before_stream_cleanup'] and fault['status']['fault_hold']
        assert fault['eldstatus']['last_error']==518 and device.connect_calls==2
        assert 'Firmware fault while waiting' in tests['simultaneous_audio']['detail']
    if case=='normalize':assert not any(c.startswith('pair ') for c in commands)
    with zipfile.ZipFile(root.with_suffix('.zip')) as z:
        assert z.testzip() is None and 'summary.json' in z.namelist() and 'dependencies.json' in z.namelist()
        assert json.loads(z.read('summary.json'))==summary
    return dict(case=case,negotiated_ceiling=ceiling,pass_=True,runner_exit=code,
                commands=len(commands),result_entries=len(tests),simulated=True,
                physical_acceptance=False,archive=str(root.with_suffix('.zip')))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path);p.add_argument('--output',type=Path)
    options=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='usbpods-cli-e2e-') as temp:
        base=Path(temp);out=(options.output or base/'results').resolve();out.mkdir(parents=True,exist_ok=True)
        candidate=options.candidate.resolve() if options.candidate else base/'candidate'
        if not options.candidate:
            candidate.mkdir();(candidate/'fixture.uf2').write_bytes(b'simulation only')
            (candidate/'candidate.json').write_text(json.dumps(dict(hardware_test_candidate=True,sha='a'*40,mic_decode=True,
                firmware='fixture.uf2',firmware_sha256=hashlib.sha256(b'simulation only').hexdigest())))
        runner_dir=candidate if options.candidate else ROOT/'tools'
        live=load_module('e2e_live_test',runner_dir/'live_test.py');audio=load_module('e2e_live_audio',runner_dir/'live_audio.py')
        manifest_path=candidate/'candidate.json';manifest=json.loads(manifest_path.read_text());live.verify_manifest(candidate,manifest)
        (base/'shim.c').write_text(SHIM)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-DUSBPODS_MIC_DECODE=1','-shared','-fPIC','-I',str(ROOT/'src'),'-I',str(ROOT/'src/btstack'),
                        str(base/'shim.c'),str(ROOT/'src/control_command.c'),str(ROOT/'src/btstack/eld_profile.c'),'-o',str(base/'parser.so')],check=True)
        lib=ctypes.CDLL(str(base/'parser.so'));lib.parse_wire.argtypes=[ctypes.c_char_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_uint8)]
        lib.profile_wire.argtypes=[ctypes.c_uint]*4+[ctypes.POINTER(ctypes.c_uint32)]
        results=[]
        for case,ceiling in [('complete',256000),('complete-320',320000),('external-capture',256000),('no-control-echo',256000),('off-unavailable',256000),('session-only',256000),('session-peer-timeout',256000),('session-no-ack',256000),
                             ('identity-mismatch',256000),('pair-rejected',256000),('start-rejected',256000),('mic-watchdog',256000),('normalize',256000),('usb-lost',256000),('reconnect-fault',256000)]:
            d=out/case;d.mkdir(exist_ok=False)
            result=run_case(live,audio,manifest_path,manifest,lib.parse_wire,lib.profile_wire,d,case,ceiling)
            results.append(result);print('PASS '+case,flush=True)
        report=dict(simulated=True,physical_acceptance=False,candidate_sha=manifest['sha'],results=results)
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(f'{len(results)} CLI end-to-end scenarios passed; {out/"summary.json"}')
