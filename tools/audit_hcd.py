#!/usr/bin/env python3
"""Record why the pinned newer UART firmware is not selected for Pico builds."""
import hashlib
import json
from pathlib import Path
import struct
import urllib.request

REF="e5f0a31b95d51bbeb7ea5ef152ab0ff563961ff8"
NAME="CYW4343A2_001.003.016.0076.0000_Generic_UART_26MHz_wlbga_BU_dl_signed.hcd"
URL="https://raw.githubusercontent.com/Infineon/ifx-linux-bluetooth/"+REF+"/fw/"+NAME
EXPECTED="7c18b92e0d1340cc664738c4b4cc79a2edf2cd10318602e5252ad630dff39387"

def audit(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:
        raise ValueError("candidate SHA-256 mismatch")
    pos=0
    commands=[]
    while pos<len(data):
        if pos+3>len(data): raise ValueError("truncated HCD command")
        opcode,length=struct.unpack_from("<HB",data,pos)
        end=pos+3+length
        if end>len(data): raise ValueError("truncated HCD payload")
        if opcode not in (0xfc4c,0xfc4e): raise ValueError("unexpected HCD opcode")
        commands.append({"opcode":hex(opcode),"bytes":length})
        pos=end
    return {"source":URL,"sha256":EXPECTED,"bytes":len(data),"commands":len(commands),
            "version":"001.003.016.0076.0000","transport":"UART","reference_clock_mhz":26,
            "selected_for_pico":False,"sco_fix_verified_on_pico":False,
            "reason":"Vendor UART/26MHz image does not establish compatibility with Pico SDIO/37MHz transport. Format conversion alone cannot port its signed configuration."}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.input: data=a.input.read_bytes()
    else:
        with urllib.request.urlopen(URL,timeout=60) as r: data=r.read()
    result=audit(data)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
