# AirPods microphone fork versus the radio-only update

Inspected 2026-11-03. This compares the current public USBPods source, our explicit
Lite baseline builds, the vendor Full production UF2, and han-um's microphone
fork. Static/binary findings are separated from author-reported hardware tests.

## Existing AAC-ELD and AACP support

Our source already implements AAC-ELD **encoding and A2DP playback** in
src/btstack/codec/codec_aaceld.c and the AVDTP source pipeline. That is the
computer-to-AirPods direction.

It also declares AACP APIs in src/btstack/btstack_aap.h. In Lite,
CMake links src/lite_stubs.c: aap_connect, control setters and other AACP APIs
are no-ops; getters report absent/unsupported features. In Full, real private
modules replace these stubs. The downloaded Full binary contains their logs
and control functionality.

The public USB audio scaffold also contains disabled microphone pieces:
- tusb_config.h sets CFG_TUD_AUDIO_FUNC_1_N_CHANNELS_TX to 0.
- src/tinyusb/uac.c comments out mic_buf and tud_audio_tx_done_pre_load_cb.
- The active tud_audio_rx_done_pre_read_cb reads speaker data arriving from the PC.
- The descriptor headers define speaker terminals, without a microphone stream.

Thus the source is not devoid of USB capture scaffolding. It lacks an enabled,
connected microphone path. Neither an AAC-ELD playback encoder nor AACP
battery/ANC controls supplies an AirPods-to-computer microphone path. The microphone requires transport framing,
start/stop, AAC-ELD **decoding**, PCM buffering and a USB audio input endpoint.

## Direct comparison

| Area | Our radio-only update | han-um microphone fork |
| --- | --- | --- |
| Controller firmware | Baseline 0031 and experimental RPI SDIO 0065 | Released v1.0.0 contains stock SDIO 0031 |
| AAC-ELD playback | Existing upstream encoder/A2DP path | Existing upstream encoder/A2DP path |
| AACP | Public API stubs in Lite; controls in vendor Full | Adds working channel management and microphone start/stop |
| Microphone transport | None added | L2CAP PSM 0x1001, type-0x58 audio SDUs |
| Microphone decoder | None added | AAC-ELD mono decoding, PCM ring |
| USB recording interface | None added | UAC2 isochronous IN endpoint 0x81 |
| SCO/HFP behavior | No demonstrated fix | Avoids SCO for the AirPods microphone; not a general HFP fix |
| Vendor Full feature parity | Missing private modules remain missing | Not equivalent to Full; an older application fork |
| Hardware evidence | No physical board available in this session | Author reports AirPods Pro 3 + Pico 2 W + Windows 11 testing |
| Original Pico W | Radio selection/probe can target it; current USBPods app is RP2350 | Author reports insufficient RAM for this decoder |

The two approaches are not alternative implementations of the same microphone
feature. Our update changes controller firmware; han-um adds the application
microphone path. The latter is the relevant implementation to evaluate for
AirPods Pro 3 microphone support.

## Binary checks of the microphone release

Source:
https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/releases/download/v1.0.0/PicoW_USB_BT_Audio.uf2

- UF2 size: 3,182,080 bytes.
- UF2 SHA-256: b9ff47d45aed5ba31692d1c7e0e137ad8d197a4dcc5531a5c50bf01b8db58d5a.
- 6,214 RP2350 Arm Secure payload blocks, plus one separate absolute-family
  compatibility block.
- Exact complete stock0031 Bluetooth payload appears once at 0x1014e000;
  rpi0065 is absent.
- The UAC2 configuration at 0x101145b8 contains speaker OUT endpoint 0x01
  and microphone IN endpoint 0x81 (130-byte maximum packet).
- Decoder/start/stop/stream telemetry strings are present.
- The source defines microphone sampling as 64,000 Hz mono and playback as
  48,000 Hz stereo.

This independently verifies that the release includes an application-level
microphone path with the older controller firmware. It does not independently
verify physical audio quality or AirPods interoperability.

## What private/full.cmake adds

The original file itself is not recoverable from a UF2. Its expected interface
is visible in public CMakeLists.txt, and its module boundary is documented by
src/lite_stubs.c. The following is an evidence-based inventory, not a claim to
have recovered the exact original file:

| Full component | Evidence and role |
| --- | --- |
| webhid_cmd.c | Named by Lite stubs; Full strings cover real configuration/feature-report handlers and settings |
| btstack_aap.c | Named by Lite stubs; Full contains AACP handshake, battery/noise/ear/game controls |
| btstack_sink_relay.c | Named by the stub section/header; Full contains phone SBC/AAC receive/decode/mix diagnostics |
| license.c | Named by Lite stubs; Full contains activation, entitlement and production-channel handling |
| Variant definitions/includes/output settings | Public CMake expects USBPODS_VARIANT_SOURCES, USBPODS_VARIANT_INCLUDE_DIRS, USBPODS_VARIANT_DEFINES, USBPODS_OUT_NAME and USBPODS_CHANNEL_DIR |
| Full output identity | The binary identifies USBPods_Pico2W, version 1.0.2+4, SDK 2.1.1, usbpods_universal |

Exact private include directories, additional crypto source/library lists and
compile definitions have not been recovered. The Full UF2 contains no microphone
streaming IN endpoint in its static descriptor sets and already contains exact
rpi0065 firmware. There is no evidence that a hidden Full CMake switch supplies
the missing microphone feature.

## Integration implication

Use han-um's source as a focused port/reference, rather than replacing our newer
tree wholesale. GitHub reports its main is 15 commits ahead and 38 behind the
current upstream, relative to common ancestor
7fdb1bf26e10018412ca448a5d22e95d1a9b124b. It predates the newer Full/Lite structure.

Preserving all vendor Full functionality still requires its private source
modules or an independent implementation of those features. The public Full
UF2 is useful binary evidence, not those original sources.

References:
- [han-um source](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/tree/d18d083bc52de3143d8d922c4abaae865cc0dc28)
- [Public Full UF2 inspection](PUBLIC-FULL-UF2.md)
- [Firmware investigation and hardware procedure](SCO-FIRMWARE.md)
