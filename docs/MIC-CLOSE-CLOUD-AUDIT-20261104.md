# Microphone-close routing: independent cloud investigation (2026-11-04)

## Immutable identity and evidence classification

The investigation starts from `18be74cfe99f2584bcf26a0c0f0571c75a7f7bec` on its own branch, not current main. The last **physically tested** firmware was `880dc318072f191f1440d3f0b262d83e32729b59`; the pinned newer candidate passed CI but was not flashed. Raw capture archives remain on the user's machine and are not part of this investigation. No local dirty checkout was touched; the branch was created remotely from the exact SHA.

**Observed on hardware** (not reproduced here): `docs/LOCAL-WINDOWS-20261104.md` and `docs/evidence/local-windows-20261104.json` record pure-tone stereo with microphone open and reopened, but silence in the left ear with capture closed while the right remains correct. This held after MaxxAudioPro was disabled on the laptop; that software's mixing did not explain earlier PC failures (the PC had no enhancements). A saved-bond ACL reconnect restored left audio with capture still closed. One explicit manual ELD refresh timed out in WAIT_START, causing a local ACL termination; it is not a spontaneous peer termination. A 45-second supplemental 256-kbps duplex interval had zero AU/PCM losses; 192 kbps lost 186 AUs and 95,168 USB samples. The already-completed 600.539-second soak on `2911a824` is retained, not repeated (7 AU drops, 14,656 missing samples against strict zero-loss criteria).

**Established by code/history:** `25ec7794` documented the left/right symptom before `101a970b` added automatic microphone-triggered playback reset; its later removal cannot alone establish a repair (`docs/MIC-ROUTING-REFERENCE-REVIEW.md`). The `2911a82` repair described in `docs/DUPLEX-LIFECYCLE-042523.md` removed the extra 0x0b jitter write on mic START/STOP; there is no physical successful close result attributable to it. All five AACP sequences in `src/btstack/aacp_mic_protocol.c` matched pinned han-um `d18d083bc52de3143d8d922c4abaae865cc0dc28` (provenance `references/manifest.json`); the Full reconstruction is not an authoritative implementation. `docs/ELD-TRANSITIONS.md` requires ELD reset only for explicit recoveries, profile transitions or independent stall events.

## Relevant production call paths

- Mic: `src/tinyusb/uac.c:tud_audio_set_itf_close_EP_cb` handles only mic alt-0 as a close; `tud_audio_set_itf_cb` and `src/tinyusb/usb_capture_lifecycle.c` combine mount/suspend/alt into capture intent. `src/btstack/aacp_mic_audio.c:aacp_mic_set_capture` increments the generation on a changed intent.
- Channel: `src/btstack/aacp_mic.c:aacp_mic_poll -> next_command -> aacp_mic_watch_target -> aacp_mic_next` chooses STOP on closed intent. `handler(L2CAP_EVENT_CAN_SEND_NOW)` recomputes intent, sends the unchanged 12-byte STOP, records successful send, invalidates mic AU/PCM generation, and does not invoke playback recovery or a jitter reapply. AACP control writes are a separate priority lane in `src/btstack/aacp_control.c`. AACP channel reconnect resets session, but mic close does not disconnect ACL.
- Speaker: `src/tinyusb/uac.c:tud_audio_rx_done_pre_read_cb -> audio_slot_push_samples` retains interleaved L/R stereo PCM; `src/btstack/btstack_avdtp_source.c` encodes and sends AVDTP/RTP independently. Its managed SUSPEND/START, peer events, or TX-stall self-heal can interrupt playback independently of mic close. USB speaker alt-0 has an independent close/flush callback; mic alt-0 should not invoke it.
- Diagnostics: the optional `U` PCM tap in `uac.c` already reports pre-gain L/R peak every 500 ms but does not label capture state. AACP STOP logs currently assert "playback unchanged" rather than recording the contemporaneous observed playback/capture state. Those logs cannot prove acoustic output.

## Competing explanations

1. **Peer/TWS transition on valid AACP STOP** (plausible; untested): failure closely follows STOP, is recovered by mic START or saved-bond reconnect, and stereo host playback remains open. Neither a single AVDTP connection nor unchanged AACP bytes proves how the earbuds internally route audio. Against: no sink-side trace or comparison with a STOP-free legitimate close is available; STOP cannot be suppressed to hide the fault.
2. **Independent ELD pump reset or USB speaker endpoint churn** (possible; untested): recovery/stall logic and speaker alt-0 can act independently; source tests show distinct call paths, not that they never happen near mic close in the field. Against: confirmed playback endpoint was kept open, and the normal mic path does not request suspend/rebuild.
3. **Windows host produces no left-channel data after capture closes** (possible, weaker after reconnect): laptop enhancements once mixed audio, but disabling them restores isolated tone behavior except on close; no pre-gain PCM snapshot tied to the final close event was supplied. A reconnect without reopening capture restored left sound, making a persistent host mute less likely. Earlier PC issue was independent of MaxxAudioPro.
4. **Wrong AACP START/STOP bytes, mic clock, encoding profile or RTP stamp** (not supported): commands match the pinned source, the speaker is one stereo RTP stream and the fault toggles with mic intent. These parameters can affect latency/audio quality, not select an individual earbud in our known code. No wire bytes, clocks or encoder policy will be changed.

## Minimal discriminator and implementation plan (written before code changes)

