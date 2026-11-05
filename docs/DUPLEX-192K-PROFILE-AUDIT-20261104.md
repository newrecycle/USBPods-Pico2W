# Independent duplex throughput and profile correctness audit (2026-11-04)

**Scope:** bounded playback/microphone packet accounting and profile verification.
**Immutable starting point:** `6c2009637c9b12bf8d2fb9c7b20127b8679fb11f`.
**Physical source:** last physically flashed firmware `880dc318072f191f1440d3f0b262d83e32729b59`; not this branch.
**Ownership:** no core-1 worker, FDK ownership, malloc, flash, stack or scheduling redesign.
**Input limitation:** `docs/LOCAL-WINDOWS-20261104.md` and
`docs/evidence/local-windows-20261104.json` are absent from the pinned
baseline. Do not fetch unpublished worktree/other worker branch content.
Only user-supplied latest observations and committed prior sanitized reports are
used here. Raw captures, sound, peer addresses and keys are not available.

## Phase 1: measured observations

| Quantity | Observation or derivation |
| --- | --- |
| Latest failing interval | Laptop with MaxxAudioPro disabled, 192 kbps, approximately 20.6 s |
| 256 kbps | Passed latest measured interval |
| 192 kbps microphone | 186 AU drops, 95,168 missing USB samples |
| Both bitrate intervals | 1,029 A2DP packets each / ~20.6 s = ~49.95 packets/s |
| Expected compressed AU demand | 64,000 / 480 = 133.333 AUs/s, ~2,746.7 AU over 20.6 s |
| AU ring | 32 entries = 15,360 samples = 240 ms at 64 kHz; reached 32/32 |
| PCM ring | 16 frames = 7,680 samples = 120 ms at 64 kHz |
| Mic USB prefill | 4,800 samples = 75 ms at 64 kHz (not added to throughput) |
| Dropped AU equivalent | 186 * 480 = 89,280 samples = 1.395 s @64 kHz |
| Missing USB equivalent | 95,168 / 64,000 = 1.487 s = 7.22% of 20.6 s |
| Difference | 5,888 samples = 92 ms; cannot assign without per-interval buffer timeline |
| Supplemental run | About 45 s; 6,089 extra decoded AUs, zero new decode/AU/PCM/USB loss; the approximate duration and accounting window prevent an exact sustained service-rate inference |
| Initial physical 035227 | 256 kbps VBR+SBR produced severe local decode starvation; subsequent CBR/core-only policy corrected it |
| 042523 | 256 kbps zero loss; 192 and both game modes still lost microphone AUs |
| 051250 | Earlier 192/game ~33.3 playback packets/s due to three AUs/packet; repaired to two AUs/packet; 10-minute soak retained, no repeat requested |
| Latest laptop | 192 loss **after** cadence repair, about 50 playback packets/s. Do not reapply the old three-to-two patch |

Queue high-water shows local backlog, not RF transmission loss by itself.
No increased timestamp-gap candidates means no observed new gaps by that heuristic,
not proof of loss-free radio arrival. Sample-equivalent output throughput
`(20.6*64000 - 95168) / (20.6*480) ~= 123.7 AUs/s` is only an approximate
USB delivery equivalent, **not** measured decoder CPU throughput or an exact
service rate: priming/rebuffer and queue-start/end inventory are unknown.
No per-interval AU arrival count, decode count, precise occupancy timeline,
encode timing histogram or loss-event timestamps are available at this baseline.
The latest run did not remeasure either game mode after its failing 192 interval.

## Hypotheses and falsification

1. **Mic scheduling/starvation:** AACP delivers on time but FDK cannot drain
   AUs while the playback encoding/BT callback occupies core 0. Falsify with
   timestamped AU arrival/decode/encode durations and occupancy showing enough
   decoder service despite the full AU ring. The separate newer, unflashed
   foreground-encode candidate is relevant as an integration hypothesis,
   **not** verified physical repair. Do not duplicate its scheduling architecture.
2. **RF batching/airtime:** 192 profile may alter radio timing despite equal
   RTP packet *count*. Falsify with event-level interarrival/packet payload
   timing that is indistinguishable from 256 during a failure. No timestamp-gap
   candidates does not disprove burst bunching.
3. **PCM backpressure:** full PCM ring can stop AU drain. Falsify with
   simultaneous AU-high/PCM-low snapshots throughout overflow. The existing
   production decoder keeps compressed AUs queued rather than decode-discard
   when PCM is full; this preserves correctness but cannot create capacity.
