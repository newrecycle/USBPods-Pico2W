# Capture lifecycle AU/PCM diagnosis — pinned 175ace9 (2026-11-07)

**Status: diagnosis and regression plan only. No production source, firmware, codec,
workflow or test code changed by this audit. No local firmware/codec tests or
firmware builds were run. No hardware, local raw recordings or private
captures were accessed.**

- Repository: https://github.com/newrecycle/USBPods-Pico2W
- Exact evidence/source tree: `175ace9f09554881b554e8226544e78ce10d06a1`
  (verified as the head of `work/local-windows-followup-20261107`).
- Physically tested single-core and opt-in dual-core source:
  `1979ae6be1c2daf9e1db8024763504d4061c4588`.
- Sanitized evidence:
  `docs/evidence/local-windows-20261107-live.json`,
  `docs/evidence/local-windows-20261107-dualcore.json`;
  chronology: `docs/LOCAL-FOLLOWUP-20261107.md`.
- Earlier independent reviews:
  `docs/MIC-CLOSE-CLOUD-AUDIT-20261104.md` and
  `docs/DUPLEX-192K-PROFILE-AUDIT-20261104.md`.
- The older physical 192 kbps laptop failure (186 AU drops, 95,168 USB
  missing samples) was on `880dc318`, not on the Nov 7 tested firmware.
  It cannot be called a regression of `1979ae6` or be merged into its
  measured interval deltas.

## 1. Evidence table — what the actual observations distinguish

| Scope | Physical or code evidence | What is **not** established |
| --- | --- | --- |
| Single-core 256 steady, 20 s | +2,752 decoded AUs; **0 new AU drops**, **0 missing USB samples**, 0 PCM-full worker exits; 1,032 TX packets. Applied bitrate 256,000, jitter 150 ms. | Absence of startup drops or all-session zero loss. |
| Single-core normal 192 steady, 20 s | +2,742 decoded AUs; **0 new AU drops**, **0 missing samples**, **1,412 PCM-full worker exits**, **0 AU drops while PCM full**, 977 TX packets. Applied bitrate 192,000, jitter 150 ms. | That backpressure is itself defective or created a drop. |
| Single-core game steady / latency | +2,744 / +2,740 decoded, both **0 new AU drops and 0 missing**, applied jitter 90 / 60 ms. | Startup or reopen losslessness outside the selected measurement windows. |
| Single-core complete session | `au_drop` reached **248 by cleanup**, including startup, interrupted runner, and microphone lifecycle activity. Intermediate Wi-Fi/runner observations were invalidated; final lifecycle used synchronized current heartbeats. | Drop-by-drop timestamps, the specific generation of each overflow, host callback delays or the cause of all 248. **Do not reset/relabel these as zero.** |
| Single-core mic close | Closed capture still lost left-ear audibility while the encoder input showed valid left PCM. Explicit K refresh and saved-bond reconnect restored left with capture closed. | A cause of compressed AU overflow, a reason to change capture timing, or a peer codec/routing diagnosis. This is an **independent** acoustic defect. |
| Opt-in core-1 256 steady | 0 new AU drops, 0 missing USB samples, 0 PCM-full worker exits, 2,745 decoded in 20 s; before/after USB underruns stayed 350 and missing stayed 22,400. | Production-grade cross-core qualification or zero prior startup losses. |
| Opt-in core-1 normal 192 steady | 0 new AU drops; **+2,816 missing USB samples**, **+44 underrun packets** (350→394), 2,732 decoded AUs, 0 PCM-full exits and 0 AU drops while PCM full; measured `au` +2,732, `decoded` +2,732. | Whether the 44 underfilled packets were consecutive, caused by scheduling, priming, Windows timing, sample clock, or a queue visibility race. `2,816 = 44 × 64` does not establish their distribution. |
| Opt-in core-1 queue headroom | AU high-water 8/32, PCM high-water 14/16, 0 AU/PCM stale in the published 192 before/after snapshots; AU wait max 18,808 μs and work max 24,011 μs were **lifetime** maxima. | That the high-water and maxima occurred inside the 192 window, or that one long work pass caused a specific USB miss. |
| Configuration boundary | Pico 2 W single-core is the production default; core-1 decode is experimental, explicit opt-in, with a 16 KiB reserved stack. Both tested variants were built from the same source but have **different UF2 hashes**. | Equal execution/scheduling between variants. Core-1 trial failed strict 192 USB-loss acceptance and was stopped; the single-core UF2 was restored. |

