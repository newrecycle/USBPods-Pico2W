#!/usr/bin/env python3
"""Verify linked firmware bytes and UF2 block integrity; never assert runtime success."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

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
    if not uf2 or len(uf2) % 512:
        raise ValueError("invalid UF2 length")
    total = len(uf2) // 512
    payloads = {}
    families = set()
    for i in range(total):
        b = uf2[i*512:(i+1)*512]
        m0, m1, flags, address, length, index, count, family = struct.unpack_from("<8I", b)
        if (m0, m1, struct.unpack_from("<I", b, 508)[0]) != (0x0a324655, 0x9e5d5157, 0x0ab16f30):
            raise ValueError("invalid UF2 magic")
        if not 0 < length <= 476 or index != i or count != total:
            raise ValueError("invalid UF2 numbering or payload size")
        if not flags & 0x2000:
            raise ValueError("missing UF2 family ID")
        families.add(family)
        for offset, byte in enumerate(b[32:32+length]):
            a = address + offset
            if a in payloads and payloads[a] != byte:
                raise ValueError("conflicting UF2 payload")
            payloads[a] = byte
    # Compare only the binary address space; UF2 may also contain a family
    # selection block outside it.
    for i, byte in enumerate(binary):
        if payloads.get(0x10000000+i) != byte:
            raise ValueError("UF2 does not reproduce linked flash binary")
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
