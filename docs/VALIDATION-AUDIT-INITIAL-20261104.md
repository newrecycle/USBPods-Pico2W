# Independent validation/runner audit — initial evidence ledger and plan

**Audit baseline:** `18be74cfe99f2584bcf26a0c0f0571c75a7f7bec` on `work/local-windows-20261104`.
**Isolation:** branch `work/local-windows-evidence-audit-20261104-gpt6` created directly from that immutable SHA. No other branch is merged. No local Windows host, Pico, COM port, AirPods or private raw capture was available.

This is the **pre-implementation** ledger and plan; later results belong in a separate final report. Evidence levels are not interchangeable.

| Claim / test | Source identity | Grounded evidence | Evidence class and limits |
| --- | --- | --- | --- |
| Candidate build + linker matrix passed | `18be74c` | [Pico workflow run 41793575782](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41793575782), all three matrix build jobs passed; the AAC-ELD job also ran real host FDK and 32-bit allocation audit, build verification and package step | **CI build/link, simulated and artifact checks**, not a flash or acoustic pass |
| Candidate focused CLI/launcher checks passed | `18be74c` | [Host run 41793575886](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41793575886), Linux compiled CLI simulation and Windows PowerShell fixture passed | **Compiler-backed CLI simulation and Windows launcher fixture**, not a physical USB/audio run |
| Last physically flashed firmware | `880dc318072f191f1440d3f0b262d83e32729b59` | `docs/LOCAL-WINDOWS-20261104.md`; `docs/evidence/local-windows-20261104.json`; original CI run 41786883085, hashes, COM4 and BOOTSEL verification recorded there | **Reported physical Windows laptop** evidence for a different commit; no candidate flash |
| With MaxxAudioPro off, mic-close silences left ear | `880dc318...` | Sanitize-only local Windows document/JSON; left-only and right-only isolated tone observations | **Reported acoustic** result. Earlier PC had no enhancements; laptop mixing was corrected, but prior PC behavior is not explained by MaxxAudioPro |
| Manual `K` refresh failed and locally disconnected ACL | `880dc318...` | Local Windows evidence, `wait-start`, stage 4, rc 4, reason `0x16` | **Reported physical** explicit refresh failure, not historical spontaneous peer 30-second termination |
| Saved-bond reuse worked | `880dc318...` (manual command), `18be74c` (new runner implementation) | Manual `savedconnect` in local evidence; `live_test.py::reuse_saved_pairing` and runner unit tests at pinned baseline | **Reported physical manual bond reuse** plus **simulated runner contract**. No power-cycle persistence or candidate-run reuse demonstrated |
| Rate 256 succeeds; rate 192 fails | `880dc318...` | Local Windows evidence: 256 zero recorded loss; 192 186 AU drops and 95,168 USB missing samples | **Reported physical Windows laptop**, not the candidate. Latest run stopped before game modes |
| Ten-minute soak already completed | `2911a824d5a44d126234d4f63545a37051d71d5f` | `duplex-packet-cadence-051250.json` via local Windows evidence: 600.539 s; reported completion; 7 AU drops and 14,656 missing USB samples | **Historical physical** duration met, strict zero-loss acceptance failed; do not prescribe repeating |
| Old handoff validation | `7de213042d82367401aedef3a0e9a864f9ab6773` | `docs/evidence/current-validation.json`: run 41746700880, separate USB host run 41746700738, 56/56 local host checks | **Historical source-specific CI/offline** record, not current head |
| Authorized hardware acceptance | docs/validation-status.json authorization basis `8b89d42` | Explicit authorization; packaging must check `build_verified` and positive 32-bit allocation audit | **Permission to test**, not a pass. Authorization record is older than both physical and candidate commits |
| START / first audio / decode | `18be74c` | `docs/LOCAL-CODEX-HANDOFF.md`; firmware diagnostic contract, `mic_started`, `mic_audio_seen`, micstats `decoded` | **Three distinct milestones**; local START submission alone cannot establish received AU, decoder output or correct acoustic pitch |
| HID / ANC-Off / RF / clock drift / pitch | mixed historical records | CDC HID submission, Windows raw HID limitations, unconfirmed AllowOff capability, no controlled RF/clock/acoustic measurement on candidate | **Unsupported / unmeasured**, never implicitly PASS or FAIL |

## Before-edit audit plan

1. **Boundaries and provenance.** Pin every reviewed file to `18be74c`. Keep pre-candidate hardware findings and newer CI evidence separate; never update old `current-validation.json` as if it represented this commit. Inspect official workflow job-level conclusions, not only a summary label.
2. **Reproduction-first.** Exercise production runner functions using fake serial/status, host WAV/capture and compiled control parser scenarios. Test saved-peer uniqueness, disconnected saved-bond path, ambiguous identity, no scan/pair/key-delete, and conflicting connected device. Check manifest and package gates by corrupting actual file bytes or build evidence.
3. **Readiness and first fault.** Create finite clock-driven status trajectories that include transient wait-start, recovery and media stalls; require a continuous steady interval and identify recovery rather than silently reporting an uninterrupted PASS. Exercise `preserve_audio_failure` before teardown and maintain the original failure artifact.
4. **Human observations.** Feed actual free-text counterexamples such as `left ear silent`, `only right audio`, `no, both` to the production classifier; do not translate all non-yes answers into UNVERIFIED. Preserve original wording in the record. Avoid interpreting AVRCP PLAY timing as a stem gesture.
5. **Capture state.** Test both prior-active and prior-inactive hosts, then independently poll final `status.capture`. Report firmware final closure separately from host exclusivity/ownership; an already-open stream cannot be claimed to have been opened exclusively by the runner.
6. **Package + launcher.** Run actual `package_live_test` with temporary verified artifacts/manifest and fake pySerial/picotool fixtures; preserve `build_verified`, positive 32-bit codec audit, UF2/hash and returning SHA checks. Run native PowerShell launcher fixture in CI, not a Python transcription of it.
7. **Minimal changes and regression evidence.** Modify only owned tools, matching tests, workflow test triggers, and sanitized documentation. Use the dedicated branch. CI pass = build/simulation evidence, never live physical proof. Document failing-before and passing-after reproduction where possible.
8. **Future integration.** Produce a checklist with SHA/branch ancestry verification, runner artifact/hash comparison, CI job URLs and negative test assertions. A short operator procedure is allowed; no request to repeat the completed ten-minute soak.

## Existing coverage gaps to investigate (not yet characterized as repaired)

- `channel_check` currently recognizes only a small set of exact failure words; explicit phrases can become UNVERIFIED.
- `capture_close_state` returns SKIP immediately when capture was active before the runner, without recording whether capture ultimately closed.
- `dwell` and steady interval evaluation observe selected end snapshots and may miss a resolved intermediate recovery.
- The manifest reader verifies checksums supplied in `candidate.json`, while the package producer enforces `build_verified`, binary/UF2 agreement and the positive 32-bit allocation audit; test both layers separately.
- Device/player output remains distinct from real microphone receive/decoded progress, acoustic channel separation and OS raw-HID access.
