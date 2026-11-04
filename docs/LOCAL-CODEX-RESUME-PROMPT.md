# Paste this into local Codex

Continue the USBPods reconstruction project in this repository. First read
`AGENTS.md`, `docs/LOCAL-CODEX-HANDOFF.md`,
`docs/MIC-ROUTING-REFERENCE-REVIEW.md` and
`docs/evidence/current-validation.json`. Check git status and the evidence
source commit before editing.

Use a separate branch/worktree. If this is an existing checkout containing
uncommitted work, preserve it and create the new worktree from `origin/main`;
do not reset or clean it. Suggested branch: `work/local-mic-routing`, worktree:
`../USBPods-local-mic-routing`. If either exists, inspect it and choose a new
name rather than overwriting it. This requirement must appear in any future
delegated agent's initial instructions too. No parallel agents are requested
by this prompt.

The hardware is Windows 11 + Pico 2 W + AirPods Pro 3. Native microphone and
simultaneous playback were reported working. The unresolved physical symptom
is that microphone close/open changes which AirPod plays audio. Quality was
later judged on par with public Full firmware after a better A/B track; do not
treat the original bass claim as established. AAC-ELD multi-rate/game-mode
playback plus the microphone are the priority. USB-only diagnostics, one CDC
COM port; no external UART adapter.

The latest implementation removes unconditional mic-triggered playback resets
and adds a bounded AACP-only received-audio watchdog. A successful local START
is not proof of microphone reception. Read the tests and validation record to
see exactly what has passed; do not claim the physical left/right issue fixed.
Normal mic START/STOP must not silently rebuild playback. Explicit/manual
playback recovery and genuine profile changes remain separate.

Reproduce the local offline checks with `tools/run_offline_checks.py`; its
bundled SDK references allow the host suite to run without the old cloud
workspace. Follow the handoff for native FDK and pinned target SDK setup.
Do not infer correctness from compilation alone. Investigate remaining gaps
from concrete evidence and keep changes isolated enough to compare.

The other hardware fork reports Windows 11 + Pico 2 W + AirPods Pro 3 working
without an A2DP reset. Its upstream LibrePods discussion directly reports a
one-AirPod playback failure, but its Linux card-profile reset is not proven
equivalent to our AVDTP reset. Five AACP command arrays match the hardware
fork byte for byte. RTP clock/profile differences remain hypotheses. The
supplied Full source/disassembly is only a suggested reference, not an
authoritative baseline. Pinned public sources, licenses, research and offline
evidence are in the repo; separate original inputs are indexed in
`docs/evidence/external-inputs.json`.

Current scope remains offline: finish reviewing/validating the code and identify
what the existing evidence cannot establish. Live packaging is paused in the
validation file; do not silently turn that into a new hardware-test request.
Keep tool output short and give progress updates during longer operations.
