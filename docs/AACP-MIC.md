# Experimental AirPods microphone

This change adds an application-level AirPods AACP microphone path alongside the pinned `0065` Raspberry Pi SDIO controller image. It does not claim to fix generic HFP/SCO (pico-sdk issue 1461). The microphone travels over L2CAP PSM `0x1001`, independently of the existing AAC-ELD A2DP speaker stream.

Two explicit Lite test builds are produced for Pico 2 W:

| Build | USB capture | Decoder |
| --- | --- | --- |
| `USBPods_Pico2W_Lite_AACP_Transport.uf2` | 64 kHz mono 16-bit; silence | None; reports received AACP SDUs/AUs |
| `USBPods_Pico2W_Lite_AACELD_Mic.uf2` | Same format; decoded PCM, silence on missing/error frames | Experimental FDK-AAC ELD, ASC `F8 E6 30 00` |

The Full edition still requires vendor private sources. These builds do not recreate Full controls, relay, activation, or private AACP implementation. Full is deliberately refused until a single-channel integration adapter is available. The application targets RP2350; only the independent SCO diagnostic is also built for Pico W. Do not flash the RP2350 application to Pico W.

## Implementation

* UAC2 has a distinct microphone AS interface and isochronous IN `0x81` (maximum 130 bytes), with a separate read-only 64 kHz clock. Existing stereo speaker descriptors keep their clock. UAC1 remains speaker-only.
* A new USB identity avoids stale host descriptor caches. Decoder and diagnostic identities differ. Press `u` in the CDC console to select UAC2, then replug, if the device is currently in UAC1 mode.
* An Apple Device ID SDP record uses handle `0x10006`, distinct from HFP's `0x10005`. Re-pair the AirPods after flashing so they rediscover it.
* AACP sends handshake, feature flags, notifications, then START when capture is open and a control response has been seen. Closing capture sends STOP. USB suspend parks capture; resume restores it only when the microphone alternate setting is still open. Unmount clears that intent. Intent is recomputed at send time so an early close cancels a pending START. Connection attempts, initialization wait, and failed sends are bounded.
* Audio subtype `0x58/0x0001` has a 22-byte header followed by `[u32 little-endian timestamp, u8 length, AU bytes]` records. The entire SDU is validated before any AU is delivered. No decoded content is logged.
* Optional decoding runs in the main loop, never in the USB or radio IRQ. Decoder allocation/configuration occurs before BT starts. Bounded SPSC queues use C11 release/acquire publication. Generation tags discard stale PCM after USB close/reopen and Bluetooth disconnect/reconnect while preserving the USB recording intent. Decoder failures and queue overflow are counted; no allocation occurs per packet.
* The inherited ASC `F8 E6 30 00` explicitly reports **48 kHz** to FDK. The reference fork exposes the resulting 480-sample frames at a **64 kHz USB clock** (7.5 ms per AU). These are intentionally distinct; this implementation preserves that reference behavior and checks the actual ASC-reported 48 kHz mono/480-sample format. Physical timestamp/cadence and pitch validation remain required. The fixed USB packet cadence is 64 samples per millisecond. Clock drift, buffering, underruns and concurrent playback resource use need physical testing. No resampler or adaptive drift controller is claimed.

