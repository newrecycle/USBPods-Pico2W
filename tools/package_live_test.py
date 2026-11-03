"""Package an offline-verified candidate; never marks hardware as tested."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
from verify_build import verify_uf2

def package(root,build,evidence,out,stem,source_sha,run_id):
    report=json.loads((evidence/'verification.json').read_text())
    if report.get('build_verified') is not True:raise ValueError('Build verification missing')
    firmware=build/(stem+'.uf2')
    binary=build/(stem+'.bin')
    actual=hashlib.sha256(firmware.read_bytes()).hexdigest()
    if report['artifacts'][firmware.name]['sha256']!=actual:raise ValueError('Verified UF2 changed')
    if not re.fullmatch('[a-f0-9]{40}',source_sha):raise ValueError('Explicit firmware source SHA required')
    data_bytes=binary.read_bytes()
    if hashlib.sha256(data_bytes).hexdigest()!=report['artifacts'][binary.name]['sha256']:raise ValueError('Verified binary changed')
    if source_sha.encode()+b'\0' not in data_bytes:raise ValueError('Source SHA is not embedded in this firmware')
    verify_uf2(firmware.read_bytes(),data_bytes)
    out.mkdir(parents=True,exist_ok=False)
    for name in ('live_test.py','live_audio.py','Run-Test.ps1','live-requirements.txt'):
        shutil.copy2(root/'tools'/name,out/name)
    shutil.copy2(root/'docs/LIVE-TEST.md',out/'LIVE-TEST.md')
    validation=json.loads((root/'docs/validation-status.json').read_text())
    shutil.copy2(root/'docs/validation-status.json',out/'validation-status.json')
    shutil.copy2(firmware,out/firmware.name)
    shutil.copy2(evidence/'verification.json',out/'verification.json')
    shutil.copy2(evidence/'firmware.json',out/'radio-firmware.json')
    shutil.copy2(root/'3rd-party/fdk-aac/NOTICE',out/'FDK-NOTICE.txt')
    shutil.copy2(root/'3rd-party/fdk-aac/USBPODS-MODIFICATIONS.md',out/'FDK-MODIFICATIONS.md')
    shutil.copy2(root/'LICENSE.txt',out/'LICENSE.txt')
    shutil.copy2(root/'LICENSE-EXCEPTIONS.md',out/'LICENSE-EXCEPTIONS.md')
    shutil.copy2(root/'src/btstack/LICENSE.txt',out/'BTSTACK-LICENSE.txt')
    shutil.copy2(root/'3rd-party/ldacBT/LICENSE',out/'LDAC-LICENSE.txt')
    data={'schema':1,'hardware_test_candidate':validation['live_test_authorized'],'validation_blockers':validation['blockers'],'hardware_tested':False,'sha':source_sha,'ci_run_id':int(run_id),
          'source_url':'https://github.com/newrecycle/USBPods-Pico2W/tree/'+source_sha,
          'firmware':firmware.name,'firmware_sha256':actual,'mic_decode':'AACELD_Mic' in stem,'board':'pico2_w','protocol':2,
          'runner_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.suffix!='.uf2'}}
    (out/'candidate.json').write_text(json.dumps(data,indent=2)+'\n')
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--stem',required=True)
    p.add_argument('--source-sha',required=True);p.add_argument('--run-id',type=int,required=True)
    a=p.parse_args();package(Path(__file__).resolve().parents[1],a.build,a.evidence,a.output,a.stem,a.source_sha,a.run_id)
