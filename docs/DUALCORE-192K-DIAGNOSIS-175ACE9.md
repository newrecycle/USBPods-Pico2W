# Experimental core-1 192 kbps USB microphone loss: evidence diagnosis

**Evidence baseline:** `175ace9f09554881b554e8226544e78ce10d06a1` (branch `work/local-windows-followup-20261107`).  
**Physically flashed firmware source for both variants:** `1979ae6be1c2daf9e1db8024763504d4061c4588`.  
**Scope:** independent cloud/source review, diagnosis and a falsifiable plan only. No device access, no uncommitted local captures, no new firmware, codec test, production modification, clock/ring change or experimental promotion.

## Evidence provenance and integrity

GitHub commit and branch were fetched by exact SHA. The evidence commit is **one documentation/evidence commit directly above the physically tested firmware commit**. Its compare contains only `docs/LOCAL-FOLLOWUP-20261107.md`, two sanitized evidence JSON files, and `docs/validation-status.json` — **no production files changed between the physical source and the evidence baseline**. The separate, committed single/dual variant identifiers are:

| Attribute | Single-core control | Experimental core-1 microphone |
|---|---|---|
| Source SHA | `1979ae6be...` | `1979ae6be...` |
| GitHub Actions run | `42419581145` | `42419581145` |
| Artifact ID | `13592873692` | `13592997637` |
| UF2 SHA-256 | `d89d964077e79f36f0ae1f825b761135a39ffac60d8659a1f404432644fc27db` | `95dd2cbeb9a8d07f9d33e47898ca43b2a8669c6ff6e14cca45be364e1d3d79cb` |
| Execution | Playback encode and mic decode on core 0 | Playback encode on core 0; mic decoder on core 1 |
| Acceptance | All four short steady profiles passed | 256 passed; 192 failed, then stopped |

Sources: `AGENTS.md`, `docs/LOCAL-AGENT-TASKS-20261107.md`, `docs/LOCAL-FOLLOWUP-20261107.md`, `docs/evidence/local-windows-20261107-live.json`, `docs/evidence/local-windows-20261107-dualcore.json`, `docs/DUAL-CORE-MIC-EXPERIMENT.md`, `docs/DUPLEX-192K-PROFILE-AUDIT-20261104.md`, and the production files at the pinned baseline.

The same host, source, nominal 20-second runner plan and applied 192 kbps/150 ms profile make the single/dual comparison valuable; they do **not** imply identical AirPods air traffic, event timing, run duration or queue phase. The single-core evidence records only interval aggregates, not all the before/after counters available for dual-core. Its short 256/192/game-standard/game-low-buffer intervals each had zero new AU drops and missing USB samples. The single-core 192 interval decoded 2,742 AUs, had zero USB loss and **1,412 PCM-full worker exits** without AU drops. Core-1 256 passed. The dual 192 failure stopped the experiment: no dual game modes, mic-close channel-lifecycle run, power-cycle or soak. The device was restored to single-core after the experiment.

## Exact dual-core before/after accounting

All differences below are **after minus before in one interval**. Times derived from USB packet counts are callback counts at nominal 1 kHz, not an independent monotonic start/end timer. `micstats` reads multiple atomics without a transactional snapshot; depth and counter reads are eventually consistent.

| Counter / derived quantity | Core-1 256 kbps (pass) | Core-1 192 kbps (fail) |
|---|---:|---:|
| USB IN callback packets | 20,652 | 20,569 |
| Expected USB PCM samples | 1,320,757 | 1,313,951 |
| Actual USB PCM samples | 1,320,757 | 1,311,135 |
| New underrun packets | 0 | **44** |
| New missing USB PCM samples | 0 | **2,816** |
| USB 63-sample packets | 1,045 | 2,465 |
| USB 65-sample packets | 74 | 0 |
| New observed AACP AUs | 2,752 | **2,732** |
| Newly decoded AUs | 2,745 | **2,732** |
| AU PCM potential (decoded × 480) | 1,317,600 | **1,311,360** |
| Expected USB minus new decoded PCM potential | 3,157 | **2,591** |
| Decoded PCM potential minus actual USB read | −3,157 | **+225** |
| AU ring depth before → after | 0 → 7 | **0 → 0** |
| PCM ring frame depth before → after | 12 → 6 | **8 → 9** |
| New AU/PCM overflow, stale or decoder error | 0 | **0** |
| New PCM-full blocked work passes / AU-drop-while-PCM-full | 0 / 0 | **0 / 0** |
| New arrival “bursts” (delta &lt;1 ms) | 2,064 | 2,049 |
| New arrival gaps (delta ≥15 ms) | 642 | 671 |
| New AACP timestamp duplicates/backward/gap candidates | 0 | 0 |
| USB short writes | 0 | 0 |
| Capture generation before → after | 9 → 9 | 9 → 9 |
| PCM primed at both snapshots | yes | **yes** |
| A2DP transmitted packets | 998 | 940 |

