> Historical hold report. Engineering fixes and replacement-candidate criteria are documented in [REVALIDATION-2026-11-03.md](REVALIDATION-2026-11-03.md). The old 238ed609 package remains withdrawn.

# Verification after the first failed physical run

**Disposition: HOLD. No next hardware run requested.** Passing compilation or
host tests is not a claim that this firmware works with AirPods. The prior
238ed609 acceptance package must not be rerun. New packages are blocked by
`validation-status.json`; the runner refuses them before opening hardware.

This pass covers the first-party firmware and runner boundaries across
discovery/authentication, AVDTP, codec setup/transitions, AACP/microphone,
USB audio/CDC/HID, relay, settings, boot/recovery and packaging. It combines
source inspection, the supplied physical capture, host regressions, real FDK
audio tests and the target build matrix. It is not an exhaustive verification
of every algorithm in the bundled FDK/LDAC/LHDC libraries or the radio firmware.
Private upstream modules remain unavailable; reconstructed reference files
remain suggestions, not authoritative implementations.

## What the physical capture establishes

Evidence: `USBPods-results-20261103T192956Z.zip`, firmware source
`238ed6091c8ca72d8e4e279ff3f5f4f7401e61e4`. Times below are UTC.

| Time | Recorded event | What it establishes |
| --- | --- | --- |
| 19:30:47.319 | Runner sends `pair 0` | Explicit scanned target selected |
| 19:30:47.402 | ACK id 132, queued 1, value 0, preceded by one space | Firmware accepted the command; old runner discarded it |
| 19:30:47.835–48.157 | ACL success, authentication status 0, encryption enabled | The intended peer connected using an existing stored key; new bonding was not exercised |
| 19:30:48.266–48.591 | AVDTP signaling/media opened, `Stream started.` | Application reached its playback-start path; this does not prove transmitted or audible media |
| 19:30:50.731 | AACP open 0, confirmed 0, attempts 1 | AACP handshake had not completed |
| 19:30:51.886 | TX stall, recovery request, SUSPEND returns 12 | A separate firmware/SDK state failure occurred |
| 19:30:52.000 | Local ACL termination | Firmware deliberately disconnected after recovery failure |
| 19:30:53.326 | Runner begins restoration after ACK timeout | It never reached its connection/handshake checks or audio matrix |
| 19:30:55.452 | Another ACL completion | A later connection attempt occurred; sustained manual hold is not demonstrated |

The pairing sound is consistent with the successful connection in the capture.
The user's failed outcome is real: no stable usable session was established.
Fixing the ACK parser does not resolve the TX stall. No microphone, rate/game,
relay, acoustic-quality or soak result can be claimed from this run.

## Corrected defects and evidence

| Finding | Change | Regression evidence |
| --- | --- | --- |
| Indented pairing ACK ignored | Accept leading spaces/tabs before the control prefix; remove trailing slot-print indentation | Replay the captured ACK through the actual threaded serial collector with split reads |
| Boolean ACK mismatch | Correlate pvol/CA user values 0/1 with firmware wire values 2/1 | Exercise both commands and both values |
| Cached/partial telemetry could be reused | Require all three current telemetry replies as well as ACK | Missing/reordered telemetry replies cannot pass |
| Playback state flag treated as sufficient | Require media-packet progress and no new submission failures during steady intervals | No-progress interval fails even with streaming flag set |
| Failure state overwritten during cleanup | Collect status, encoder state, telemetry and saved devices before restoration | Failure bundle now includes the pre-cleanup state |
| Unchanged settings reapplied on failure | Restore only differences from the original settings | Unchanged cleanup schedules no game/rate rebuild |
| Reconnecting a known peer filled the other favorite | Prefer the existing matching favorite before finding a free slot | Production pairing function tested for same-MAC reuse, free slot and replacement |
| AVDTP CID used to disconnect AVRCP | Use the independent AVRCP CID | Production teardown tested with different AVDTP/AVRCP CIDs |
| Discovery table/capability copy unchecked | Bound and deduplicate endpoints, reject unknown/oversized capabilities, handle no sink endpoints, validate variable vendor payload lengths | ASan/UBSan boundary sweep over capability lengths and endpoint capacity |
| Same-CID unrelated endpoint events could affect playback | Check the selected local SEID on media grants and transport accepts; reject AVRCP from inactive peers | Source review plus target compilation; not a full peer-event integration test |
| Settings debounce assumed every main-loop pass was 50 ms | Use actual elapsed milliseconds at 2/10/50 ms loop cadences; retain dirty data after failed explicit flush | Production debounce tests for each cadence, wrap, retry and update-during-commit |
| UART adapter required by runner prompt | Use the single USB CDC port by default; UART is explicit opt-in | CDC transport remains the same collector used by ACK replay |
| Ordinary diagnostics dumped stored link-key bytes | Log addresses/key types without key material | Source inspection; raw capture remains private and is not committed |
| Immediate reconnect call slept in callback context | Remove the 200 ms sleep after the nonblocking dial request | Source inspection plus target compilation |

