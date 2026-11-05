# Independent USBPods validation audit: findings and integration handoff

**Source:** newrecycle/USBPods-Pico2W, immutable ancestor 18be74cfe99f2584bcf26a0c0f0571c75a7f7bec. **Isolation:** work/local-windows-evidence-audit-20261104-gpt6 created directly from that SHA. No other branches merged. No firmware codec/core/FDK code changed.

Read [the initial, pre-edit evidence ledger and plan](VALIDATION-AUDIT-INITIAL-20261104.md) first. This final report documents results and integrator instructions. The cloud worker had **no hardware, Windows laptop, COM port, AirPods, local raw archives, Bluetooth keys or acoustic access**. No firmware was flashed.

## Evidence ledger (do not mix proof levels)

| Claim | Exact source | Evidence and limit |
| --- | --- | --- |
| Original candidate target, native host FDK, 32-bit heap, package | 18be74cfe99f2584bcf26a0c0f0571c75a7f7bec | [Pico Actions 41793575782](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41793575782): Windows launcher and all three target jobs success; AACELD build did native FDK and 32-bit codec-heap audit, UF2 verification and package. **Build/link/simulation, not hardware** |
| Original candidate host tests | 18be74cfe99f2584bcf26a0c0f0571c75a7f7bec | [Host Actions 41793575886](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41793575886): compiled CLI parser, stateful audio and Windows native PowerShell fixtures success. **Simulated host, not hardware** |
| Last flashed firmware | 880dc318072f191f1440d3f0b262d83e32729b59 | [Local Windows findings](LOCAL-WINDOWS-20261104.md), [sanitized evidence](evidence/local-windows-20261104.json); previous CI 41786883085, original UF2 and package hashes/COM4 recorded. **Only this revision was physically tested** |
| Mic close/open left-ear silence | 880dc318... | Reported physical: left tone plays when mic open, silent with mic closed, plays after reopening; right tone remains right-only. Laptop MaxxAudioPro mixing was corrected but silence persists. Earlier PC tests used **no** enhancements |
| Explicit failed refresh | 880dc318... | Manually requested K timed out WAIT_START, stage 4, rc 4; firmware **locally terminated ACL, reason 0x16**. Do not confuse with historical spontaneous remote 30-second termination |
| Saved-bond reuse | 880dc318... manual; 18be74c runner | Physical manual savedconnect reused bond with no scan/new pairing, followed by recovered left sound while mic remained closed. Runner saved-mode behavior has simulation contracts, **no candidate physical pass or power-cycle proof** |
| Latest physical bitrate sample | 880dc318... | 256kbps PASS; 192kbps FAIL, +186 mic AU drops and +95,168 USB missing samples. Neither game mode was measured; no firmware-only PC-vs-laptop regression inference |
| Ten-minute duplex soak | 2911a824d5a44d126234d4f63545a37051d71d5f | **Already completed**, 600.539 seconds, user reported clear audio, strict zero-loss FAIL (7 AU drops, 14,656 missing USB samples). **Do not prescribe a repeat** |
| Earlier validation snapshot | 7de213042d82367401aedef3a0e9a864f9ab6773 | docs/evidence/current-validation.json: historical source-specific CI 41746700880 and USB-host CI 41746700738; not the current candidate state |
| Hardware authorization | docs/validation-status.json references 8b89d42 | Permission to package/test, not a physical pass. Actual candidate packager still requires build_verified and positive 32-bit codec allocation proof |
| Unknown/unmeasured | none for 18be74c hardware | AirPods ANC-Off AllowOff capability, RF behavior, host clock drift, pitch, game modes latest run, true AVRCP gesture type, raw HID access on some Windows systems: **UNVERIFIED/SKIP**, not blanket pass/fail |

## Reproduced defects and scoped fixes

