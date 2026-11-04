# Static offline review and repairs — 2026-11-03

This record covers the offline static-review pass requested before any further
live test. It is **not** hardware evidence: no device was flashed or executed.
After these repairs and the green CI build, live verification was authorized by
explicit repository-owner order (2026-11-03) and
`docs/validation-status.json` now carries that authorization; each live
candidate still has to pass the per-candidate `build_verified` plus 32-bit
codec-heap-audit packaging gate. The physical left/right symptom remains
unexplained and unclaimed.

## Scope and constraints

- Entire first-party tree: `src/`, `tests/`, `tools/`, build configuration
  (`CMakeLists.txt`, `tusb_config.h`, `sdk-patches/`, CI workflow), and
  documentation claims. Third-party libraries, `references/` and the supplied
  Full bundle are not build inputs and were not treated as product code.
- Work stayed on `work/local-mic-routing`. Host suite, target builds and probe
  reproductions only; no live run, no flashing, no package authorization.
- Settled non-bugs were excluded from findings: RTP millisecond timestamps and
  marker 0, the gap snap/kick strategy, the AACP-only bounded mic liveness
  watchdog, fault lifetime across capture generations/channel sessions,
  per-attempt retry counters, no speculative EQ, and physical routing.

## Method

1. Three scoped, read-only low-reasoning reviewers covered (a) USB/control
   plane, (b) AVDTP playback/HCI/relay, (c) ELD/codec/microphone pipeline. A
   fourth integration reviewer audited the main loop and context boundaries.
2. The Lead reproduced every high/medium finding against the source, then fixed
   it with a regression that executes production bodies (regex-extracted
   functions compiled under ASan/UBSan) or a byte/event-level fixture — no
   parallel state models where production code could be run instead.
3. One whole-codebase reviewer then read all of `src/`, `tests/`, `tools/`,
   build configuration and docs at `8fc20d8`; its findings were triaged, fixed
   and spot-checked item by item (see below).
4. A final single low-reasoning whole-candidate review pass is run on the
   repaired tree; its outcome is appended in the follow-up documentation commit.

## Findings fixed

### AVDTP / playback / relay

| # | Finding | Fix | Regression |
|---| --- | --- | --- |
| A2-F1 | `a2dp_demo_timer_stop()` left `is_streaming` set; CLOSE/ABORT, signalling release and disconnect helpers did not clear playback flags. | Clear `is_streaming`, `src_stream_established`, scan/pending flags at the four real teardown sites (not in `timer_stop`, whose TX-stall path keeps the stream). | `tests/test_source_boundaries.py` asserts the helper clears all flags. |
| A2-F2 | AVRCP reconnect seed treated 0 and 127 as "uninitialised", dropping a legitimate full/zero level to 50 %. | One-shot `src_volume_known` flag set by `set_bt_volume()`, both volume keys and the AVRCP notification; seed runs once. | ASan fixture: 0/127 survive reconnect, seed only before known. |
| A2-F3 | Unchecked SDK returns for discovery/capability/AVRCP/SDP; COMMAND_DISALLOWED could park the session with no recovery. | Check all returns; scan failures use the existing bounded `src_sig_disallowed` wedge policy; AVRCP/SDP failures logged only. | Source review; wedge policy covered by existing SDK contract tests. |
| A2-F4 | Relay lifecycle mock diverged from production (12 vs 4 slots, 5-byte synthetic event, phone address always true). | Mock now matches `RELAY_PKT_N 4`, the real 14-byte event layout and an address table. | Wrong address, failed status and mismatched CID cases added. |
| A2-F5 | START accepted during the capability scan left the pump off (silence until a peer suspend/park watchdog). | Pending-start flag plus shared `src_pump_start()` invoked from both the START path and the scan-completion branch; cleared on teardown. | Extractable predicate asserted in the ASan fixture. |

### USB / control plane