SDK endpoint state, media CID, remote SEID, pending START/SUSPEND/grant flags,
packet count and send failures are now logged at START, before ELD failure
teardown and on `:telemetry`, all over CDC. The old physical capture did not
contain these fields. This is evidence collection, not a transport fix.

## Open blockers

1. **Startup TX stall and SUSPEND error 12.** Checked against the exact pinned
   BTstack revision `501e6d2b86e6c92bfb9c390bcf55709938e25ac1`, from Pico SDK
   `bddd20f928ce76142793bef434d4f75f4af6e433`. `avdtp_suspend_stream()` returns
   12 when the remote SEID is unregistered, endpoint state is not STREAMING,
   or SUSPEND is already pending. Its media-grant handler also requires the
   actual endpoint to be STREAMING. The capture cannot distinguish those
   preconditions. A new regression executes those actual SDK function bodies;
   it does not recreate the full controller/peer event sequence. The new bounds
   and SEID guards may address contributing defects, but causation has not
   been established. The immediate failure disconnect remains deliberate;
   it must not be suppressed merely to make the run look successful.
2. **320 kbps negotiation.** `eld_profile.c` selects 320000 CBR, while
   `codec_aaceld.c` currently emits a fixed 256000 codec configuration. Native
   encode/decode success proves neither peer acceptance nor compliance with
   that configuration. Peer capability limits, negotiated parameters and live
   profile changes must be reconciled before claiming the 320 kbps feature.
   No speculative private codec bytes were introduced in this audit.
3. **Microphone timing.** The raw ASC decodes as 48000 Hz/480 samples; USB
   consumes 64 samples per millisecond and labels recordings 64000 Hz. This
   requires an established mapping to the peer's AU cadence and signal clock.
   A local FDK round trip does not establish that mapping. It remains an
   experimental timing path, not validated microphone support.

## Remaining coverage limits by area

| Area | Review/checks | Remaining uncertainty |
| --- | --- | --- |
| Boot/board/radio | Board/variant guards, source SHA, unchanged radio image and UF2 checks | Physical startup/USB recovery and RF behavior |
| Discovery/authentication/favorites | Captured real authentication; bounded discovery and production favorite/teardown regressions | New bond creation, occupied favorites on real devices, inbound reconnect hold |
| Playback/ELD/game modes | Production transition adapter failures/deadlines, encoder fault injection, real FDK profile cycle | Actual SDK/peer startup sequence, negotiation ceiling, target deadlines and acoustics |
| AAC-LC/LDAC/LHDC | Source/dispatch/configuration review and target compilation | Non-ELD setup still allocates in Bluetooth callbacks; needs the same allocator-context audit/defer policy before broad headset testing. Hardware codec quality is unverified |
| AACP/control/microphone | Bounds, session ownership, stale epochs, queue/telemetry and real FDK decoding tests | AACP interoperability with this headset and 48/64 kHz mapping |
| USB capture | Alt/mount/suspend/close state tests; callback wiring and linked descriptors | Windows stream behavior, clock drift and physical suspend/re-enumeration |
| HID | Bounded queue, press/release retry/epoch tests, four-thread stress fixture | Host application action; opening a HID handle is not delivery evidence |
| Phone relay | CID ownership/lifecycle, epoch reset, RTP bounds/fragment tests, SBC-only mic variant | Real phone marker conventions, RF coexistence and mixed-audio quality |
| Settings/flash | Snapshot/CRC/record bounds review; real-time debounce and retry tests | Power-loss recovery and physical flash latency under duplex load |
| Runner/package | Recorded ACK replay, value correlation, fresh telemetry gate, cleanup, WAV tests, hashes and validation hold | Native PowerShell/PortAudio behavior and all unrun matrix stages |

Native tests exercise synthetic input and mocked platform calls. Callback-body
fixtures are useful regressions but are not a substitute for executing the
entire Bluetooth stack with a peer. Existing comments describing upstream
hardware observations are not evidence that this reconstructed revision passed.

## Verification results for this pass

- The complete host protocol/lifecycle/transition/USB/HID/UF2 suite passed
  locally (31 compile/test commands before adding the pinned-SDK contract;
  the additional SDK contract also passed). C fixtures use ASan/UBSan.
- Runner suite: 14 tests passed locally, including NumPy/audio cleanup tests.
- Actual repository FDK: microphone mono AAC-ELD round trip passed; subsequent
  AAC-LC LATM decoding passed at both 44.1 and 48 kHz.
- Actual FDK duplex fixture: 24 profile transitions, 3072 playback frames and
  active microphone decode passed with ASan; microphone generation stayed
  fixed. This measures host algorithm behavior, not Cortex-M33 timing.
- Target compilation, linked radio/UF2/descriptors and 32-bit codec heap audit
  run in the three-entry Pico CI matrix for this revision. Consult that run's
  job results; a successful build does not lift the validation hold.

The next hardware request requires a documented disposition for the blockers
and a revised coverage plan. There is no request to reflash or rerun in this
audit, and no new claim of live-test readiness.