1. **Free-text negative observations were hidden.** The actual matrix only recognized literal yes/no/silent/both/wrong-side; phrases such as “left ear is silent” or “only the right bud played” were recorded as UNVERIFIED. Playback/pitch prompts also ignored negative prose, stem was unconditionally UNVERIFIED. Added conservative production observation_status classifier in tools/live_audio.py; wired it through tools/live_test.py and matrix channel prompts. Original wording is preserved in test detail. Explicit failures are FAIL, ambiguous statements remain UNVERIFIED; no AVRCP gesture type is guessed from PLAY timing. Stateful real matrix and classifier fixtures reproduce.
2. **External initial capture prevented observation of final closure.** Previous capture_close_state immediately returned SKIP when capture was already active before runner start. It now independently polls final firmware status.capture; records capture_active_before_runner, firmware_capture_closed, runner_exclusive_ownership_verified=false. If final closure confirmed, report PASS even with external initial activity, but NEVER claim exclusive ownership; if a third-party app still holds capture, report SKIP rather than blaming firmware. Tested with production AudioSession, capture lasting/releasing and bounded status sequence.
3. **A startup retry could be treated as a clean steady interval.** Duplex-readiness now waits two continuous seconds with TX progression and notes recovery_observed. Delayed WAIT_START during fixed settle is surfaced in result metadata. Steady measurement watches intermediate readiness, pending recovery, and retry counter changes as well as start/end decoded and USB metrics. A recovered startup may begin a **new** steady window, explicitly marked; a retry within that steady window fails instead of being marked clean. The finite sampling cadence is a residual blind spot.
4. **First transient failure risked being replaced by cleanup state.** The steady path captures audio-failure-state.json on first observed fault before cleanup, and preserves that file on later failures. A test exercises production preserve_audio_failure with deliberately different cleanup state.
5. **Conflicting identities could initiate flashing.** PowerShell Run-Test.ps1 rejects both -TargetName and -TargetMac supplied together before invoking flash_candidate. The **actual Windows launcher** fixture proves no flash helper was invoked.
6. **Compiler-backed fixture exposed import-time dependency.** tools/live_test.py now imports the observation classifier inside main() to permit production module injection in tests/test_live_cli_e2e.py. That test compiles and uses real C control_command and eld_profile parsers, then drives production Python audio/runner against simulated USB/CDC, not real hardware.
7. **Build/package gate preserved.** Production package_live_test.package must see build_verified=true, positive memory.runtime_allocation_verified from the actual 32-bit heap audit, matching ELF-derived BIN/UF2 hashes, UF2 payload and embedded source SHA. flash_candidate checks board/protocol/returning SHA and refuses ambiguous device selection; verify_manifest checks supplied UF2 and declared runner-file SHA256s. Negative tests now exercise actual package and manifest functions with changed bytes. Note: consistency with the package's own manifest is **not a digital signature** against an actor that can alter every bundle file and manifest.

8. **A rejected preflight could falsely claim a physical run.** Previously the runner initialized summary.hardware_run=true before reading the manifest or checking firmware. It now starts with hardware_run=false and hardware_phase=not_started, changes to firmware_identity_verified only after a matching CDC identity is obtained, then separately records targeted-connection and audio-attempt phases. The missing-manifest failure regression asserts no hardware run is reported. Hardware-related summaries created by mocked CLI fixtures must still be treated as simulated by their harness; only an actual host/device visit yields physical evidence.

**Mic evidence:** locally submitted START (mic_started), *framed received AU* (mic_audio_seen when present), successfully decoded frames, delivered USB PCM, and correct acoustic pitch are distinct. None establishes the others by itself.

**HID evidence:** Windows may prevent raw HID reads of OS-owned media interfaces. A CDC firmware HID “sent” log only establishes submitted report, not host application actuation. All observed AVRCP multi-press attempts reported PLAY; neither timing nor PLAY proves single/double/triple stem semantics.

## Tests and reproduction commands

Use an isolated clean checkout of this branch (or an integrator worktree); do not reset existing uncommitted work.

~~~bash
python3 tests/test_validation_audit.py
python3 tests/test_live_runner.py
python3 tests/test_live_matrix.py
python3 tests/test_flash_candidate.py
python3 tests/test_verify_uf2.py
python3 tests/test_live_cli_e2e.py --output build-live-runner-cli
~~~

The CLI test compiles src/control_command.c and src/btstack/eld_profile.c and exercises production live_test.main / live_audio.run_matrix with stateful serial, HID, clock and WASAPI mocks. The AudioSession matrix drives actual Python audio callbacks/WAV writer. The Windows test tests/start_script.ps1 invokes **actual** Run-Test.ps1 with simulated Python/flash entry points; no actual COM, USB, picotool flash or AirPods is accessed. Firmware GitHub workflow additionally exercises native FDK and 32-bit allocation audit before candidate packaging. Both workflows include the new validation audit suite. Always record exact head SHA of the corresponding CI run. A partial suite or passed build must never be labeled physical acceptance.

## Future integration checklist

1. In an isolated worktree, inspect git status. Fetch only this branch. Verify the exact pinned ancestor, and review the entire scoped diff, with no other workers' commits mixed in:

   ~~~bash
   git fetch origin work/local-windows-evidence-audit-20261104-gpt6
   git merge-base --is-ancestor 18be74cfe99f2584bcf26a0c0f0571c75a7f7bec FETCH_HEAD
   git diff --name-status 18be74cfe99f2584bcf26a0c0f0571c75a7f7bec FETCH_HEAD
   ~~~

   Integrate only reviewed runner/test/docs/workflow changes through an isolated worktree or cherry-picks. Do **not** merge into main or another worker branch automatically.
