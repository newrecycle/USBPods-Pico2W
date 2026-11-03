# Full edition requirement and wireless firmware investigation

**Current microphone work:** [AACP-MIC.md](AACP-MIC.md) documents the newly added AACP USB microphone transport and optional experimental decoder. This uses a distinct path from HFP/SCO. The investigation below describes the earlier radio-only baseline; no physical microphone success or generic SCO fix is claimed. Full integration additionally needs an adapter for the private AACP channel.

**The requested final deliverable is the vendor Full edition, not Lite.**
The public repository does not include its `private/full.cmake` or proprietary
Full modules. Connected repository search currently finds only this public fork.
The fork now defaults to `USBPODS_REQUIRE_FULL=ON` and fails before any Lite
fallback. A manual Full Actions build also checks for the missing modules before installing tools. The workflow now defaults to explicit Lite baseline builds at the user's request while Full inspection continues.

**Status: Full build blocked on authorized Full sources.** Earlier successful
stock0031/rpi0065 artifacts are Lite baseline evidence only. They do not satisfy
the Full deliverable and are not a substitute for it. The expanded diagnostic
verification run was canceled when the Full requirement was clarified.
No Full artifact or working SCO patch has been produced.

Keep proprietary Full sources in an authorized private build context. Do not
commit them into this public fork. A prebuilt Full UF2 cannot substitute for the
source modules needed to rebuild with a controller-firmware change.


Goal: build USBPods for Pico 2 W with a compatible controller firmware update,
and identify whether SCO/HFP can be enabled. **No SCO fix or microphone support
has been established by this work.** Compile success is separate from hardware
startup, synchronous-link completion, and end-to-end microphone audio.

## Firmware selections

| Selection | Source | Purpose |
| --- | --- | --- |
| stock0031 | Pico SDK 2.1.1 cyw43-driver pin | Upstream USBPods baseline |
| rpi0065 | Raspberry Pi SDIO/37MHz image from pinned cyw43-driver | Experimental radio-firmware upgrade, with the rest of SDK 2.1.1 unchanged |
| Infineon 0076 UART/26MHz | Pinned Longma firmware | Audited, not installed: different transport/configuration |

Both selected images are unchanged vendor bytes, verified by header and payload
SHA-256 before installation into an isolated SDK. This preserves signed
configuration. No UART-to-SDIO conversion, configuration grafting or signature
mutation is represented as a fix. A newer version number does not prove that
the Linux SCO fix applies to this transport.

USBPods' own sdk-patches/README.md requires 0031 and records reverting a previous
0065 experiment. The rpi0065 artifact is deliberately an A/B investigation
build, not an upstream-supported upgrade.

References:
- [USBPods HFP request](https://github.com/wasdwasd0105/USBPods-Pico2W/issues/25)
- [Pico SCO failure](https://github.com/raspberrypi/pico-sdk/issues/1461)
- [Infineon release and firmware](https://github.com/Infineon/ifx-linux-bluetooth/tree/e5f0a31b95d51bbeb7ea5ef152ab0ff563961ff8)
- [Independent 1YN transplant experiment](https://github.com/LegitCamper/cyw43_iso/blob/0e26e30400f067be8d72273cc33e124187461b9a/analysis/hardware-results.md)
  reports that full Murata 0071 and a code-only transplant failed to reach HCI
  readiness. That experiment concerns ISO research; it is evidence about startup
  compatibility, not a test of our HFP diagnostics.

## Reproduce the build

Run **Pico firmware build** Actions. Its default is the explicitly requested temporary Lite baseline; select edition=full only after providing authorized Full source modules. Each radio-image selection can build either the explicit Lite baseline or vendor
Full USBPods image, according to the edition input for the upstream universal RP2350 board (including Pico 2 W),
plus separate SCO diagnostics for stock pico_w and pico2_w board definitions.

The SDK is pinned to 2.1.1 commit
bddd20f928ce76142793bef434d4f75f4af6e433. Its BTstack and TinyUSB patches are
applied before configuration. Rust is pinned to 1.85.1 with the
thumbv8m.main-none-eabi target. Full is blocked before compilation until its modules are supplied. Lite builds proceed. Jobs retain firmware manifests, artifact
hashes, CMake configuration, and compile commands.

Verification checks the exact complete controller payload in the linked binary,
its ELF symbol size, UF2 block integrity, and reconstruction of the flash binary.
It does not execute a Pico or validate the radio.

## Hardware acceptance, not yet run

Use only the UF2 matching the board. Full USBPods currently targets RP2350 and
cannot be flashed to RP2040 Pico W. The **probe** supports both; the underlying
controller-image selection is the same for them.

1. Save your working firmware first. Hold BOOTSEL and copy the selected probe
   UF2 to the board. Open its USB serial port. Send `?` followed by Enter.
2. Require `phase=ready`. An init failure or startup timeout is a failed
   firmware startup, not proof of an SCO connection.
3. Put AirPods/headset into pairing mode. Send `s` plus Enter; then
   `c AA:BB:CC:DD:EE:FF` using its actual discovered address.
4. Require `SLC_COMPLETE status=00`. Send `a` plus Enter.
5. Require `SCO_COMPLETE status=00` and `RESULT SCO_LINK_ESTABLISHED`.
   `SCO_REQUEST status=00` means only that the host accepted the request.
   A missing completion or `RESULT TIMEOUT phase=sco` is a failure.
6. Record board, firmware selection, headset/firmware, and the complete serial
   transcript. Repeat with stock0031, then rpi0065. Disconnect/replug between
   attempts; a wedged controller can outlive an HFP reconnect.
7. Restore your saved working USBPods UF2 and verify playback.

The probe intentionally offers CVSD only to isolate basic SCO establishment.
It does not send voice audio, provide a USB microphone, validate mSBC, or prove
call quality. Its deadlines run on the host event loop; if the transport itself
wedges, they may not execute and the board must be reset.

## Remaining blocker

A vendor-supported SDIO/37MHz CYW43439 image containing the SCO fix has not been
located. The published 0076 image is UART/26MHz. Hardware testing of 0065 is
still required, and the upstream discussion reports SCO failures with that
version. After controller SCO works, USBPods still needs microphone descriptors,
capture buffering, an HFP audio pipeline and playback/call mode transitions.
Those are not provided by swapping a Bluetooth patch image.

See [Public Full UF2 inspection](PUBLIC-FULL-UF2.md) for the downloaded vendor binary, exact radio-image identification, and a separate AirPods microphone implementation lead.
