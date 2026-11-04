"""Flash the packaged RP2350 candidate, then identify its returning CDC port."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

from live_test import parse_control, verify_manifest

BOOTSEL = ['--vid', '0x2e8a', '--pid', '0x000f']


def firmware_info(serial_module, port):
    with serial_module.Serial(port, 115200, timeout=.2, write_timeout=3) as connection:
        connection.write(b':info\n');connection.flush()
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            line=connection.readline().decode('utf-8',errors='replace').strip()
            try:info=parse_control(line)
            except (ValueError, json.JSONDecodeError):continue
            if info and info.get('kind')=='info':
                if info.get('board')!='rp2350' or info.get('protocol')!=2:
                    raise RuntimeError('CDC port is not the expected USBPods RP2350 firmware')
                return info
    raise RuntimeError('No USBPods firmware identity from '+port+'; close apps using the port')


def flash(root, cdc=None, *, serial_module=None, ports=None, run=subprocess.run,
          which=shutil.which, clock=time):
    root=Path(root).resolve();manifest=json.loads((root/'candidate.json').read_text())
    verify_manifest(root,manifest)  # Includes UF2 hash; no reset/write before this gate.
    if manifest.get('board')!='pico2_w':raise RuntimeError('Automatic flashing requires the Pico 2 W candidate')
    executable=which('picotool')
    if not executable:raise RuntimeError('picotool was not found in PATH')
    if serial_module is None:
        import serial as serial_module
    if ports is None:
        from serial.tools.list_ports import comports
        ports=comports
    report={'schema':1,'candidate_sha':manifest['sha'],'events':[],'complete':False}
    report_path=root/'flash-log.json'
    def save():report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def invoke(arguments,timeout=15):
        try:
            result=run([executable,*arguments],capture_output=True,text=True,timeout=timeout)
        except (OSError,subprocess.TimeoutExpired) as error:
            report['events'].append({'command':arguments,'error':str(error)});save();raise
        report['events'].append({'command':arguments,'returncode':result.returncode,
                                 'stdout':result.stdout,'stderr':result.stderr});save()
        return result
    try:
        available=list(ports())
        selected=[p for p in available if p.device.upper()==cdc.upper()] if cdc else [p for p in available if p.vid==0xcafe]
        if len(selected)>1:raise RuntimeError('Multiple USBPods CDC devices; specify -CdcPort')
        if cdc and not selected and any(p.vid==0xcafe for p in available):
            raise RuntimeError('Requested CDC port is absent while another USBPods is running; refusing to choose it')
        previous_serial=None
        if selected:
            device=selected[0]
            if device.vid!=0xcafe:raise RuntimeError('Selected CDC port does not have the USBPods VID')
            report['previous_info']=firmware_info(serial_module,device.device)
            previous_serial=device.serial_number
            report['previous_port']=device.device
            print('Entering BOOTSEL for the firmware update...',flush=True)
            filters=['--vid',hex(device.vid),'--pid',hex(device.pid)]
            if previous_serial:filters+=['--ser',previous_serial]
            reset=invoke(['reboot','-u','-f',*filters])
            if reset.returncode:
                # Existing USBPods has the 1200-baud hook but no SDK reset
                # vendor interface. picotool still performs the actual load.
                report['reset_method']='cdc-1200-fallback';save()
                try:
                    with serial_module.Serial(device.device,1200,timeout=.2,write_timeout=3):pass
                except (OSError,serial_module.SerialException) as error:
                    # Windows can report removal during the successful reset;
                    # the BOOTSEL probe below must independently establish it.
                    report['events'].append({'cdc_reset_error':str(error)});save()
            else:report['reset_method']='picotool'
        else:
            report['reset_method']='already-bootsel'
            print('Looking for the Pico 2 W in BOOTSEL...',flush=True)
        deadline=clock.monotonic()+20
        while True:
            probe=invoke(['info',*BOOTSEL],timeout=5)
            if probe.returncode==0:break
            if clock.monotonic()>=deadline:
                raise RuntimeError('Pico 2 BOOTSEL is unavailable or ambiguous; see flash-log.json')
            clock.sleep(.5)
        # picotool refuses an ambiguous BOOTSEL selection. No erase-all: only
        # UF2 sectors are written, preserving the settings/key store outside it.
        print('Loading and verifying the bundled UF2 with picotool...',flush=True)
        loaded=invoke(['load','-v','-x',str(root/manifest['firmware']),*BOOTSEL],timeout=120)
        if loaded.returncode:raise RuntimeError('picotool load/verify failed; see flash-log.json')
        deadline=clock.monotonic()+45;last_error=None
        while clock.monotonic()<deadline:
            returned=[p for p in ports() if p.vid==0xcafe and
                      (not previous_serial or p.serial_number==previous_serial)]
            if len(returned)>1:raise RuntimeError('Multiple returning CDC devices; refusing to choose one')
            if len(returned)==1:
                try:
                    info=firmware_info(serial_module,returned[0].device)
                except (OSError,serial_module.SerialException,RuntimeError) as error:last_error=str(error)
                else:
                    if info.get('sha')!=manifest['sha']:
                        raise RuntimeError('Returning firmware SHA differs from this candidate; stopping before tests')
                    report.update(complete=True,cdc=returned[0].device,info=info);save()
                    print('Firmware verified; CDC ready on '+returned[0].device,flush=True)
                    return returned[0].device
            clock.sleep(.5)
        raise TimeoutError('Flashed firmware did not return on CDC: '+str(last_error))
    except Exception as error:
        report['error']=str(error);save();raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    p.add_argument('--cdc');p.add_argument('--port-file',type=Path,required=True)
    args=p.parse_args()
    # An old successful port file must never survive a failed update.
    args.port_file.unlink(missing_ok=True)
    port=flash(args.root,args.cdc)
    args.port_file.write_text(port,encoding='ascii')


if __name__=='__main__':main()
