#!/usr/bin/env python3
"""Bounded USBPods hardware acceptance; never reports simulation as hardware."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import queue
import re
import sys
import threading
import time
import traceback
import wave
import zipfile

PREFIX = '[control] '
IDS = dict(zip('info scan scanlist scanstop pair connect disconnect settings uart debug game earpause stem gamelevel eldrate usbvol phvol connmode slot savedconnect saveddelete phonepair phonedisc phoneconnect relayaac uac1 rate44 bootconn pausedc swvol btnmode ldacq lhdcrate reboot telemetry savedlist'.split(), range(128,164)))
IDS['eldstatus']=164
IDS['profile']=165
IDS.update(noise=13, pvol=38, ca=40, aa=46, jitter=11)
QUERIES = {'eldstatus':'eldstatus', 'status':'status', 'info':'info', 'settings':'settings', 'scanlist':'scanlist', 'savedlist':'savedlist'}

def parse_control(line):
    # The legacy console can leave indentation after a status/prompt. Do not
    # discard an otherwise complete response (the first hardware pair ACK did).
    line = line.lstrip(' \t')
    if not line.startswith(PREFIX):
        return None
    obj = json.loads(line[len(PREFIX):])
    if not isinstance(obj, dict):
        raise ValueError('control response is not an object')
    return obj

def choose_target(items, mac=None, name=None):
    if not (mac or name):raise ValueError('No exact target supplied')
    matches = [x for x in items if (x.get('mac','').upper()==mac.upper() if mac else x.get('name')==name)]
    if len(matches) != 1:
        raise ValueError(f'Expected one exact AirPods match; found {len(matches)}. Specify --target-mac or an exact --target-name.')
    return matches[0]

def restoration_commands(original, current):
    """Avoid side effects from reapplying unchanged preferences after a failure."""
    if not current:return []
    commands=[]
    profile=lambda settings:(settings['eldrate'] or 2,int(bool(settings['usbset']&128)),settings['gamelevel'] or 1)
    if profile(original)!=profile(current):commands.append(('profile',profile(original)))
    for name in ('earpause','stem','debug','usbvol','phvol','btnmode','ldacq','lhdcrate'):
        def value(settings):
            if name in ('game','uart'):return int(bool(settings['usbset'] & (128 if name=='game' else 64)))
            return settings[name]
        if value(original)!=value(current):commands.append((name,value(original)))
    return commands

def connection_preflight(link,recorder,seconds=5):
    """Require sustained source traffic before feature mutations or recording."""
    settle_until=time.monotonic()+15
    while True:
        start=link.request('status');encoder=link.request('eldstatus')
        recorder.log('connection-preflight.jsonl',{'phase':'settle','status':start,'encoder':encoder})
        if start.get('mic_watchdog_failed') or start.get('fault_hold') or not start.get('connected') or encoder.get('transition')=='failed':
            raise RuntimeError('Firmware failed while settling initial microphone/playback: '+str({'status':start,'encoder':encoder}))
        if (start.get('confirmed') and start.get('streaming') and start.get('codec')==4 and
            encoder.get('transition')=='ready' and not encoder.get('pending') and
            not start.get('mic_recovery_pending') and (not start.get('capture') or start.get('mic_started'))):break
        if time.monotonic()>=settle_until:raise TimeoutError('Initial microphone/playback recovery did not settle')
        time.sleep(.25)
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        state=link.request('status');encoder=link.request('eldstatus')
        recorder.log('connection-preflight.jsonl',{'status':state,'encoder':encoder})
        if not all(state.get(k) for k in ('connected','confirmed','streaming')) or state.get('codec')!=4:
            raise RuntimeError('Headset/AACP/playback did not remain connected: '+str(state))
        if encoder.get('transition')!='ready' or encoder.get('pending') or state.get('mic_recovery_pending') or state.get('fault_hold') or state.get('mic_watchdog_failed'):
            raise RuntimeError('Firmware setup/recovery failed: '+str(encoder))
        time.sleep(.25)
    end=link.request('status')
    if not ((end.get('tx_packets',0)-start.get('tx_packets',0))&0xffffffff):
        raise RuntimeError('Playback state reported streaming but no media packets progressed')
    if ((end.get('send_failures',0)-start.get('send_failures',0))&0xffffffff):
        raise RuntimeError('Playback media submissions failed during connection preflight')
    return {'start':start,'end':end,'seconds':seconds}

def verify_manifest(root, manifest):
    if manifest.get('validation_blockers'):
        raise ValueError('Hardware validation is on hold: '+'; '.join(manifest['validation_blockers']))
    if manifest.get('hardware_test_candidate') is not True or not re.fullmatch(r'[a-f0-9]{40}',manifest.get('sha','')):
        raise ValueError('Missing verified hardware-test candidate manifest')
    root=root.resolve()
    firmware = (root / manifest['firmware']).resolve()
    if firmware.parent != root or firmware.suffix != '.uf2':
        raise ValueError('Invalid firmware path')
    if hashlib.sha256(firmware.read_bytes()).hexdigest() != manifest['firmware_sha256']:
        raise ValueError('Firmware hash does not match the verified candidate')
    for name,digest in manifest.get('runner_files',{}).items():
        file=(root/name).resolve()
        if file.parent!=root or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
            raise ValueError('Bundle file is missing or changed: '+name)
    return firmware

class Recorder:
    def __init__(self, root):
        self.root, self.lock, self.bytes = root, threading.Lock(), {}
        self.stop = threading.Event()
        self.threads, self.handles = [], []
        self.events = queue.Queue(maxsize=8192)
        self.errors = [];self.latest = {}
    def log(self, name, obj):
        data = json.dumps({'utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'monotonic_ns':time.monotonic_ns(), **obj}, ensure_ascii=True)+'\n'
        with self.lock:
            size=self.bytes.get(name,0)
            if size+len(data)>16*1024*1024:
                if size<=16*1024*1024:
                    self.errors.append(name+' log reached 16 MiB limit')
                    self.bytes[name]=16*1024*1024+1
                return
            with (self.root/name).open('a',encoding='utf-8') as f:f.write(data)
            self.bytes[name]=size+len(data)
    def serial_reader(self, port, name, controls=False):
        def run():
            buffer=b''
            while not self.stop.is_set():
                try:
                    data=port.read(4096)
                    if not data:continue
                    buffer+=data
                    if len(buffer)>65536:raise ValueError('serial line exceeds 64 KiB')
                    while b'\n' in buffer:
                        line,buffer=buffer.split(b'\n',1)
                        text=line.decode('utf-8',errors='replace').rstrip('\r')
                        self.log(name,{'line':text})
                        if controls:
                            try:
                                obj=parse_control(text)
                                if obj is not None:
                                    with self.lock:self.latest[obj.get('kind','unknown')]=obj
                                    self.events.put_nowait(obj)
                            except (ValueError,queue.Full) as e:
                                self.errors.append(f'{name}: {e}')
                except Exception as e:
                    if not self.stop.is_set():self.errors.append(f'{name} read: {e}')
                    break
        t=threading.Thread(target=run,daemon=True);t.start();self.threads.append(t)
    def control_snapshot(self):
        with self.lock:return {k:dict(v) for k,v in self.latest.items()}
    def close(self):
        self.stop.set()
        for t in self.threads:t.join(timeout=2)
        for h in self.handles:
            try:h.close()
            except Exception:pass

class Link:
    def __init__(self, port, recorder):
        self.port,self.recorder=port,recorder
    def request(self, command, timeout=6):
        name=command.split()[0]
        if name not in IDS and name!='status':raise ValueError('Unknown host command')
        while True:
            try:self.recorder.events.get_nowait()
            except queue.Empty:break
        self.recorder.log('commands.jsonl',{'sent':command})
        self.port.write((':'+command+'\n').encode('ascii'));self.port.flush()
        deadline=time.monotonic()+timeout
        kind=QUERIES.get(name,'ack')
        expected_value = int(command.split()[1]) if len(command.split())==2 or name=='profile' else 0
        if name in ('pvol','ca'):
            expected_value = 1 if expected_value else 2  # Firmware ACK uses wire enum.
        pending = {'micstats','usbcapture','hidstats'} if name=='telemetry' else set()
        ack = None
        while time.monotonic()<deadline:
            try:obj=self.recorder.events.get(timeout=min(.25,max(.01,deadline-time.monotonic())))
            except queue.Empty:continue
            if obj.get('kind')=='error':raise RuntimeError(str(obj))
            pending.discard(obj.get('kind'))
            if ack is not None and not pending:return ack
            if obj.get('kind')!=kind:continue
            if kind=='ack' and obj.get('id')!=IDS[name]:continue
            if kind=='ack' and obj.get('value')!=expected_value:continue
            self.recorder.log('commands.jsonl',{'received':obj})
            if kind=='ack' and obj.get('queued')!=1:raise RuntimeError(f'Command rejected: {command}: {obj}')
            if pending:
                ack=obj
                continue
            return obj
        raise TimeoutError('No matching response to '+command)
    def wait(self, predicate, timeout=45):
        deadline=time.monotonic()+timeout;last={}
        while time.monotonic()<deadline:
            last=self.request('status')
            if predicate(last):return last
            if last.get('fault_hold') or last.get('mic_watchdog_failed'):
                raise RuntimeError('Firmware fault while waiting for device state: '+str(last))
            time.sleep(.5)
        raise TimeoutError(f'Device state timeout; last={last}')

CONTROL_WIRE = {'noise':(0x0d,1),'pvol':(0x26,2),'ca':(0x28,3),'aa':(0x2e,4),'jitter':(0x0b,0)}

def peer_control_values(command, values, state):
    """Off is an optional AirPods capability, not an ANC application failure."""
    if command=='noise' and state.get('allow_off')!=1:
        return [v for v in values if v!=1]
    return list(values)
def submit_peer_control(link, command, value):
    identifier,_=CONTROL_WIRE[command]
    before=link.request('status')
    link.request(f'{command} {value}')
    wire_value=(1 if value else 2) if command in ('pvol','ca') else value
    sent=link.wait(lambda s:((s.get('control_tx',0)-before.get('control_tx',0))&0xffffffff)>0 and
                   s.get('control_last_id')==identifier and s.get('control_last_value')==wire_value,5)
    return before,sent

def observe_peer_control(link, command, value, before, seconds=3):
    _,index=CONTROL_WIRE[command]
    previous=before.get('control_rx_seq',[0]*5)[index]
    deadline=time.monotonic()+seconds;last=before
    while time.monotonic()<deadline:
        last=link.request('status')
        seq=last.get('control_rx_seq',[0]*5)[index]
        if seq!=previous and last.get(command)==value:return True
        time.sleep(.25)
    if last.get('control_rx_seq',[0]*5)[index]!=previous:
        raise RuntimeError('Fresh peer notification differs from requested '+command+': '+str(last.get(command)))
    return False # Several AirPods control writes do not produce an echo.

def select_audio(sd, kind, explicit):
    devices=sd.query_devices()
    if explicit is not None:return explicit
    candidates=[i for i,d in enumerate(devices) if d['max_'+kind+'_channels'] and ('usbpods' in d['name'].lower() or 'tinyusb bt' in d['name'].lower())]
    wasapi=[i for i in candidates if 'WASAPI' in sd.query_hostapis(devices[i]['hostapi'])['name']]
    if len(wasapi)==1:return wasapi[0]
    if len(candidates)==1:return candidates[0]
    raise ValueError(f'Ambiguous {kind} audio endpoint. See audio-devices.json and use --{kind}-device. Candidates: {candidates}')

def collect_hid(recorder, cdc):
    import hid
    devices=hid.enumerate(cdc.vid or 0xcafe,cdc.pid or 0)
    serial=cdc.serial_number
    matched=[d for d in devices if serial and d.get('serial_number')==serial]
    recorder.log('hid-devices.jsonl',{'devices':[{k:(v.hex() if isinstance(v,bytes) else v) for k,v in d.items()} for d in devices]})
    if not matched:raise RuntimeError('No HID interface with the CDC device serial number; refusing unrelated devices')
    opened=0
    for d in matched:
        try:
            h=hid.device();h.open_path(d['path']);recorder.handles.append(h);opened+=1
            def reader(handle=h):
                while not recorder.stop.is_set():
                    try:
                        data=handle.read(64,100)
                        if data:recorder.log('hid-input.jsonl',{'data':bytes(data).hex()})
                    except Exception as e:
                        recorder.log('hid-errors.jsonl',{'error':str(e)});break
            t=threading.Thread(target=reader,daemon=True);t.start();recorder.threads.append(t)
        except Exception as e:recorder.log('hid-errors.jsonl',{'error':str(e),'interface':d.get('interface_number')})
    if not opened:raise RuntimeError('OS did not allow raw HID reads; firmware HID send logs will still be captured')
    return opened

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=Path(__file__).with_name('candidate.json'))
    parser.add_argument('--cdc',help='USB CDC diagnostic/control port; no UART adapter is used')
    target=parser.add_mutually_exclusive_group()
    target.add_argument('--target-name');target.add_argument('--target-mac')
    parser.add_argument('--input-device',type=int);parser.add_argument('--output-device',type=int)
    parser.add_argument('--duration',type=int,default=20,help='Steady seconds per playback profile')
    parser.add_argument('--soak-seconds',type=int,default=600)
    parser.add_argument('--phone-relay',action='store_true',help='Include phone relay with both USB streams open')
    parser.add_argument('--session-only',action='store_true',help='Only a 45-second AAC-ELD/mic/USB session probe; omit the full feature matrix')
    parser.add_argument('--output',type=Path,default=Path.cwd())
    parser.add_argument('--noninteractive',action='store_true')
    args=parser.parse_args()
    if not 5<=args.duration<=120:parser.error('--duration must be 5..120 seconds')
    if not 10<=args.soak_seconds<=1800:parser.error('--soak-seconds must be 10..1800')
    if args.phone_relay and args.noninteractive:parser.error('--phone-relay requires physical phone prompts')
    if args.phone_relay and args.session_only:parser.error('--session-only cannot include phone relay')
    if args.noninteractive and not (args.target_name or args.target_mac):parser.error('Noninteractive pairing requires an exact target identity')
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root=args.output/('USBPods-results-'+stamp);root.mkdir(parents=True,exist_ok=False)
    recorder=Recorder(root);link=None;original=None;summary={'schema':1,'hardware_run':True,'tests':{},'host':platform.platform(),'started':stamp}
    def result(name,status,detail=None):
        summary['tests'][name]={'status':status,'detail':detail};print(name+': '+status,flush=True)
    def prompt(message):
        if args.noninteractive:return ''
        return input(message+' ').strip()
    try:
        manifest=json.loads(args.manifest.read_text());verify_manifest(args.manifest.parent.resolve(),manifest)
        flash_log=args.manifest.parent/'flash-log.json'
        if flash_log.is_file():
            flash=json.loads(flash_log.read_text(encoding='utf-8'))
            if flash.get('candidate_sha')==manifest['sha']:
                (root/'flash-log.json').write_text(json.dumps(flash,indent=2),encoding='utf-8')
        summary['candidate']=manifest;(root/'candidate.json').write_text(json.dumps(manifest,indent=2))
        import serial
        from serial.tools import list_ports
        ports=list(list_ports.comports());(root/'ports.json').write_text(json.dumps([{'device':p.device,'vid':p.vid,'pid':p.pid,'serial':p.serial_number,'description':p.description} for p in ports],indent=2))
        candidates=[p for p in ports if p.device==args.cdc] if args.cdc else [p for p in ports if p.vid==0xcafe]
        if len(candidates)!=1:raise RuntimeError('Select one Pico CDC port with --cdc COMx; inventory is in ports.json')
        cdc=candidates[0];port=serial.Serial(cdc.device,115200,timeout=.1,write_timeout=3)
        recorder.handles.append(port);recorder.serial_reader(port,'cdc.jsonl',True);link=Link(port,recorder)
        time.sleep(.5);info=link.request('info')
        if info.get('sha')!=manifest['sha'] or info.get('protocol')!=2:raise RuntimeError('Running firmware does not match this verified bundle')
        if info.get('mic_decode')!=manifest['mic_decode']:raise RuntimeError('Wrong firmware variant')
        summary['firmware']=info;result('firmware_identity','PASS',info)
        original=link.request('settings');summary['original_settings']=original
        summary['original_saved']=link.request('savedlist')
        # Descriptor mode changes require one explicit replug, before any pairing.
        if info.get('uac1') or original['connmode']!=1 or original['usbset']&8:
            link.request('connmode 1')
            if info.get('uac1'):link.request('uac1 0')
            if original['usbset']&8:link.request('rate44 0')
            reboot=bool(info.get('uac1') or original['usbset']&8)
            original=None # Keep intentional UAC2/manual/48k normalization for the rerun.
            if reboot:link.request('reboot')
            raise RuntimeError('Saved UAC2/manual/48k mode. Replug the Pico and rerun; no AirPods pairing was attempted.')
        if info['mic_decode'] and not link.request('status').get('decoder_ready'):raise RuntimeError('Microphone decoder allocation failed; do not proceed with pairing')
        result('diagnostic_transport','PASS',{'transport':'usb-cdc','port':cdc.device,'log':'cdc.jsonl','includes':'application, AACP, codec, USB and firmware HID submission logs'})
        try:result('hid_connection','PASS',collect_hid(recorder,cdc))
        except Exception as e:result('hid_connection','SKIP',str(e))
        link.request('disconnect')
        link.wait(lambda s:not s.get('connected'),15)
        prompt('Put the intended AirPods case into pairing mode now. Press Enter when ready:')
        link.request('scan');time.sleep(16);link.request('scanstop')
        items=link.request('scanlist')['items'];(root/'scan.json').write_text(json.dumps(items,indent=2))
        try:chosen=choose_target(items,args.target_mac,args.target_name)
        except ValueError:
            if args.noninteractive:raise
            print('Scanned devices:',json.dumps(items,indent=2),flush=True)
            index=int(prompt('Enter the index of the intended AirPods from that list (no automatic guess):'))
            selected=[item for item in items if item.get('index')==index]
            if len(selected)!=1:raise ValueError('Not one scanned target at that index')
            chosen=selected[0]
        summary['target']=chosen
        link.request('pair '+str(chosen['index']))
        state=link.wait(lambda s:s.get('connected') and s.get('peer','').upper()==chosen['mac'].upper(),45)
        result('targeted_connection','PASS',state)
        state=link.wait(lambda s:s.get('connected') and s.get('confirmed') and s.get('peer','').upper()==chosen['mac'].upper(),30)
        result('aacp_peer_response','PASS',state)
        link.request('telemetry');link.request('eldstatus')
        session=recorder.control_snapshot().get('aacpsession',{})
        result('aacp_handshake','PASS' if session.get('open') and session.get('handshake_ack') else 'UNVERIFIED',
               {'session':session,'reason':'Peer traffic and locally submitted initialization do not independently establish a handshake acknowledgment'})
        result('connection_preflight','PASS',connection_preflight(link,recorder))
        link.request('earpause 0');link.request('stem 0')
        if state.get('relay_connected'):
            link.request('phonedisc');link.wait(lambda s:not s.get('relay_connected'),15)
        if args.session_only:
            print('Session probe starts automatically: wear the AirPods. PC playback and microphone capture stay open for 45 seconds. Play your phone-speaker clip for the first 20 seconds if convenient; no counting or talking is required.',flush=True)
        else:
            prompt('Wear the AirPods. The PC will play a quiet tone. For microphone input, play a clip through your phone SPEAKER near the AirPods, or speak. Keep the phone audio off Bluetooth. Press Enter to start:')
        capture_ca=link.request('status').get('ca',-1)
        audio_ok=False
        try:
            if capture_ca>0:
                submit_peer_control(link,'ca',0)
            if not info['mic_decode']:raise RuntimeError('This priority matrix requires the microphone-decoder candidate')
            from live_audio import run_matrix
            run_matrix(args,root,link,recorder,select_audio,result,prompt,chosen['mac'])
            audio_ok=True
        except Exception as e:
            result('simultaneous_audio','FAIL',str(e));(root/'audio-exception.txt').write_text(traceback.format_exc(),encoding='utf-8')
            try:
                from live_audio import preserve_audio_failure
                preserve_audio_failure(root,link,recorder,e,before_cleanup=False)
            except Exception as error:recorder.errors.append('audio failure diagnostics: '+str(error))
        finally:
            if capture_ca>0:
                try:submit_peer_control(link,'ca',capture_ca)
                except Exception as e:recorder.errors.append('restore ca after audio: '+str(e))
        link.request('telemetry')
        if audio_ok and not args.session_only:
            for command,field,values in [('noise','noise',[1,2,3,4]),('pvol','pvol',[0,1]),('ca','ca',[0,1]),('aa','aa',[0,50,100])]:
                control_state=link.request('status');initial=control_state[field]
                if initial<0 or (field=='noise' and initial==0):result(command,'SKIP','No peer notification establishes support/state');continue
                if command=='noise' and initial==1 and link.request('status').get('allow_off')!=1:
                    result(command,'SKIP','Current Off mode cannot be safely restored without an AllowOff notification');continue
                selected_values=peer_control_values(command,values,control_state)
                if selected_values!=values:
                    result('noise_off','SKIP','Peer has not reported AllowOff=1; Off is unavailable or unconfirmed')
                observed=[]
                try:
                    for value in selected_values:
                        before,sent=submit_peer_control(link,command,value)
                        echo=observe_peer_control(link,command,value,before)
                        observed.append({'requested':value,'wire_sent':True,'fresh_peer_readback':echo,'control_tx':sent['control_tx']})
                    result(command,'PASS' if all(x['fresh_peer_readback'] for x in observed) else 'UNVERIFIED',
                           {'changes':observed,'reason':'Missing echo is not proof of application; physical control behavior requires observation'})
                except Exception as e:result(command,'FAIL',str(e))
                finally:
                    try:submit_peer_control(link,command,initial)
                    except Exception as e:recorder.errors.append('restore '+command+': '+str(e))
            link.request('jitter 150');result('jitter','UNVERIFIED','Queued exact reference command; no independent peer readback')
            for command,field,values in [('usbvol','usbvol',[75,100]),('phvol','phvol',[75,100]),('btnmode','btnmode',[1,2,3,4]),('ldacq','ldacq',[1,2,3]),('lhdcrate','lhdcrate',[1,2,3,4])]:
                try:
                    for value in values:
                        link.request(f'{command} {value}')
                        if link.request('settings')[field]!=value:raise RuntimeError('Setting readback mismatch')
                    result('setting_'+command,'PASS','RAM readback; codec performance requires matching headset')
                except Exception as e:result('setting_'+command,'FAIL',str(e))
                finally:
                    try:link.request(f'{command} {original[field]}')
                    except Exception as e:recorder.errors.append('restore '+command+': '+str(e))
            heard=prompt('Was playback clear? Type yes, no, or Enter for unverified:')
            result('playback_quality','PASS' if heard.lower()=='yes' else 'FAIL' if heard.lower()=='no' else 'UNVERIFIED',heard)
            wavs=sorted(root.glob('*.wav'))
            if wavs:
                print('Recorded clips:',', '.join(p.name for p in wavs),flush=True)
                heard=prompt('Listen to a recorded WAV in the results folder. Was microphone pitch/speed natural? Type yes/no, or Enter if not checked:')
                result('microphone_pitch','PASS' if heard.lower()=='yes' else 'FAIL' if heard.lower()=='no' else 'UNVERIFIED',heard)
            else:result('microphone_pitch','UNVERIFIED','Audio capture produced no WAV files; no listening prompt was presented')
            link.request('earpause 1');link.request('stem 1')
            note=prompt('Start playback, remove/reinsert one then both buds, and try single/double/triple stem presses. Describe behavior (or Enter to leave unverified):')
            result('ear_and_stem','UNVERIFIED',note or 'No physical observation supplied; see firmware HID and raw HID logs')
        else:
            result('post_audio_controls','SKIP','Session-only diagnostic scope' if args.session_only else 'Audio matrix failed; no further control mutations or physical prompts')
        if not args.phone_relay:result('phone_relay_duplex','SKIP','Use --phone-relay to include a physical phone in this same session')
        result('persistence_suspend_uac_slots_other_codecs','UNVERIFIED','Requires the guided matrix in LIVE-TEST.md; destructive/USB-reenumeration tests are not silently automated')
        link.request('savedlist');link.request('telemetry')
    except (Exception,KeyboardInterrupt) as e:
        result('run','FAIL',str(e));(root/'exception.txt').write_text(traceback.format_exc(),encoding='utf-8')
        # Preserve the failure state before cleanup can rebuild or reconnect.
        if link:
            diagnostics={}
            for command in ('status','eldstatus','telemetry','savedlist'):
                try:diagnostics[command]=link.request(command,timeout=2)
                except Exception as error:diagnostics[command]={'error':str(error)}
            diagnostics['observed']=recorder.control_snapshot()
            (root/'failure-state.json').write_text(json.dumps(diagnostics,indent=2),encoding='utf-8')
    finally:
        if link and original:
            restore=[]
            try:current=link.request('settings',timeout=2)
            except Exception as e:
                current={};restore.append({'command':'settings-before-restore','error':str(e)})
            for command,value in restoration_commands(original,current):
                try:link.request(command+' '+' '.join(str(int(v)) for v in (value if isinstance(value,tuple) else (value,))),timeout=2)
                except Exception as e:restore.append({'command':command,'error':str(e)})
            summary['restore_errors']=restore
            try:
                time.sleep(2.5) # Allow the existing debounced settings writer to run.
                summary['restored_settings']=link.request('settings',timeout=2)
            except Exception as e:restore.append({'command':'settings','error':str(e)})
        recorder.close();summary['collector_errors']=recorder.errors
        summary['complete']=bool(summary['tests']) and all(x['status']=='PASS' for x in summary['tests'].values()) and not recorder.errors and not summary.get('restore_errors')
        summary['automated_pass']=bool(summary['tests']) and not any(x['status']=='FAIL' for x in summary['tests'].values()) and not recorder.errors and not summary.get('restore_errors')
        (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        versions={}
        for name in ('pyserial','hidapi','sounddevice','numpy'):
            try:versions[name]=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:versions[name]='missing'
        (root/'dependencies.json').write_text(json.dumps(versions,indent=2))
        archive=root.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for file in root.iterdir():
                if file.is_file():z.write(file,file.name)
        print('Return this bundle:',archive)
    return 0 if summary['automated_pass'] else 2

if __name__=='__main__':
    sys.exit(main())
