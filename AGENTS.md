# USBPods reconstruction / usb-hub

Read `docs/LOCAL-CODEX-HANDOFF.md` before changing code. It records the current
implementation, evidence, references, build setup and unresolved physical issue.

- Priority: simultaneous AAC-ELD playback and microphone; multiple negotiated
  bitrates and both game modes. The user uses Windows 11, Pico 2 W and AirPods
  Pro 3. Diagnostics use USB CDC only; do not require an external UART adapter.
- Inspect `git status` and preserve existing work. Use a dedicated branch and
  worktree unless this checkout is already dedicated to the task. Never reset
  or clean an existing user's checkout to make room. If parallel agents are
  explicitly requested, give each agent its own named branch/worktree in its
  initial prompt. Do not start agents merely because slots are available.
- The supplied Full disassembly/reconstructed source is a suggested reference,
  not authoritative private source or a proven best implementation. Preserve
  the distinction between that reference and independently implemented code.
- Reason from code and captured evidence, reproduce failures offline and use
  appropriate integration tests. A successful build alone does not prove a
  protocol, routing, acoustic or physical outcome. Do not label a change live
  ready on that basis.
- The original bass complaint was withdrawn after a better A/B comparison.
  Do not add speculative EQ or change working microphone clocks for that claim.
- Keep source and test changes focused. Preserve independent/manual playback
  recovery while keeping normal microphone lifecycle independent of playback.
- `references/` contains pinned, licensed comparison sources, not build inputs
  or replacement implementations. Use `references/manifest.json` for provenance.
- `docs/validation-status.json` records authorization for controlled live
  verification. Obey its packaging gates and the current user request; do not
  infer physical success from authorization or simulated checks. Keep actual
  physical findings distinct from simulated results.
- Do not publish raw captures, keys or the non-public supplied reference bundle.
  `docs/evidence/external-inputs.json` inventories those separate local inputs.
- Keep command output bounded. Save long logs to files, show compact summaries,
  and report progress during lengthy work. Do not dump complete CI logs into
  the conversation or leave long silent waits.