**Hard USB-packet inference:** `usb_capture_note_tx(want, got, written)` increments `underruns` for `got < want` and adds `want-got` to `missing_samples`. The USB callback chooses 63, 64 or 65 samples, substitutes a 64-sample silent packet when the mic clock returns zero, and logs successful bytes separately. During 192 there were no 65-sample requests. Therefore each of the **44 new underruns had a 64-sample deficit and supplied zero PCM**: 44 × 64 = 2,816. They are **fully silent packets**, not 44 marginal partial reads. The evidence lacks event timestamps, so their contiguity is unknown. `short_writes=0` excludes an observed TinyUSB short-write event but does not establish that USB callbacks had regular spacing.

**Conservation/inventory:** At 192 the 2,732 decoded AUs yielded 1,311,360 PCM samples; USB consumed 1,311,135, leaving a net **225 samples buffered** across the counter window. The frame-ring depth grew from 8 to 9 (a nominal +480 samples), which is compatible with an approximately **+255-sample change in the unreported partial-frame `pcm_offset`**: `Δavailable = 480×Δframe_depth − Δpcm_offset = 480 − 255 = 225`. For 256, the six-frame decrease and a possible +277 offset change similarly reconcile −3,157. These offset differences are **algebraically inferred, not measured**; staggered non-transactional snapshots limit exactness. There is no evidence of an uncounted 2,816-sample PCM discard.

Another equivalent 192 identity is:

```text
USB demand          1,313,951 samples
decoded PCM supply  1,311,360 samples  (2,732 × 480)
net demand deficit      2,591 samples  (40.48 ms at 64 kHz)
net PCM retained          225 samples  (including unknown partial-frame offset)
USB padding             2,816 samples  (44 ms at 64 kHz)
                    2,591 + 225 = 2,816
```

**Rate/clock caution:** Over 20,569 USB callbacks the 192 interval's aggregate observed AU equivalent was approximately 63,754 samples/s; the adaptively requested USB rate averaged approximately 63,880 samples/s. That is a window deficit of ~126 samples/s; the nominal 64,000 sample/s clock had already been lowered ~1,873 ppm on average (2,465 × 63-sample packets, zero 65). The clock algorithm limits its correction to ±2,000 ppm and cannot invent samples. This makes a transient or window-average PCM supply shortfall **quantitatively sufficient**, but it does not prove an actual peer clock drift: endpoints may cut through four-AU bursts, USB and mic snapshots have different capture times, and the “measured_rate” fields (64,796 → 64,916) are last completed ~1-second AACP grouping windows, not paired interval-average input rates. Do not diagnose a permanent 48/64 kHz mismatch or alter the clock.

**Arrival pattern:** Each interval showed exactly 75% sub-1-ms arrival gaps among observed AU increments (2,064/2,752 and 2,049/2,732), consistent with batched AACP delivery. At 192 there were 671 ≥15-ms gaps, versus 642 at 256; without their durations, USB-relative phase and intra-interval event timestamps, counts alone cannot establish a producer stall. Raw AACP timestamp step remained 180, with no reported discontinuity candidates; no conversion from unknown peer timestamp units to PCM time is justified.

## Source-path review and the 44 empty packets

