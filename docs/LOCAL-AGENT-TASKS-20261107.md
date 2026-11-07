# Local Codex task handoff — 2026-11-07

## Start here

Repository: https://github.com/newrecycle/USBPods-Pico2W
Reviewed integration baseline: `263de0c707e95a668f8ce2686ac38ba3058cee3d`.
The handoff commit adds documentation and a host CI watcher; use current
`origin/main`, not an old local working branch. PRs #3/#4 are merged; all 19
non-main branches were deleted after verifying zero unique commits. Their
commits remain in main history. No workers are currently assigned.

Read AGENTS.md, LOCAL-CODEX-HANDOFF.md, INTEGRATION-REVIEW-20261105.md,
LOCAL-WINDOWS-20261104.md and its evidence JSON, PLAYBACK-RESTART-AUDIT-20261104.md,
MIC-CLOSE-CLOUD-AUDIT-20261104.md, DUPLEX-192K-PROFILE-AUDIT-20261104.md,
DUAL-CORE-MIC-EXPERIMENT.md, LIVE-TEST.md and validation-status.json.
Treat older authorization/source/build statements as historical, not as
acceptance of the latest candidate.

Inspect and preserve local changes. Fetch origin and create a dedicated
branch/worktree from origin/main, e.g. `work/local-windows-followup-20261107`
and sibling `../USBPods-followup-20261107`. Choose another name if occupied;
never reset/clean an existing checkout. This branch prefix triggers the firmware
and runner workflows. Do not create parallel workers unless the user asks.

## Hard constraints

- Keep firmware compilation AND firmware/codec tests in GitHub Actions. Do not
  install an ARM toolchain or build firmware/native FDK locally. Add meaningful
  regression coverage to existing workflows for each firmware repair. Local
  work is source review, runner/watcher tests and authorized hardware diagnosis.
- GitHub builds supply UF2/ELF/map, allocation evidence and checksummed bundles.
  Identify exact source SHA, run ID, variant and artifact hash before flashing.
  Successful builds/simulations are not acoustic or physical acceptance.
- Windows 11, Pico 2 W, AirPods Pro 3. One CDC port (previously COM3/COM4), USB
  audio output/input and HID. Enumerate actual ports; USB-only diagnostics.
  No external UART adapter. Keep automatic picotool BOOTSEL/load/verify behavior.
- Priorities: concurrent AAC-ELD playback/microphone, supported bitrates and
  both game modes. Keep normal microphone lifecycle independent of playback
  resets; preserve explicit manual recovery. No speculative EQ changes: the
  initial bass complaint was withdrawn after A/B comparison.
- Preserve the current microphone clock/protocol contract pending measured
  evidence. AACP is the control/mic transport; AAC-ELD is the codec, not a
  competing name for the same layer.
- Core-1 microphone decode stays opt-in OFF and excluded from automatic live
  packaging. The old core-1 encoder stays disabled. No global flash-safety bypass.
- Do not silently substitute Lite for Full or claim proprietary Full parity.
  Existing public-source workflows explicitly build the Lite baseline; missing
  vendor sources are a constraint, not something to fabricate or bypass.
- Keep raw captures, addresses/keys and private reconstructed Full inputs local.
  The supplied disassembly is suggested reference, not authoritative upstream.

## Execute in this order

1. Reconcile current handoff/validation documentation with integrated main.
   Preserve historical evidence and authorization chronology; do not turn an
   old candidate authorization into proof of latest firmware acceptance.
2. Review the actual integrated capture-close, AACP lifecycle and playback
   paths against han-um's pinned microphone implementation and its history.
   Form falsifiable causes before edits. With mic closed, the last physical
   result was left silent/right correct; reopening mic restored both channels.
   Saved-bond reconnect recovered left playback with mic closed. Identify
   whether local PCM/RTP content remains correct before attributing peer routing.
3. Diagnose 192k mic service loss. Last failed laptop interval: 186 AU drops,
   95,168 missing USB samples in ~20.6s, with ~50 playback packets/s and queue
   saturation. A separate ~45s interval decoded 6,089 AUs without new loss.
   Foreground bounded encoding is merged but not physically verified. Examine
   service time, burst delivery and queue backpressure; do not loosen thresholds
   or simply enlarge queues to hide loss.
4. Verify the merged playback restart fixes with workflow regression tests:
   OPENED preconditions, one bounded unanswered START retry, transaction-label
   filtering and retirement before reentrant accept callbacks. Physical explicit
   refresh previously timed out in WAIT_START and locally disconnected (0x16).
5. Push a coherent repair batch and let CI validate it using the completion
   mechanism below. Use failures to investigate code, not builds as the only
   reasoning method. Keep short source/evidence checkpoints.
6. Prepare a short, same-host live comparison once CI passes: 256k baseline,
   mic close/open with isolated left/right tones, 192k duplex, both game modes,
   supported 320k only if the peer ceiling allows it, then explicit refresh and
   saved-bond reconnect. Confirm applied profile/jitter and continuous readiness;
   retain first-fault snapshots before cleanup. The user uses phone audio for
   the microphone stimulus instead of repeated counting/talking. Keep playback,
   microphone and USB diagnostics concurrent during steady intervals.
7. Compare optional dual-core only as an explicitly identified experiment, with
   the same host/inputs/profiles. Require on-target stack/heap headroom, worker
   ownership and flash writes under duplex load before recommending it. Do not
   bypass its packaging gate. Keep the previous ten-minute soak evidence; no
   replacement long soak unless a specific new question justifies it.
