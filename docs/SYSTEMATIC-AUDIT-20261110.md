# Systematic audit — 2026-11-10 UTC

## Source and scope

Reviewed the newest combined development source, `8309def1612bc5f3ab670e518665cefbb2c02f10`, rather than repeating changes against older main `018685157ab8c5dedc66008e2e54ae3a38994e25`. This builds on draft PR #7, which itself targets the Windows follow-up branch. The isolated repair branch does not replace other workers' branches or silently merge their work into main.

This pass reviewed the current integration reports and evidence provenance, microphone capture lifecycle and first-underrun telemetry, codec/profile validation, live runner phase coverage and collection, and CI watcher ownership/completion rules. Existing firmware, real-codec, USB/HID, launcher and host regression suites remain the broader regression gate. This is a bounded systematic pass, not a proof that every possible project defect has been eliminated.

## Repaired defects

1. **Reconnect false passes:** reconnect steady intervals checked firmware counters but omitted host input/output evidence. They now include `AudioSession.phase_errors`, preserve first failure before stream cleanup, and fail when either host stream stalls.
2. **Phone-relay false passes:** the optional relay interval had the same omission. It now checks host input/output errors and liveness as well as firmware progress and the operator's response. Replay tests cover a healthy relay and each stalled host direction. Reconnect/relay warmup callbacks are recorded in separate transition phases, so they cannot satisfy the later steady measurement. Strengthened tests allow warmup callbacks and then stall only during measurement; all four directions reproduced false passes before phase separation.
3. **Channel observation despite invalid stimulus:** an operator could answer yes after host output underflow. Channel probes now reject recorded output callback errors before requesting an acoustic verdict. No callback still means UNVERIFIED stimulus.
4. **Incomplete counters interpreted as clean:** modular delta defaulted absent counters to zero; missing fields could pass and malformed values could raise exceptions. Health checks now require valid unsigned counters at both endpoints for decoded/PCM/TX progress, generation, microphone/USB loss, send failures and microphone recovery. Missing/invalid data fails validation before arithmetic. Genuine uint32 wrap remains supported.
5. **Cross-core diagnostic timestamp race:** USB sampled the clock before reading producer timestamps; a concurrent publication could create an age close to UINT32_MAX. It now reads producer timestamps before sampling the clock. The first-fault snapshot remains bounded, sticky and atomic. A deterministic regression extracts the production function, injects the publication interleave and covers uint32 clock rollover; an archived pre-repair production function must fail both controls.

No sample clocks, queue capacities, codec profiles, core scheduling, radio/session commands or physical channel behavior have been changed by this patch.

## Validation and limits

Before repairing the runner gates, three targeted regressions failed against the previous implementation. The missing/invalid counter cases also reproduced failures and exceptions before repair. All 68 host tests passed locally (runner 27, matrix 16, validation 8, profiles 9, watcher 8). The first GitHub CLI integration run at `6f83b87` failed because its simulated device omitted newly required counters. The simulator now emits the real counter fields and has a separate missing-counter case requiring CLI failure, first-fault preservation and a valid ZIP. Final exact-source GitHub results are recorded with the pull request after completion. Firmware tests and builds run only in GitHub Actions; no local firmware build is used as evidence.

The new timestamp test models a legal interleave in extracted production code. It is not an RP2350 scheduling, IRQ-latency or RF/acoustic measurement. Host replay uses simulated devices; callbacks and changing firmware counters cannot prove either AirPod played sound. The runner still requires explicit listening observations.

## Physical findings that remain open

The last physically flashed source remains `1979ae6be1c2daf9e1db8024763504d4061c4588`; later evidence-only commits do not change that identity.

- Single-core rpi0065 AAC-ELD 256/192 kbps and both game-mode steady intervals had zero new AU/USB loss in the recorded short measurements. The 192 kbps PCM-full work exits were backpressure, not lost samples. Startup/lifecycle lifetime losses must not be erased by quoting steady results.
- Mic-close left-ear silence remains unresolved. Left PCM was present before encoding; reopening capture, an explicit refresh, and a separate saved-bond reconnect restored left playback in recorded observations. This does not identify the peer-side cause or justify an automatic refresh workaround.
- Experimental core1 192 kbps recorded 44 USB underrun packets / 2,816 missing samples without AU overflow. It remains opt-in and off by default. New diagnostics improve attribution; they do not repair that physical fault.
- The historical ten-minute soak retained its strict-loss failure. No new long soak, physical channel pass, or proprietary Full-edition parity is claimed.

Continue USB-only diagnostics on the existing CDC interface. Do not ask for a UART adapter. Use phone-speaker audio for microphone stimulus. Do not automatically flash hardware or announce live readiness from CI success. The current Desktop watcher is record-only unless explicitly owned by a verified idle CLI session; an accepted callback is not proof of a new Desktop turn.
