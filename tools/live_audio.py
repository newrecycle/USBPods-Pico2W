"""Duplex hardware matrix. Imports host audio dependencies only when invoked."""
import contextlib
import json
import math
import queue
import threading
import time
import wave

PROFILES = [
    ('eld256',2,False,1,256000,5,1,6),
    ('eld192',1,False,1,192000,0,0,6),
    ('eld320',3,False,1,320000,0,0,9),
    ('game_stable',3,True,1,192000,0,0,6),
    ('game_latency',3,True,2,192000,0,0,4),
    ('restore256',2,False,1,256000,5,1,6),
]

def profile_matches(state, profile):
    _,_,_,_,bitrate,vbr,sbr,slots=profile
    if state.get('negotiated_vbr')==0:vbr=sbr=0
    return (state.get('ready')==1 and not state.get('pending') and
            state.get('transition')=='ready' and state.get('input_rate')==48000 and
            state.get('requested_revision')==state.get('built_revision') and
            all(state.get(k)==v for k,v in [('active_bitrate',bitrate),('active_vbr',vbr),
                                          ('active_sbr',sbr),('active_slots',slots)]))

def await_profile(link, profile, timeout=15):
    deadline=time.monotonic()+timeout;last={}
    while time.monotonic()<deadline:
        last=link.request('eldstatus')
        if last.get('transition')=='failed':
            raise RuntimeError('Firmware transition failed: '+str(last))
        if profile_matches(last,profile):return last
        time.sleep(.25)
    raise TimeoutError('Active ELD profile did not converge: '+str(last))

def snapshot(link, recorder, label):
    link.request('telemetry')
    state=recorder.control_snapshot()
    state['eldstatus']=link.request('eldstatus')
    state['status']=link.request('status')
    recorder.log('snapshots.jsonl',{'phase':label,'state':state})
    return state

def delta(before, after, key):
    return (int(after.get(key,0))-int(before.get(key,0))) & 0xffffffff

def health(before, after):
    """Evaluate steady intervals; transition/reconnect padding is kept separate."""
    a,b=before.get('micstats',{}),after.get('micstats',{})
    u,v=before.get('usbcapture',{}),after.get('usbcapture',{})
    errors=[]
    for item in (before,after):
        s=item.get('status',{});e=item.get('eldstatus',{})
        if not s.get('streaming') or s.get('codec')!=4 or e.get('transition')!='ready':
            errors.append('Playback was not in a ready AAC-ELD stream')
    if not delta(before.get('status',{}),after.get('status',{}),'tx_packets'):
        errors.append('No playback media packets progressed')
    if delta(before.get('status',{}),after.get('status',{}),'send_failures'):
        errors.append('Playback media submission failed')
    if not a or not b or not u or not v:return ['Missing firmware diagnostic snapshots']
    for item in (a,b):
        if not item.get('clock_windows') or abs(item.get('measured_rate',0)-64000)>3200:
            errors.append('Microphone cadence does not establish the expected 64 kHz PCM timeline')
        if item.get('coding_rate')!=48000 or item.get('pcm_rate')!=64000:
            errors.append('Unexpected microphone coding/PCM clock contract')
    if a.get('generation')!=b.get('generation'):errors.append('Microphone generation changed during steady playback')
    if not b.get('capture') or not v.get('running'):errors.append('USB capture stopped')
    if not delta(a,b,'decoded'):errors.append('No microphone frames decoded')
    if not delta(u,v,'pcm_samples'):errors.append('No decoded PCM reached USB')
    for key in ('errors','au_drop','pcm_drop'):
        n=delta(a,b,key)
        if n:errors.append(f'Microphone {key}: +{n}')
    for key in ('missing_samples','short_writes'):
        n=delta(u,v,key)
        if n:errors.append(f'USB {key}: +{n}')
    return errors

