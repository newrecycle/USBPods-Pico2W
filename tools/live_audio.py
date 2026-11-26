"""Duplex hardware matrix. Imports host audio dependencies only when invoked."""
import contextlib
import json
import math
import queue
import re
import threading
import time
import wave
import traceback

def observation_status(text, category='quality', expected=None):
    """Classify an explicit physical observation; never infer missing evidence.

    Callers retain the operator's exact text. Free-form descriptions of problems
    are FAIL, rather than silently UNVERIFIED, but unclear reports remain so.
    """
    value=re.sub(r'\s+', ' ', text.strip()).casefold()
    if not value:
        return 'UNVERIFIED'
    if value in ('yes','y'):
        return 'UNVERIFIED' if category=='gestures' else 'PASS'
    if value in ('no','n','fail','failed','wrong-side','wrong side','silent','both'):
        return 'FAIL'
    if re.match(r'^no(?:[,.:;!]|\s+(?:it|the|audio|sound|left|right|playback)\b)', value):
        return 'FAIL'
    if category=='channel' and expected in ('left','right'):
        other='right' if expected=='left' else 'left'
        side=re.fullmatch(r'(?:(?:only|just) (?:the )?)?(left|right)'
                          r'(?: (?:ear|bud|side|channel))?(?: (?:only|audible|playing))?',value)
        if side:
            return 'PASS' if side.group(1)==expected else 'FAIL'
        if re.search(r'\b'+expected+r' (?:ear|bud|side|channel) (?:is |was )?'
                     r'(?:silent|muted|missing|not (?:playing|audible))\b',value):
            return 'FAIL'
        if re.search(r'\b(?:only (?:the )?'+other+r'|'+other+
                     r' (?:ear|bud|side|channel) only)\b',value):
            return 'FAIL'
        if re.search(r'\b(?:both ears?|both sides?|wrong (?:ear|side|channel)|'
                     r'neither ear|no (?:audio|sound|playback)|nothing happened|did nothing)\b',value):
            return 'FAIL'
        if re.search(r'\b'+expected+r'[- ]only.*\b(?:silent|inaudible|missing)\b',value):
            return 'FAIL'
        # Silence in the opposite ear is compatible with a one-sided stimulus.
        return 'UNVERIFIED'
    if re.search(r'\b(?:distorted|crackling|clipping|incorrect|wrong|'
                 r'did nothing|nothing happened|did not work|doesn.t work|'
                 r'not working|not audible|silent|silence|'
                 r'no (?:audio|sound|playback)|too (?:fast|slow|high|low)(?:[ -]pitched)?|'
                 r'sped up)\b',value):
        if not re.search(r'\b(?:not silent|no distortion|no clipping|no crackling)\b',value):
            return 'FAIL'
    return 'UNVERIFIED'


PROFILES = [
    ('eld256',2,False,1,256000,5,1,6),
    ('eld192',1,False,1,192000,0,0,6),
    ('eld320',3,False,1,320000,0,0,9),
    ('game_stable',3,True,1,192000,0,0,6),
    ('game_latency',3,True,2,192000,0,0,4),
    ('restore256',2,False,1,256000,5,1,6),
]

def profile_matches(state, profile):
    """Require the selected preference AND the applied, rebuilt codec policy.

    Normal 192 CBR and game-standard share 192 kbps and six slots; the active
    jitter policy (150 vs 90 ms) is necessary to distinguish them. This is
    firmware-selected policy, not proof the peer acknowledged an AACP write.
    Missing diagnostics fail closed instead of accepting stale profiles.
    """
    _, rate, game, level, bitrate, vbr, sbr, slots = profile
    if state.get('negotiated_vbr') == 0 or state.get('duplex_cbr') == 1:
        vbr = sbr = 0
    jitter = 60 if game and level == 2 else 90 if game else 150
    revision = state.get('requested_revision')
    expected = (
        ('selected_rate', rate), ('game', int(game)), ('gamelevel', level),
        ('desired_bitrate', bitrate), ('active_bitrate', bitrate),
        ('active_vbr', vbr), ('active_sbr', sbr), ('active_slots', slots),
        ('active_jitter', jitter), ('desired_jitter', jitter),
    )
    return (
        state.get('ready') == 1 and state.get('pending') == 0
        and state.get('transition') == 'ready'
        and state.get('input_rate') == 48000
        and isinstance(revision, int) and revision == state.get('built_revision')
        and isinstance(state.get('negotiated_bitrate'), int)
        and state['negotiated_bitrate'] >= bitrate
        and all(state.get(key) == value for key, value in expected)
    )

