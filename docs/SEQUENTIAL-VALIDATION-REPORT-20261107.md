# Sequential USBPods validation / reconciliation report — 2026-11-07

**Purpose:** Re-audit the currently active follow-up branch and every extant PR/worker commit, reconcile the independently authored Markdown, and move every safely reproducible claim into production-body GitHub Actions checks. This report distinguishes **source/CI verification** from the **earlier user's physical measurements**. No hardware or raw local archive was accessed.

**Frozen base**: work/local-windows-followup-20261107 @ 175ace9f09554881b554e8226544e78ce10d06a1. **Independent branch**: audit/sequential-validation-20261107-gpt6, created directly at that exact SHA. Main at discovery: 018685157ab8c5dedc66008e2e54ae3a38994e25 (3 commits behind the frozen development branch). Do not use the current-validation.json historical record as a current candidate. Initial plan committed *before* implementation: [SEQUENTIAL-VALIDATION-PLAN-20261107.md](SEQUENTIAL-VALIDATION-PLAN-20261107.md).

## Sequential source/PR review and retained evidence

| Order | Source SHA / branch | Audited changes | Disposition |
| --- | --- | --- | --- |
| 0 | Main 0186851, merge #3 263de0c (includes #4 e2229dc) | Previously integrated FDK, AACP, USB, playback/restart and runner audits | Ancestor of development branch, not replayed or double-merged; CI is build/simulation only |
| 1 | e9f548259cfc402db88a1e2ea7ca0a56ee99844a | Windows duplex diagnostics, CI watcher, codec tap, counters | Physical device did flash but AVDTP media never configured at 256, before steady test. Sanitized setup record and CI 42417493025/14/56 preserved |
| 2 | 1979ae6be1c2daf9e1db8024763504d4061c4588 | Move AVDTP accepted response-label retirement *before* synchronous discovery/capability callback | Physically flashed source for both single and experimental dual-core builds. CI 42419581145/084/191 passed. The production SDK reentry regression executes all 15 label positions and asserts the prior patch fails; fix is preserved |
| 3 | 175ace9f09554881b554e8226544e78ce10d06a1 | Follow-up documentation, single/dual physical findings and authorization chronology; **no firmware change from 1979ae6** | Firmware Actions 42423214285, USB 42423214239, runner 42423214310 passed. **175ace9 itself was not flashed** |
| 4 | 7a06d4ab97f16f3db318186194a8612ef100f069, audit/capture-lifecycle-175ace9-gpt6-20261107 | One Markdown diagnosis (blob 8cd14cd483c9b7afe293ad8656b68b01b47c999f) | Copied *verbatim* in own commit ec4c7916; no worker code was adopted or invented |
| 5 | cc27598f00112f62337e1dbd5ed8cebb06125314, audit/mic-close-175ace9-20261107 | One Markdown diagnosis (blob 2fa38bc99fc8264a3860d7922e733fe82b07ffc8) | Copied *verbatim* in own commit 3719315c |
| 6 | PR #5, b7017314 then db4b82ca54bf619f570a5897ad5db535d1f2a390, audit/runner-completion-175ace9 | Two docs-only commits (second fixes Markdown syntax). Final document blob 1b1809e065ba452d9592e203e4117e0128edf5c2 | Final document copied *verbatim* in own commit e57ea8e; neither GitHub watcher status nor callback acceptance can prove Desktop auto-resume |
| 7 | PR #6, 9e25083aa86a5e80991bfe05db35d6821edeb5e6, audit/core1-service-175ace9 | One Markdown diagnosis (blob f75345694231b8ab3d78ffc16a9ae95a7d88bb0a) | Copied *verbatim* in own commit fb61cd0; zero-PCM packet and clock accounting are supported but a physical root cause is **not** |

At discovery **PR #5 and PR #6 were draft/open**. Their docs are now preserved on the reconciliation branch; do not claim PR merges merely because content was copied. The two additional unmerged diagnosis branches are likewise retained until reviewed integration and deletion. The exact worker commits remain discoverable by SHA after branch deletion.

## Physical evidence that the audit does not change