1. **AACP producer:** `src/btstack/aacp_mic.c::au()` calls `aacp_mic_audio_note_au()` **before** the conditional enqueue (session started, capture wanted, watchdog not failed). The `observed` count is therefore not formally a count of admitted AUs. However, in the stable, unchanged generation-9 192 window, observed and decoded both advanced 2,732, with zero AU/stale/decoder errors and zero final AU backlog. This strongly weighs against missing or permanently unserviced compressed frames; individual AU identity still cannot be proven from aggregates.
2. **AU ring:** `src/btstack/aacp_mic_audio.c` uses a 32-slot release-published AU ring (`aw` written by core-0 radio producer, `ar` consumed by core-1 decoder). The consumer checks the generation and PCM space before decoding. No 192 AU overflow, stale count or end-of-window backlog. Lifetime `au_high` stayed at 8; it does **not** reveal the failing instant or certify that all service gaps were short.
3. **Decoder/PCM producer:** `aacp_mic_audio_work()` processes up to eight AUs/pass, then publishes 480-sample PCM frames to the 16-frame ring with release ordering. The USB consumer acquires `pw` and tracks its own `pcm_offset`. The coherent SPSC producer/consumer architecture appears appropriate for distinct cores; no demonstrated torn frame, duplicate consumer, epoch mismatch, decoder error or PCM ring overflow is present. This is not a proof against every weak-ordering or flash/XIP interaction.
4. **USB and priming:** `src/btstack/mic_clock.c::mic_clock_packet()` requires 4,800 queued PCM samples (75 ms) to leave unprimed state. It adjusts USB packet size by 63/64/65 samples within ±2,000 ppm and sets `primed=false` when `available < n`; no resampling occurs. `src/tinyusb/uac.c::tud_audio_tx_done_pre_load_cb()` substitutes 64 zero samples whenever the mic clock returns 0, and the capture-accounting callback records all 64 as missing. **The `pcm_primed=1` before/after values do not rule out an intervening unprime/rebuffer episode.** A returning `want=64` with a zero `aacp_mic_audio_read()` is a less-supported alternative that still needs a reason counter at the callback.
5. **USB capture lifecycle:** `usb_capture_set_alt`, mount, suspend/resume and real alt-0 close publish atomic capture intent. The measured 192 before/after states remained mounted/running/alt-1, unsuspended, capture generation 9, no PCM stale samples, and no short USB writes. A normal lifecycle restart during that interval is not supported, although USB callback cadence itself was never timestamped.
6. **Core-1 service:** In `src/main.c::mic_core1_entry()`, the persistent decoder is enabled only after its one-time FDK initialization. The worker performs bounded decode passes, immediately repeats if work remains runnable, or calls `sleep_us(250)`. Its `mic_core1_passes` counter is not included in the committed USB diagnostics. A nominal 250-µs sleep does **not** measure wake-to-decode latency under concurrent XIP, bus, allocator or IRQ activity. Conversely, the absence of AU drops and full PCM blocking plus empty end AU queue does not suggest sustained incapacity to decode 133⅓ AUs/s.
7. **Core-0 playback and contention:** `codec_fdk_fill()` encodes one ELD AU per foreground pass in the mic build, and `src_eld_encode_work()` still uses the CYW43 async lock on core 0. `a2dp_source_main_pending()` can suppress the core-0 sleep independently of microphone pending work. Concurrent FDK instruction/table XIP reads and SRAM writes on core 1 could alter core-0 callback scheduling, while the decoder may be delayed by bus contention. No per-core execution time, USB callback phase or memory-bus contention telemetry was recorded. 192 had 940 TX packets versus 998 in the separate dual 256 interval; this is a potential scheduling/airtime correlate, **not** a direct explanation of mic PCM loss.
8. **Flash lockout:** The dual build did not set global `PICO_FLASH_ASSUME_CORE1_SAFE=1`. Both cores register for `flash_safe_execute_core_init()`; BOOTSEL QSPI CS polling is disabled in this build. `settings_tick()` can commit ~200 ms after a setting change using `flash_safe_execute(...,500)`; core-1 is an SDK lockout victim. Profile changes were exercised without an observed reset, but no per-interval flash enter/exit/timeout counter or timestamp was saved. A short flash stall coincident with rebuffer is possible; it is **unproven** and should not be assumed to be the cause.
9. **Elapsed duration telemetry:** `decode_max_us=3,946`, `au_wait_max_us=18,808`, `work_max_us=24,011`, and `au_high=8/pcm_high=14` were already at these lifetime maxima at the **start** of 192 and unchanged at the end. Their persistence supplies no new 192 maxima and does not establish a healthy 192 tail latency. `decode_last_us` 2,486→2,593 and EMA 2,607→2,690 are snapshots of different moments, **not** CPU utilization. Playback `encode_max_us` increased 15,267→17,293 during 192, but wall-clock time includes preemption/contending execution; a new maximum cannot locate 44 separate zero PCM packets.

## Competing causes, predictions and falsifiers (ranked by current evidence)