8. After primary failures are resolved: power-cycle saved-bond persistence,
   suspend/resume and endpoint churn, notified controls, physical HID and stem
   multi-press mapping. Previously all observed AVRCP attempts appeared as PLAY;
   do not infer gesture identity from command timing.

Report repaired defects, remaining hypotheses, exact source/run/artifact
identities and observed physical outcomes separately. If local hardware access
is absent, complete source/CI work and provide a reviewable candidate instead
of claiming a live result.

## CI completion callback — no agent polling loop

`tools/watch_ci.py` is a local, non-model watcher. It queries GitHub every 60s,
accepts only push runs for a FULL exact source SHA, waits for every required
workflow, and writes `completion.json` atomically. Cancelled/skipped/failed,
missing workflows, timeout and watcher errors cannot become a pass. It can
then issue one `codex exec resume <exact-session-UUID>` callback. That resumes
work non-interactively; it does not inject a message into an already active
ChatGPT/Desktop conversation. Logs and final response stay in the local output
directory. No inbound webhook, public listener, GitHub-held Codex key, approval
bypass or new GitHub workflow is needed.

Local prerequisites: Python 3, authenticated `gh` (`gh auth status`), and for
resumption, authenticated Codex CLI whose `codex exec resume --help` supports
the shown interface. Verify locally; cloud CLI availability does not prove the
Windows installation supports or can access the same session. Use the exact
session UUID from the local CLI/session UI; NEVER `--last`, which might resume
another project. Do not inspect or copy authentication secrets.

For branch pushes with the stated prefix, expected workflow names are:
`Pico firmware build`, `USB capture and HID host tests`,
`Live runner host regressions`. On other refs/events, inspect trigger rules
once and pass repeated `--workflow` arguments for the workflows actually
expected. Do not use a missing workflow as an excuse to accept partial CI.
PR merge refs can have a different SHA: this helper deliberately tracks push
runs; explicitly identify the source under review instead of mixing events.

PowerShell, from the dedicated repository worktree after pushing:

```powershell
$sha = (git rev-parse HEAD).Trim()
# Replace with THIS local Codex session UUID, confirmed accessible by its CLI.
$session = 'REPLACE-WITH-EXACT-SESSION-UUID'
$sessionLog = 'REPLACE-WITH-MATCHING-LOCAL-SESSION-JSONL-PATH'
# Unique local directory, outside the repository; keep it free of spaces here.
$out = Join-Path $env:TEMP ('USBPods-CI-' + $sha.Substring(0,8) + '-' + [guid]::NewGuid().ToString('N'))
Start-Process -WindowStyle Hidden -FilePath (Get-Command python).Source -WorkingDirectory (Get-Location).Path -ArgumentList @(
  'tools/watch_ci.py', '--sha', $sha, '--output', $out,
  '--resume-session', $session, '--session-log', $sessionLog
) -RedirectStandardOutput ($out + '.stdout.log') -RedirectStandardError ($out + '.stderr.log')
```

Have the original agent checkpoint its next actions and YIELD/END ITS TURN
before the callback runs. Never concurrently resume a session being actively
used. If CI is already complete, handle its result in the current turn rather
than starting a competing continuation. For strict idle-session operation,
launch the command from a separate terminal after the original session yields.
The callback now requires a matching local session JSONL. After recording CI,
it waits for all logged `task_started` turns to receive matching `task_complete`
or `turn_aborted` records before invoking the CLI. Unknown identity, partial
records or a busy-session timeout refuse resumption. This is an idle check, not
an exclusive Desktop lock: keep the session unused until the callback finishes.
No fixed delay is treated as evidence that the session yielded.
The watcher survives the end of that agent turn, provided its local process
is not terminated and the machine remains awake.

The callback verifies the intended candidate, reads the aggregate result and
continues this handoff. It does not flash hardware automatically. If the CLI
needs an interactive approval, do not add a bypass: use `completion.json` and
`callback-status.json` to resume manually with normal permissions. The callback
response is `callback-response.md`; callback stderr/stdout are `callback.log`.

If the local agent harness has a native background-task completion notification,
prefer running the watcher WITHOUT `--resume-session` as that managed task and
let its completion notify the existing agent. Confirm that capability exists;
a detached process writing a file alone does not wake a model. Otherwise use
the explicit CLI resume callback above. Do not use repeated agent turns,
`write_stdin` calls or short sleeps just to ask whether GitHub is finished.
Do useful independent review while waiting, or yield to the completion callback.

On callback, inspect only failed-job logs or required artifact metadata once.
A new source change needs a new SHA and a new watcher/output directory. Changes
or reruns started AFTER the watcher completed require a fresh watch; an old
completion record cannot approve a newer attempt. If investigating a PR-specific
check, do not reuse a push-run record as evidence for a different merge tree.

References:
- https://cli.github.com/manual/gh_run_list
- https://cli.github.com/manual/gh_run_watch (simpler single-run alternative)
- Codex local `codex exec resume --help`; verify before enabling callbacks.

Watcher validation: `python tests/test_watch_ci.py` covers exact SHA/event
filtering, latest-run selection, aggregate completion, non-success conclusions
and missing-workflow timeout, session identity and active/overlapping-turn
refusal without calling GitHub or a model. No firmware
build or hardware test was performed while preparing this handoff.
