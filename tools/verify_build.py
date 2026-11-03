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
    total, families = verify_uf2(uf2, binary)
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
