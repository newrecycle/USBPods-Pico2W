# Repair after live capture 042523

The private run `USBPods-results-20261104T042523Z.zip` tested source `a952fa9`.
It confirms the previous CBR/backpressure change substantially improved the
priority path: both 256 kbps intervals and the reopened-mic duplex interval
passed with zero AU drops, PCM drops, decode errors or missing USB samples.
USB CDC/HID collection and cleanup stayed available; no collector/restoration
errors were reported. The original capture and speech remain private.

## Remaining observed failures

| Check | Captured result |
| --- | --- |
| 192 kbps | 65 compressed AUs dropped; 33,088 USB samples missing |
| Game standard | 88 AUs dropped; 43,328 USB samples missing |
| Game low buffer | 61 AUs dropped; 29,120 USB samples missing |
| All profiles | Zero decoder errors and zero discarded decoded PCM frames |
| Mic active, left | User described left-only playback with delayed onset; runner classified free text UNVERIFIED |
| Mic active, right | PASS |
| Mic closed | Left PASS; right answered no. The answer does not distinguish silence, both buds, or wrong-side output. |
| Mic reopened | Left/right and duplex counters PASS |
| Reconnect 1 | Eventually connected, but only after an old ACL supervision timeout; 2,240 USB samples missing in the measured interval |
| Reconnect 2 | Initial media OPEN timed out after three seconds, stage 6 / code 518 (`0x206`); firmware deliberately dropped the ACL and held a fault |
| Reconnect 3 / soak | Not reached |

The 320 kbps profile remained correctly skipped at the peer's 256 kbps ceiling.
The recorded maximum encoder wall time was 8,005 us per frame, and decoder
wall time reached 77,594 us. These measurements include interrupt/preemption
time and are not pure CPU-cycle measurements.

## Repairs

### Bound radio-context encode batches

At 192 kbps, three AUs fit in an RTP packet and the old source filled all three
in one radio-context call. At 256 kbps the existing packet budget already
stopped at two. The mic-capable ELD build now limits every fill call to two
AUs, preserving catch-up capacity above the required 100 AUs/s while reducing
per-call blocking of the foreground mic worker. The bound is constant across
mic open/close, so capture itself does not change packet aggregation. Apple AU
headers, sample accounting, RTP timestamps and the peer bitrate ceiling are
unchanged. Transport-only behavior remains unchanged.

The real-FDK production PCM/packet test asserts the new batch bound and still
checks stereo gain/order, frame sequence wrap and MTU. It fails against the
previous source's three-AU fill at 192 kbps and passes the new source.

### Give the existing mic ring more service-gap headroom

The prefill/target changes from 2,880 to 4,800 samples: 45 to 75 ms on the
64 kHz PCM timeline. This adds about 30 ms of buffering; it does not change
the coding/USB rates, resample speech, or enlarge the sixteen-frame PCM ring.
A synthetic 78 ms service-gap case, motivated by the observed decoder wall
time, fails with the old target and passes with the new target. This is a
bounded model, not a reconstruction of the live packet trace. Existing
ten-minute drift tests at -1500/-250/0/+250/+1500 ppm also pass within ring
capacity, with zero missing packets after priming.

### Make disconnect/reconnect an ACL transaction

The old explicit disconnect closed AVDTP/AVRCP/AACP channels but could leave
HFP/SDP and the underlying ACL alive. Reconnect then reused a partially torn
down session. The capture shows the first reconnect cycling until that ACL
timed out, and the second failing media OPEN shortly after reusing the link.

Explicit disconnect now cancels deferred codec setup and OPEN/START timers,
then requests ACL release. A following Connect is coalesced and deferred until
the matching HCI disconnect event. Another
Disconnect cancels that queued Connect. Other/phone ACL events do not release
this gate, and headset signaling arriving during teardown is rejected.
Pairings and history are retained. Deterministic tests execute the production
disconnect, reconnect and HCI-notification helpers, including duplicate intents
and unrelated handles.

Initial media OPEN gets a bounded ten-second window rather than sharing the
three-second START-acceptance budget. When media arrives, the START timer is
rearmed for its own full three seconds. Managed rate-change deadlines remain
three seconds and duplicate requests do not extend them. This is a separate
bounded phase allowance, not an unbounded retry or the sole reconnect repair.

### Keep mic lifecycle writes independent of playback jitter

The capture records an extra `0x0b=150` playback-jitter write roughly 500 ms
after mic STOP, immediately before the failed closed-mic channel check. The
pinned working microphone reference does not send this control on START/STOP.
Those unsolicited lifecycle writes are removed. Explicit game/profile policy
and new-channel initialization still own their jitter commands. A transport
regression verifies that START/STOP do not enqueue playback jitter.

This removes a demonstrated side effect; it does not prove the AirPods'
physical channel symptom fixed. The next run must verify that outcome.

### Fail promptly and preserve meaningful observations

The host now stops a state wait as soon as firmware reports a held fault,
instead of spending the rest of a 45-second connection timeout waiting for a
known failed setup. The full CLI replay covers the second-reconnect stage-6
fault, diagnostic preservation and cleanup. Channel prompts accept explicit
`silent`, `both` and `wrong-side` failure answers alongside yes/no, preserving
free-text observations as unverified.

## Verification and limits

The maintained offline suite passes 64 checks with no failures/skips. Eleven
complete CLI scenarios cover success, policy/ownership, transport errors and
reconnect faults. New assertions exercise production bodies and include old
source negative controls for packet batching and service-gap buffering.
Target CI, candidate identity and sanitized live deltas are recorded in
[the evidence record](evidence/duplex-lifecycle-042523.json).

```sh
python3 tools/run_offline_checks.py --fdk-lib /absolute/path/to/asan/libfdk-aac.a
python3 tests/test_live_cli_e2e.py --candidate /path/to/extracted/candidate --output build-candidate-cli
```

Use a fresh output directory. The physical run must still establish drop-free
lower-rate/game performance, closed-mic stereo, all three reconnects and soak.
The new buffering target's acoustic latency is not measured offline. No new
mic clock, protocol, EQ or guessed stem mapping is introduced.