- Last **physically tested firmware code** is 1979ae6be1c2daf9e1db8024763504d4061c4588, not the more recent evidence commit. Single-core, Lite rpi0065 AAC-ELD: [sanitized source and artifacts](evidence/local-windows-20261107-live.json), firmware Actions 42419581145, artifact 13592873692. Four ~20-second *steady* 256/192/game-standard/game-latency intervals had zero new AU drops and zero USB missing samples, with active jitter 150/150/90/60. The 192 profile produced **1,412 PCM-full work exits** but **0 AU drop**. This is backpressure, not automatically failure. Whole-session lifetime AU drops reached **248**, including prior startup/interrupted periods; no claim of all-session zero loss. No 320 test because peer ceiling was 256.
- User-reported **left-ear silence when microphone closed** persists with one open playback endpoint, despite correct post-gain pre-encoder left PCM peak windows. Reopen mic restored left; explicit K refresh and saved-bond reconnect separately restored left with capture closed. Actual AAC-ELD compressed-content/peer rendering at failed phase was **not captured or verified**, so no root cause is proven. This is a historical physical FAIL, not evidence that an offline channel test repaired it.
- Explicit **experimental** core-1 mic decoding, same code SHA, differently hashed artifact 13592997637: 256 interval passed, 192 **failed** with 44 new underrun USB packets, +2,816 missing samples and 0 new AU drops. Each of the 44 was a fully missing 64-sample PCM packet (2,816/44); no timestamps show if contiguous. Dual-core game/close/power-cycle/soak were not measured. Default single-core was restored. Do not enable core1 default or count its 192 result as PASS.
- Earlier completed ~600.539-second soak remains historical duration **completed**, strict zero-loss **failed**. No new soak is required for this audit.
- Unsupported/unmeasured: ANC-Off capabilities, 320 beyond peer ceiling, RF/drift, physical pitch, Windows OS HID reads vs firmware report submission, actual stem gesture type (AVRCP multi-press attempts appeared PLAY), external microphone app ownership, autonomous Desktop wake-up. Do not convert these into simulated passes or physical failures.

## Claim-by-claim online reproduction and fixes

**Capture lifecycle and 248 lifetime overflows.** Previous deterministic tests already exercised production USB mount/alt/suspend/close and actual AACP PCM stale, errors, generation changes and backpressure. New [test_mic_service_schedules.c](../tests/test_mic_service_schedules.c) *links actual production* aacp_mic_audio.c, mic_clock.c and usb_capture_lifecycle.c with a small deterministic decoder stub. It runs separate processes for on-time four-AU/30ms arrival, a producer gap, a delayed decoder worker, a long delayed USB consumer, and a full stale PCM ring with a 64-sample partial-frame offset across close/reopen. Uses original 32 AU slots, 16 PCM frames, 480 samples/AU, 4800-sample priming and 63/64/65 samples/USB callback. Checks correct per-generation fresh PCM, actual USB expected vs delivered + padding, no silent AU-overflow cover-up, and explicit full-PCM backpressure versus genuine overflow. An intentionally incorrect zero-USB-loss assertion **must abort** on the delayed worker trace; CI checks the precise assertion text to avoid counting compilation failure as a negative control. **What this proves:** both producer timing and worker delay *can* produce zero-AU-overflow USB loss in synthetic schedules; it does not establish which one caused real core1 192 underflows or assign the 248 prior losses to specific epochs.

**Microphone-close left-channel path.** Existing tests/test_eld_pcm_tap.py validates actual post-gain pre-FDK PCM tap, capture generation labels, wrap and disabled reset; test_mic_recovery_integration.py executes the production USB capture/AACP/ELD ownership paths and manual-vs-automatic recovery contracts. Expanded [test_pcm_packet_path.py](../tests/test_pcm_packet_path.py) to run real AAC-ELD FDK encode/decode with stereo, left-only and right-only synthetic PCM at each existing profile and gain. The decoded signal must be nonzero on the intended channel and below a bounded leakage ratio on the silent channel, with Apple AU framing, sequence wrap, actual gain and payload MTU checked; a deliberately swapped decoded L/R sample stream must fail an assertion. **What it proves:** the synthetic sender pipeline can preserve independent channels; it cannot demonstrate that closing a real AirPods microphone leaves the peer decoding both channels. No automatic refresh, codec clock or mic transport behavior changed.

**CI watcher / runner evidence integrity.** In production tools/watch_ci.py, selection now orders by GitHub run database ID **and attempt**: a completed earlier attempt cannot approve a newer in-progress retry under the same run ID. session_is_idle now fails closed on an empty/partial log, orphan task completion or duplicate start. --resume-session requires an explicit --session-owner cli; the default **Desktop** ownership is record-only and cannot be resumed with the unsupported CLI writer path. A successful CLI subprocess exit is recorded as **cli_process_exited_unverified**, with desktop_turn_observed=false and fresh_turn_observed=false, never advertised as autonomous Desktop continuation. tests/test_watch_ci.py uses production functions and mock run attempts/log states, including an explicit Desktop ownership rejection and confirmation that no subprocess spawned. This addresses concrete false-positive states; it does not implement a native Desktop notification or an agent heartbeat/lease on the owner's machine.

