"""Execute the production USB speaker PCM tap with synthetic stereo tones.

The mic-close acoustic failure cannot be simulated: this regression proves that
future optional CDC observations discriminate host-side L/R data in an
open/closed/transition capture window. A baseline without state tagging must
fail, rather than falsely attributing a mixed window to a closed microphone.
"""
import os
import re
import subprocess
import tempfile
from pathlib import Path

from test_source_boundaries import ROOT, function

src = (ROOT / "src/tinyusb/uac.c").read_text()
start = src.index("volatile bool usb_pcm_tap;")
structure = re.search(r"static struct\s*\{[^}]*\}\s*tap;", src[start:], re.S)
assert structure, "Missing production tap counters"
declaration = structure.group(0)

fixture = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint32_t simulated_ms;
static bool capture_on;
static uint32_t get_absolute_time(void) { return simulated_ms; }
static uint32_t to_ms_since_boot(uint32_t t) { return t; }
bool usb_capture_running(void) { return capture_on; }
"""
tests = r"""
int main(void) {
    const int16_t left[] = {1200,0,1000,0};
    const int16_t right[] = {0,900,0,1100};

    capture_on=true;simulated_ms=100;
    usb_pcm_tap_feed(left,sizeof left);
    simulated_ms=600;usb_pcm_tap_feed(left,sizeof left); // stable open

    capture_on=false;simulated_ms=650;
    usb_pcm_tap_feed(left,sizeof left);
    simulated_ms=1150;usb_pcm_tap_feed(left,sizeof left); // transition window
    simulated_ms=1200;usb_pcm_tap_feed(right,sizeof right);
    simulated_ms=1700;usb_pcm_tap_feed(right,sizeof right); // stable closed

    capture_on=true;simulated_ms=1750;
    usb_pcm_tap_feed(right,sizeof right);
    simulated_ms=2250;usb_pcm_tap_feed(right,sizeof right); // transition window
    simulated_ms=2300;usb_pcm_tap_feed(left,sizeof left);
    simulated_ms=2800;usb_pcm_tap_feed(left,sizeof left); // stable reopened
    return 0;
}
"""

with tempfile.TemporaryDirectory() as temp:
    directory = Path(temp)
    c = directory / "mic_tap.c"
    exe = directory / "mic_tap"
    c.write_text(
        fixture + "\n" + declaration + "\n"
        + function("src/tinyusb/uac.c", "usb_pcm_tap_feed") + "\n" + tests
    )
    subprocess.run(
        ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
         "-fsanitize=address,undefined", str(c), "-o", str(exe)],
        check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        [str(exe)], capture_output=True, text=True,
        env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0"},
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    summaries = [
        line for line in result.stdout.splitlines()
        if line.startswith("[tap] ") and " pkts " in line
    ]
    expected = ("mic=open", "mic=transition", "mic=closed",
                "mic=transition", "mic=open")
    assert len(summaries) == len(expected), summaries
    for summary, capture in zip(summaries, expected):
        assert capture in summary, f"{capture}: {summary}"
    assert "peak L 1200 R 0" in summaries[0], summaries[0]
    assert "peak L 0 R 1100" in summaries[2], summaries[2]
    assert "peak L 1200 R 0" in summaries[-1], summaries[-1]
print("Production UAC tap: left/right source PCM and mic state correlation passed")