| Candidate | Current support / caveat | Measurement that distinguishes or falsifies it |
|---|---|---|
| **A. Batched or briefly insufficient AACP PCM supply relative to USB clock, triggering rebuffer** | Strong aggregate accounting: 2,591-sample demand-minus-new-AUs gap, 44 fully empty packets, empty AU queue at both 192 endpoints; 75% burst arrivals and repeated ≥15-ms interarrival gaps. Clock is already correcting downward. | On each empty USB packet, capture **time since last admitted AU** and **time since last PCM publish**, AU depth, exact PCM available samples/offset and `primed` transition. If AUs are arriving on time, AU depth grows and core-1 is delayed while PCM empties, then A alone is insufficient. If AU depth remains zero and decode tracks recent arrivals, A is favored. |
| **B. Short-lived core-1 decoder scheduling/wake/dual-core XIP contention** | Plausible structural change from single-core; aggregate zero AU backlog does not rule out transient delays; 250-µs poll is only requested sleep, not actual latency. | Event-time queue residency histogram and core-1 wake-to-work / decode-publish gap; correlate with empty USB packets. Persistent AU backlog **while PCM < 64 samples** and long worker idle gaps favors B; zero AU backlog throughout and arrivals late favors A. CPU usage cannot be inferred from wall times. |
| **C. Temporary mic-clock de-priming and 75-ms rebuffer amplification** | 44 × 64 silent samples and code-level unprime logic are compatible. Both snapshots show primed, so any loss was transient. Whether 44 packets were one burst or multiple is unknown. | Count `primed → unprimed` transitions and classify callback zero as prefill, low-buffer rebuffer, or unexpected short read; record timestamps/start/end available. If no unprime occurred, investigate read/callback path instead. |
| **D. Core-0 USB callback timing / shared XIP, DMA, allocator or radio contention** | Changing cores can affect core-0 timing even without moving the USB code; short writes are zero but no inter-callback intervals were measured. | USB callback interarrival histogram, missed/late callback counter, last core-0 encoder block and decoded-publish event at each zero packet. No callback lateness and low producer supply falsifies USB scheduling as primary cause. |
| **E. Profile-switch settings flash lockout or other bounded stall** | Deferred settings write could coincide with early 192; no failure/reset, but no lockout timing or status telemetry. | Record settings dirty/commit start/end/RC and lockout duration plus the zero-packet timestamp. Fail if lockout errors occur; if no lockout intersects loss, E is falsified for that run. |
| **F. Mic USB lifecycle, sample-format or a permanent 48/64-kHz coding error** | Disfavored: generation, ready/rate (48 kHz coding, 64 kHz PCM), alt, capture and PCM stale counters stayed stable; 256 and single-core 192 passed. | On-target per-event generation/alt and sample-format evidence. Do not change protocol clocks or thresholds without contrary physical evidence. |

**Working diagnosis, not a claimed root cause:** The 192 interval incurred a temporary PCM delivery/priming deficit at USB deadlines. The decoded-versus-demand accounting and empty AU queue endpoints make a producer timing/clock-phase shortfall a higher-priority hypothesis than a permanently overloaded decoder; core-1 contention remains credible as a *transient* contributing factor or as a change to AACP arrival timing on core 0. The snapshots cannot establish which event first caused PCM to fall below its packet threshold.

## Smallest distinguishing regression, CI only (proposed; not implemented)

Add one deterministic **host regression** in the existing GitHub Actions codec/firmware test workflow; do not introduce a new firmware rebuild configuration merely to run it. Run production `mic_clock_packet()`, `aacp_mic_audio_enqueue/work/read()`, and `usb_capture_note_tx()` with the existing mock FDK at 1-ms USB ticks. Preserve **32 AU slots, 16 PCM frames, 480 samples/AU, 4,800-sample prefill, 63/64/65 packet policy and strict zero-loss assertions**. Allow a synthetic 4-AU/30-ms AACP delivery clock, explicit arrival timestamps and controlled decoder dispatch. Initialize/prime through the production API rather than forcing internal state.

Three table-driven schedules on identical total-AU budgets are sufficient:

1. **On-time reference:** regular 4-AU batch delivery plus promptly invoked decode. Assert no AU drops, zero silent USB packets after priming, decoded count and queue conservation.
2. **Producer-gap control:** hold one or more batches while the decoder drains all available input, then catch up with the **same total AUs**. Assert that nonzero missing USB samples can arise with zero AU drops and eventual empty AU backlog. Classify startup/rebuffer versus unexpected read failure from the callback reason instrumentation; this distinguishes A/C from a necessary decoder bottleneck.
3. **Worker-delay control:** deliver the identical on-time AU schedule but defer decoder passes for a prescribed interval. Assert a PCM-low/AU-nonempty signature before padding, then recovery with no ring/epoch corruption. This distinguishes B from upstream deficiency.

