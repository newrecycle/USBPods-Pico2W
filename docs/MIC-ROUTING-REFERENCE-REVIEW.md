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
| Mic-triggered playback reset | None explicitly requested | Successful START queues a reset after 800 ms; STOP queues one immediately. This follows the LibrePods Linux lifecycle, not a hardware requirement established by the fork. |
| ELD RTP timestamps | Sample-count increments, frames × 480 | Millisecond wall-clock stamps inherited from the suggested Full source. The source comment attributes this to a macOS capture, which this review has not independently validated. |
| Playback encoder | 265 kbps CBR, SBR off | Negotiated bitrate ceiling, multiple rate/game profiles, including a VBR/SBR profile. Do not exceed the peer's accepted ceiling just to copy the fork. |
| No first microphone audio | STOP/START watchdog retry | No corresponding received-audio watchdog in the current channel state machine. |
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

No firmware behavior was changed for this research result. Existing coupled
tests verify our selected policy's implementation; they do not validate that
policy inside the AirPods. Hardware packaging remains paused.
