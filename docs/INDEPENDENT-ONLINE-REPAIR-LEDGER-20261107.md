# Independent online-only diagnostic ledger and falsifiable plan — 2026-11-07

## Immutable intake (before any production edit)

- Target at intake: `work/local-windows-followup-20261107` = `2cc988df66b7ad84cdfdb2ae89b9e93604c87c0b`.
- `main` at intake = `018685157ab8c5dedc66008e2e54ae3a38994e25`; target is 31 commits ahead, zero behind.
- Isolated branch: `audit/sequential-validation-online-20261107`, forked **from the above exact target**. Never merge to main or modify another worker's ref.
- Last physically flashed firmware source = `1979ae6be1c2daf9e1db8024763504d4061c4588`; its single-core artifact is `13592873692`, opt-in core-1 artifact `13592997637`. The candidate at intake is **not physically tested**.
- Read and reconcile AGENTS, local handoff/tasks/follow-up, the sequential plan/report, four 175ACE9 diagnoses, sanitized setup/live/dualcore JSON and production code/tests/workflow implementations. Historical claims remain scoped to their own exact SHA.
- Constraint: no physical device, COM port, private captures, Desktop writer or Windows host. No firmware compilation or codec execution outside GitHub Actions. GitHub-connected repository operations only; all experiments must be labeled synthetic.

## Evidence ledger, reproduction hypotheses and falsifiers

| ID | Observation and status at intake | Falsifiable online check / next action | Hardware boundary |
|---|---|---|---|
| MIC-01 | **Physical FAIL** at 1979ae6: closed capture silences the left ear, but left-only post-gain pre-FDK PCM still peaks 316–317, right 1. Explicit K refresh and saved-bond reconnect each restore audible left while closed. Actual fault-phase AAC output and peer state unknown. | Inspect production USB close, AACP STOP/START, epoch, ELD profile/encoder lifetime and actual staging. Re-use *existing* real-FDK stereo/Apple AU positive and swap-negative contracts. Add a new test only if it exercises an uncovered production transition. Check that mic close never silently rebuilds/restarts playback, that codec input remains independent of capture generation, and that test assertions distinguish raw PCM from compressed decoding. | Synthetic channel fidelity **cannot** establish AirPods rendering or codec content at the real fault instant. No speculative automatic K, reconnect, undocumented control or clock change. |
| CORE1-02 | **Physical FAIL** at 1979ae6 opt-in core1 192 kbps: 44 fully missing 64-sample USB packets = 2816 PCM samples; zero new AU overflow. Same-source single-core 192 passed a short interval. | Existing production linked `test_mic_service_schedules.c` already contrasts producer gap, delayed worker, held USB consumer, epoch and a deliberate zero-loss false claim. Audit clock/rebuffer and distinct timing hypotheses. Add a bounded, allocation-free, race-safe **post-priming first-underrun** snapshot / interval counters only if production code reveals a diagnostic blind spot; assert first-event origin/ages and negative controls via the existing firmware workflow. | No reproduction of RF scheduling, core occupancy, flash XIP contention, or physical USB callback jitter. Core1 remains opt-in OFF by default and excluded from automatic package. |
| LIFE-03 | **Unproven cause:** 248 lifetime AU drops across startup/interruption/capture history. Steady single-core measured windows have zero *new* loss. `pcm_blocked` is backpressure, not AU overflow. | Use existing production queue/epoch/delayed-consumer fixture. Add an assertion only for a missing independently reproducible defect; verify generation fencing, stale full PCM, partial offset, no hidden loss, USB consumer ownership. Keep strict `missing_samples` and `au_overflows` accounting; do not reinterpret losses. | First Windows WASAPI callback latency and exclusive input ownership require host timestamps/telemetry. |
| CI-04 | **Online verifiable:** watcher previously conflated retry attempts, Desktop CLI return with actual continuation; current production implements attempt ordering and record-only Desktop mode. | Inspect `watch_ci.py`, `live_test.py`, `live_audio.py`, launchers and host fixtures. Verify no accepted callback, completion file or CLI exit is labeled autonomous Desktop turn. Inspect **exact source SHA**, workflow run attempts, job conclusions, canceled/skipped and artifact hashes. Preserve `build_verified`, UF2 identity and positive 32-bit allocation validation. | Host-only stimulus liveness / actual Windows/recorder behavior cannot pass in cloud. |
| SETUP-05 | **Historical fixed offline / physical evidence:** e9f5482 media setup stall prompted production SDK accepted-label retirement repair at 1979ae6; subsequent real saved-bond media setup succeeded. | Inspect the production SDK patch/15-position response reentry fixture and negative old patch. Do not conflate an accepted callback with confirmed running playback. | Intermittent RF/peer setup still requires physical observation. |

## Strict validation matrix and stopping conditions

1. Write this ledger **as the first isolated commit** before changing firmware, CI, test code or run claims.
2. Inspect upstream production implementation and existing fixture coverage before choosing a minimal diff. Avoid suites that duplicate already successful real-FDK, PCM/queue and runner tests.
3. Reproduce before a repair wherever possible. An intentional negative control must fail for the **specified assertion** after successful compilation; generic compile/runtime failure never counts.
4. Use only existing GitHub Actions **Pico firmware build**, **USB capture and HID host tests**, **Live runner host regressions** on the **exact pushed SHA**. Branch name matches existing push filters. Inspect latest attempts, all jobs including canceled/skipped; do not accept in-progress or a PR merge SHA as a successful push-source test.
5. Firmware/codec tests and 32-bit allocator gate execute in GitHub Actions; no local build or physical flash. Preserve source/UF2 manifest checks, hashes and `build_verified`.
6. Keep a post-implementation report with ordered commits, source SHA, run IDs, evidence level per claim, negative controls and only the short `-MicCloseOnly` future manual acceptance procedure. No extra ten-minute soak.

## Explicit non-goals

No AirPods/Windows access, no raw recordings or Bluetooth addresses, no automatic speaker restarts or speculative clock changes, no core1 enablement, no PR merge, branch deletion, direct Desktop callback, or unreviewed hardware programming.