The physical source and artifact identities must not be conflated:
single-core firmware SHA-256
`d89d964077e79f36f0ae1f825b761135a39ffac60d8659a1f404432644fc27db`,
core-1 experimental firmware SHA-256
`95dd2cbeb9a8d07f9d33e47898ca43b2a8669c6ff6e14cca45be364e1d3d79cb`;
firmware CI run `42419581145`; artifact IDs `13592873692` (single-core)
and `13592997637` (core-1).

## 2. Timeline model (ordering only; timestamps explicitly unknown)

This is a **possible** sequence, not a reconstructed trace. The committed
snapshots do not supply exact inter-event timestamps, AU/PCM occupancy at each
capture transition, or an independent host-input callback timeline.

| Logical step | Code-level event and state changes | Known / unknown |
| --- | --- | --- |
| T0: host opens input | Windows runner opens `sounddevice.RawInputStream` in `AudioSession.set_capture(True)` **after** the speaker `RawOutputStream`; the input may be WASAPI shared at the selected host default rate/channel layout. Windows/TinyUSB mount, resume and mic alt 1 yield `usb_capture_running()=true`; `publish()` changes capture intent. | **Unknown:** when the host actually issues the first USB IN request relative to alt 1, host callback start, RF START or any producer burst; other Windows clients may hold a capture handle. |
| T1: capture generation | `usb_capture_lifecycle.c` publishes intent via `aacp_mic_set_capture()`. A changed boolean increments `generation`; redundant mic alt 1→alt 1 leaves the generation intact. Actual alt 0 close, suspend/unmount can withdraw capture. | **Unknown:** exact order/number of host transitions in interrupted attempts. Capture and generation are distinct atomic operations, not an indivisible snapshot. |
| T2: AACP command | `aacp_mic_poll()` recomputes desired START/STOP from latest intent and the watchdog. `L2CAP_EVENT_CAN_SEND_NOW` recomputes it again; **only** a successful local `l2cap_send` commits `aacp_mic_sent`. START/STOP then increments generation with `aacp_mic_discontinuity()`; channel release does likewise. | Local command submission is neither peer receipt nor first decoded AU. Actual transaction/send timing is not available in committed summary. |
| T3: AUs arrive / queue | AACP parser records AU arrival before optional enqueue; only `session.started && wanted() && !mic_watch.failed` admits `aacp_mic_audio_enqueue`. The AU producer tags epoch, enqueue time and publishes `aw` using release semantics. Queue has 32 × 480-sample AUs (~240 ms at a nominal 64 kHz timeline). | **Unknown:** producer burst lengths, exact epoch of 248 overflows, whether PCM fullness coincided with those events. |
| T4: decode worker | Default core 0 main loop calls `aacp_mic_audio_work()` after BT poll; opt-in core 1 calls the same body from a persistent loop. It discards up to 32 stale AU entries and processes up to 8 current AUs per pass. If PCM ring is full it exits *without consuming* the current AU; a bounded 2 ms sleep may follow. | **Unknown:** actual worker service gaps, preemption and producer-to-worker backlog at the time of startup losses. |
| T5: epoch reset | On first successfully processed AU of new epoch, decoder clears transport buffer then Fill + DecodeFrame with `CLRHIST|INTR`; failed reset/decode retries history clearing on later AU and publishes zero PCM only for the failed current AU. An epoch changed mid-decode prevents publishing its old PCM. | A decoded-zero replacement is not an AU overflow; `errors` and `flush_errors` must remain separate. |
| T6: USB IN / priming | Only the USB consumer advances `pr` and `pcm_offset`. The first `aacp_mic_audio_packet_samples()` for an active capture removes up to 16 stale PCM head frames, resets the clock on generation change and waits for **4,800 current samples (75 ms)** before priming. `aacp_mic_audio_read()` consumes frame fragments of 63/64/65 samples with partial offsets. | **Unknown:** first callback after the new alt, whether stale PCM filled the ring before it, and which USB packets were early priming/rebuffer silence. |
| T7: host closes/reopens | `AudioSession.set_capture(False/True)` closes/recreates the input context, while speaker output persists. Mic alt 0 closes capture; a redundant alt 1 does **not** close it. Capture/START/STOP/channel changes all create different generations. | **Unknown:** runner/Wi-Fi interruption ordering, external input ownership, whether any host change suppressed USB IN for > one ring window. |

