# Offline triage plan — 2026-11-03

Goal: correct demonstrated defects and investigate acoustic regressions before
requesting another physical run. A target build is the final compatibility
check, not evidence that protocol behavior or audio quality is correct.
No new live-test package is planned for this pass.

## Evidence and sequence

1. Preserve and compare the 192956, 212827 and 220546 captures; use explicit
   user confirmation of native microphone and simultaneous playback. The latest
   capture proves the Windows shared capture fix and exposes a redundant
   settings-induced ELD restart followed by START rejection 263.
2. Compare the complete han-um microphone fork at pinned d18d083, upstream
   LibrePods microphone lifecycle and the suggested Full reconstruction.
   Separate verified byte/protocol contracts from implementation choices.
3. Reproduce captured transition order offline with actual production adapters
   and pinned SDK state changes. Fix repeated identical configuration requests,
   group profile application, preserve forced recovery as a separate intent,
   and check crossing settings/mic START/STOP and stale peer events.
4. Extend audio checks through production PCM/framing and fixed peer decoder
   assumptions. Compare bass/mid/high response, channel separation, multiple
   simultaneous tones and dynamic level envelopes; do not compensate a
   routing/codec problem with speculative EQ. Native synthetic success alone
   cannot establish AirPods acoustic quality.
5. Diagnose controls/stems from the received wire evidence and reference setup.
   Prove buffer ownership, notification attribution, supported control lengths,
   send completion and duplicate-event behavior before changing protocol bytes.
   Keep unsupported or indistinguishable gestures explicit.
6. Repair runner stage ordering and state ownership: establish capture ownership,
   preserve the first failure before cleanup, apply profiles once, isolate
   independent checks, and report external capture activity without treating
   it as a failed USB lifecycle. Replay the latest failure with a stateful fake
   device/audio backend, rather than only testing helper functions.
7. Re-audit edits, run production regressions, real FDK audio checks and bounded
   resource/cadence stress. Run all target variants only after those pass.
   Commit/push code and an evidence-based findings report. Do not request a
   physical rerun or label acoustic/gesture issues solved without evidence.

## Completion criteria

- Captured redundant transition reproduced before the fix, prevented afterward.
- Effective unchanged profiles produce no signaling/rebuilds; genuine changes
  and forced recovery remain bounded and serialize correctly.
- Runner can traverse/collect a simulated multi-profile duplex run and preserves
  first-fault evidence under the actual recorded rejection and capture-ownership
  conditions. No echo/no capture ownership is misreported as hardware success.
- Audio conclusions state the tested signal path and decoder assumptions.
- Each remaining limitation has a concrete cause or next required evidence,
  rather than a build result or another speculative hardware-test request.

Execution evidence and remaining limits: [OFFLINE-TRIAGE-FINDINGS.md](OFFLINE-TRIAGE-FINDINGS.md).