def await_profile(link, profile, timeout=15):
    deadline=time.monotonic()+timeout;last={}
    while time.monotonic()<deadline:
        last=link.request('eldstatus')
        if last.get('transition')=='failed' or (last.get('error_stage') and last.get('transition')=='off'):
            raise RuntimeError('Firmware transition failed: '+str(last))
        if profile_matches(last,profile):return last
        time.sleep(.25)
    raise TimeoutError('Active ELD profile did not converge: '+str(last))

def await_duplex_ready(link, recorder, profile, label, timeout=20):
    """Start steady measurement after both paths settle, retaining startup logs."""
    deadline=time.monotonic()+timeout;stable_since=None;start_tx=None;last={}
    recovery_observed=False;previous_retry=None
    while time.monotonic()<deadline:
        status=link.request('status');eld=link.request('eldstatus')
        last={'status':status,'eldstatus':eld}
        recorder.log('connection-preflight.jsonl',{'phase':label,**last})
        if status.get('fault_hold') or status.get('mic_watchdog_failed') or not status.get('connected') or eld.get('transition')=='failed':
            raise RuntimeError('Firmware failed during '+label+': '+str(last))
        ready=(profile_matches(eld,profile) and status.get('streaming') and status.get('codec')==4 and
               status.get('confirmed') and status.get('capture') and status.get('mic_started') and
               not status.get('mic_recovery_pending'))
        retry=(status.get('mic_restarts'),status.get('mic_retry_count'),status.get('mic_watchdog_failures'))
        if previous_retry is not None and retry!=previous_retry:
            recovery_observed=True;ready=False
        previous_retry=retry
        if ready:
            if stable_since is None:stable_since=time.monotonic();start_tx=status.get('tx_packets',0)
            if time.monotonic()-stable_since>=2 and delta({'tx_packets':start_tx},status,'tx_packets'):
                last['readiness']={'continuous_ready_seconds':2,'recovery_observed':recovery_observed,
                                   'mic_retry_count_at_ready':status.get('mic_retry_count')}
                return last
        else:
            # This function runs only after await_profile reported READY.
            # Returning to a transition here is a startup interruption, not
            # an uninterrupted clean readiness window.
            recovery_observed=True
            stable_since=None
        time.sleep(.25)
    raise TimeoutError('Duplex did not settle during '+label+': '+str(last))

def snapshot(link, recorder, label):
    link.request('telemetry')
    state=recorder.control_snapshot()
    state['eldstatus']=link.request('eldstatus')
    state['status']=link.request('status')
    recorder.log('snapshots.jsonl',{'phase':label,'state':state})
    return state

def delta(before, after, key):
    return (int(after.get(key,0))-int(before.get(key,0))) & 0xffffffff

def steady_state_errors(state, profile):
    """Retain a sampled interruption even if both endpoint snapshots recover."""
    status=state.get('status',{});eld=state.get('eldstatus',{})
    issues=[]
    if (not status.get('streaming') or status.get('codec')!=4
            or not profile_matches(eld,profile)):
        issues.append('Playback left the requested ready profile during the steady interval')
    if status.get('mic_recovery_pending') or status.get('mic_started')==0:
        issues.append('Microphone START/recovery state changed during the steady interval')
    return issues

