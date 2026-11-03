#!/usr/bin/env python3
"""Verify linked firmware bytes and UF2 block integrity; never assert runtime success."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

def verify_uf2(uf2, binary):
    if not uf2 or len(uf2) % 512:
        raise ValueError("invalid UF2 length")
    total = len(uf2) // 512
    main, compatibility, families = [], [], set()
    for i in range(total):
        b = uf2[i*512:(i+1)*512]
        m0,m1,flags,address,length,index,count,family = struct.unpack_from("<8I",b)
        if (m0,m1,struct.unpack_from("<I",b,508)[0]) != (0x0a324655,0x9e5d5157,0x0ab16f30):
            raise ValueError("invalid UF2 magic")
        families.add(family)
        if family == 0xe48bff57:
            # picotool's RP2350 compatibility block has its own numbering.
            if (i,flags,address,length,index,count) != (0,0xa000,0x10ffff00,256,0,2):
                raise ValueError("invalid RP2350 compatibility block")
            compatibility.append(b)
        elif family in (0xe48bff56,0xe48bff59) and flags == 0x2000 and length == 256:
            main.append((address,index,count,family,b[32:32+length]))
        else:
            raise ValueError("unexpected UF2 family, flags or payload size")
    if not main or len({b[3] for b in main}) != 1:
        raise ValueError("missing or mixed flash families")
    if compatibility and (len(compatibility)!=1 or main[0][3]!=0xe48bff59):
        raise ValueError("unexpected compatibility block")
    if len(main) != (len(binary)+255)//256:
        raise ValueError("unexpected flash block count")
    result=bytearray()
    for i,(address,index,count,family,data) in enumerate(main):
        if (address,index,count) != (0x10000000+i*256,i,len(main)):
            raise ValueError("invalid UF2 flash numbering/address")
        result.extend(data)
    if result[:len(binary)] != binary or any(result[len(binary):]):
        raise ValueError("UF2 does not reproduce linked flash binary")
    return total, families

def verify_microphone_descriptors(binary, symbols):
    configs = {}
    for name in ("desc_configuration_uac2", "desc_configuration_uac1", "desc_configuration_uac1_44"):
        found = [line.split() for line in symbols.splitlines() if line.endswith(" "+name)]
        if len(found) != 1:
            raise ValueError("missing USB descriptor symbol: "+name)
        address, size = int(found[0][0],16)-0x10000000, int(found[0][1],16)
        data = binary[address:address+size]
        if len(data) != size or data[:2] != bytes([9,2]) or int.from_bytes(data[2:4],"little") != size:
            raise ValueError("invalid configuration descriptor length")
        off=0; endpoints=[]; interfaces=set(); current=None; clocks=[]; iad=None
        while off<len(data):
            n,kind=data[off:off+2]
            if n<2 or off+n>len(data): raise ValueError("invalid USB descriptor boundary")
            d=data[off:off+n]
            if kind==11 and d[2]==0: iad=d[3]
            if kind==4:
                interfaces.add(d[2]); current=(d[2],d[3],d[5],d[6])
            if kind==0x24 and current and current[2:]==(1,1) and d[2]==10:
                clocks.append(d[3])
            if kind==5 and (d[3]&3)==1:
                endpoints.append((d[2],int.from_bytes(d[4:6],"little"),current))
            off+=n
        if len(interfaces)!=data[4] or interfaces!=set(range(data[4])):
            raise ValueError("USB interface count/numbering mismatch")
        ins=[e for e in endpoints if e[0]&0x80]
        outs=[e for e in endpoints if not e[0]&0x80]
        if name.endswith("uac2"):
            if ins != [(0x81,130,(2,1,1,2))] or len(outs)!=1 or outs[0][:2]!=(1,196):
                raise ValueError("missing/incorrect UAC2 microphone or speaker endpoint")
            if iad!=3 or clocks!=[4,0x14]:
                raise ValueError("invalid audio function or microphone clock topology")
        elif ins or len(outs)!=1 or outs[0][:2]!=(1,192):
            raise ValueError("UAC1 speaker personality changed unexpectedly")
        configs[name]={"interfaces":len(interfaces),"iso_endpoints":[{"address":hex(e[0]),"max_bytes":e[1]} for e in endpoints]}
    return configs

def verify(build, evidence, name="USBPods_Pico2W_Lite"):
    report = json.loads((evidence / "firmware.json").read_text())
    fw = (evidence / "btfw.bin").read_bytes()
    stem = build / name
    binary = stem.with_suffix(".bin").read_bytes()
    elf = stem.with_suffix(".elf")
    uf2 = stem.with_suffix(".uf2").read_bytes()
    if binary.count(fw) != 1:
        raise ValueError("selected controller payload is not present exactly once in linked binary")
    symbols = subprocess.check_output(["arm-none-eabi-nm", "-S", str(elf)], text=True)
    matching = [s.split() for s in symbols.splitlines() if s.endswith(" cyw43_btfw_43439")]
    if len(matching) != 1 or int(matching[0][1], 16) != len(fw):
        raise ValueError("linked controller symbol/size mismatch")
    addresses = {}
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) >= 3:
            try: addresses[fields[-1]] = int(fields[0], 16)
            except ValueError: pass
    if "__HeapLimit" in addresses and "end" in addresses:
        region = addresses["__HeapLimit"] - addresses["end"]
        if region <= 0: raise ValueError("no linker heap region remains")
        report["memory"] = {"heap_region_bytes": region, "heap_start": hex(addresses["end"]), "heap_limit": hex(addresses["__HeapLimit"]), "runtime_allocation_verified": False}
    total, families = verify_uf2(uf2, binary)
    if name.startswith("USBPods_"):
        report["usb_descriptors"] = verify_microphone_descriptors(binary,symbols)
    report.update({"build_verified": True, "uf2_blocks": total,
                   "uf2_families": [hex(f) for f in sorted(families)],
                   "binary_firmware_offset": binary.index(fw)})
    report["artifacts"] = {p.name: {"bytes":p.stat().st_size,
        "sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in [elf, stem.with_suffix(".bin"), stem.with_suffix(".uf2")]}
    (evidence / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--stem", default="USBPods_Pico2W_Lite")
    a=p.parse_args()
    verify(a.build,a.evidence,a.stem)

