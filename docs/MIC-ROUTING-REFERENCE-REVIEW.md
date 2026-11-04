# Microphone routing: fork history and upstream discussion

This review follows the report that closing microphone capture silences one
AirPod, while activating capture restores its playback. It is a source/history
investigation, not evidence that the physical symptom has been fixed.

## Scope

Reviewed the public han-um fork's `main` and `hires-mic` branches, both pointing
to [d18d083](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/tree/d18d083bc52de3143d8d922c4abaae865cc0dc28).
The comparison against its pre-microphone base `7fdb1bf` contains 15 commits.
Also reviewed older playback history and the commits/comments in the fork's
source project, [LibrePods PR 655](https://github.com/librepods-org/librepods/pull/655).
The fork's issue list was empty at review time.

## Direct symptom match upstream

[Kavish's comment](https://github.com/librepods-org/librepods/pull/655#issuecomment-4854732405)
explicitly describes playback from only one AirPod. It says the Linux transport
reset can also switch the device into the headset profile, and recommends
switching the audio card off and back to A2DP instead of suspending the sink.
The same comment calls for disabling Conversation Awareness during capture.

[Commit 1f8948d](https://github.com/librepods-org/librepods/commit/1f8948d5dd9fb8679968c51b3a296810cadffa53)
implements that reset change: it replaces sink suspend/resume plus a 200 ms
sleep with card-profile off/restore and resumes previously playing media
players. [Commit 697ed3e](https://github.com/librepods-org/librepods/commit/697ed3ebf091c5305042cf3f0830e4210d0e260b)
also makes resetting optional. These are Linux audio-stack operations; they do
not establish that a Pico AVDTP SUSPEND/rebuild/START sequence is equivalent.

Most relevant to our hardware is
[han-um's reply](https://github.com/librepods-org/librepods/pull/655#issuecomment-4980170555):
the author reports simultaneous AAC-ELD playback and microphone operation on
Windows 11, Pico 2 W and AirPods Pro 3 without requiring a transport reset.
The final fork source agrees: mic START/STOP does not explicitly call an A2DP
reset. Its ordinary playback stall-recovery mechanism still exists.

This is a direct precedent for the symptom and a strong reason to revisit the
reset assumption. It is not proof that our failure has the same cause.

## Relevant commits in the hardware fork

| Commit | Finding | Relevance |
| --- | --- | --- |
| [104132a](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/commit/104132a7b9fad9265fdaca39bf94f354aa9785e3) | Adds the working USB microphone path with a distinct fixed 64 kHz clock and main-loop START/STOP. Notes stale Windows endpoint state after flashing. | Same host/board/AirPods generation. No per-bud connection assignment or mic-triggered A2DP reset is added. |
| [52e04c3](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/commit/52e04c3959d1569475702f67e5f6738365b83422) | Retries STOP/START if no mic audio arrives within the watchdog interval, including when the very first START was ignored. | Our `session.started` records successful local submission, not received microphone audio. A missing first-audio watchdog remains a concrete difference. It does not explain the reported working-mic/one-speaker state by itself. |
| [fbe93e7](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/commit/fbe93e77b9ad5f9d3ff83f963a076f25db6a6a10) | Removes blocking UART stdout after it interrupted audio. | Our runtime SDK UART stdout is already disabled; project diagnostics use USB. |
| [c33224d](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/commit/c33224db4e2a4cef6fdf17e8cf96ff9a7bb1842d) | Older inherited change moves USB/SBC buffer resynchronization and adds delays around reconfiguration/connection. | Its TWS-related title is tempting, but it predates AAC-ELD and the microphone implementation. It does not document this mic-dependent left/right symptom and is not a justification for copying blocking delays. |

## Byte and routing comparison

All five command arrays were compared byte for byte with our production
`aacp_mic_protocol.c`: handshake 16 bytes, feature flags 14, notifications 10,
microphone START 19 and STOP 12. They are identical. The review found no
transcription error or intentional left/right selection in our integration.
Identical undocumented bytes do not establish the meaning of every field.

Both implementations address AACP to the connected headset's Bluetooth address
and encode playback as stereo. They do not open one playback connection per
bud. This does not reveal which internal AirPods route or microphone is active.

Other significant differences remain:

| Area | Hardware fork | Current reconstruction |
| --- | --- | --- |
| Mic-triggered playback reset | None explicitly requested | The prior Linux-derived automatic reset has been removed. Capture and AACP retries do not rebuild playback; explicit source recovery remains separate. |
| ELD RTP timestamps | Sample-count increments, frames × 480 | Millisecond wall-clock stamps inherited from the suggested Full source. The source comment attributes this to a macOS capture, which this review has not independently validated. |
| Playback encoder | 265 kbps CBR, SBR off | Negotiated bitrate ceiling, multiple rate/game profiles, including a VBR/SBR profile. Do not exceed the peer's accepted ceiling just to copy the fork. |
| No first microphone audio | STOP/START watchdog retry | Now implemented with two-second silence detection and a three-retry budget per capture generation; exhaustion is observable over USB. |
| Conversation Awareness | No explicit capture-time policy in this fork | No automatic capture-time disable/restore policy. The upstream Linux discussion recommends one; our peer notification reliability is still unverified. |

## Chronology and next decisions

The user reported the left/right problem on
[25ec7794](https://github.com/newrecycle/USBPods-Pico2W/tree/25ec77940d9c477e7dd87ab22ac3975cea7c7fc0).
Its successful mic-command path only updates the sent state and logs START or
STOP. The automatic mic-triggered playback recovery was added afterward in
`101a970b`. Therefore that added reset cannot be the cause of the original
report, and simply removing it cannot be described as a demonstrated fix.

Prioritize received-audio liveness and the playback transport/format differences
over speculative per-bud addresses. Treat mic-triggered playback recovery as
an unverified policy choice. Keep explicit/manual fault recovery separate from
ordinary capture intent, and compare reset behavior without changing clocks,
encoder parameters and routing simultaneously. Do not infer success from a
locally accepted START command or from a build result.

The initial research result changed documentation only. The subsequent handoff
implementation removes unconditional playback reset and adds bounded AACP-only
liveness recovery. A before/after probe reproduces the ignored-START gap; coupled
tests verify capture isolation and profile races. They do not prove the physical
left/right issue resolved. Hardware packaging remains paused.

## Offline re-review after the isolation change

Reviewed locally in branch `work/local-mic-routing` at handoff source
`7de2130` (documentation-only HEAD `2503a52`; verified with
`git diff --stat 7de2130..2503a52`). The maintained host suite passes 56/56
with native FDK after a clang-only fixture fix, and the archived ignored-START
baseline still fails while the current probe passes. No hardware run or live
package is involved.

The three compatibility-matrix firmware targets (`rpi0065` with and without
AAC-ELD microphone decode, plus `stock0031`, all Lite/reconstructed) and both
SCO diagnostic probes were also rebuilt and byte-verified locally against the
pinned SDK and Rust toolchain; see
[`docs/evidence/local-target-builds.json`](evidence/local-target-builds.json).
That is build/link/UF2 evidence only. It does not execute firmware, and it does
not establish USB enumeration, radio behavior, HFP/SCO, microphone liveness or
the physical left/right symptom.

### What this pass establishes offline

- The USB capture path cannot request playback work: `usb_capture_lifecycle.c`
  only publishes intent through `aacp_mic_set_capture()`. The coupled test
  asserts `SUSPENDS`/`BUILDS` unchanged at each capture transition and that
  playback keeps streaming across open/close, retries, profile races and
  teardown (`tests/test_mic_recovery_integration.py`).
- The liveness watchdog is AACP-only: 2 s after a successful START send,
  three STOP/START retries per generation, only successful sends commit, and
  exhaustion sends one final STOP and stops AU enqueue while playback stays up.
  `aacp_mic.c` does not call `a2dp_source_recover_eld_stream()` or
  `a2dp_source_apply_eld_rate()` from capture lifecycle.
- The only sink-directed write clocked to a mic transition beyond AACP
  START/STOP is the deferred AACP `0x0b` jitter control:
  `a2dp_source_queue_jitter()` is reissued at channel open and after
  START/STOP, and the source defers it 500 ms while streaming
  (`src/btstack/btstack_avdtp_source.c:1622-1634`). The pinned working fork
  sends no `0x0b` writes in its snapshot. This remains an unverified
  reconstruction policy, not a demonstrated defect.
- An exhausted capture fault is cleared by a new capture generation or by
  AACP channel teardown. The teardown reset is required so a peer-dropped
  channel can reconnect and retry; retry counters are per channel attempt,
  not boot lifetime. The coupled test now pins this boundary and the handoff
  wording was corrected.
- RTP stamping is the plain millisecond wall clock
  (`btstack_avdtp_source.c:649-650`), the marker bit is always 0 (`:511`), and
  a detected send gap only increments `src_ts_snaps` and schedules a kick — it
  does not move the clock. A stale comment claiming gap compensation was
  corrected this pass; no behavior changed.

### Hypotheses still unresolved

| Hypothesis | Evidence available | Status |
| --- | --- | --- |
| RTP millisecond clock vs sample-count | macOS wire note used by the Full source; fork accumulates frames × 480 | Both are reported to play. One stereo A2DP stream carries both channels, so timestamp policy changes playout/jitter-buffer timing, not which bud renders. No host test pins it. Unchanged. |
| Encoder profile | Fork 265 kbps CBR/SBR off; this project negotiates 192/256/320 kbps with VBR/SBR on the VBR profile | Differences change bitrate/latency, not channel selection. The 101a970 capture contained a redundant profile rebuild and a rejected START (263); later transaction fixes cover that, not routing. Unchanged. |
| Reset semantics | LibrePods Linux card-profile precedent; working identical-hardware fork needs no reset; original symptom predates the added automatic reset | Removal is a controlled hypothesis. Sink decoder/TWS relay reinitialisation is the only documented mechanism that can change per-bud rendering, but our hardware has no capture showing it. Residual automatic resets (TX-stall recovery, suspended-stream self-heal) remain and could still fire if the pump stalls. |
| AACP `0x0b` jitter writes | Present here, absent in the working fork | Could reinitialise a sink-side buffer at exactly the mic transition; untested and unproven. |
| Windows endpoint churn | `src/tinyusb/uac.c` reacts to playback stop (`usb_stop_delay`, connmode 2 replug); mic open/close can make the host reopen streams | Offline code cannot observe host-side endpoint events; correlation logging is needed. |
| Per-bud TWS relay behaviour | Upstream one-bud comment; no AirPods internals | Only physical listening plus sink-side state correlation can establish it. |
| Conversation Awareness | Upstream Linux advice disables it during capture; this firmware has no capture-time CA policy | CA affects ANC/transparency, not proven to switch a bud. Adding speculative policy is out of scope. |
| HID/stem gestures | Recorded AVRCP attempts looked like PLAY | No gesture semantics added or inferred. |

### Proposed single-variable checks for a later authorized session

No live run is requested. When packaging is unpaused:

1. Log correlation across several mic toggles: CDC `:status` timestamps, mic
   START/STOP sent, `0x0b` jitter writes, ELD `SUSPEND`/`BUILD`/`DROP`, USB
   playback endpoint stop/reopen (`usb_stop_delay`) and the per-bud listening
   result. This separates a sink reaction to AACP traffic from host endpoint
   churn or an AVDTP rebuild.
2. If the symptom persists with no rebuild and no reset, the remaining
   suspects are the AACP START/STOP(+jitter) sink reaction or the host
   endpoint path; if it disappears, the removed automatic reset is implicated
   but the chronology still prevents calling it a fix.
3. Keep RTP clock, encoder profile and clock policy fixed in that session; they
   cannot select one bud and changing them would confound the result.
4. Require per-bud listening plus received/decoded and USB counters; do not
   infer success from an accepted START, a build or a runner preflight.
