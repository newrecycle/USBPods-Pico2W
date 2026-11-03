# Public Full UF2 inspection — 2026-11-03

This is a static inspection of the production Pico 2 W download referenced
by https://hub.usbpods.com/ . No board was flashed and no runtime microphone
or SCO test was performed.

## Download and image identity

| Field | Observed value |
| --- | --- |
| Firmware URL | https://hub.usbpods.com/firmware-latest/pico2w/USBPods_Pico2W.uf2 |
| Manifest URL | https://hub.usbpods.com/firmware-latest/pico2w/latest.json |
| Manifest | name 1.0.2, code 4 |
| Embedded program / version | USBPods_Pico2W / 1.0.2+4 |
| Embedded board / SDK | usbpods_universal / 2.1.1 |
| Embedded application build date | Sep 1 2026 |
| UF2 size | 3,686,400 bytes |
| UF2 SHA-256 | 503218b796c41a76134e310597d0d0bace15cf5e261ce9442d884b7146f31699 |
| UF2 blocks / family | 7,200 / 0xe48bff59 (RP2350 Arm Secure) |
| Flash address range | 0x10000000 through 0x101c1fff |
| Contiguous flash payload | 1,843,200 bytes |
| Flash payload SHA-256 | b5dd43b8394e4a00671576d19b5db1e6d256abf8ede203917614418beb6fedf6 |

Every UF2 block passed the magic, payload-size, numbering and total-count
checks; overlapping bytes were checked for agreement. The extracted flash
payload has no gaps.

## Bluetooth controller image

At flash address 0x10187618 the Full binary contains the complete 6,970-byte
controller image:

`CYW4343A2_001.003.016.0065.0000_Generic_SDIO_37MHz_wlbga_BU_RPI_dl_signed`

Its SHA-256 is
`d974384d0aa8124d30084f30d13519a3ed3b9f759f7ddd6a34ef3dcf1441bcf7`.

This is an exact whole-payload match to the pinned rpi0065 image used by this
fork's passing Lite baseline build, not merely a matching version string.
The stock0031 payload was not found.

**Replacing this Full download's radio image with rpi0065 would therefore be
a no-op. It does not supply a newer SCO fix.**

## USB microphone and HFP evidence

The image contains complete static configuration-descriptor sets at:

| Address | Kind | Audio-streaming endpoint |
| --- | --- | --- |
| 0x1014cea0 | Audio-disabled HID/CDC/vendor configuration | none |
| 0x1014cf10 | UAC1 | OUT 0x01, 192-byte maximum |
| 0x1014cfec | UAC1 variant | OUT 0x01, 192-byte maximum |
| 0x1014d0c8 | UAC2 | OUT 0x01, 196-byte maximum |

None of these sets contains an isochronous audio-streaming IN endpoint for
microphone capture. Other IN endpoints belong to interrupt/control, HID or
CDC functions. This is static evidence, not a live enumeration.

Application log strings describe an HFP battery-only service and unexpected SCO
handling. Generic HFP microphone-gain and SCO strings also exist in the linked
BTstack library; their presence is not evidence of a USB microphone path.
The Hub's public JavaScript separately treats Pico2W status byte 26 as lacking
call support.

The Full image does contain AACP controls, phone-relay and activation-related
application strings. Those demonstrate compiled Full modules, not recoverable
original C source. No activation mechanism was modified or exercised.

## Separate open-source microphone lead

[han-um/USBPods-Pico2W-2-way-audio-implement](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement),
inspected at commit d18d083bc52de3143d8d922c4abaae865cc0dc28,
implements an alternate AirPods microphone path:

- L2CAP PSM 0x1001 and type-0x58 AACP microphone packets;
- AAC-ELD microphone decoding;
- a USB microphone streaming interface at 64 kHz.

The source contains the implementation, not just README claims. Its author
reports hardware testing with Pico 2 W, AirPods Pro 3 and Windows 11.
We have not reproduced that hardware test. It avoids the SCO link used by HFP;
it is not a general HFP firmware fix and not a drop-in replacement for all vendor
Full features. The author says this decoder does not fit the original Pico W.

## Build status distinction

The vendor Full edition remains the desired final deliverable. Its source
modules are not included in the public repository. At the user's request,
Actions now defaults to explicit Lite baseline builds while Full UF2 inspection
continues. A manual Full selection still refuses Lite fallback.
