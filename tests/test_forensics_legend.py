"""scratch[7] watchdog breadcrumb writers and their printed legend agree.

B1 review found the reset banner decoded 0x10/0x20 markers that no code writes
while real handler markers were undecodable. This test collects every marker
written by the product sources and requires the legend strings to list it.
"""
import re
from pathlib import Path

MARKERS = set()
for path in Path("src").rglob("*.[ch]"):
    text = path.read_text(errors="ignore")
    MARKERS.update(int(m, 16) for m in re.findall(r"scratch\[7\]\s*=\s*(0x[0-9A-Fa-f]{2})", text))

EXPECTED = {0x30, 0x31, 0x3A, 0x3B, 0x3C, 0x3F, 0x40, 0x4F,
            0x42, 0x44, 0x46, 0x70, 0x72, 0x7F, 0x80, 0x8F}
assert MARKERS == EXPECTED, (sorted(MARKERS), sorted(EXPECTED))

main = Path("src/main.c").read_text().lower()
avdtp = Path("src/btstack/btstack_avdtp_source.c").read_text().lower()
legend = main + "\n" + avdtp
for marker in sorted(EXPECTED):
    token = f"0x{marker:02x}"
    assert token in legend, f"scratch[7] writer {token} is not decoded by any legend"
# The old legend claimed USB/bootsel markers that are never written.
for stale in ("0x10 usb-task", "0x20 bootsel"):
    assert stale not in legend, stale
print("scratch[7] watchdog legend matches every writer")