def health(before, after, profile=None):
    """Strict steady loss and applied-profile checks, apart from recovery."""

    a,b=before.get('micstats',{}),after.get('micstats',{})
    u,v=before.get('usbcapture',{}),after.get('usbcapture',{})
    errors=[]
    # Missing counters are unknown evidence, not zero loss. Validate both
    # endpoints before modular subtraction, including recovery counters.
    required={
        'micstats':('generation','decoded','errors','au_drop','pcm_drop'),
        'usbcapture':('pcm_samples','missing_samples','short_writes'),
        'status':('tx_packets','send_failures','mic_restarts','mic_retry_count','mic_watchdog_failures'),
    }
    for label,item in (('begin',before),('end',after)):
        for section,keys in required.items():
            for key in keys:
                value=item.get(section,{}).get(key)
                if type(value) is not int or not 0<=value<=0xffffffff:
                    errors.append(f'Missing or invalid {section}.{key} at {label} of steady interval')
    if errors:return errors
    for label,item in (('begin',before),('end',after)):
        s=item.get('status',{});e=item.get('eldstatus',{})
        if profile is not None and not profile_matches(e,profile):
            errors.append(f'Applied ELD profile mismatch at {label} of steady interval')
        if s.get('mic_watchdog_failed'):errors.append('Microphone received-audio watchdog exhausted its retry budget')
        if s.get('mic_recovery_pending'):errors.append('Microphone recovery was active during steady playback')
        if s.get('capture') and s.get('mic_started') == 0:
            errors.append('Microphone START was not submitted while capture was active')
        if s.get('capture') and s.get('mic_audio_seen') == 0:
            errors.append('Microphone framed audio was not observed')
        if not s.get('streaming') or s.get('codec')!=4 or e.get('transition')!='ready':
            errors.append('Playback was not in a ready AAC-ELD stream')
    if not delta(before.get('status',{}),after.get('status',{}),'tx_packets'):
        errors.append('No playback media packets progressed')
    if delta(before.get('status',{}),after.get('status',{}),'send_failures'):
        errors.append('Playback media submission failed')
    for key in ('mic_restarts','mic_retry_count','mic_watchdog_failures'):
        start_status=before.get('status',{});end_status=after.get('status',{})
        if key in start_status and key in end_status and delta(start_status,end_status,key):
            errors.append('Microphone recovery counter changed during steady playback: '+key)
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

def capture_format(sd, device):
    """Use the selected endpoint's real host format; never relabel PCM clocks."""
    info=sd.query_devices(device)
    api=sd.query_hostapis(info['hostapi'])['name']
    if 'WASAPI' in api.upper():
        # Windows shared capture exposes its mixer rate/channel layout, which
        # can differ from the independent 64 kHz mono USB clock. Preserve that
        # actual host format in WAVs instead of requesting an unsupported rate.
        rate=int(info['default_samplerate'])
        channels=int(info['max_input_channels'])
        if not 1<=channels<=2:raise RuntimeError('Unexpected USB microphone host channel layout: '+str(info))
        extra=sd.WasapiSettings(exclusive=False)
        mode='wasapi-shared'
    else:
        rate,channels,extra,mode=64000,1,None,'native-request'
    sd.check_input_settings(device=device,channels=channels,samplerate=rate,dtype='int16',extra_settings=extra)
    return dict(samplerate=rate,channels=channels,extra_settings=extra,host_api=api,mode=mode)

def preserve_audio_failure(root,link,recorder,error,before_cleanup=True):
    path=root/'audio-failure-state.json'
    if path.exists():return
    state={'error':str(error),'before_stream_cleanup':before_cleanup}
    for command in ('status','eldstatus','telemetry'):
        try:state[command]=link.request(command,timeout=2)
        except Exception as exc:state[command]={'error':str(exc)}
    state['observed']=recorder.control_snapshot()
    path.write_text(json.dumps(state,indent=2))

