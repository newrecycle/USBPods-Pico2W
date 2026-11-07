# Runner and CI completion continuity diagnosis — 175ace9

**Nature:** diagnosis and proposed plan only. **Source baseline:** \`175ace9f09554881b554e8226544e78ce10d06a1\`, on \`work/local-windows-followup-20261107\`. **Evidence commit parent:** \`1979ae6be1c2daf9e1db8024763504d4061c4588\`, the physically flashed single-core firmware source. This report does not assert access to the owner's Windows Desktop, microphone, USB device, COM port, local probe processes, session-store writer, audio recordings or raw results ZIPs.

## 0. Plan before any implementation

1. **Freeze the evidence and classify observations.** Use only the pinned commit, the committed sanitized observations, and inspected production watcher/runner/launcher code. Keep GitHub CI results, watcher file writes, callback attempts, a new agent turn, USB/device telemetry, actual stimulus and operator hearing as *different* levels of proof. Preserve first faults and original observations.
2. **Define completion and runner state machines.** Specify observable gates, independent delivery and continuation states, durable records, explicit failure/manual paths and ownership boundaries. Design against interruption and retries before considering production edits.
3. **Design deterministic host-only regression fixtures.** Mock GitHub CLI results, clock/process lifetime, event-log ownership, optional notification adapters, serial reports, tap acknowledgments, SoundDevice callbacks, file writes, launcher failures and crash/restart. Test the *production* Python functions or newly extracted pure helpers, not a duplicate implementation. Never label a mock an autonomous Desktop wake-up or acoustic pass.
4. **Validate separately on the owner's Windows host, after a review.** Use verified exact-source CI and a short, deliberately bounded same-host runner comparison. Record actual Desktop idle-to-running evidence, if a supported mechanism exists, without a user message; otherwise accept record-only/manual continuation as the supported result. Do not automatically flash, reconnect, alter firmware audio policy, bypass Desktop writer ownership or repeat an unnecessary soak.

**No implementation is part of this commit.** Proposed future production ownership is limited to \`tools/watch_ci.py\`, \`tools/live_test.py\`, \`tools/live_audio.py\`, \`tools/Run-Test.ps1\`, their dedicated host tests and documentation. Firmware compilation and all firmware/codec tests stay in GitHub Actions. No other worker's unpublished results or local ad-hoc scripts are prerequisites.

## 1. Evidence hierarchy and constraints

| Observation at the pinned revision | What it establishes | What it cannot establish |
| --- | --- | --- |
| \`tools/watch_ci.py\`: \`gh run list\` filtered by full \`headSha\`, push event and expected workflow names; atomic \`completion.json\`. \`tests/test_watch_ci.py\` has mock coverage for exact identity, missing workflows, negative conclusions and session-log idle checks. | The watcher can record the terminal status of the specified GitHub runs without waking a model. | A saved file is not a delivered callback, an executable turn, or hardware acceptance. |
| \`docs/LOCAL-FOLLOWUP-20261107.md\` §Observed callback limitation: exact-source CI passed for \`e9f548259cfc402db88a1e2ea7ca0a56ee99844a\` and the one \`codex exec resume\` attempt was refused with a Desktop thread-store active-writer conflict. | A CLI attempt against that Desktop-owned session failed despite an observed \`task_complete\`. | The session log's apparent idleness is **not** proof Desktop released its persistent writer. Retrying, using \`--last\` or overriding the lock is not justified. |
| Same document §final callback: a supported native follow-up tool accepted a delayed message; it was surfaced only after another human message. A later watcher ran record-only. | Delivery acceptance and eventual message visibility occurred. | Autonomous idle-to-running continuation was **not** seen. Neither accepted delivery nor surfacing after a human prompt counts as automatic wake-up. |
| \`docs/evidence/local-windows-20261107-live.json\`: source \`1979ae6...\`, firmware run \`42419581145\`, single-core artifact \`13592873692\`, hash-verified COM4 session. Short 256/192 and two game-mode steady intervals passed with zero **new** AU drops and USB missing samples. | These specific measured physical steady windows are historical, source-scoped observations. | No lifetime zero-loss, source \`175ace9\` physical pass, raw acoustic reproduction here, or proof of an automatic continuation. The 192 kbps interval still had 1,412 PCM-full worker exits. |
| Same JSON: accepted mic lifecycle showed left-only when open, silent with mic closed, left-only after reopening, while phase-matched post-gain left PCM peaks remained around 316. Explicit K refresh and saved-bond reconnect recovered left without reopening mic. | A real source-scoped mic-close defect survived; phase-matched encoder-input PCM did not vanish. | Peer-side acoustic/routing root cause, compressed audio correctness, or a firmware lifecycle fix. Manual recovery is not an automatic repair. |
| \`docs/LOCAL-FOLLOWUP-20261107.md\` §§Physical comparison / final: interrupted Wi-Fi/runner sessions invalidated an intermediate fresh-open silence observation; restarted probe wrongly assumed tap OFF; later accepted comparisons required live heartbeats and synchronized toggle acknowledgments. | Observation continuity and instrument state materially affect admissibility. | Which process or OS mechanism terminated the probes, or the exact behavior of the **uncommitted local ad-hoc scripts**. Those scripts are unavailable and were **not inspected**. |
| \`docs/VALIDATION-AUDIT-REPORT-20261104.md\` and current \`live_audio.py\`: host-owned input and firmware \`capture=0\` are separately recorded; first fault is preserved before subsequent cleanup when possible. | A local stream close plus firmware status can be tested separately. | Exclusive ownership of Windows' shared input endpoint; the existing result explicitly sets \`runner_exclusive_ownership_verified=false\`. |
| \`tools/Run-Test.ps1\`: performs \`flash_candidate.py\` before running \`live_test.py\`. | Current normal launcher is a flash-and-run sequence. | A safe unattended continuity/restart mechanism. Re-running the launcher is not a harmless reconnect or an idempotent resume. |

Other physical provenance: \`docs/evidence/local-windows-20261107-setup.json\` records the initial \`e9f5482\` no-media setup failures; \`docs/evidence/local-windows-20261107-dualcore.json\` records an **opt-in experimental** 192 kbps interval with 2,816 new missing USB samples, which does not qualify a production core-1 default. Do not combine these artifacts or replace their original evidence.

## 2. A — CI monitoring, delivery and actual continuation

### 2.1 Present behavior and diagnosis

\`wait_for_ci()\` queries GitHub on a bounded interval, selects runs with matching exact source SHA and \`event=push\`, then marks CI success only when every required workflow has \`status=completed\` and \`conclusion=success\`. Latest run selection currently compares \`databaseId\`; the queried \`attempt\` field is present but is not used as a tie-breaker. The default workflow names are \`Pico firmware build\`, \`USB capture and HID host tests\`, and \`Live runner host regressions\`. The source/branch/event and set of expected workflows must be fixed when a watch is created; never accept a partial matrix or a PR merge ref as an exact push SHA.

The callback path waits for JSONL \`task_started\` records to be balanced by \`task_complete\` or \`turn_aborted\` and for a matching session UUID. This is a **log-lifecycle guard**, not a session-store writer lease. Then it runs \`codex exec resume <exact UUID>\` once with no shell and no approval bypass. The current \`callback-status.json\` records a process return code or exception type, not a verified new Desktop turn. Even a process exit code of zero would need distinct proof of which session actually ran; it cannot prove the original Desktop UI resumed. The observed Desktop conflict defeats this delivery mode for the owner's current session.

The current watcher should remain **record-only for the Desktop-owned session**. A future supported mechanism must be demonstrated explicitly. The native delayed-message trial presently belongs in a state such as \`delivery_accepted_unverified\`, not \`resumed\` or \`completed_autonomously\`. File writing, message acceptance, a prior \`task_complete\`, eventual visibility and a CLI subprocess return code are deliberately separate fields.

### 2.2 Proposed completion architecture (independent state dimensions)

Use one immutable \`watch_id\` per \`(repository, exact SHA, expected workflow set, CI event, candidate revision)\`, plus a one-shot \`delivery_id\`. Persist event records with creation times and read-after-write confirmation in the local watcher output directory. Do not store GitHub tokens, session-log contents, raw task text or private credentials in tracked evidence.

| Dimension | States and allowed transitions | Proof / fallback |
| --- | --- | --- |
| **Monitoring** | \`CREATED → MONITORING → CI_SUCCESS\` or \`CI_NON_SUCCESS\` or \`WATCH_TIMEOUT\` or \`WATCH_ERROR\`. \`CI_SUCCESS\` is terminal for the watched run IDs/attempts only. | Atomic \`completion.json\` containing exact SHA, push event, expected workflows, each run ID, attempt, status, conclusion, completion timestamp and URL. Retain original terminal failures; no reset of a failed attempt. |
| **Delivery** | \`NOT_REQUESTED → REQUESTED → ACCEPTED_UNVERIFIED\`, \`REJECTED\`, \`UNSUPPORTED\` or \`ERROR\`. Record-only leaves \`NOT_REQUESTED\`. | Native acceptance receipt (if documented and observable) or CLI invocation/exit details. An acceptance does **not** transition the continuation dimension. Desktop writer-conflict becomes \`REJECTED\` and disables further CLI attempts for that Desktop session. |
| **Continuation** | \`NOT_OBSERVED → RESUMED_TURN_CONFIRMED\` only with a **new, correlated turn-start observation** on the intended exact session after delivery, without an intervening human message. Otherwise \`NOT_OBSERVED\` or \`UNVERIFIABLE\`. | Evidence must identify the new turn/session, associated \`delivery_id\` or unambiguous event correlation, and timestamps. A prior turn's \`task_complete\`, a file, a displayed notification, accepted delivery, or a CLI response file alone are insufficient. An uninstrumented Desktop cannot satisfy this automatically. |
| **Recovery** | \`NONE → MANUAL_REQUIRED → MANUAL_ACKNOWLEDGED\` upon a human's explicit continuation, or \`NONE → VERIFIED_AUTOMATIC\` **only** after the continuation gate above. | Record whether recovery was manual or automatic; never upgrade manual recovery to automatic success. One-shot delivery failure/timeout goes to manual; no competing writer retries. |

For a supported **CLI-owned** session, a separately verified CLI turn can be recorded as \`CLI_TURN_CONFIRMED\`; this is not evidence of a resumed **Desktop** turn. For a Desktop-owned session, record-only is the supported working mode today. A future Desktop-managed native notification is acceptable only if its public/supported interface and **idle-to-running transition** can both be demonstrated; no assumed Desktop APIs or credential scraping. If the harness cannot expose turn-start evidence, record \`UNVERIFIABLE\` and use a human-approved resume.

**One-shot contract:** the watcher may poll GitHub non-interactively within a bounded timeout. It must not poll model turns, send recurring messages, use \`--last\`, launch concurrent CLI writers, retry active-writer conflicts, or rely on arbitrary sleep as proof of idleness. A later workflow rerun, source change or PR merge commit requires a new watch identity. A failed CI result still gets recorded and delivered for human diagnosis, never promoted to a pass.

### 2.3 Proposed durable record (illustrative schema; not an implemented API)

    {
      "schema": 2,
      "watch_id": "local-generated-id",
      "source": {"repo": "newrecycle/USBPods-Pico2W", "sha": "<full SHA>", "event": "push"},
      "ci": {
        "state": "CI_SUCCESS | CI_NON_SUCCESS | WATCH_TIMEOUT | WATCH_ERROR",
        "expected_workflows": ["<exact names>"],
        "runs": [{"workflow": "<name>", "run_id": 1, "attempt": 1,
                  "status": "completed", "conclusion": "success"}]
      },
      "delivery": {"state": "NOT_REQUESTED | REQUESTED | ACCEPTED_UNVERIFIED | REJECTED | UNSUPPORTED | ERROR",
                   "delivery_id": "<local correlation id>", "transport": "record_only | cli_owned | supported_native",
                   "observed_at": "<UTC time>", "reason": null},
      "continuation": {"state": "NOT_OBSERVED | UNVERIFIABLE | CLI_TURN_CONFIRMED | RESUMED_TURN_CONFIRMED",
                       "session_id": null, "new_turn_id": null, "observed_at": null,
                       "evidence_kind": null},
      "recovery": {"state": "NONE | MANUAL_REQUIRED | MANUAL_ACKNOWLEDGED | VERIFIED_AUTOMATIC",
                   "actor": null, "observed_at": null},
      "hardware_run": false
    }

Do not create or claim a \`new_turn_id\` from a guessed event, receipt ID, reused session UUID or previous \`task_complete\`. Written completion records are deliberately independent of delivery/continuation records. Atomically commit records before delivery, and persist failures even when a subprocess crashes; failure classification must survive restarts.

### 2.4 Mockable host tests for a later implementation

Proposed home: extend \`tests/test_watch_ci.py\`; no GitHub, Desktop process or model call in mocks.

1. Exact SHA/event/required-workflow filtering; missing workflow, skipped/cancelled/failure, timeout, CLI error, and a later rerun with the **same run ID but higher attempt**. Verify immutable attempt-specific completion and no stale pass when starting a *new* watch.
2. Simulate a complete session JSONL, concurrent active writer, partial last line, wrong session UUID, abrupt file disappearance, and the real error classification \`thread-store conflict\`; verify that any Desktop-owned session remains record-only and the writer is never bypassed or retried.
3. Model a native transport that returns \`accepted\` but never produces a fresh turn-start event; verify \`ACCEPTED_UNVERIFIED\` plus \`NOT_OBSERVED\`, then manual fallback. Replay a late human message and verify no retroactive automatic-wake credit.
4. Model successful explicit CLI-owned-session start with a *new* correlated turn ID; assert \`CLI_TURN_CONFIRMED\` not \`RESUMED_TURN_CONFIRMED\` for the owner's Desktop session. Test absent/mismatched correlation, duplicate receipt, stale event, mixed project, and one-shot idempotency.
5. Inject failures between \`completion.json\`, delivery record, process spawning, receipt write and continuation proof. Assert atomic, restart-safe failure records, no duplicate callback and no false successful continuation. Confirm no secrets or session logs are serialized to tracked artifacts.

## 3. B — local runner continuity and evidence admissibility

### 3.1 Present behavior and diagnostic gaps

\`Recorder\` in \`tools/live_test.py\` records UTC and \`monotonic_ns\` for lines, but it does not establish an independent process **lease/heartbeat**, phase-source epoch or callback-progress proof. A serial-reader thread can terminate on read error; \`errors\` are accumulated. \`Link.request\` uses bounded timeouts and collects current responses, but a response is not proof that the playback stimulus was audible.

\`AudioSession\` in \`tools/live_audio.py\` opens raw output and input, invokes tone and capture callbacks, queues PCM and records phase WAV/metrics. It verifies that an input buffer exists and is not all digital silence; that is insufficient to establish a particular **phone-speaker stimulus** or correct acoustic routing. The phase name is mutable while callbacks and the writer are concurrent, so phase transition barriers/epochs should be explicit before comparing metrics. \`run_matrix\` snapshots firmware status/ELD/telemetry at bounded intervals, checks ready state, preserves first observed audio faults and separately checks final firmware capture closure. Its documented external-capture flag correctly does **not** claim exclusive host ownership. A run can still be terminated, lose stimulus between samples, or inherit state left by a prior probe.

\`tools/Run-Test.ps1\` always flashes before running the Python matrix; it is not a safe automatic restart command. The owner’s detached local ad-hoc probe scripts (which supplied heartbeat and tap synchronization in the final comparison) are **not committed**. No implementation or exact heartbeat message schema from those scripts can be inferred. The evidence reports Wi-Fi/session interruptions, but the repository alone cannot determine whether network loss, Desktop ownership or process termination was the causal mechanism.

### 3.2 Proposed runner state machine and ownership boundary

| State | Entry condition | Exit / invalidation |
| --- | --- | --- |
| \`CREATED\` | Unique run ID, immutable candidate SHA/variant/artifact hash, source outputs and planned phases. | Do not acquire devices until identity and local lease verified. |
| \`PREFLIGHT\` | Enumerate actual CDC/audio endpoints; verify \`:info\` SHA and protocol, package hashes, selected playback/input devices, baseline capture ownership, tap acknowledgments and operator stimulus plan. | Any mismatched identity/unknown tap state becomes \`UNVERIFIED\` or \`INVALIDATED\` before measurement; no auto-flash. |
| \`ARMED\` | This runner owns its process/streams and has fresh callbacks/heartbeats, confirmed endpoint readiness and an explicit phase plan. | Start a **new** phase epoch only after both host output and input callbacks and current device diagnostics advance. |
| \`MEASURING\` | Expected 48 kHz output callback frames and selected-format input frames progress; stimuli and diagnostics have matching phase/epoch and fresh liveness evidence. | A missing required stimulus, stale heartbeat, mismatched tap state, changed device identity, process death, lost stream or capture ownership uncertainty invalidates that phase immediately. |
| \`INVALIDATED\` | Save first fault with exact reason and all obtainable contemporaneous snapshots. Do not use later healthy counters to validate this interval. | \`FIRST_FAULT_SEALED\` after durable write, or \`INCOMPLETE_EVIDENCE\` if interrupted before a full snapshot. Both remain non-pass. |
| \`CLEANUP_OWNED\` | After first fault is sealed, close **only** streams/handles/settings known to be owned and safely restorable by this process. | Report attempted/confirmed/failed cleanup independently; never infer physical recovery from cleanup. |
| \`MANUAL_RECOVERY_REQUIRED\` | Process lost, ownership ambiguous, tap baseline unknown, or user must restart or restore a device/session. | Human confirms recovery/ownership; use a **new run ID** and new evidence epochs. No automatic reconnect, K refresh, redial, reflash or retry as a way to obscure a failure. |
| \`ACCEPTED\` | Every required phase met liveness, stimulus and diagnostics gates. | Result is **phase-scoped**; manual hearing remains a separate observation. A completed process/ZIP is not itself an accepted phase. |

Maintain separate \`run_id\`, \`runner_pid + process_start\`, \`source_sha\`, \`device_identity\`, \`phase_id\`, \`phase_epoch\`, \`stream_generation\`, \`tap_state\`, \`stimulus_state\`, \`capture_owner_evidence\`, \`last_heartbeat\` and \`first_fault_id\`. A launcher-held local exclusive lease prevents **another local runner** from concurrently using the same known port/output directory. This is not proof of exclusivity against arbitrary Windows shared-mode microphone clients.

### 3.3 Liveness and stimulus contract

- **Heartbeat:** propose a 1-second local, non-model heartbeat with monotonically increasing sequence, process birth identity, current phase/epoch, last CDC response and input/output callback-progress counters. A 5-second or three-interval stale window is a **testable initial policy**, not an established hardware threshold. Check current time against same-host monotonic time; also record UTC for correlation. Across a reboot or PID reuse require a new process identity and run ID. A stale, missing, reordered or wrong-process heartbeat invalidates the phase; a detached process being launched is not evidence that it remained alive.
- **Host output stimulus:** count callback invocations, frames, planned channel (left/right), expected tone/nonzero output samples, callback status/underflow and elapsed phase time. Require strictly increasing progress in the **same** phase; a configured output handle or a static WAV does not establish ongoing sound.
- **Microphone/phone stimulus:** distinguish \`PLANNED\`, \`OPERATOR_CONFIRMED\`, \`HOST_INPUT_OBSERVED\` and \`UNVERIFIED\`. Require fresh input callback frames/status plus phase-matched energy/decoded-USB progression as applicable, **and** a contemporaneous operator statement that the phone speaker actually played near the AirPods for any claimed physical stimulus. PCM energy cannot identify its acoustic source; absence of input energy with no confirmed stimulus is \`INVALID/UNVERIFIED\`, not a mic defect. Confirmed stimulus plus sustained silence can be a legitimate negative observation. Do not treat a captured signal alone as proof of correct pitch, routing or listening.
- **Phase match:** bracket each interval by current \`status\`, \`eldstatus\`, \`micstats\`, \`usbcapture\` and tap diagnostics where available. Match to host phase epoch, time range, microphone generation, selected/applied profile and current live connection. Reject stale/pre-transition windows, old maximum counters and data arriving after the interval; use interval **deltas** for wrapping counters. Gaps in diagnostics are not filled by interpolation or assumed steady playback.
- **Tap state:** \`U\` is an inherited **toggle**, not an idempotent \`set on\` command. Do not assume OFF on restart. Establish actual current state from a supported acknowledgment/diagnostic sequence and correlate it with this run/phase; when the state is unknown, no toggle guess and no accepted tap comparison. After a confirmed toggle, wait for the matching ON/OFF acknowledgment and for phase-matched \`[tap]\`/\`[eld-pcm]\` windows before accepting diagnostics. Record original state and restore only if actually known/owned, with separate cleanup evidence. The repository does not expose the unavailable ad-hoc script's exact acknowledgment logic; that detail needs a Windows validation fixture before production adoption.
- **Capture ownership:** record whether capture was active **before** opening, exact locally owned input stream/handle lifecycle, input callback sequence, any stream/process restart and firmware capture=0/1. A shared Windows endpoint can have external users; never turn \`capture=0\` or a closed local stream into an exclusive-ownership claim. If the runner dies/restarts, changes devices or loses its input callback while USB still reports capture, label ownership \`UNKNOWN/EXTERNAL_POSSIBLE\` and invalidate the measurement. A second runner cannot claim the first runner's stream/lease.

### 3.4 First-fault journal and manual recovery

Before any auto-cleanup, append a bounded local fault event with \`run_id\`, phase epoch, host monotonic/UTC times, process/stream identity, reason code (for example \`STALE_HEARTBEAT\`, \`STIMULUS_UNVERIFIED\`, \`TAP_STATE_MISMATCH\`, \`CAPTURE_OWNER_LOST\`), latest CDC/ELD/PCM diagnostic windows, callback counts and the **raw operator wording**. Atomically write a \`first-fault.json\` (or equivalent journal with write-through/flush) once and never overwrite it; add later cleanup events separately. If the runner is killed before snapshots arrive, preserve the failure event and mark missing evidence instead of manufacturing a complete snapshot. An external supervisor may notice an abrupt exit and record that fact, but must not silently assume exclusive device ownership or perform recovery actions.

Only the same still-running owner process may close its tracked input/output handles or revert confirmed settings when safe. Unexpected interruption should move to **manual recovery required**, with explicit instructions to inspect PID/port/device and recording before manually stopping a stale process. Do not suppress the first fault by launching another runner, changing the tap, reconnecting AirPods, refreshing K or reflashing. Successful cleanup is a distinct field, never a measurement pass.

### 3.5 Mockable host-only regressions to implement later

Suggested coverage in \`tests/test_live_runner.py\`, \`tests/test_live_matrix.py\`, \`tests/test_live_cli_e2e.py\`, and \`tests/test_start_script.ps1\`, with one dedicated continuity fixture if useful:

1. Inject a fake monotonic clock, heartbeat writer and process identity; test live/reordered/stale/wrong-epoch heartbeats, PID reuse, process death, wall-clock adjustment and a restarted runner that must obtain a new run ID and stream lease. No firmware/codec compilation locally.
2. Feed actual \`AudioSession\` callbacks through fake sounddevice streams. Distinguish missing output callbacks, lost microphone callbacks, callback underflows, confirmed versus absent phone stimulus, phase-switch races, stale decoded/USB snapshots and a recovered but **not continuous** stream. Assert no accepted interval on lost stimulus.
3. Mock \`U\` toggle and acknowledgment ordering: initially ON, initially OFF, lost acknowledgment, duplicated/delayed ACK, interrupted toggle, reconnect with persisted state and restoration only after state is established. Do not change firmware to implement a hypothetical idempotent command.
4. Simulate an external shared microphone client, local stream close while firmware capture stays ON, local crash leaving capture active, and another local runner with a conflicting lease. Assert \`runner_exclusive_ownership_verified=false\` unless a genuinely supported host capability proves otherwise; reject reused old ownership state.
5. Cause a device/serial failure in \`Recorder\` while another thread reports healthy samples. Verify first-fault preservation before settings cleanup; fail closed on incomplete snapshots, lost ZIP writer or killed supervisor. Ensure an explicit manual restart gets a new run/epoch and does not change the failed original verdict.
6. Exercise **the actual** \`Run-Test.ps1\` with temporary fake \`flash_candidate.py\`/\`live_test.py\` (existing Windows fixture pattern). Assert no automatic flash or rerun on recovery, correct failure exit codes, no ambient COM4 assumption, and preservation of logs from the first failure. A future explicit no-flash diagnostic mode must still verify matching \`:info\` and package identities.
7. Include negative controls for a perfect synthetic sine tone but no human-confirmed phone speaker, a valid \`[eld-pcm]\` line from a **prior** phase and a native message accepted without Desktop wake-up. Mocks must report \`SIMULATED\` / \`UNVERIFIED\`, never \`hardware_run=true\` or automatic continuation.

All pure watcher/runner Python tests may run locally. Firmware, codec, SDK and target-binary tests stay exclusively in GitHub Actions, as required by the handoff. A mocked callback or native follow-up tool cannot prove an actual Desktop turn started; a fake input stream cannot prove audible stimulus or ear-specific playback.

## 4. Precise Windows validation procedure (future, not executed here)

Perform two separately timestamped protocols. Keep raw captures and any user or Bluetooth identifiers **local**, outside the repository. Share only sanitized metrics/source hashes and observation labels.

### 4.1 CI completion and Desktop wake-up

1. On the owner's Windows host, use a new **dedicated** worktree and inspect \`git status\`; verify the exact current candidate SHA with \`git rev-parse HEAD\` and its push workflow triggers. Confirm \`gh auth status\` without copying tokens. Record the expected workflow names, event=push and source SHA before the watcher starts.
2. Start \`python tools/watch_ci.py --sha <full-current-SHA> --output <new-local-directory>\` **without \`--resume-session\`**, from a terminal independent of Desktop. Observe the watcher PID and its final \`completion.json\`. Verify all expected runs, run IDs/attempts, status, conclusion, source SHA and URLs. A failure, missing workflow, timeout or watcher error must remain negative. This is a completed **record-only** test.
3. Confirm the Desktop-owned conversation is unaffected. **Do not retry** \`codex exec resume\` against the known persistent Desktop writer. If CLI callback behavior needs a test, use a separately created disposable **CLI-owned** session with a verified exact UUID and supported CLI interface, never \`--last\`, and record its result as CLI-only.
4. Only if the local product/harness documents a **supported** native managed-task completion mechanism, test it with a new correlation ID. Start monitoring, end/yield the original turn, avoid all human messages and UI interactions until its bounded observation window completes; retain source-side task/notification receipts and whether the original conversation emitted a new correlated turn-start. An \`accepted\` delivery without a new turn is **not a pass**. If no supported turn-start observation exists, report \`UNVERIFIABLE\`.
5. Finally, manually post the completion reference into the original chat, confirm the corresponding CI record is still the intended SHA, and mark \`MANUAL_ACKNOWLEDGED\`. Do not reclassify this human-initiated transition as autonomous continuation.

### 4.2 Live runner continuity and acoustic gates

1. Obtain an authorized, exact-source GitHub Actions candidate with verified run/variant/UF2/package hashes and memory gates. \`1979ae6...\` remains **historical physical evidence**, not automatic approval for any new source or hardware claim. Back up the working UF2. Enumerate current CDC and audio endpoints; do not hardcode COM4 because it was merely observed in the earlier run.
2. Record the launcher and runner process identities, one-run output directory, package SHA, flashed \`:info\` SHA/protocol and baseline local/external capture. The existing \`Run-Test.ps1\` **flashes first**; do not use it just to recover or resume a disrupted probe. For already authorized flashed hardware, invoke the reviewed no-flash diagnostic path only after \`:info\` and package identity are verified. Avoid default 600-second soak and unnecessary full matrix.
3. Begin with a short continuously open playback/input session. Establish a fresh heartbeat and incrementing input/output callback counts. Inspect actual \`U\` tap acknowledgments: record baseline state, toggle deliberately only if required and confirm returned state. Do not accept an assumed-OFF startup.
4. Use one operator-confirmed phone **speaker** clip (not routed to Bluetooth) near the AirPods during a labeled mic window. Capture host frames, callback status, current firmware mic/USB counters, and operator verbatim statement that the clip actually played. Capture one short left-only and one short right-only host tone window with corresponding phase-matched post-gain firmware diagnostics. Require current heartbeat and stream generation throughout. A missing clip observation or disconnected stimulus process makes that window \`UNVERIFIED\`, not a mic success/failure.
5. In a **separate short controlled interruption experiment**, first verify the local probe's ownership and safety, then cause a bounded network interruption. Check whether the detached local process actually survives by PID **and birth time**, heartbeat sequence and callback progress; do not infer death from missing Desktop messages alone. Separately test forced runner termination with a simulated device or a preapproved non-destructive short session, capturing the first-fault record. The new runner must not inherit tap assumptions, stream ownership or old accepted intervals.
6. Trigger or simulate a tap-ACK mismatch and an external microphone client in separate attempts. Verify fail-closed phase invalidation, original state preservation, no automatic AirPods refresh/reconnect, and no accidental flash by the launcher. On the real device, treat any unexpected capture=1 after local close as ownership-uncertain until investigated.
7. Confirm first-fault event timestamp and counters precede any cleanup; retain failed phase and collector errors even if subsequent heartbeat/diagnostics recover. Stop/restore only owned state, record each cleanup action/result and require operator approval for re-run. Archive the result ZIP locally, publish sanitized run IDs/checksums and explicit \`PASS\`, \`FAIL\`, \`SKIP\` or \`UNVERIFIED\` **per phase**. Do not claim a whole-session zero-loss result from the short successful windows; do not repeat the already completed ten-minute soak without a new specific question.

### 4.3 Acceptance matrix and stopping rules

| Question | Required evidence | Stop/fallback if absent |
| --- | --- | --- |
| CI monitor worked? | Exactly matched complete push workflow set and atomic terminal record | \`WATCH_TIMEOUT/ERROR\` or \`CI_NON_SUCCESS\`; investigate once, retain record |
| Delivery was accepted? | Genuine supported transport receipt tied to one delivery ID | \`NOT_REQUESTED/REJECTED/UNSUPPORTED\`; record-only/manual |
| Original Desktop autonomously resumed? | New **correlated Desktop turn** starts after delivery without a human stimulus | \`NOT_OBSERVED/UNVERIFIABLE\` → manual; CLI return code, message visibility and \`task_complete\` do not qualify |
| Runner was continuously live? | Fresh same-process heartbeats, live input/output callback progress, unchanged device/phase epoch | Invalidate phase; seal first fault |
| Actual stimulus occurred? | Phase-matched host signal **and** contemporaneous operator confirmation of phone speaker/audible tone | \`UNVERIFIED\`, not an inferred mic defect |
| Tap and capture ownership known? | Synchronized ACK, known baseline, tracked local stream and fresh firmware status; external user distinction retained | \`INVALIDATED\` and manual ownership check |
| Recovery was safe? | First fault sealed, explicit owned-handle cleanup record, separate manual approval for new run | Never rewrite failed evidence as pass; no automatic refresh, reconnect or flash |

## 5. Disposition and boundaries

**Current supported architecture:** an exact-source, local record-only CI watcher followed by a manual handoff in the existing Desktop conversation; a short local runner whose observations are accepted only with current liveness/stimulus/tap/phase provenance. A verified and separately owned CLI session may receive a CLI-only continuation, but the current Desktop-owned thread must not be resumed competitively.

**Not established:** an automatic Desktop idle-to-running callback, the cause of the local Wi-Fi/session process interruptions, access to the owner's ad-hoc probes, exclusive Windows microphone ownership, a physical pass for the pinned documentation commit, full compressed-audio correctness or any new acoustic result.

**Proposed edit scope only, pending review:** watcher/runner/launcher files, their host tests and docs. No firmware, AACP, playback, codec, microphone clock, approval policy, Windows credential stores, GitHub workflow polling model turns or other workers' branches are changed by this diagnosis.