### Critical backpressure interaction to reproduce

In `src/btstack/aacp_mic_audio.c`, producer index `aw` and consumer index
`ar` govern the 32-AU ring; `pw` and `pr` govern the 16-PCM-frame ring.
The worker tests **raw PCM occupancy** `pw - pr >= PCM_SLOTS`, regardless of
whether the queued PCM has the current epoch. `aacp_mic_audio_pending()`
likewise returns false when the PCM ring is full. Stale AU entries *can* be
cleared by the worker despite full PCM; **stale PCM is retired by the USB
consumer**, through `packet_samples()` or `read()`.

Therefore an obsolete full PCM ring plus new capture intent/START may block
decoding current AUs **until the USB consumer runs**. A host input endpoint
that has opened but has not yet generated an IN callback can allow new AUs to
accumulate, eventually overflowing the 32-slot compressed ring. This path is
source-consistent and testable; whether it occurred physically remains unknown.
The existing `tests/test_mic_audio.c` explicitly verifies that a full stale
PCM ring recovers *once `packet_samples()` is called*. It does not establish
bounded behavior before that first USB callback. Merely increasing capacity
would postpone, not diagnose, a delayed-consumer deadlock/starvation.

The pending/worker distinction also matters across ownership modes:
single-core runs a bounded worker in `src/main.c` and skips the 2 ms sleep
when useful AU work is pending; experimental core 1 loops on the same production
worker with a 250 μs idle sleep, while core 0 remains the AACP producer and USB
consumer. The SPSC release/acquire indices are necessary but cannot guarantee
the Windows host services the USB endpoint or that producer arrival matches
consumer demand. Never move `pr`, `pcm_offset`, or `packet_clock` ownership
to the worker/core 1 as a shortcut.

## 3. Accounting: expected cleanup vs genuine loss

| Counter/condition | Production meaning | Interpretation |
| --- | --- | --- |
| `au_drop` / `au_overflows` | Active, decoder-ready AU offered while `aw-ar >= 32`; new compressed AU discarded. | **Real capacity loss**. The lifetime 248 cannot be erased as expected generation cleanup, even if its cause was startup. Requires time/epoch attribution. |
| `au_drop_pcm_full` | Subset of those overflows where PCM occupancy was *exactly* 16 at enqueue time. | Correlation at overflow, not proof PCM caused it; zero does not rule out PCM pressure earlier. |
| `pcm_blocked` | Worker encountered a current AU but PCM ring held 16 frames and exited without consuming it. | **Backpressure event, not a drop.** Single-core 192 +1,412 with 0 losses is valid. Count is worker attempts/exits, not milliseconds blocked. |
| `au_stale` | Worker removes AU whose epoch is obsolete (or capture no longer requested). | Intentional discontinuity cleanup. Some useful audio may be abandoned at close, but this must not be conflated with `au_drop`. |
| `pcm_stale` | USB consumer removes a PCM frame from another epoch. | Intentional cleanup; reset of partial-frame offset prevents old fragments reaching new capture. Count is **frames**, not 64-kHz samples. |
| `au_inactive` | AU enqueue attempted when capture false or decoder unavailable. | Ineligible/ignored AU, not AU-ring overflow. AACP parser's `au` observation counter also includes frames not admitted to decoder. |
| `pcm_drop` / `pcm_overflows` | Defined in stats but the inspected production decoder does not increment this counter in the full-ring path; it stops before decoding. | **Zero is not proof of ample PCM capacity.** Use `pcm_blocked`, `pcm_depth`, stale and USB counters. |
| `decode_errors`, `flush_errors` | Failed FDK decode/format or history-reset attempts; the worker may produce current-epoch zero PCM on error. | Wrong/empty PCM must be distinguished from a missing AU or a full-ring exit. |
| `usbcapture.missing_samples` / `underruns` | In a valid IN callback, short decoded read relative to nominal packet demand; when `packet_samples()` returns 0, callback explicitly requests 64 silent samples and accounts their absence. | **Actual USB-supplied silence deficit**, including expected startup priming/rebuffering; it is not a one-to-one conversion of `au_drop`, and cannot by itself prove steady decoder starvation. |
| `au_wait_max_us`, `work_max_us`, ring high-water | Nondecreasing lifetime maxima (plus last/EMA values for selected quantities). | Do not assign a lifetime peak to a 20-second interval or use unchanged peak to claim that interval had no long stall. |