4. **Clock deficit/drift:** sustained arrival rate exceeds 64 kHz USB demand.
   Falsify with rate/priming history and occupancy stability over a controlled
   interval; current clock correction is bounded to 2,000 ppm and never
   creates PCM samples.
5. **Host effects:** laptop output callback behavior and Windows enhancements
   differ from the previous PC. Falsify by paired same-host/same-firmware
   256/192 measurements, including host callback error counts. Cross-host
   comparisons alone do not establish firmware regression.
6. **Wrong applied game configuration:** normal 192 kbps non-game has the same
   bitrate and six slot count as game standard. The existing runner can
   misidentify one as the other because `profile_matches` checks only active
   bitrate/VBR/SBR/slots, without checking selected rate, game, or level.
   Falsify with a production status snapshot where all these fields
   match the requested command; a negative fixture must reject the
   normal-192-as-game-standard false positive.

## Minimal scoped repair / plan (written before implementation)

- Tighten host `tools/live_audio.py::profile_matches` to require the firmware's
  explicit `selected_rate`, `game`, `gamelevel` and `desired_bitrate`
  along with the already verified **applied** encoder fields and revision
  equality. The requested preset must not silently substitute for applied
  CBR/VBR state. Retain strict failure on missing fields.
- Require the advertised negotiated ceiling to be known and sufficient for
  the **actual requested profile**. No forced 320 kbps: `eld320` remains
  skipped when the peer negotiated 256 kbps. Game presets request rate selector
  3 but apply 192 kbps; evaluate the effective bitrate, not preference 320.
- Add focused before/after regression: under the old matching algorithm a
  ready normal-192 state passes as `game_stable`; with the repair it must
  fail, and correct 256, 192, game-standard and game-latency states must pass.
  Rejected/missing/stale desired or selected state must fail. Keep full
  `tools/live_audio.health` zero-loss acceptance unchanged.
- Update the existing stateful host matrix fixture to return the production
  `eldstatus` selected/desired fields. Do not change firmware audio,
  48k stereo playback, 48k mic coding, 64k USB PCM or packetization.
- Run existing offline checks with real FDK when available and the PR-host
  workflows. A host pass never establishes Pico schedule or acoustics.
  No firmware change in this scoped repair: target/memory build identities
  stay the exact baseline, and do not claim a new physical build.

## Handoff and validation boundaries

The independent core-1 worker owns cross-core synchronization, allocator,
flash lockout and encoder/decoder instance lifetime. The mic queue remains
single-producer/single-consumer; a concurrency redesign must re-audit it.
An integration candidate incorporating the separately owned bounded
foreground-encode scheduling change should preserve this profile verifier
and the strict loss counters. It must not be assembled here from another
worker's unpublished branch.

**Future hardware:** no repeat 10-minute soak. Once the integrated candidate
is reviewed and independently authorized, compare only short (10–25 s)
steady 256/192/game-standard/game-low-buffer intervals on the *same* host,
separating recovery from steady snapshots and preserving failure evidence.
Inspect AU arrival, decoded, AU/PCM depth/high-water, AU drop, USB missing,
RTP packet cadence, encoder and decoder time, capture status, and host callback
errors. No hardware execution or raw capture is claimed in this audit.

### Profile verifier addendum (pre-code review)

`eldstatus` currently exposes `active_slots` but not `active.jitter`.
A normal 192 kbps profile and game-standard both have 192 kbps, six slots,
CBR and core-only SBR disabled. Merely checking the **requested** `game` flag
would still allow the *old active* six-slot profile to appear correct. Therefore
add `active_jitter` and `desired_jitter` to the existing, read-only
`eldstatus` diagnostics and require the expected 150/90/60 millisecond
profile-policy value. This is an observable active-profile selection, **not**
peer acknowledgment of the AACP jitter command. No actual jitter is changed.

Since the optional relay check currently uses an arbitrary `gamelevel=2`
while the restored baseline uses level 1, the relay verifier must derive
selected rate/game/level from the actual restored baseline; keep the 164 kbps
relay ceiling and six slots unchanged. This avoids converting a previously
unchecked preference into a false failure.

This one additive firmware-status field pair requires target compilation and
heap/memory checks in CI, even though no codec/packet/USB processing changes.
