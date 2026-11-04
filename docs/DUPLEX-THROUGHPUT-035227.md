# Duplex throughput repair after capture 035227

The live run `USBPods-results-20261104T035227Z.zip` tested source `5a4ea5e` on
Windows 11/Pico 2 W/AirPods Pro 3. The original capture and speech WAVs remain
private. Sanitized facts are in [the evidence record](evidence/duplex-throughput-035227.json).

## What the capture establishes

- Firmware identity, selected-peer connection, AACP handshake and five-second
  playback preflight passed. Both isolated left/right prompts were answered
  yes with capture active. Mic-closed/reopened routing was not reached.
- The peer accepted a 256 kbps ceiling; 320 kbps was correctly skipped.
- The initial 256 kbps CBR/core-only warmup reported no AU/PCM drops over its
  short window. Changing to 256 kbps VBR=5/SBR=1 quickly saturated the AU queue.
- All five measured steady profiles failed the strict loss checks:

| Profile | Decoded mic frames | Dropped compressed AUs | USB decoded samples delivered | USB samples missing |
| --- | ---: | ---: | ---: | ---: |
| 256 VBR+SBR | 432 | 2,308 | 15.7% | 84.3% |
| 192 CBR | 2,610 | 153 | 92.9% | 7.1% |
| Game standard | 2,643 | 139 | 93.6% | 6.4% |
| Game low buffer | 2,630 | 139 | 93.6% | 6.4% |
| Restore 256 VBR+SBR | 390 | 2,346 | 14.3% | 85.7% |

Decoder errors and history-clear failures remained zero. AUs continued arriving
around the 64 kHz PCM timeline, with no timestamp duplicates/backtracking or
step changes. Mic generations stayed stable during profile intervals. This is
a servicing/throughput failure, not evidence of a changed mic clock or failed
FDK history reset. The 256 VBR+SBR association is strong; the short CBR warmup
does not establish sustained CBR success under every signal.

At the last snapshot, 11,458 AUs had overflowed, 190 decoded frames had been
discarded, and 5,630,400 USB samples were missing. Decoder wall-time reached
509,696 us; that interval includes preemption by playback/USB interrupts and
must not be treated as pure decoder CPU time.

CDC and HID lost access to the device around 03:56:09 UTC during the quality
comparison. No reset banner was captured. Unplug/reflash, watchdog reset and
other USB loss cannot be distinguished from this archive. Reconnects and soak
were not reached; no successful completion is claimed.

## Implemented repairs

1. The mic-capable build uses CBR/core-only ELD at each peer-permitted bitrate.
   This bounds configuration cost instead of changing packetization, adding a
   speculative time exit to the encode loop, or reintroducing the disabled
   core-1 encoder. Transport-only builds retain their existing VBR policy.
   `eldstatus.duplex_cbr` identifies the applied policy independently of peer
   VBR permission. The matching runner checks that policy explicitly. Capture
   opening/closing does not itself trigger a playback profile rebuild.
2. Before decoding a current AU, the decoder reserves available PCM capacity
   by checking the single-producer queue. If it is full, the AU stays queued.
   USB can only free capacity while decoding; it cannot invalidate this check.
   Stale generations are still discarded before backpressure. This removes
   the old decode-then-discard behavior, which increased loss when a backlog
   caught up. Compressed-ring overflow remains bounded and visible if target
   throughput is still insufficient.
3. The main loop skips its idle sleep while AUs are runnable and PCM capacity
   is available. Each pass remains bounded at eight decodes, with watchdog,
   control, settings and other main-loop work serviced between batches. A full
   PCM queue still allows idle sleep.
4. Telemetry includes encoder last/max wall time and decoder last/EMA wall
   time. `info` includes the already-stashed reset kind/phase/IRQ and fault
   evidence so a subsequent USB session can report reset forensics without
   an external UART adapter. Reset kind is 0 clean, 1 watchdog, 2 hard fault,
   3 panic; replugging/power loss may erase evidence.
5. The runner proceeds directly from mic-active channel checks to mic
   close/reopen, three reconnects and the duplex soak. The withdrawn Full/bass
   comparison no longer interrupts that sequence. USB-loss simulation checks
   that a failed run still writes its results archive and reports restoration
   failures rather than claiming success.

The mic ASC, independent 64 kHz USB clock, adaptive USB packet sizing,
negotiation ceiling, Apple AU header and RTP timing are unchanged. Backpressure
does not enlarge any audio queue or add allocations to the audio path.

## Verification and next physical run

The maintained offline suite passes 63 checks with zero failures/skips,
including ten complete CLI scenarios. The real-FDK test fills the PCM queue
from 32 queued AUs, then verifies every retained frame against fresh-decoder
PCM in order. The old decoder fails the new zero-drop/backlog assertion.
Existing stereo/gain/AU/MTU, mic restart, USB lifecycle and ownership tests remain
in the suite. Both transport and mic profile-policy variants are tested.

```sh
python3 tools/run_offline_checks.py --fdk-lib /absolute/path/to/asan/libfdk-aac.a
```

Target CI and exact next-candidate identity are recorded in the evidence file.
These changes address demonstrated configuration and queue defects; they do
not establish target schedulability or explain the previous USB loss. The next
live run must still prove low/drop-free mic delivery under all supported CBR
profiles, both game modes, capture close/reopen, reconnects and sustained soak.
Return the results even on failure, and note whether any USB loss happened by
itself or followed a physical unplug/reset.