Reconstruct a given generation with separate accounting for (i) old AU/PCM
discarded as stale, (ii) invalid/capture-off AUs, (iii) current AU overflow,
(iv) decoder history reset/error replacement, (v) startup silence before
75 ms priming, (vi) post-priming USB underfill, and (vii) host callback/
recorder interruptions. Preserve monotonic counters and the original
before/after steady deltas. Do not silently redefine pass criteria.

## 4. Alternative hypotheses and falsifiers

1. **Full stale PCM ring blocks newly admitted AUs at reopen** (highest-priority
   deterministic probe). Force 16 old PCM frames, leave a partial old frame
   offset, change capture generation, resume AACP AU production and deliberately
   delay the first USB IN callback. Check when `ar` stops, whether `pcm_blocked`
   rises, and if/when `au_drop` increases. Falsified for bounded host delays
   if current AUs progress without drop through a correctly synchronized
   consumer-owned stale retirement.
2. **Foreground worker starvation / burst scheduling.** Inject 4-AU / 30 ms
   bursts plus bounded main-loop service interruptions; measure queued-time
   deltas and occupancy with *free* PCM. If AU overflows with free PCM and
   worker not called, scheduling is implicated. A 192-kbps applied profile
   does not by itself explain a startup overflow when 256/192 steady tests
   passed on the same single-core build.
3. **USB consumption/priming delays independent of decode.** Hold USB read
   callbacks for a finite duration, then resume 63/64/65-sample ticks.
   `pcm_blocked` without `au_drop` can be tolerated; underfilled current
   packets after priming must be flagged. Probe the host first-callback
   boundary, not only the existence of an opened `RawInputStream`.
4. **Partial frame / epoch transition.** Partially read a 480-sample PCM frame,
   advance generation via mic close/reopen and successful START/STOP, then
   ensure the first new packet contains no old PCM; stale counters increase
   appropriately. Repeat across clock wrap and generation churn.
5. **Experimental core-1 timing/visibility.** A no-overflow threaded test
   with a producer that throttles at AU depth <20 is insufficient to stress
   forced producer bursts or delayed consumer. Repeat with a real concurrent
   producer/decoder/USB consumer and deterministic barriers; check exact
   production sequence values, release/acquire visibility, no double consumer,
   no stale output, bounded completion and TSAN/ASan where supported.
6. **Windows input-handle/runner effect.** Runner opens `RawOutputStream`
   first, then `RawInputStream` with the host-advertised WASAPI shared rate
   (not necessarily 64 kHz). `set_capture(False)` closes its context; the
   Windows audio engine or other clients may keep the device's alt active.
   A callback/writer queue failure is host evidence, not necessarily an AU
   overflow. Source-level tests must model delayed/reentrant input startup,
   repeated open/close, callback under/overruns and capture-active-after-close;
   do not fabricate a local machine trace.

## 5. Deterministic regressions to add **after owner coordination**

Only a single integration owner should modify production queue/USB modules,
because they overlap the dual-core worker. Propose CI-only tests first; no
production implementation is authorized by this diagnosis.

