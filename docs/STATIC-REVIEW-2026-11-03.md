# Static offline review and repairs — 2026-11-03

This record covers the offline static-review pass requested before any further
live test. It is **not** hardware evidence: no device was flashed or executed,
`docs/validation-status.json` still pauses live packaging, and the physical
left/right symptom remains unexplained and unclaimed.

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
| W-F5 | Packaging gate accepted `build_verified=True` even when the 32-bit codec-heap audit was skipped. | `package_live_test.require_codec_heap_audit()` requires `runtime_allocation_verified == true` for USBPods candidates. | Unit test covers missing/false/true; packaging still paused. |
| W-F6 | No test for the mute state machine or the untrusted name path; doc drift. | Tests above; fixed settings UART default, LHDC rate mapping, first-commit sector and 189-byte license comments. | Same tests. |

## Verification at this record

- Host suite: `python3 tools/run_offline_checks.py --fdk-lib build-host-fdk/libfdk-aac.a`
  → **59 passed, 0 failed, 0 skipped** (native FDK, ASan/UBSan, clang 22.1.2;
  includes new `resamp44`, `forensics-legend` and the extended fixtures).
- Ignored-START probe before/after: archived
  `build-offline-evidence/archive/audit-output/mic-watch-before.c` still fails
  its assertion; current `tests/test_mic_recovery_integration.py --probe`
  passes with playback untouched.
- Target matrix and SCO probes: all three CI variants plus both boards build,
  pass controller-image selection/`uart0076` audit/`verify_build.py`, with the
  UAC1 44.1 rate/endpoint check active. Hashes are recorded in
  `docs/evidence/static-review-candidate-2026-11-03.json`.
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
