#!/usr/bin/env python3
"""Select an unchanged, hash-pinned Raspberry Pi SDIO Bluetooth patch image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

IMAGES = {
    "stock0031": {
        "ref": "c1075d4bc440422cf2b2fd12c64a1f53f77660ee",
        "header_sha256": "11fc817e33a875e4f619c6939f934e916be0dfa083ce4af073867f340779a6c9",
        "payload_sha256": "ce1992c1a6a16ae51bc012439486e9fb212623eca92d9e82a8090c2acf7ef1df",
        "bytes": 6164,
    },
    "rpi0065": {
        "ref": "055d64274b014dd7b1c2fc94d26e8a18face7124",
        "header_sha256": "d05a8dca7e232ada470d8ed723edaa1ea78000098870f9b979d490d83ad35b22",
        "payload_sha256": "d974384d0aa8124d30084f30d13519a3ed3b9f759f7ddd6a34ef3dcf1441bcf7",
        "bytes": 6970,
    },
}
def sha(data):
    return hashlib.sha256(data).hexdigest()

def parse_header(text):
    match = re.search(r"cyw43_btfw_43439\[\][^=]*=\s*\{([^}]*)\}", text, re.S)
    if not match:
        raise ValueError("missing CYW43439 byte array")
    body = re.sub(r"/\*.*?\*/|//[^\n]*", "", match[1], flags=re.S)
    tokens = re.findall(r"0x[0-9a-fA-F]+|\d+", body)
    data = bytes(int(t, 0) for t in tokens)
    declared = re.search(r"cyw43_btfw_43439_len\s*=\s*(\d+)\s*;", text)
    if not declared or int(declared[1]) != len(data):
        raise ValueError("declared image length mismatch")
    return data

def inspect(data):
    if not data or not 1 <= data[0] < len(data) - 1:
        raise ValueError("invalid version length")
    n = data[0]
    if data[n] != 0 or 0 in data[1:n]:
        raise ValueError("invalid version terminator")
    version = data[1:n].decode("ascii")
    if not version.startswith("CYW4343A2_") or "_Generic_SDIO_37MHz_" not in version:
        raise ValueError("not a Pico-compatible SDIO/37MHz image")
    p, upper, count, writes, ended = n + 2, 0, 0, [], False
    while p < len(data):
        if p + 4 > len(data):
            raise ValueError("truncated record header")
        length, address, kind = data[p], int.from_bytes(data[p+1:p+3], "big"), data[p+3]
        p += 4
        if p + length > len(data):
            raise ValueError("truncated record payload")
        payload = data[p:p+length]
        p += length
        count += 1
        if kind == 1:
            if length or address or p != len(data):
                raise ValueError("invalid EOF record")
            ended = True
            break
        if kind == 4 and length == 2 and address == 0:
            upper = int.from_bytes(payload, "big") << 16
        elif kind == 0 and length:
            start = upper + address
            if address + length > 0x10000:
                raise ValueError("record crosses extended-address boundary")
            writes.append((start, payload))
        else:
            raise ValueError("unsupported record type or length")
    if not ended or not writes or count != data[n+1]:
        raise ValueError("missing EOF/data or record count mismatch")
    # These are required by the SDK loader to select the configuration and start
    # the controller. We inspect them, without modifying the signed image.
    memory = {a+i: b for a, payload in writes for i, b in enumerate(payload)}
    if not all(a in memory for a in range(0x2038d4, 0x2038d8)):
        raise ValueError("missing controller configuration pointer")
    if not all(a in memory for a in range(0x204164, 0x204168)):
        raise ValueError("missing controller startup pointer")
    return {"version": version, "bytes": len(data), "sha256": sha(data),
            "records": count, "memory_writes": len(writes),
            "runtime_tested": False, "sco_fix_verified": False}

def select(sdk, image, output):
    spec = IMAGES[image]
    destination = sdk / "lib/cyw43-driver/firmware/cyw43_btfw_43439.h"
    url = ("https://raw.githubusercontent.com/georgerobotics/cyw43-driver/"
           + spec["ref"] + "/firmware/cyw43_btfw_43439.h")
    if image == "stock0031":
        header = destination.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            header = response.read()
    if sha(header) != spec["header_sha256"]:
        raise ValueError("firmware header SHA-256 mismatch")
    data = parse_header(header.decode())
    report = inspect(data)
    if sha(data) != spec["payload_sha256"] or len(data) != spec["bytes"]:
        raise ValueError("firmware payload mismatch")
    if image != "stock0031":
        destination.write_bytes(header)
    output.mkdir(parents=True, exist_ok=True)
    (output / "btfw.bin").write_bytes(data)
    report.update({"selection": image, "source": url,
                   "header_sha256": sha(header), "compatible_boards": ["pico_w", "pico2_w"],
                   "note": "Firmware selection/build evidence; not an HFP microphone implementation."})
    (output / "firmware.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sdk", type=Path, required=True)
    p.add_argument("--image", choices=IMAGES, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    select(a.sdk, a.image, a.output)