class AudioSession:
    """Callbacks only copy/queue samples. A worker owns WAV files and metrics."""
    def __init__(self,root,recorder,sd,np,output,inp):
        self.root,self.recorder,self.sd,self.np=root,recorder,sd,np
        self.output,self.inp=output,inp
        self.phase='capture_open';self.position=0
        self.rng=np.random.default_rng(0)
        self.queue=queue.Queue(maxsize=512);self.stop=threading.Event()
        self.lock=threading.Lock();self.metrics={};self.errors=[];self.output_errors={};self.drops=0
        self.files={};self.clip_samples={};self.stack=contextlib.ExitStack()
    def set_phase(self,name):
        self.phase=name;self.recorder.log('phases.jsonl',{'phase':name})
    def tone(self,outdata,frames,timing,status):
        np=self.np
        t=(np.arange(frames)+self.position)/48000
        values=np.column_stack((500*np.sin(2*np.pi*440*t),500*np.sin(2*np.pi*660*t)))
        # Quiet broadband sections exercise more than the inexpensive sine case.
        noise=(t.astype(np.int64)%8>=4)
        values+=self.rng.uniform(-140,140,(frames,2))*noise[:,None]
        self.position+=frames;outdata[:]=values.astype('<i2').tobytes()
        if status:self.output_errors.setdefault(self.phase,[]).append(str(status))
    def capture(self,indata,frames,timing,status):
        try:self.queue.put_nowait((self.phase,bytes(indata),str(status) if status else ''))
        except queue.Full:self.drops+=1
    def writer(self):
        while not self.stop.is_set() or not self.queue.empty():
            try:phase,data,status=self.queue.get(timeout=.1)
            except queue.Empty:continue
            try:
                samples=self.np.frombuffer(data,dtype='<i2').astype(self.np.int64)
                with self.lock:
                    m=self.metrics.setdefault(phase,{'samples':0,'sumsq':0,'peak':0,'clipped':0,'host_errors':[]})
                    m['samples']+=len(samples);m['sumsq']+=int(samples@samples)
                    m['peak']=max(m['peak'],int(self.np.abs(samples).max(initial=0)))
                    m['clipped']+=int((self.np.abs(samples)>=32760).sum())
                    if status and status not in m['host_errors']:m['host_errors'].append(status)
                saved=self.clip_samples.get(phase,0);count=min(len(samples),max(0,12*64000-saved))
                if count:
                    if phase not in self.files:
                        wav=wave.open(str(self.root/(phase+'.wav')),'wb')
                        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(64000);self.files[phase]=wav
                    self.files[phase].writeframes(data[:count*2]);self.clip_samples[phase]=saved+count
            except Exception as e:
                self.errors.append('audio writer: '+str(e));self.stop.set();break
    def __enter__(self):
        self.thread=threading.Thread(target=self.writer,daemon=True);self.thread.start()
        try:
            self.stack.enter_context(self.sd.RawOutputStream(device=self.output,channels=2,samplerate=48000,
                                    blocksize=0,dtype='int16',callback=self.tone))
            self.stack.enter_context(self.sd.RawInputStream(device=self.inp,channels=1,samplerate=64000,
                                    blocksize=640,dtype='int16',callback=self.capture))
        except BaseException:
            self.close();raise
        return self
    def close(self):
        try:self.stack.close()
        finally:
            self.stop.set();self.thread.join(timeout=5)
            if self.thread.is_alive():self.errors.append('Audio writer did not drain within five seconds')
            else:
                for wav in self.files.values():wav.close()
            with self.lock:
                result={k:{**v,'rms':math.sqrt(v['sumsq']/max(v['samples'],1))} for k,v in self.metrics.items()}
            (self.root/'audio-metrics.json').write_text(json.dumps({'phases':result,'errors':self.errors,
                     'output_status':self.output_errors,'collector_dropped_buffers':self.drops,'input_rate':64000,'output_rate':48000},indent=2))
    def __exit__(self,*exc):self.close()
    def phase_errors(self,name):
        with self.lock:m=dict(self.metrics.get(name,{}))
        errors=list(m.get('host_errors',[]))+list(self.output_errors.get(name,[]))+list(self.errors)
        if not m.get('samples'):errors.append('No host input samples collected')
        if m.get('samples') and not m.get('peak'):errors.append('Microphone recording contains only digital silence')
        if self.drops:errors.append('Audio collector queue overflowed')
        return errors