| # | Finding | Fix | Regression |
|---| --- | --- | --- |
| A1-F1 | Redundant mic alt 1→1 `close_EP` cleared capture, bumping the AACP generation and resetting the 45 ms mic prefill. | Close capture intent only when the new alt is 0. | Boundary fixture: generation/false-call unchanged on redundant alt 1; alt 1→0 still clears. |
| A1-F2 | Host volume request flag was cleared after applying, losing a SET_CUR that landed in the window. | `_Atomic` flag exchanged before the BT apply; volume/mute snapshotted first. | Fixture makes `set_bt_volume()` inject a request; newer value applies next pass. |
| A1-F3 | Code/tests accepted speaker alt 2 that no descriptor advertises (fixture-only 24-bit path). | `N_FORMATS=1`, one 16-bit format, alt > 1 rejected. | Production-constant boundary cases. |
| A1-F4 | Speaker clock advertised read-only while SET_CUR was implemented and tested. | Advertise `AUDIO_CTRL_RW` (mic clock stays read-only). | Descriptor/handler consistency assertions. |
| A1-F5 | Settings loader did not validate the record version. | `page_valid()` rejects `version != SETTINGS_VERSION`; v1 `PSET` migration untouched. | Newer valid-CRC record ignored, older record loads. |
| A1-F6 | Console claimed a USB replug applies boot-latched UAC1/44.1 settings. | ".reboot to apply"; test also proves descriptors latch once in `main()`. | Wiring test. |
| A1-F7 | `settings.h` documented v1 storage geometry. | v2 geometry (512 B, 8/sector, 2 sectors) and a size static assert. | Static assert. |

### Main loop / concurrency

| # | Finding | Fix | Regression |
|---| --- | --- | --- |
| B1-F1 | `audio_slot_queue_init()` re-ran `queue_init()`→`calloc` from the BTstack IRQ on disconnect/slot switch (malloc-mutex deadlock risk) and leaked buffers. | Allocate once at boot; later calls drain/repopulate the existing queues. | Source-boundary assertions on the once-guard and drain path. |
| B1-F2 | Connmode-3 dial and host-volume apply mutated BTstack/AVRCP from the main loop without the cyw43 async-context lock. | Both take the async-context lock; the volume request is dropped when no radio context exists. | Wiring test pins lock acquisition around both calls. |
| B1-F3 | Radio-absent build could run BT/led actions from console/`usb_mode_task` before `btstack_main()`. | Radio-absent guards; only locally-safe console keys remain available. | Wiring test. |
| B1-F4 | Watchdog reset banner decoded stale `0x10/0x20` markers that no code writes. | Legend matches every real `scratch[7]` writer. | `tests/test_forensics_legend.py` collects writers from `src/` and checks the legend. |

### ELD / codec / microphone

| # | Finding | Fix | Regression |
|---| --- | --- | --- |
| A3-F1 | Resampler left a negative phase and read out of bounds if the output buffer filled mid-block. | Exact needed-output precheck; refuses an undersized cap without touching state; header documents the whole-block contract. | New `tests/test_resamp44.c` (ASan): exact 441→480, FNV pin, 100/479 caps refused, nonzero phase. |
| A3-F2 | Peer SUSPEND during managed WAIT_START armed no recovery; 3 s deadline aborted the stream/ACL. | Advance to one bounded `ELD_REBUILD` (`ELD_STOP\|ELD_BUILD`). | `tests/test_eld_adapter.py` block: no disconnect, no 3 s wait. |
| A3-F3 | AAC-LC setup failures left a partially configured encoder handle. | Transactional cleanup: close/handle-free, zero state, leave `cur_codec` for the owner to fail closed. | `tests/test_codec_setup.py` injects `aacEncOpen` and first-`SetParam` failures. |
| A3-F4 | `USB-CAPTURE-HID.md` still described fixed 64-sample/128-byte packets. | Document 63/64/65-sample (126/128/130 B) packets and `written != want*2`. | 63/65 exact and 62/66 reject cases. |
| A3-F5 | ELD retry ladder stepped 256→192 on a duplicate/late rejection after acceptance. | Pending-offer flag set only after a successful SET_CONFIGURATION send. | Negotiation test: post-acceptance rejection does not step down. |
| A3-F6 | First-AU decoder flush failure was never retried. | Failed flush does not advance the epoch; error counter in `[mic-dec]` telemetry. | `tests/test_mic_audio.c` mock fails the first flush and asserts retry. |

### Whole-codebase review (at `8fc20d8`)