| Proposed regression | Exact setup and assertions | Proposed CI placement |
| --- | --- | --- |
| `mic_capture_stale_full_before_first_usb` | Populate 16 PCM frames in epoch N; optionally leave `pcm_offset` at 64; capture closes/reopens, AACP success creates epoch N+1, enqueue current AUs before first IN callback. Assert no old samples, bounded stale retirement at consumer handoff, current AU progress, strictly counted overflow if intentional delay exceeds capacity. Capture all generation/counter deltas. | Extend `tests/test_mic_audio.c`, production body with deterministic FDK mock. |
| `mic_capture_burst_delayed_consumer` | At 64 kHz, deliver 4 AUs / 30 ms with imposed USB callback holds (0, 40, 75, 120, 240, 300 ms). Force PCM full/empty and obsolete/current combinations; verify `pcm_blocked` may rise without AU loss, and a long intentional stall produces explicit `au_drop` rather than a fake pass. Test post-unblock catch-up and finite work budgets. | Extend deterministic AU/PCM test and `tests/test_mic_clock.c`; do not alter 4800-sample prefill. |
| `mic_capture_partial_epoch` | Consume 64/63/65 samples of a current 480-sample frame, then close/reopen, STOP/START success, channel release; assert partial old tails are discarded exactly once, `pcm_offset` is reset, and first decoded new frame uses history-reset flags. Inject Fill, clear, decode and format errors. | `tests/test_mic_audio.c` plus production `tests/test_mic_recovery_integration.py`. |
| `mic_capture_spsc_transition_stress` | Three real threads; pause USB consumer while producer bursts past AU depth 20, flip generation at defined barriers, unblock at variable PCM occupancy. Assert no torn data, stale resurrection, false-prime, unbounded spin or unaudited drop. Include multiple reopen cycles and forced wrap. | Extend `tests/test_mic_core1_threaded.c` using barriers and sanitizer options; default and experimental CI variants. |
| `mic_capture_usb_alt_host` | Open USB speaker and microphone independently; redundant mic alt 1→1 must not bump generation, real alt 0 must; suspend/resume and mount/unmount must change capture correctly. Model first USB IN after delayed Windows handle start and separate reporter/collector errors from actual `usbcapture` deficits. | `tests/test_usb_control_boundaries.py`, `tests/test_usb_host_input.c`, and runner contract tests. |
| `mic_capture_loss_accounting` | Snapshot lifetime and per-generation counters before/after cleanup, actual overflow and bounded start/settle windows. Verify `au_drop` never decreases, stale/inactive cleanup does not increment overflow, first-fault evidence persists, and steady intervals still fail on any new AU drop, decode error, USB missing sample or short write. | `tests/test_live_matrix.py` / runner contract + production mic stats fixture. |

Test methodology: add first a reproducible **failing-before** source-body
fixture on the exact `175ace9` implementation; distinguish intended failure
of a pre-fix assertion from compile/test-harness failure. Follow with a
passing-after candidate **only after** cross-worker ownership is reconciled.
The C/FDK/native codec tests, experimental threaded test, firmware compilation,
32-bit heap audit, four target matrix variants (including opt-in core 1)
and patched-SDK verification run **exclusively in GitHub Actions**. Do not
execute local firmware/codec tests or build toolchains. The current
`.github/workflows/pico-firmware.yml` already includes deterministic mic,
threaded, USB and real-FDK tests; update it only after a test implementation
exists. Recheck workflow trigger rules for an `audit/*` branch rather than
mistaking a missing workflow for a pass. In this documentation-only phase,
**no CI result is claimed**.

## 6. Minimal conditional fix scope (not implemented)

1. **Fix only an evidenced stale-PCM/current-AU startup deadlock:** keep USB
   consumer ownership of `pr`, `pcm_offset` and `packet_clock`. Introduce
   a bounded, consumer-side stale-epoch retirement at a clearly serialized
   USB capture/open or first-IN boundary. If that boundary cannot prove single
   USB-consumer ownership, publish an atomic purge request and execute it in
   the next valid USB-consumer callback; never let the core-1 producer/decoder
   change `pr` directly. Clear only obsolete PCM, never live current data.
   A first-callback-only purge cannot by itself solve a host that issues **no**
   IN callbacks for longer than the AU ring's buffering budget.
