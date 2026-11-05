#!/usr/bin/env python3
"""Run the checked-in offline suite without cloud paths or radio hardware.

Linux/WSL: python3 tools/run_offline_checks.py --build-fdk
An existing ASan-instrumented native FDK archive can be supplied with --fdk-lib.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def run(command, timeout, output, env):
    start=time.monotonic()
    try:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,text=True,timeout=timeout)
        code,text=result.returncode,result.stdout
    except subprocess.TimeoutExpired as exc:
        code=124;text=exc.stdout or ''
        if isinstance(text,bytes):text=text.decode(errors='replace')
        text+='\nOffline check timed out\n'
    except OSError as exc:
        code=127;text=str(exc)+'\n'
    output.write_text(text)
    return dict(command=command,returncode=code,seconds=round(time.monotonic()-start,3),log=output.name)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-fdk',action='store_true')
    p.add_argument('--fdk-lib',type=Path)
    p.add_argument('--sdk-source',type=Path,help='Already-patched SDK classic source directory')
    p.add_argument('--output',type=Path,default=ROOT/'build-offline-evidence')
    a=p.parse_args()
    if a.build_fdk and a.fdk_lib:p.error('Choose --build-fdk or --fdk-lib')
    if not shutil.which('cc'):p.error('A native C compiler named cc is required; use Linux/WSL')
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
    fdk=a.fdk_lib.resolve() if a.fdk_lib else None
    if a.build_fdk:
        build=ROOT/'build-host-fdk'
        setup=[['cmake','-S','3rd-party/fdk-aac','-B',str(build),'-DBUILD_SHARED_LIBS=OFF',
                '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER=cc','-DCMAKE_CXX_COMPILER=c++',
                '-DCMAKE_C_FLAGS=-fsanitize=address','-DCMAKE_CXX_FLAGS=-fsanitize=address -fno-omit-frame-pointer'],
               ['cmake','--build',str(build),'--parallel','2']]
        for i,cmd in enumerate(setup):
            result=run(cmd,900,a.output/f'fdk-setup-{i}.txt',env)
            if result['returncode']:
                print('Native FDK setup failed; see',a.output/result['log']);return 1
        fdk=build/'libfdk-aac.a'
    if fdk and not fdk.is_file():p.error('Native FDK archive does not exist')
    commands=json.loads((ROOT/'tests/offline-commands.json').read_text())
    results=[];skipped=[]
    with tempfile.TemporaryDirectory(prefix='usbpods-offline-') as temp:
        sdk=a.sdk_source
        if sdk is None:
            # Keep the pinned comparison sources pristine. Exercise the actual
            # production patch against a disposable copy, as target CI does.
            sdk=Path(temp)/'btstack/src/classic'
            sdk.mkdir(parents=True)
            for source in (ROOT/'references/btstack').iterdir():
                if source.is_file():shutil.copy2(source,sdk/source.name)
            subprocess.run(['git','apply','--include=src/classic/avdtp.c',
                            '--include=src/classic/avdtp_initiator.c',
                            str(ROOT/'sdk-patches/btstack-usbpods.patch')],
                           cwd=sdk.parent.parent,check=True)
        values={'{PYTHON}':sys.executable,'{TMP}':temp,'{SDK}':str(sdk.resolve()),
                '{FDK}':str(fdk) if fdk else ''}
        for i,item in enumerate(commands):
            if item.get('requires_fdk') and not fdk:
                skipped.append(item['name']);continue
            cmd=[]
            for arg in item['argv']:
                for token,value in values.items():arg=arg.replace(token,value)
                cmd.append(arg)
            result=run(cmd,item.get('timeout',120),a.output/f'check-{i:02}.txt',env)
            result['name']=item['name'];results.append(result)
            print(('PASS' if not result['returncode'] else 'FAIL')+' '+item['name'],flush=True)
    summary={'schema':1,'hardware_run':False,'results':results,'skipped':skipped,
             'passed':sum(not r['returncode'] for r in results),'failed':sum(bool(r['returncode']) for r in results)}
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(f"{summary['passed']} passed, {summary['failed']} failed, {len(skipped)} skipped; {a.output/'summary.json'}")
    return int(bool(summary['failed']))


if __name__=='__main__':raise SystemExit(main())