| # | Finding | Fix | Regression |
|---| --- | --- | --- |
| W-F1 | Unclamped inquiry/EIR name length copied into a 240-byte stack buffer (HCI callback). | Shared clamped `inquiry_name_copy()` helper used by the print path. | ASan fixture sweeps lengths −2..300 and cap 0. |
| W-F2 | Host mute implemented as a toggle, inverting mute→unmute→mute and ignoring a first mute at a new volume. | Apply the requested mute state directly. | Boundary fixture asserts the full mute/unmute/mute sequence and a first-mute case. |
| W-F3 | Main-loop TinyUSB writes (`tud_audio_int_write`, `tud_hid_report`) could interleave with the 500 µs timer-IRQ `tud_task()`. | Short interrupt-disabled section around each main-side TinyUSB write (single-core build). | Wiring test pins all three call sites. |
| W-F4 | UAC1 44.1 kHz personality advertised the 48 kHz 192-byte endpoint maximum. | Descriptor macro parameterised per personality: 44.1 → 180, 48 → 192; `verify_build.py` checks rate/endpoint pairs. | Target `verify_build.py` (both UAC1 configs). |
| W-F5 | Packaging gate accepted `build_verified=True` even when the 32-bit codec-heap audit was skipped. | `package_live_test.require_codec_heap_audit()` requires `runtime_allocation_verified == true` for USBPods candidates. | Unit test covers missing/false/true; the gate stays mandatory when packaging is authorized. |
| W-F6 | No test for the mute state machine or the untrusted name path; doc drift. | Tests above; fixed settings UART default, LHDC rate mapping, first-commit sector and 189-byte license comments. | Same tests. |

### Whole-codebase review dispositions

The whole-codebase reviewer report (`.tools/review/full-review.md`, git-ignored)
was rechecked at `7bd1c47`; it records ten findings (1 high, 4 medium, 5 low),
all fixed, and no open code findings at that revision. Disposition:

| # | Severity | Finding | Status |
|---| --- | --- | --- |
| W1 | high | HCI inquiry/EIR name copied with an unclamped length into `char[240]` (stack overflow). | Fixed in `f3e53a7`: clamped `inquiry_name_copy()`; ASan length sweep. |
| W2 | medium | UAC host mute implemented as a toggle; mute→unmute→mute inverted and first mute at a new volume was ignored. | Fixed in `f3e53a7`: apply the host mute state; boundary sequence test. |
| W3 | medium | Main-loop `tud_hid_report`/`tud_audio_int_write` could race the timer-IRQ `tud_task()`. | Fixed in `f3e53a7`: interrupt-disabled sections; wiring test. |
| W4 | low | UAC1 44.1 kHz advertised the 48 kHz 192-byte endpoint maximum. | Fixed in `f3e53a7`: per-personality 180/192; verifier checks rate/endpoint pairs. |
| W5 | medium | Packaging could accept `build_verified` without the 32-bit codec-heap audit. | Fixed in `f3e53a7`: `require_codec_heap_audit()` gate + unit test. |
| W6 | medium | The descriptor-only 44.1 fix left `spk_arm` at 192 bytes, splitting the ISO transfer 180+12 B. | Fixed in `7bd1c47`: arm `tu_edpt_packet_size(&s_ep_out_desc)`; wiring test. |
| W7 | low | All-channels GET_CUR volume returned the right-channel value. | Fixed in `7bd1c47`: master readback; UAC1 control fixture case. |
| W8 | low | Failed/cancelled UAC1 ISO transfers still published the stale buffer as PCM. | Fixed in `7bd1c47`: failed result re-arms without pushing; wiring test. |
| W9 | low | UART input could starve CDC input on a noisy/floating RX. | Fixed in `7bd1c47`: CDC serviced before UART; wiring test. |
| W10 | low | `VERIFICATION-2026-11-03.md` still claimed non-ELD codec setup allocates in Bluetooth callbacks. | Fixed in `7bd1c47`: doc now states the main-loop deferral. |

Residual static risks kept explicit: AVDTP pending-START ordering when a peer
reverses the normal establish-then-START order is untested; the relay PCM
indices are `volatile` with an explicit `dmb` rather than C11 atomics (single-
core handoff intended); the TinyUSB IRQ exclusion and UAC1 44.1 host behaviour
are statically argued, not host-observed. A final low-reasoning whole-candidate
review pass was run after the repairs; its outcome is recorded below.

### Final whole-candidate review

