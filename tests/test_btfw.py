#!/usr/bin/env python3
"""Exercise firmware truncation/transport rejection against the actual selected image."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from btfw import inspect,parse_header

payload=parse_header(Path(sys.argv[1]).read_text())
result=inspect(payload)
for n in range(len(payload)):
    try: inspect(payload[:n])
    except ValueError: continue
    raise AssertionError("truncated firmware accepted at byte "+str(n))
mutated=payload.replace(b"Generic_SDIO_37MHz",b"Generic_UART_26MHz")
assert mutated!=payload
try: inspect(mutated)
except ValueError: pass
else: raise AssertionError("wrong transport accepted")
try: inspect(payload+b"\x00")
except ValueError: pass
else: raise AssertionError("trailing data accepted")
print("Validated",result["version"],"; rejected all",len(payload),"truncations, wrong transport, and trailing data")