Maintain all current audio/clock/controller behavior. First run the existing production-body offline fixtures: `tests/test_usb_control_boundaries.py --case valid` / `--case alternate`, `tests/test_mic_recovery_integration.py`, `tests/test_aacp_transport.c`, and `tests/test_usb_host_input.c`. Their baseline should show correctly isolated USB mic alt-0 STOP and AVDTP state, not an acoustic repro.

**Proposed narrow instrumentation repair:** in the optional UAC speaker PCM tap summary, include the **current USB mic capture-running bit** alongside existing left/right peak and packet counters. At a successful AACP START/STOP, replace the unconditional text "playback unchanged" with the measured local capture-generation and `a2dp_source_is_playing()` state. Do not log addresses, raw PCM, keys or unknown AACP payloads. Do not change command bytes, debounce/delay STOP, auto-reconnect, or keep capture open after alt-0. Add a source-body regression covering USB speaker/mic alternate boundaries and the requested diagnostic correlation. The old diagnostic lacks a capture tag (expected failing baseline); the new one must contain it while ordinary routing tests continue to pass. CI success would establish only firmware correctness/build, not a physical fix.

**Smallest later physical acceptance:** with enhanced audio disabled, maintain speaker playback and send isolated left-only/right-only tones. Record `U` tap L/R peaks and the START/STOP+AVDTP log/status during one mic open -> close -> reopen sequence. Require correct left/right ear output at all three states and confirm capture=0 and no new AVDTP SUSPEND/START on close. If the tap shows left PCM after close but the ear is silent, pursue AACP/TWS peer behavior; if the tap loses left PCM, pursue host USB endpoint/routing. No new soak or automatic reconnect should be used.

## Constraints and remaining uncertainty

No hardware access, Windows endpoints, raw captures, peer ACK for STOP, ear-specific radio state or acoustic validation. Protocol bytes, 48/64-kHz clocks, RTP timestamp policy, game/bitrate profiles, and multicore architecture remain unchanged. Passing tests cannot be called a repair to left-ear silence. Likely integration conflict surface: a separate worker may concurrently edit `uac.c`, `aacp_mic.c` or their test fixtures; this work stays on its own branch and must be cherry-picked deliberately.

## Offline implementation and validation result

**Repair status:** diagnostic isolation, not an acoustic repair. No AACP START/STOP bytes or command ordering, microphone USB intent/generation rules, playback encoder, audio routing, clock, RTP policy, restart, or multicore code changed. The attached changes deliberately enable one discriminating experiment; a peer-side routing diagnosis still requires listening on hardware.

| File | Change | Public interface |
| --- | --- | --- |
| `src/tinyusb/uac.c` | In optional `U` stereo PCM summaries, tag measured microphone intent as `mic=open`, `mic=closed`, or `mic=transition`; a window crossing a USB mic state change cannot be misrepresented. The first actual PCM packet establishes the initial capture state even if a 50-ms tap tick initialized the time window while idle. Zero-packet reports include current intent. | Existing CDC text gains `mic=` field; no new callable API |
| `src/btstack/aacp_mic.c` | On successful AACP START/STOP print measured capture bit, mic generation, and AVDTP streaming status instead of the unconditional and unprovable `playback unchanged` claim. | Existing CDC log line gains `capture=`, `mic_gen=`, `a2dp_streaming=`; no new callable API |
| `tests/test_mic_close_tap.py` | Compiles actual production PCM tap and timer callback function bodies with deterministic stereo left/right PCM, alternate capture intent, and a timer-before-packet case; verifies source lane peaks and transition-state labels. | New offline test, no firmware interface |
| `tests/offline-commands.json` and `.github/workflows/pico-firmware.yml` | Register the new source-body regression in local host suite and every firmware CI matrix job. | Build/test configuration only |
| This document | Preserve evidence provenance, hypotheses, test plan and remaining limits. | Documentation only |

**Before/after local host reproduction:** a manually compiled Linux GCC/ASan/UBSan fixture containing the pinned production `usb_pcm_tap_feed` body showed five 500-ms L/R signal windows, but its old diagnostic lacked microphone state. The state-aware diagnostic produced the expected `open / transition / closed / transition / open` classifications while retaining left-only peak 1200 and right-only peak 1100 in their respective windows. This is a reproducible *observability* before/after, not reproduction or repair of silent left-ear acoustic output. The added regression compiles the production function body directly and includes an idle timer-before-first-packet negative-control case. CI must run this at the final source SHA before a target build is considered validated.

Host replay entry points from repository root:

```sh
python3 tests/test_mic_close_tap.py
python3 tests/test_usb_control_boundaries.py
python3 tests/test_mic_recovery_integration.py
python3 tests/test_eld_foreground.py
python3 tools/run_offline_checks.py --build-fdk
```

The `--build-fdk` run requires native SDK dependencies; without FDK the runner explicitly skips codec-dependent commands, so a partial host suite is not full validation. The GitHub target workflow runs the independent stock0031 transport, rpi0065 transport, and rpi0065 AAC-ELD builds and production host tests. Final CI result and exact branch SHA must be checked from the run itself; historical passes do not establish a new firmware binary's correctness.

**Integration hazards:** `uac.c` is also edited by USB/HID workers and `aacp_mic.c` by AACP workers, so integration should cherry-pick these two small logging hunks against current work and rerun each owner's tests. No other worker branch is touched. The optional `U` tap logs aggregated pre-gain USB samples; it does not inspect the transmitted AAC frame, peer decoder, TWS forwarding, or actual ear output.