A final single low-reasoning whole-candidate reviewer (report
`.tools/review/final-review.md`, git-ignored) re-read the repaired tree at
`7bd1c47`. It verified all ten earlier findings fixed and found no firmware
regression, but returned **CHANGES REQUESTED** for one tooling defect: the new
packaging codec-heap gate required `memory.runtime_allocation_verified == true`
while `verify_build.py` still always wrote false, so even a valid
`codec-heap32.json` could never satisfy the gate. Fixed in `3c9a034` by
factoring `apply_codec_heap_audit()`: it rejects non-32-bit pointers,
missing/negative peaks and over-heap estimates, and only after every check
passes records `host_codec_estimate` and sets
`runtime_allocation_verified = true`. `tests/test_verify_uf2.py` covers a valid
audit and five invalid ones and asserts the flag is never set on rejection. A
full `package()` success-path integration test remains a known gap (the gate
and its producer are unit-tested separately; the first authorized CI package
is the end-to-end exercise). The final
candidate at `3c9a034` differs from `7bd1c47` only in tools/tests, not firmware
sources.

### Reproducible-build correction (found by the final end-to-end run)

The final end-to-end verification rebuilt each target twice from the same
commit and produced **different ELF/BIN/UF2 hashes**, which would undermine
UF2-hash-based candidate identity and evidence pinning. Two sources of
embedded build time were found and removed in `e8b6320`:

- `3rd-party/fdk-aac` embeds `__DATE__`/`__TIME__` in its library-info strings
  by default. The target now builds with `SUPPRESS_BUILD_DATE_INFO`; the
  strings are diagnostic only and are not used at runtime.
- The `src/main.c` boot banner printed `__DATE__`/`__TIME__`; it now prints
  `USBPODS_BUILD_SHA` (the same deterministic source SHA already exposed by
  the control-channel `info` reply).

Verified after the fix: two independent clean `rpi0065`/AAC-ELD builds at the
same commit produce byte-identical UF2 (`sha256 c87b378e…2972` for the final
candidate), and a rebuild in a fresh build directory matches the recorded
end-to-end hash exactly. Hashes remain tied to the embedded source SHA, so a
later docs-only commit rebuilds with a different SHA field (the firmware
sources are unchanged).

## Verification at this record

- Host suite: `python3 tools/run_offline_checks.py --fdk-lib build-host-fdk/libfdk-aac.a`
  → **59 passed, 0 failed, 0 skipped** (native FDK, ASan/UBSan, clang 22.1.2;
  includes new `resamp44`, `forensics-legend` and the extended fixtures),
  re-run at the final firmware candidate `e8b6320` (host suite is
  source-independent of the docs-only record commit).
- Ignored-START probe before/after: archived
  `build-offline-evidence/archive/audit-output/mic-watch-before.c` still fails
  its assertion; current `tests/test_mic_recovery_integration.py --probe`
  passes with playback untouched.
- Target matrix and SCO probes: all three CI variants plus both boards were
  rebuilt and re-verified at final-candidate source state `e8b6320`;
  `verify_build.py` passes with the UAC1 44.1 rate/endpoint check active, and
  the UF2/ELF/BIN hashes are recorded in
  `docs/evidence/static-review-candidate-2026-11-03.json`. The SCO probe
  hashes are unchanged (`pico_w` f6332740…c3265, `pico2_w` adfdd021…404e).
- Evidence limits: build/link/UF2 verification only; no flash, boot, radio,
  audio, physical-routing or packaging validation. The 32-bit codec-heap audit
  was not reproduced locally (now an explicit packaging gate instead), and the
  TinyUSB/IRQ race and UAC1 44.1 host behavior are only statically argued.

## Deferred and out of scope

- Physical channel asymmetry, per-bud TWS relay behaviour, Windows endpoint
  churn and HID gesture mapping remain hypothesis-level; see
  [MIC-ROUTING-REFERENCE-REVIEW.md](MIC-ROUTING-REFERENCE-REVIEW.md) and
  [LIVE-FINDINGS-2026-11-03.md](LIVE-FINDINGS-2026-11-03.md).
- Full web HID feature surface (`webhid_get_report`) is not in this tree.
- Flash power-fail injection, host USB bus traces and RF/acoustic behaviour
  cannot be established offline.
