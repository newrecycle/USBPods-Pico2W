# Experimental core-1 microphone decoder

The project now supports an **opt-in** `-DUSBPODS_DUAL_CORE_MIC=ON` build
(requires `-DUSBPODS_MIC_DECODE=ON`). Default is OFF. Its UF2 filename ends
`_EXPERIMENTAL_Core1Mic`. It is compiled by CI but explicitly excluded from
automatic live-test packaging. No hardware acceptance is claimed.

## Why this worker, not the old encoder

The existing `core1_aaceld_encoder_loop()` is *still disabled*: it uses
`handleAAC`, shared with the core-0 fill/encode/rebuild/release paths, has no
stop/idle acknowledgment before a handle can be destroyed, and its encoded
ready queue is not consumed by the production A2DP packetizer. A `volatile`
activity flag does not synchronize lifetime. Re-enabling the old launch would
reintroduce a use-after-free risk.

Instead, the microphone decoder is initialized once on core 0 before radio
startup, then only `aacp_mic_audio_work()` runs on core 1. The AACP AU producer
and USB PCM consumer remain on core 0. Existing release/acquire SPSC rings
carry data; neither core issues new Bluetooth/USB operations. Core 0 still
owns the playback encoder and profile rebuild. No extra codec allocation is
performed in the worker. Both coding rates, AACP commands, USB descriptors,
packet/clock policy and playback lifecycle are unchanged.

## Flash and BOOTSEL rules

`PICO_FLASH_ASSUME_CORE1_SAFE=1` has been removed. Both cores call
`flash_safe_execute_core_init()`, with a bounded READY acknowledgment before
entering the main loop. SDK multicore FIFO is reserved for flash lockout, not
application messages. This permits existing settings flash writes to request
a safe SDK-mediated stop of core-1 XIP access.

The custom BOOTSEL reader drives QSPI chip select and briefly disables
external flash access; masking core-0 interrupts does not stop core 1.
The experimental build does **not** schedule BOOTSEL polling. CDC reset and
picotool BOOTSEL flashing still work. The original single-core build preserves
the existing button polling.

An explicit aligned 16 KiB decoder stack is reserved; that size is not a
measured upper bound. Worker failure to register lockout fails closed rather
than proceeding without coordination.

## Tests and remaining acceptance

- Host: the same production compressed AU and PCM queues are exercised with
  producer/decoder/USB consumer threads and ASan/UBSan, plus source guards.
- CI: the normal three variants plus an experimental core-1 AAC-ELD variant
  must compile against the pinned/patched SDK. Success is not live verification.
- Physical test **not performed**. Before any experimental flash, review linker
  RAM/stack high-water, allocator and FDK-global concurrency, lockout behavior
  during settings/TLV commits, USB servicing and watchdog behavior. Include
  profile rebuilds, reconnects, mic open/close, drop/underrun counters and
  sustained duplex timing. Left/right AirPods routing and the 48/64 kHz
  cadence are independent questions not solved by moving decode.

Future encoder offload must introduce a single encoder owner, generation-tagged
buffer protocol and acknowledged STOP/IDLE before any rebuild or release. This
branch intentionally does not claim that work completed.

## Safety review correction (before live use)

The initial opt-in implementation placed core-1 startup after settings/JEDEC
operations, leaving an unsafe gap with the implicit assumption removed.
Corrected: core 1 launches and registers its flash-safe lockout victim IRQ
immediately after core 0, *before* settings migration, flash TLV access and
boot-time JEDEC/QE commands. It idles behind an atomic decoder-enable flag
until the main core finishes allocating/configuring FDK. Both cores must be
registered before any SDK flash_safe_execute call; startup fails closed
otherwise. JEDEC, QE register updates and WIP polling now use
`boot_flash_do_cmd`, whose SRAM callback is protected by
`flash_safe_execute`. Legacy single-core builds keep the accurate
`PICO_FLASH_ASSUME_CORE1_SAFE=1` flag, applied only when the second core is
not used; otherwise SDK flash_safe_execute rejects single-core flash writes.

The SDK's `multicore_launch_core1_raw` temporarily disables the core-0 FIFO
interrupt during its startup handshake, then restores the flash-lockout IRQ.
This sequencing was checked against the exact pinned pico-sdk revision
`bddd20f928ce76142793bef434d4f75f4af6e433`.

## Actual concurrent FDK host regression

The dual-core CI variant also compiles `tests/test_eld_duplex_fdk.c` in a
host-pthread mode, with the repository's **real FDK-AAC** library linked. The
microphone FDK decoder runs in a separate thread while the playback encoder
continues across 24 rate/game/profile rebuilds and 3,072 stereo ELD encode
frames. Real compressed mic AUs are produced before playback work and decoded
through the production AU/PCM queue. The test checks decoded-frame shape,
microphone PCM amplitude and generation continuity. After joining the decoder
worker, the existing deterministic real-FDK microphone disconnect, history
reset and full-queue backpressure regressions still run unmodified.

This is a host concurrency test, **not** proof that the RP2350/XIP/USB scheduling
is safe or that the peer accepts every profile in the physical environment.