def capture_close_state(link,external_before,seconds=3):
    """Observe final firmware capture separately from initial host ownership.

    Prior activity does not prove that this runner exclusively owned the input.
    But it also must not conceal a subsequently confirmed final closure.
    """
    last=link.request('status')
    end=time.monotonic()+seconds
    while last.get('capture') and time.monotonic()<end:
        time.sleep(.25);last=link.request('status')
    closed=last.get('capture') == 0
    detail={'state':last,'capture_active_before_runner':bool(external_before),
            'firmware_capture_closed':closed,'runner_exclusive_ownership_verified':False}
    if 'capture' not in last:
        detail['reason']='No firmware capture-close telemetry was available'
        return 'UNVERIFIED',detail
    if closed:
        detail['reason']='Firmware confirms final closure; host-client exclusivity was not established'
        return 'PASS',detail
    if external_before:
        detail['reason']='Capture still active; another host client was already using it before this runner'
        return 'SKIP',detail
    detail['reason']='Runner input handle closed, but firmware capture is still active'
    return 'UNVERIFIED',detail

class AudioSession:
    """Callbacks only copy/queue samples. A worker owns WAV files and metrics."""
    def __init__(self,root,recorder,sd,np,output,inp,input_format=None,on_failure=None):
        self.root,self.recorder,self.sd,self.np=root,recorder,sd,np
        self.on_failure=on_failure
        self.output,self.inp=output,inp
        self.input_format=input_format or dict(samplerate=64000,channels=1,extra_settings=None,mode='native-request')
        self.input_rate=self.input_format['samplerate'];self.input_channels=self.input_format['channels']
        self.phase='capture_open';self.position=0
        self.rng=np.random.default_rng(0)
        self.queue=queue.Queue(maxsize=512);self.stop=threading.Event()
        self.lock=threading.Lock();self.metrics={};self.errors=[];self.output_errors={};self.output_callbacks={};self.drops=0
        self.files={};self.clip_samples={};self.stack=contextlib.ExitStack();self.input_stack=contextlib.ExitStack()
    def set_phase(self,name):
        self.phase=name;self.recorder.log('phases.jsonl',{'phase':name})
    def tone(self,outdata,frames,timing,status):
        # A callback is evidence of the *host requesting* output samples, not
        # evidence that the AirPods played them. Count per phase before writing.
        phase=self.phase
        self.output_callbacks[phase]=self.output_callbacks.get(phase,0)+1
        np=self.np
        t=(np.arange(frames)+self.position)/48000
        values=np.column_stack((500*np.sin(2*np.pi*440*t),500*np.sin(2*np.pi*660*t)))
        # Quiet broadband sections exercise more than the inexpensive sine case.
        noise=(t.astype(np.int64)%8>=4)
        values+=self.rng.uniform(-140,140,(frames,2))*noise[:,None]
        if phase.endswith('_left'):values[:,1]=0
        if phase.endswith('_right'):values[:,0]=0
        if phase=='music_quality':values[:]=0
        self.position+=frames;outdata[:]=values.astype('<i2').tobytes()
        if status:self.output_errors.setdefault(phase,[]).append(str(status))
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
                saved=self.clip_samples.get(phase,0);count=min(len(samples),max(0,12*self.input_rate*self.input_channels-saved))
                if count:
                    if phase not in self.files:
                        wav=wave.open(str(self.root/(phase+'.wav')),'wb')
                        wav.setnchannels(self.input_channels);wav.setsampwidth(2);wav.setframerate(self.input_rate);self.files[phase]=wav
                    self.files[phase].writeframes(data[:count*2]);self.clip_samples[phase]=saved+count
            except Exception as e:
                self.errors.append('audio writer: '+str(e));self.stop.set();break
    def __enter__(self):
        self.thread=threading.Thread(target=self.writer,daemon=True);self.thread.start()
        try:
            self.stack.enter_context(self.sd.RawOutputStream(device=self.output,channels=2,samplerate=48000,
                                    blocksize=0,dtype='int16',callback=self.tone))
            self.set_capture(True)
        except BaseException as error:
            self.note_failure(error);self.close();raise
        return self
    def set_capture(self, enabled):
        self.input_stack.close();self.input_stack=contextlib.ExitStack()
        if enabled:
            self.input_stack.enter_context(self.sd.RawInputStream(device=self.inp,channels=self.input_channels,samplerate=self.input_rate,
                extra_settings=self.input_format.get('extra_settings'),blocksize=0,dtype='int16',callback=self.capture))
    def close(self):
        try:
            try:self.input_stack.close()
            finally:self.stack.close()
        finally:
            self.stop.set();self.thread.join(timeout=5)
            if self.thread.is_alive():self.errors.append('Audio writer did not drain within five seconds')
            else:
                for wav in self.files.values():wav.close()
            with self.lock:
                result={k:{**v,'rms':math.sqrt(v['sumsq']/max(v['samples'],1))} for k,v in self.metrics.items()}
            (self.root/'audio-metrics.json').write_text(json.dumps({'phases':result,'errors':self.errors,
                     'output_status':self.output_errors,'output_callbacks_by_phase':self.output_callbacks,
                      'collector_dropped_buffers':self.drops,'input_rate':self.input_rate,'input_channels':self.input_channels,
                     'usb_microphone_rate':64000,'host_capture_mode':self.input_format.get('mode'),
                     'output_rate':48000},indent=2))
    def note_failure(self,error):
        if self.on_failure:
            try:self.on_failure(error)
            except Exception as exc:self.errors.append('Preserving first audio failure: '+str(exc))
    def __exit__(self,kind,error,tb):
        if error is not None:self.note_failure(error)
        self.close()
    def phase_errors(self,name):
        with self.lock:m=dict(self.metrics.get(name,{}))
        errors=list(m.get('host_errors',[]))+list(self.output_errors.get(name,[]))+list(self.errors)
        if not self.output_callbacks.get(name,0):
            errors.append('No host output callbacks observed')
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
    input_format=capture_format(sd,inp)
    (root/'audio-format.json').write_text(json.dumps({k:v for k,v in input_format.items() if k!='extra_settings'},indent=2))
    def dwell(seconds,label,profile=None):
        faults=[]
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            time.sleep(min(5,max(0,end-time.monotonic())))
            state=snapshot(link,recorder,label)
            status=state.get('status',{});eld=state.get('eldstatus',{})
            if status.get('mic_watchdog_failed') or status.get('fault_hold') or not status.get('connected') or eld.get('transition')=='failed':
                raise RuntimeError('Playback failed during '+label+': '+str({'status':status,'eldstatus':eld}))
            if profile is None and label.startswith('settle_') and (
                    not status.get('streaming') or eld.get('transition')!='ready' or
                    status.get('mic_recovery_pending')):
                faults.append('Transition observed after profile readiness during startup settle')
            if profile is not None:
                issues=steady_state_errors(state,profile)
                if issues:
                    faults.extend(issues)
                    preserve_audio_failure(root,link,recorder,RuntimeError('; '.join(issues)))
            if audio.stop.is_set():raise RuntimeError('Audio collector stopped: '+str(audio.errors))
        return faults
    external_capture=bool(link.request('status').get('capture'))
    recorder.log('capture-ownership.jsonl',{'capture_active_before_open':external_capture})
    with AudioSession(root,recorder,sd,np,output,inp,input_format,
                      on_failure=lambda error:preserve_audio_failure(root,link,recorder,error)) as audio:
        link.wait(lambda s:s.get('capture') and s.get('confirmed'),15)
        dwell(3,'capture_warmup')
        limits=link.request('eldstatus')
        ceiling=limits.get('negotiated_bitrate',0)
        if ceiling<192000:raise RuntimeError('No valid AAC-ELD session ceiling: '+str(limits))
        baseline=PROFILES[-1] if ceiling>=256000 else ('restore192',1,False,1,192000,0,0,6)
        probe_only=getattr(args,'session_only',False)
        mic_close_only=getattr(args,'mic_close_only',False)
        profiles=([('session_probe',*baseline[1:])] if probe_only else [baseline] if mic_close_only
                  else PROFILES[:-1]+[baseline])
        for profile in profiles:
            name,rate,gaming,level,*_=profile
            if profile[4]>ceiling:
                result(name,'SKIP',{'reason':'Peer/accepted configuration ceiling is lower than this profile','negotiated_bitrate':ceiling,'requested_bitrate':profile[4]})
                continue
            audio.set_phase('transition_'+name)
            settings=link.request('settings')
            if (settings.get('eldrate'),bool(settings['usbset']&128),settings.get('gamelevel'))!=(rate,gaming,level):
                link.request(f'profile {rate} {int(gaming)} {level}')
            applied=await_profile(link,profile)
            settle_notes=dwell(2,'settle_'+name)
            # A delayed damage refresh can start during the fixed dwell after
            # await_profile returned. Require both live paths to settle before
            # taking the steady interval's starting snapshot, as on reconnect.
            readiness=await_duplex_ready(link,recorder,profile,name+'_ready')
            if settle_notes:
                readiness['readiness']['recovery_observed']=True
                readiness['readiness']['settle_observations']=settle_notes
            seconds=45 if probe_only else args.duration
            audio.set_phase(name);print(f'{name}: {seconds} seconds of concurrent playback/capture. Phone-speaker input for the first 20 seconds is sufficient.',flush=True)
            before=snapshot(link,recorder,name+'_begin');transient_faults=dwell(seconds,name,profile)
            after=snapshot(link,recorder,name+'_end')
            errors=health(before,after,profile)+transient_faults+audio.phase_errors(name)
            if errors:preserve_audio_failure(root,link,recorder,RuntimeError('; '.join(errors)))
            result(name,'FAIL' if errors else 'PASS',
                   {'errors':errors,'applied':readiness['eldstatus'],'readiness':readiness.get('readiness'),
                    'before':before,'after':after})
        if probe_only:
            audio.set_phase('session_closing');audio.set_capture(False)
            closed,detail=capture_close_state(link,external_capture)
            result('capture_close',closed,detail)
            result('full_feature_matrix','SKIP','45-second session diagnostic only; no channel/control prompts or ten-minute soak')
            return
        def channel_check(label):
            for side in ('left','right'):
                audio.set_phase(label+'_'+side);dwell(2,label+'_'+side)
                phase=label+'_'+side
                if not audio.output_callbacks.get(phase,0):
                    result(phase,'UNVERIFIED','No host output callbacks observed; acoustic stimulus cannot be assumed')
                    continue
                output_errors=audio.output_errors.get(phase,[])
                if output_errors:
                    preserve_audio_failure(root,link,recorder,RuntimeError('; '.join(output_errors)))
                    result(phase,'FAIL',{'output_errors':list(output_errors)})
                    continue
                answer=prompt(f'{label}: tone is {side.upper()} only. Type yes if correct; otherwise no, silent, both, wrong-side, or a description:')
                result(phase,observation_status(answer,'channel',side),answer)
        channel_check('mic_active')
        prompt('Keep this firmware connected. Press Enter to check microphone close/reopen while script playback continues:')
        audio.set_phase('mic_closing');audio.set_capture(False)
        closed,detail=capture_close_state(link,external_capture)
        result('mic_close_endpoint',closed,detail)
        if closed=='PASS':
            dwell(3,'mic_closed_settle');await_profile(link,baseline);channel_check('mic_closed')
        else:result('mic_closed_channels','SKIP','USB capture did not close exclusively under runner control')
        audio.set_phase('mic_reopening');audio.set_capture(True)
        link.wait(lambda s:s.get('capture') and s.get('confirmed'),15);dwell(3,'mic_reopened_settle')
        await_profile(link,baseline)
        if closed=='PASS':channel_check('mic_reopened')
        audio.set_phase('mic_reopened_steady')
        before=snapshot(link,recorder,'mic_reopened_begin');faults=dwell(5,'mic_reopened_steady',baseline)
        after=snapshot(link,recorder,'mic_reopened_end');errors=health(before,after,baseline)+faults+audio.phase_errors('mic_reopened_steady')
        if errors:preserve_audio_failure(root,link,recorder,RuntimeError('; '.join(errors)))
        result('mic_close_reopen_duplex','FAIL' if errors else 'PASS' if closed=='PASS' else 'UNVERIFIED',
               {'errors':errors,'closure':closed,'before':before,'after':after})
        if mic_close_only:
            audio.set_phase('mic_close_acceptance_cleanup')
            audio.set_capture(False)
            final_closed,final_detail=capture_close_state(link,external_capture)
            result('capture_close',final_closed,final_detail)
            result('reconnect_game_soak','SKIP','Focused mic-close acceptance: no three reconnects, game profiles, relay, or repeat ten-minute soak')
            return
        for cycle in range(3):
            name=f'capture_reconnect_{cycle+1}';audio.set_phase(name+'_transition')
            link.request('disconnect');link.wait(lambda s:not s.get('connected'),15)
            link.request('connect')
            link.wait(lambda s:s.get('confirmed') and s.get('peer','').upper()==target_mac.upper(),45)
            await_profile(link,baseline);dwell(3,name+'_settle')
            await_duplex_ready(link,recorder,baseline,name+'_ready')
            audio.set_phase(name)
            before=snapshot(link,recorder,name+'_begin');faults=dwell(5,name,baseline)
            after=snapshot(link,recorder,name+'_end');errors=health(before,after,baseline)+faults+audio.phase_errors(name)
            if errors:preserve_audio_failure(root,link,recorder,RuntimeError('; '.join(errors)))
            result(name,'FAIL' if errors else 'PASS',{'errors':errors,'before':before,'after':after})
        audio.set_phase('duplex_soak');print(f'Duplex soak: {args.soak_seconds} seconds. Leave both streams open.',flush=True)
        before=snapshot(link,recorder,'soak_begin');faults=dwell(args.soak_seconds,'duplex_soak',baseline)
        after=snapshot(link,recorder,'soak_end');errors=health(before,after,baseline)+faults+audio.phase_errors('duplex_soak')
        if errors:preserve_audio_failure(root,link,recorder,RuntimeError('; '.join(errors)))
        result('duplex_soak','FAIL' if errors else 'PASS',{'seconds':args.soak_seconds,'errors':errors,'before':before,'after':after})
        if args.phone_relay:
            audio.set_phase('phone_relay_transition');link.request('phonepair 1')
            try:
                prompt('Pair/play a phone now; leave PC playback and microphone capture running. Press Enter when playing:')
                state=link.wait(lambda s:s.get('relay_connected') and s.get('relay_streaming'),60)
                relay_profile=('relay',*baseline[1:4],164000,0,0,6)
                await_profile(link,relay_profile);dwell(3,'relay_settle')
                audio.set_phase('phone_relay_duplex')
                before=snapshot(link,recorder,'phone_relay_duplex_begin');faults=dwell(15,'phone_relay_duplex',relay_profile)
                after=snapshot(link,recorder,'phone_relay_duplex_end');errors=health(before,after,relay_profile)+faults+audio.phase_errors('phone_relay_duplex')
                if errors:preserve_audio_failure(root,link,recorder,RuntimeError('; '.join(errors)))
                heard=prompt('Was the mixed phone/PC audio clear? Type yes/no, or Enter for unverified:')
                result('phone_relay_duplex','FAIL' if errors or heard.lower()=='no' else 'PASS' if heard.lower()=='yes' else 'UNVERIFIED',{'state':state,'errors':errors,'before':before,'after':after})
            finally:
                link.request('phonedisc');link.request('phonepair 0')
    closed,detail=capture_close_state(link,external_capture)
    result('capture_close',closed,detail)
