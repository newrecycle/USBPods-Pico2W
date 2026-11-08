# Independent online-only USBPods integration report — 2026-11-07

## Audit and source identity

- Source at intake: `work/local-windows-followup-20261107` = **`2cc988df66b7ad84cdfdb2ae89b9e93604c87c0b`**.
- Main at intake: `018685157ab8c5dedc66008e2e54ae3a38994e25`, ancestor of follow-up (31 commits behind, 0 ahead).
- Isolated implementation: `audit/sequential-validation-online-20261107`, draft PR [#7](https://github.com/newrecycle/USBPods-Pico2W/pull/7) targets follow-up, **not main**.
- The first independent commit `a3d80037adda24aed3222101f5453047b8fd5f82` contains the pre-edit [evidence ledger](INDEPENDENT-ONLINE-REPAIR-LEDGER-20261107.md).
- **Exact compiled/tested production source:** `a25c4635829d06e82563add659fd5489fd1061e5`. This report is a subsequent **documentation-only** commit; do not reuse `a25c463`'s artifact hashes for a different source without checking the embedded manifest.
- Last **physically flashed** firmware remains `1979ae6be1c2daf9e1db8024763504d4061c4588`. **Nothing in this audit was physically flashed**, and no raw audio, Bluetooth addresses, keys or private captures were copied.

## Ordered independent commits

| Commit | Scope |
|---|---|
| `a3d8003` | Evidence ledger, priorities, reproduction plan **before** source edits |
| `17d57ef` | Race-safe, USB-consumer-owned first post-prime loss provenance; cumulative post-prime fault/rebuffer counters and producer/PCM timestamps |
| `fd8ddb4` | Actual production AU/PCM/clock schedule tests, backlog-vs-no-producer and rebuffer checks |
| `c34937a` | Failing provenance and strict missing-sample negative controls added to the existing firmware workflow |
| `67eb9c5` | Host output-callback progress gate; firmware TX progress cannot stand in for output stimulus; simulated callback-stall fixture |
| `d2e4a95` | Same real-FDK AAC-ELD encoder persists across production USB capture alt-1 → alt-0 → alt-1, with separate phase channel energy and a deliberate close-phase mute |
| `c6e4abf` | Existing real-FDK workflow requires phase-specific mute negative control |
| `a25c463` | Corrected an old test assertion that still required a success result when the new negative-stimulus fixture correctly returned failure |

No additional firmware variant or workflow was added. The existing four Pico firmware configurations and Windows launcher job were retained.

## Findings and honest classifications

### MIC-01 — left channel silent after microphone closes

**Historical physical FAIL, not fixed on hardware.** The source-scoped November 7 recording for `1979ae6` reports left audible with mic open, silent while closed, audible again when reopened. Phase-matched post-gain/pre-FDK left-only PCM remains about L=316–317, R=1 throughout. Explicit K refresh and a separately tested saved-bond reconnect restore left while capture stays closed. The working closed-state right-only observation came from an earlier separate trial. No fault-phase emitted compressed-AU capture, peer-received RTP or AirPods internal rendering evidence is available.

**Fixed/reproduced offline: synthetic sender continuity is now covered.** The existing real-FDK regression linked actual production USB capture lifecycle and actual PCM gain, queue, codec, Apple AU framing/sequence, MTU and decode. It now holds a **single encoder handle** through an open → closed → reopened microphone, verifies left-only decoded channel energy separately for all three phases, and demonstrates that deliberately zeroing decoded left PCM **only in the closed phase** fails. Existing decoded L/R swap negative control still fails as intended. Capture/AACP/ELD coupled production-body tests independently verify that STOP/START does not restart playback, rebuild ELD or issue a mic-triggered jitter command. This rules out some generic deterministic regressions; it **does not** rule out the actual source's on-device codec output, peer control effects, TWS receiver state or radio loss.

**Unresolved hypothesis:** an AACP STOP-induced peer receiver/routing transition versus a sender-only fault not represented by synthetic inputs. No speculative automatic K/reconnect, undocumented commands, microphone clock changes or automatic playback refresh were introduced. The falsifier remains fault-phase encoded/decode evidence plus a bounded `-MicCloseOnly` physical listening comparison.

### CORE1-02 — experimental 192 kbps PCM gap

**Historical physical FAIL, root cause unknown.** Source `1979ae6`, opt-in core1: +44 missing USB packets, +2,816 missing samples, zero new AU overflows. With no 65-sample requests during the failing interval, 44×64=2,816 means each affected packet had a full 64-sample PCM deficit. Observed 2,732 decoded AUs imply 1,311,360 PCM samples; USB demand was 1,313,951 and actual PCM read was 1,311,135. The 2,591 net newly decoded PCM-vs-USB demand deficit plus the 225 retained-sample difference exactly accounts for the 2,816 padding. Snapshot boundaries and the unreported PCM partial-frame offset preclude declaring a permanent peer clock drift or a contiguous 44 ms gap. No profile-specific timestamps of events or flash/XIP contention were recorded.

**Offline reproduction and instrumentation, not timing repair:** existing production-linked clock/queue scenarios distinguish no AUs arriving (empty compressed AU queue) from a stalled decoder (backlogged AUs) with the same strict USB losses, without AU overflow. Added `micunderrun` CDC record includes sticky first **post-priming** fault time, generation, exact request/supply, AU/PCM depth, available PCM, latest admitted AU age, PCM publication age, rebuffer trigger; monotonic counters include post-prime faults and rebuffer transitions. The USB callback only performs bounded atomics and unchanged strict USB accounting. These data can help distinguish producer gaps from worker delays. They do **not** independently measure RP2350 core affinity, XIP flash stall, USB IRQ latency, physical FIFO underruns or peer RF data. First fault is sticky until reboot; it must be correlated with the operator's interval timestamps, not presumed to belong to 192.

**Status:** core1 remains experimental, opt-in **OFF by default**, with no automatic package; neither the 48/64 kHz clocks, AU=32/PCM=16 slot limits, 4,800-sample priming target, flash lockout policy nor decode scheduling have changed. No claim that core1 192 kbps is repaired.

### LIFE-03 — AU loss/capture epochs

**Offline behaviors covered:** production AU and PCM ring generation retirement (including 16 full stale PCM frames and a partially consumed old frame), delayed first USB consumer, producer and worker-gap timing, strict expected/got USB accounting, PCM-full backpressure and real 32-slot AU overflow are tested in existing GitHub Actions fixtures. Deliberately claiming zero USB loss in a delayed worker schedule fails the exact assertion; deliberately claiming zero queued AU at a worker-stall first fault also fails the exact assertion. Neither stale cleanup nor PCM fullness is counted as a synthetic loss-free pass. USB remains sole consumer of PCM read offset.

**Historical evidence / unknown:** single-core 192 accumulated 1,412 PCM-full worker exits but no steady AU loss. Lifetime AU overflows reached 248 across startup, interruptions and lifecycle; none can be assigned to a particular cause from sanitized totals. First Windows input callback, WASAPI handle exclusivity, callback scheduling on RP2350 and hardware startup epochs still need physical timestamps, not new offline claims.

### RUN-04 — runner and CI integrity

**Offline false-positive class repaired:** the actual live audio runner formerly used changing firmware TX counters and host input metrics without requiring **any current-phase host output callback**. A fixture deliberately suppresses every output callback while allowing fake firmware TX counters to advance. Production now counts host output callbacks per phase and marks unavailable stimulus as unverified; an output-less steady interval fails rather than passing, and mic-reopen steady results include callback/collector gating. A callback still proves **only host buffer production**, never acoustic AirPods playback, physical stimulus arrival or an autonomous Desktop turn. Phase transitions have callback overlap uncertainty; no exclusive ownership has been invented.

Existing watcher/runner tests confirm exact push-source SHA, most recent attempt per run ID, failure/cancel/skipped as not success, first-fault preservation and Desktop-owned record-only. A prior accepted callback or CLI exit remains **UNVERIFIED** for autonomous Desktop resume. No actual Desktop turn was observed.

The new output-callback fixture uncovered an outdated assertion: runner workflow `42428065513` **FAILED** at `67eb9c5` because the final old assertion wrongly expected PASS from the correctly failing probe; `a25c463` reconciled that expectation, and the subsequent exact-SHA runner passed. Intermediate builds `42428065506`, `42428206165` and runner `42428206188` were canceled during newer pushes; they do not establish success. An earlier `c34937a` source passed standalone USB and runner workflows but not this final source matrix.

### SETUP-05 — prior AVDTP setup failure

**Earlier repaired and supported by earlier physical evidence:** `e9f5482` setup failed to configure media. `1979ae6` moved SDK accepted-response label retirement before reentrant callback and subsequently connected in real hardware. Existing production 15-label reentry regression includes an older negative baseline. No new SDK or peer command modification was needed.

## Exact-source GitHub Actions results

All required **push** workflows for `a25c4635829d06e82563add659fd5489fd1061e5` have terminal success at **attempt 1**:

| Workflow / run | Outcome and relevant gate |
|---|---|
| [Pico firmware build 42428254636](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/42428254636) | **SUCCESS**: all five jobs, including stock0031 transport, rpi0065 transport, rpi0065 AAC-ELD, rpi0065 experimental core1 and Windows launcher |
| [USB capture and HID host tests 42428254674](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/42428254674) | **SUCCESS**: production helper tests and callback wiring |
| [Live runner host regressions 42428254666](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/42428254666) | **SUCCESS**: production host runner/mock Desktop ownership, simulated stream and launcher contracts |

In the default AAC-ELD job, the production AU/PCM clock schedules and both deliberate-failure controls, **real FDK encode/decode channel/Apple AU fixtures with both swap and mic-close-mute negative controls**, the **positive 32-bit codec allocator audit**, firmware build, **linked radio image/UF2 verification**, authorized package gate and artifact upload all completed successfully. The experimental core1 job also passed real FDK, 32-bit allocation, build and UF2 verification. Its production schedule step (default-mic-only) and automatic live-test packaging step were **intentionally skipped by the existing workflow condition**; do not confuse them with validation failure or core1 hardware acceptance.

### Artifact ZIP digests (GitHub Actions)

These digests are for **uploaded workflow artifact archives**, *not individual UF2 binaries*. Per-file hashes and embedded source SHA are enforced separately by existing verification/package code.

| Artifact ID / name | GitHub SHA-256 digest |
|---|---|
| `13596133946` `pico2w-lite-rpi0065-aaceld` | `141b1fd759ef929304dc9015cb31837ee51948df784b5fc4fddb7e8c7d7268bc` |
| `13595854553` `pico2w-lite-rpi0065-aaceld-core1-experimental` | `3f9250d64cfa3ae4f61a156cb45cd48ef97050d9c839a0a07e153c90657ab3b3` |
| `13596078975` `pico2w-lite-rpi0065-transport` | `c9c2569b99379150e2912a95144d147b940498f19093fe82fe8aec25fb0c8fb9` |
| `13595769730` `pico2w-lite-stock0031-transport` | `5796891d572db7674f2b96662e4758cb189b9ca9a9f6a0198ee8bc610ecd2fae` |

**Evidence limits:** no physical mic-close acoustic pass, real AirPods media/peer decoding, 192 kbps core1 acceptance, USB RF/clock drift, Apple HID OS delivery, ANC/gestures, actual WASAPI exclusivity, flash lockout timing, core1 stack high-water, or autonomous Windows Desktop continuation was measured. A green firmware Actions run is never a hardware acceptance pass.

## Minimal future owner-only acceptance

After review and **explicit human authorization to flash** an exact-source/hash-verified single-core package, back up the known-good UF2 and use the existing short interactive launcher mode (it **flashes the UF2**, so do not invoke casually):

```powershell
.\Run-Test.ps1 -CdcPort COMx -MicCloseOnly -ReusePairing -StageSeconds 10
```

Choose the actual current CDC port, ensure saved target selection is unambiguous, and keep one playback output open while listening to isolated left/right windows at microphone open → closed → reopened. Keep operator observations, CDC `micunderrun`/AU/USB/ELD snapshots and any local audio recordings **off GitHub**. If silence reproduces, mark as FAIL and optionally perform **one separately labeled manual K refresh** as a discriminating control; no automatic reconnect or repeated ten-minute soak. Do not run core1 until a separately authorized short targeted 256→192 measurement is justified. No worker accessed COM, the device, raw archives or Desktop.

## Integration decision

**Ready for code review, not physical acceptance or merge.** The new code changes observability and host evidence gates, and is validated by exact-source GitHub Actions. The two top-priority physical faults remain unresolved; do not announce an acoustic or real-time core1 fix. Preserve PR #7 as draft until reviewed and accepted by the owner. 