2. Reconcile potential overlapping edits in tools/live_audio.py, tools/live_test.py, tools/Run-Test.ps1, tests/test_live_matrix.py, tests/test_start_script.ps1, new tests/test_validation_audit.py, and both CI test lists. Retain START vs AU vs decode distinction, first-fault preservation, recovery state and ownership metadata; adapt counters if another worker has renamed diagnostic fields.
3. Run all above production Python and compiled CLI regressions, actual Windows PowerShell fixture and appropriate compiler-backed offline checks. If FDK available, tools/run_offline_checks.py --build-fdk validates a larger host suite; annotate skips. Record exact commit SHA, CI URLs, pass/fail/skip totals. Never label simulation a hardware test.
4. Before flashing, inspect actual evidence/verification.json for build_verified=true and runtime_allocation_verified=true for USBPods target, verify UF2+binary+runner hashes against candidate.json. After flash require info SHA exactly equal to manifest.sha and verify board/variant. Even docs-only source SHA changes may change embedded USBPODS_BUILD_SHA and resulting UF2; never mix prior artifact and newer manifest.
5. Preserve docs/evidence/current-validation.json as historical 7de2130 evidence; new candidate state belongs to a new SHA-specific record. Preserve earlier 256 pass/192 fail, ten-minute soak duration completed with strict loss FAIL, no latest game-mode results and explicit local refresh failure.
6. New physical data requires exact flashed firmware SHA and operator testimony. Return raw result ZIP **locally only**; source control should contain only sanitized metrics, test statuses and optional SHA256 checksums, no audio, MACs, Bluetooth keys or private captures. Do not auto-reconnect to obscure a failed explicit refresh.
7. When collecting listening text, preserve operator verbatim wording and classify explicit negatives FAIL; ambiguous/not performed remains UNVERIFIED. Record final firmware capture separately from initial OS ownership. Keep unmeasured pitch, clock drift, RF, ANC-Off, raw Windows HID and game-mode behavior unverified.

## Short local operator acceptance script (NOT executed by this worker)

**Warning:** Run-Test flashes the UF2 in the extracted, verified candidate package. Back up the currently working UF2 first and only run an authorized test. COM on the laptop was normally COM4; confirm actual port. Reuse pairing avoids case mode and fresh pairing but requires unambiguous saved history (use one exact -TargetMac or -TargetName if necessary, never both).

~~~powershell
# From the extracted, authorized test package; DO NOT use with untrusted UF2.
$ErrorActionPreference = 'Stop'
$manifest = Get-Content .\candidate.json -Raw | ConvertFrom-Json
if (!$manifest.hardware_test_candidate -or $manifest.hardware_tested) {
  throw 'Expected an authorized but not yet physically tested candidate'
}
Write-Host "Testing source $($manifest.sha), UF2 $($manifest.firmware)"
.\Run-Test.ps1 -CdcPort COM4 -SessionOnly -ReusePairing
if ($LASTEXITCODE -ne 0) {
  Write-Warning 'Preserve results ZIP and first-fault JSON; do not auto-refresh'
}
~~~

Then, with that **same confirmed firmware SHA** and a still-connected output path, perform only a *short manually labeled channel observation*: microphone open, isolated left-only and right-only; close only microphone and independently confirm firmware capture=0; repeat left-only and right-only; reopen capture and repeat. Keep playback open, record exact operator words, initial external mic ownership, :info.sha, received-AU/decoded/USB counters and any disconnect reason. The session-only launcher **does not automatically execute these manual listening steps**; record separately. **Do not repeat the already-completed ten-minute soak.** Game modes remain “not measured” unless actually observed.

## Assumptions and remaining gaps

- No device, raw local archive, COM port or OS microphone was accessed. New claims are repository-derived simulation/build/CI only. Original candidate 18be74c was never physically tested.
- This audit does not solve physical mic-close left-ear silence, firmware START transport, RF losses, core timing, FDK ownership or any codec repair. Those are separate worker scopes.
- Finite runtime polling can miss very brief changes not reflected in counters; no complete continuity guarantee is made beyond sampled counters/observations.
- Final capture closure does not prove which OS application owned it. Maintain that explicit distinction.
- 320kbps exceeding negotiated 256kbps ceiling, ANC-Off unsupported/unconfirmed, Windows raw HID inaccessible, pitch, clock drift, RF, latest game modes and independent gesture semantics are not automatic failures or successes.
- The reported K refresh terminated ACL locally, not by historical remote 30-second timeout. Do not infer gesture identity from multiple AVRCP PLAY records.