def run_matrix(args,root,link,recorder,select_audio,result,prompt,target_mac):
    import numpy as np
    import sounddevice as sd
    devices=list(sd.query_devices());(root/'audio-devices.json').write_text(json.dumps(devices,indent=2))
    output=select_audio(sd,'output',args.output_device);inp=select_audio(sd,'input',args.input_device)
    sd.check_output_settings(device=output,channels=2,samplerate=48000,dtype='int16')
    sd.check_input_settings(device=inp,channels=1,samplerate=64000,dtype='int16')
    def dwell(seconds,label):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            time.sleep(min(5,max(0,end-time.monotonic())))
            snapshot(link,recorder,label)
            if audio.stop.is_set():raise RuntimeError('Audio collector stopped: '+str(audio.errors))
    with AudioSession(root,recorder,sd,np,output,inp) as audio:
        link.wait(lambda s:s.get('capture') and s.get('confirmed'),15)
        dwell(3,'capture_warmup')
        limits=link.request('eldstatus')
        ceiling=limits.get('negotiated_bitrate',0)
        if ceiling<192000:raise RuntimeError('No valid AAC-ELD session ceiling: '+str(limits))
        baseline=PROFILES[-1] if ceiling>=256000 else ('restore192',1,False,1,192000,0,0,6)
        profiles=PROFILES[:-1]+[baseline]
        for profile in profiles:
            name,rate,gaming,level,*_=profile
            if profile[4]>ceiling:
                result(name,'SKIP',{'reason':'Peer/accepted configuration ceiling is lower than this profile','negotiated_bitrate':ceiling,'requested_bitrate':profile[4]})
                continue
            audio.set_phase('transition_'+name)
            settings=link.request('settings')
            for command,value,key in [('eldrate',rate,'eldrate'),('gamelevel',level,'gamelevel')]:
                if settings.get(key)!=value:link.request(f'{command} {value}')
            if bool(settings['usbset']&128)!=gaming:link.request('game '+str(int(gaming)))
            applied=await_profile(link,profile)
            dwell(2,'settle_'+name)
            audio.set_phase(name);print(f'{name}: speak/count during {args.duration} seconds of duplex capture.',flush=True)
            before=snapshot(link,recorder,name+'_begin');dwell(args.duration,name)
            after=snapshot(link,recorder,name+'_end')
            errors=health(before,after)+audio.phase_errors(name)
            result(name,'FAIL' if errors else 'PASS',{'errors':errors,'applied':applied,'before':before,'after':after})
        for cycle in range(3):
            name=f'capture_reconnect_{cycle+1}';audio.set_phase(name)
            link.request('disconnect');link.wait(lambda s:not s.get('connected'),15)
            link.request('connect')
            link.wait(lambda s:s.get('confirmed') and s.get('peer','').upper()==target_mac.upper(),45)
            await_profile(link,baseline);dwell(3,name+'_settle')
            before=snapshot(link,recorder,name+'_begin');dwell(5,name)
            after=snapshot(link,recorder,name+'_end');errors=health(before,after)
            result(name,'FAIL' if errors else 'PASS',{'errors':errors,'before':before,'after':after})
        audio.set_phase('duplex_soak');print(f'Duplex soak: {args.soak_seconds} seconds. Leave both streams open.',flush=True)
        before=snapshot(link,recorder,'soak_begin');dwell(args.soak_seconds,'duplex_soak')
        after=snapshot(link,recorder,'soak_end');errors=health(before,after)+audio.phase_errors('duplex_soak')
        result('duplex_soak','FAIL' if errors else 'PASS',{'seconds':args.soak_seconds,'errors':errors,'before':before,'after':after})
        if args.phone_relay:
            audio.set_phase('phone_relay_duplex');link.request('phonepair 1')
            try:
                prompt('Pair/play a phone now; leave PC playback and microphone capture running. Press Enter when playing:')
                state=link.wait(lambda s:s.get('relay_connected') and s.get('relay_streaming'),60)
                await_profile(link,('relay',2,False,2,164000,0,0,6));dwell(3,'relay_settle')
                before=snapshot(link,recorder,'phone_relay_duplex_begin');dwell(15,'phone_relay_duplex')
                after=snapshot(link,recorder,'phone_relay_duplex_end');errors=health(before,after)
                heard=prompt('Was the mixed phone/PC audio clear? Type yes/no, or Enter for unverified:')
                result('phone_relay_duplex','FAIL' if errors or heard.lower()=='no' else 'PASS' if heard.lower()=='yes' else 'UNVERIFIED',{'state':state,'errors':errors,'before':before,'after':after})
            finally:
                link.request('phonedisc');link.request('phonepair 0')
    link.wait(lambda s:not s.get('capture'),10)
    result('capture_close','PASS','Host capture intent cleared after stream close; inspect STOP log as separate wire evidence')