Protocol commands, framing and ASC are adapted from [han-um's GPL-3.0 fork](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/tree/d18d083bc52de3143d8d922c4abaae865cc0dc28), whose implementation derives these from [librepods](https://github.com/librepods-org/librepods). New modules retain GPL-3.0-only notices. FDK-AAC retains its own notices/license.

## Hardware acceptance

No attached Pico/AirPods hardware has been exercised by this change. Passing CI establishes compilation, protocol/state tests, descriptors and binary packaging, not working audio.

1. Start with the `rpi0065-transport` artifact. Flash only the application UF2, re-pair AirPods, use UAC2, and open the CDC serial console. Expect `[mic] AACP opened`, `confirmed=1`, then `START sent` only after a recording application opens the mic.
2. Record for 30 seconds. This build intentionally records silence. Expect `sdu`, `au`, and `bytes` to rise, with `malformed=0`. Close recording: expect `STOP sent`. Rapidly open/close, disconnect/reconnect, unplug/replug and suspend/resume. Verify the speaker keeps working and capture never starts by itself after closure.
3. If transport works, flash the AAC-ELD build. Expect `AAC-ELD decoder ready` (48 kHz ASC / 64 kHz USB clock), increasing `[mic-dec] ok`, and your voice in a 64 kHz mono recording. `allocation/configuration FAILED` disables START in the decoder build; use the diagnostic build to isolate transport.
4. Test simultaneous stereo playback and recording for at least 10 minutes. Check decode errors, queue drops, maximum decode duration, audible artifacts and resets. Test repeated recording sessions for stale audio. Report logs and whether AirPods Pro 3 are paired to another device.

Local/CI tests include a synthetic 32-frame sine round trip through the actual repository FDK encoder/decoder using the exact inherited ASC (48 kHz mono, 480 samples), plus mocked decoder integration tests for queue overflow, stale audio generations and decode/format errors. This is not an AirPods packet fixture or a hardware audio test. They also cover transactional rejection of malformed packets, exact wire commands, deferred start/stop coalescing, UF2 corruption, and both UF2 flash families plus Pico 2 W compatibility blocks. The build verifier checks the linked UAC2 microphone endpoint and separate clocks, unchanged UAC1 speaker descriptors, and the selected radio blob in the linked binary and byte-for-byte UF2 reconstruction.

Local configure requires the SDK patches described in `sdk-patches/README.md` and:

```sh
cmake -S . -B build -DUSBPODS_LITE=ON -DUSBPODS_REQUIRE_FULL=OFF \
  -DUSBPODS_BTFW=rpi0065 -DUSBPODS_MIC_DECODE=ON
cmake --build build
```

CMake defaults to `rpi0065`; CI also builds a `stock0031` transport baseline. The radio header is hash pinned and cached when already correct. Switching images updates a shared SDK file, so use a separate SDK checkout per concurrent build.



## Reference integration, 2026-11-03

The transfer bundle is disassembly/reference material. Its reconstructed files
are not a replacement for this fork. The current open-source builds now share
one AACP channel between microphone lifecycle and bounded control intents.
Noise, personalized volume, conversation awareness, adaptive strength and
jitter use 11-byte commands; getters report validated peer notifications rather
than pending intent. Battery notifications validate the complete counted list,
handle the combined-buds component and clamp levels to 100. Channel teardown
clears observed state and pending controls. Microphone start/stop has priority.
Setters serialize with the CYW43 async context, including playback-recovery
callers. Only the channel owner performs L2CAP writes.

Command provenance: the vendor image with SHA-256
503218b796c41a76134e310597d0d0bace15cf5e261ce9442d884b7146f31699 has
jitter builder `FUN_10016698` and control parser `FUN_10015dbc`; librepods
AACPManager at 89356c08cea3db0b6b54792d9329d09a87cc85fa corroborates IDs and
Boolean encodings. This change retains the existing microphone provisioning;
it does not add the seven-command Full replay. Jitter accepts the reference
values 30/60/90/150; noise 1..4; Boolean controls 1/2; adaptive strength 0..100.
These are bounded reference domains, not validated support for every model.
Unknown/malformed notifications cannot confirm microphone startup. Ear packets
have no host-media side effects in this stage.

The AAC-LC source now restores the shared slot size from FDK's actual frame
length after configuration, instead of retaining ELD's 441/480-sample size.
The real FDK host fixture checks ELD followed by 48/44.1 kHz LATM AAC-LC
round trips. It does not execute the application's whole codec-switch state
machine or establish physical playback quality.

New host regressions exercise the actual transport implementation with mocked
SDK events: wrong-CID data/close, malformed confirmation, failed-send retry,
mic priority, clearing pending controls on reconnect, and failed can-send
requests. Pure control tests cover transactional battery updates, exact command
bytes, value validation, coalescing and observed-versus-pending state.

Remaining Full reconstruction work: WebHID command/report adapter, ear/stem
policy, deliberate provisioning/feature negotiation, and corrected optional
phone relay with a microphone/relay memory policy. Full remains unavailable in
this build; WebHID/relay stubs remain. No vendor activation module or speculative
probe is imported. Hardware testing is deferred at the user's request.


## CDC line controls

The existing USB CDC serial console is the first independent control transport.
Existing single-key commands continue to work. Send a colon-prefixed line with
CR or LF termination; lines over 31 characters or with invalid syntax are
rejected and discarded through the next newline. Responses start with
`[control] ` followed by a single JSON object, interleaved with ordinary logs.

| Command | Meaning |
| --- | --- |
| `:status` | Channel/confirmation state, observed controls and battery |
| `:noise 1` .. `:noise 4` | Off / ANC / transparency / adaptive |
| `:pvol 0` or `:pvol 1` | Personalized volume off/on |
| `:ca 0` or `:ca 1` | Conversation awareness off/on |
| `:aa 0` .. `:aa 100` | Adaptive strength reference value |
| `:jitter 30`, `60`, `90`, `150` | Queue a reference jitter value |

`queued:1` means accepted into the current session's bounded command queue; it
is not acknowledgment by the earbuds. Query `:status` for observed values.
Unknown noise is 0; unknown pvol/ca/aa is -1; absent battery is 255, otherwise
low 7 bits are percent and high bit indicates charging. A disconnect clears
pending commands and observed peer values. Invalid values or no open channel
return `queued:0`; radio-absent boards return an error. Before radio startup,
control getters return unknown values without touching the async context.
This transport uses existing CDC descriptors; it adds no USB HID dependency.
A future Web Serial or desktop UI can use this command layer. Physical CDC
and AirPods interoperability testing remains deferred.