2. **If the test shows overflow with the USB endpoint genuinely not consuming,**
   diagnose the bounded host-start interval and explicit START/STOP sequencing
   before choosing any wire-policy change. Do not introduce automatic
   reconnects, indefinite waits, silent producer discard, fake counter resets
   or speculative queue enlargement.
3. **Keep FDK decoder history reset strictly epoch-aware**, preserve the
   initial transport clear + Fill + CLRHIST/INTR order, and keep bounded worker
   scheduling. Keep no global core/flash ownership edits here.
4. **Add narrow, privacy-preserving attribution** only if existing snapshots
   cannot disprove the hypothesis: per-generation observed/eligible/enqueued,
   stale and overflow deltas; first USB IN and first primed IN markers; an
   overflow-time PCM occupancy category; and a bounded count of USB
   post-prime underfills. No payload, addresses or raw audio.
5. Do not modify clocks, AACP command bytes, playback encoder, core assignment,
   persistent worker, flash lockout, heap allocation or ring size. A separate
   core-1 owner must review every proposed shared-queue memory-ordering change.

Likely shared ownership conflicts: `src/btstack/aacp_mic_audio.c`,
`src/btstack/aacp_mic.h`, `src/main.c`, `src/tinyusb/uac.c`,
`src/tinyusb/usb_capture_lifecycle.c`, `tests/test_mic_audio.c` and
`tests/test_mic_core1_threaded.c`. This audit does **not** merge any
unpublished branch, alter any of those sources, or establish a preferred
multicore architecture.

## 7. Physical acceptance criteria for a *future authorized candidate*

- Exact source commit, CI workflow run, variant, UF2 hash and 32-bit
  allocation gates verified **before** any hardware test. Default single-core
  first; experimental core-1 is a separately labeled optional comparison,
  never silently substituted or automatically packaged.
- Use one short same-host capture-open→close→reopen sequence with the speaker
  continuously open, then separate 256/192 steady intervals; **no replacement
  ten-minute soak**. Host input format, open/close/first-callback timing,
  external ownership uncertainty, AACP successfully submitted START/STOP,
  capture generation and first USB IN/prime state should be correlated.
  Preserve first-fault snapshots before cleanup.
- Startup measurements report their own `au_drop`, `au_stale`,
  `pcm_stale`, `pcm_blocked`, `pcm_primed`, `missing_samples`,
  `au_drop_pcm_full` and host callback failures. A successful target should
  show **no avoidable compressed AU overflows** for its explicitly tested
  bounded open/reopen schedule; expected old-epoch cleanup remains counted.
  If USB deliberately stops beyond buffer capacity, drops must be reported,
  not hidden or promoted to PASS.
- Every accepted steady window still requires **zero new AU drops, decoder
  errors, PCM drops, USB missing samples and short writes**, correct 48 kHz
  coding/64 kHz PCM/USB packet contract, bounded sample-clock correction,
  continuous decoder/pump progress, stable generation and correct applied
  profile. The previously observed +1,412 PCM-blocked exits may be acceptable
  if they cause neither loss nor deadline failure.
- For core-1 to qualify independently, it must at minimum remove the
  reproducible +2,816 missing samples at normal 192 on an equivalent
  same-host steady interval *without* relaxing any threshold, plus demonstrate
  core-1 stack high-water and correct flash lockout. None of those
  post-test claims is established here.
- The left-ear silence with capture closed is an independent acceptance
  failure: preserve its status and use separate PCM/audio-routing evidence;
  success on these queue/lifecycle tests **cannot** be reported as an
  acoustic routing repair.

## 8. Disposition

**Diagnosis delivered, implementation deferred.** The strongest source-level
risk is delayed stale PCM retirement when a new capture generation starts
before the Windows USB IN consumer advances. This is testable and may explain
some startup/reopen compressed AU overflow, but the 248 lifetime drop events
cannot be assigned to it from committed evidence. Separately, the core-1
192-kbps trial demonstrates a real 44-packet USB underfill without AU drop or
PCM-full pressure. Both require distinct regressions; neither licenses an
acoustic channel or on-air protocol diagnosis.

No production edits, local firmware/codec execution, hardware actions, private
data access or automatic CI continuation were performed in this audit.