Include negative controls around capture generation and PCM partial-frame offset so `decoded × 480 − usb_pcm_samples` reconciles inventory; zero padding must **not** increment the decoded or actual-PCM count. Prefer a small host test, not a fabricated physical 192-kbps transcript: no per-packet arrival timestamps were committed. Run this regression only in GitHub Actions as required by `LOCAL-AGENT-TASKS-20261107.md`. An optional second, separately compiled real-FDK concurrency check can be run by Actions if event timing from the first run implicates FDK reentrancy; the existing host real-FDK parallel test already passed and by itself cannot validate RP2350 scheduling.

**Falsifiable decision rule:** If a promptly served decoder fed by an arrival schedule reproduces rebuffer, upstream timing/clock alone is sufficient for that synthetic trace. If only the delayed-worker trace pads, worker service matters. Both may be sufficient under different synthetic traces; the **on-device per-event queue and clock evidence** is required to select which occurred physically.

## Minimum low-overhead on-target telemetry for the next authorized experiment

No source modifications in this audit; the capture-lifecycle worker owns potentially overlapping modules. Propose an explicit API/ownership agreement before implementation. Counters should be monotonic and delta-scoped, and a tiny, bounded *first-underrun* event record should be copied or atomically published from the USB IRQ without printing, locking or allocating there.

1. **USB packet reason:** increment separate `clock_unprimed_wait`, `clock_underrun_reset`, `pcm_read_empty`, `pcm_read_short` and `reprime_success` counters. At the first loss, record `time_us_32`, `want/got`, pre/post `primed`, available PCM **samples** (not only frames), current `pcm_offset`, generation, `AU depth` and `PCM depth`. Count loss streak length and provide the first/last timestamp; `usbcapture.underruns` alone is insufficient.
2. **Producer versus decoder service:** record last successfully enqueued AU timestamp, last AU decoded start and last PCM publish timestamp; expose queue residence-time interval histogram or bounded maximum **with interval reset/epoch semantics**, current AU depth when PCM <64, and worker-pass count/last-pass time from core 1. A one-time `get_core_num()` confirmation and measured stack high-water (without unsafe diagnostic writes) are needed before qualifying core 1.
3. **USB service and producer cadence:** record USB callback interarrival maximum and any missing/late callbacks, plus last AACP SDU arrival timestamp and AUs-per-SDU (counts only; no audio/private payload). An optional bounded ring of first-fault interarrival deltas is more useful than an unqualified lifetime maximum.
4. **Flash and scheduling confounders:** record settings commit `flash_safe_execute` result code and enter/exit duration, count lockouts during capture and associate their timestamps with underrun events. Retain profile-revision/jitter and TX packet progression, but do not equate encode/decode wall-clock durations with CPU utilization.

All telemetry must be safe for a single core-0 USB consumer, core-0 AACP producer and core-1 decoder; use release/acquire publication and avoid changing ownership. Do not put USB serial prints or malloc on interrupt paths. Snapshot after a bounded **same-host, same-input, steady 256 → 192 comparison** and stop at the first strict failure. Capture simultaneous steady and first-fault counters before cleanup, and avoid a replacement 10-minute soak. If neither profile fails, the result is an inconclusive non-reproduction, not proof that the defect is fixed.

## Guardrails and remaining limitations

- **No fixes are implemented or assumed here.** Do not enlarge queues, change the 48 kHz AAC-ELD ASC or 64 kHz USB clock, raise PCM prefill, loosen strict zero-loss acceptance, bypass the flash lockout, restore unsafe QSPI BOOTSEL polling, enable the abandoned core-1 encoder or make dual-core the default.
- Do not conflate single-core lifetime AU drops from startup/interruptions with its **zero-loss steady** intervals. Do not compare lifetime maxima with one another as interval duration/CPU observations.
- This artifact uses **only committed sanitized metrics**. The raw local archive (SHA `ed2d1f9927f1766584a47c0df80098d4ecb5142173ae4149a7b95ea8e16999a2`) was not accessible or inspected. No AirPods packet-level delivery chronology, CPU utilization, measured core-1 stack high-water, inter-core XIP contention, firmware debug trace, live flash lockout outcome or cross-core acoustic result is available.
- Firmware and codec tests/builds, when later implemented, must run **exclusively in GitHub Actions**. The diagnosis branch makes **only this documentation addition**. Production modules, fixtures, GitHub workflows and other workers’ unpublished changes remain untouched.
- The observed dual-core 192 failure blocks production recommendation. Physical evidence shows the board was restored to the known single-core firmware. Any eventual patch needs separate CI validation, authorization and on-target verification.

**Disposition:** precise failure class and accounting established; first causal trigger **not** established. Diagnosis complete, awaiting separate implementation/measurement ownership.