**Source and package identity.** Existing production runner, manifest, UF2 and 32-bit codec-heap positive/negative tests remain intact. The firmware workflow still builds the four existing Lite variants, including opt-in core1, and retains the positive build_verified/memory.runtime_allocation_verified gates. The experimental core1 artifact remains excluded from automatic test packaging; no global flash-safety bypass. The new production schedule and FDK channel negative controls run inside existing firmware Actions jobs **without adding another target variant or workflow**. Existing Linux CLI, PowerShell launcher, USB/HID and typed file-hash tests remain in GitHub Actions.

**Tests and gaps NOT falsely claimed:** No new physical mic-close, RF, peer data, Desktop callback, acoustics, sample clock, stack high-water or flash lockout timing was collected; the new C tests use deterministic clocks and mock FDK for queue behavior; real FDK is used separately for stereo decoding. The actual RP2350 multicore timing remains unavailable from hosted CI.

## Runner/CI validation commands (CI only for firmware/codec)

Production schedule regression (existing Pico firmware build, aaceld default mic row only):
~~~bash
cc -std=c11 -O1 -Wall -Wextra -Werror -fsanitize=address,undefined \
 -DUSBPODS_MIC_DECODE=1 -I tests/mic_mocks -I src/btstack -I src/tinyusb \
 tests/test_mic_service_schedules.c src/btstack/aacp_mic_audio.c \
 src/btstack/mic_clock.c src/tinyusb/usb_capture_lifecycle.c -o /tmp/test-mic-service
for case in on-time producer-gap worker-delay consumer-hold capture-epoch; do
 /tmp/test-mic-service "$case"
done
# CI must reject the deliberately false zero-loss negative control, checking
# that the expected assertion, rather than compilation failure, caused failure.
~~~

Real FDK stereo and deliberate-channel-swap negative control are added to the existing real FDK workflow step. CI also executes 32-bit FDK allocator/heap checks, complete Pico target firmware builds and signed-off candidate manifest packaging, plus the Linux/Windows runner and USB/HID jobs. **Do not run firmware/native FDK builds locally** under the current handoff policy.

Read current run artifacts by exact SHA, not merely workflow display name. A green CI workflow establishes only code/build/simulation acceptance. Report new successful workflow IDs and artifact hashes without representing the new unflashed candidate as physically tested.

## Remaining true physical-only acceptance, minimized

After a reviewed candidate and valid package hash/identity are available on the owner's Windows laptop, *if needed* test only:

1. **Acoustic mic-close isolation**: with one continuously open output endpoint, short left-only and right-only tone windows while mic open → mic closed and final firmware capture=0 → reopened. Keep current heartbeats, phase-tagged post-gain tap, applied profile and first-fault snapshots. Record the operator's exact observations and whether OS mic was already owned elsewhere; do not assume SDK START sent means AU received, decoded or acoustically correct. If failed, at most one explicit manual K as a labelled control; do not auto-reconnect.
2. **Opt-in core1 headroom**: **only if a core1 fix/telemetry patch is proposed and separately authorized**, short same-host 256→192 comparison of source/variant/timestamped first-underrun counters and stack/flash safety; stop at strict loss. No default core1 or substitute 600s soak.
3. Explicit HID/stem/ANC, power-cycle bond and RF/pitch are separately optional/unsupported, not blocking simulated CI success and not to be silently marked PASS.

No repeat of the already completed ten-minute soak. No local worktree, COM, private audio or secrets were available to this cloud worker. Raw archives stay on owner's machine.

## Conflict and cleanup boundaries

- Review the normal and experimental mic code under any **newer** work merged after the frozen 175ace9 base. Production PCM queues/clock/FDK/SDK were not changed here; only test harnesses and watcher CI semantics. Exact source SHA may differ due to documentation or tests; never reuse old UF2 hashes.
- Four worker diagnoses were preserved as their *original* blobs, not blindly accepted as final causal findings. PR #5 and #6 retain distinct historical source commit identities; closing them requires accepted integration, not their CI pass alone.
- GitHub branch deletion is not provided by this cloud worker's current GitHub connector. [Cleanup-Reconciled-Workers.ps1](../tools/Cleanup-Reconciled-Workers.ps1) implements an opt-in, safe, blob-verified cleanup on the owner's authenticated git checkout **after** accepted branch integration/PR closure; it refuses moved refs/dirty worktrees and never touches main or the active follow-up branch. The cloud worker cannot access or remove local worktrees. Do not claim branch deletion or local worktree removal until observed.
- The next **online-only independent agent prompt** is [ONLINE-ONLY-SUBAGENT-FOLLOWUP-20261107.md](ONLINE-ONLY-SUBAGENT-FOLLOWUP-20261107.md), targeting the remaining hypotheses and safely implementable source-level diagnostics/tests.
