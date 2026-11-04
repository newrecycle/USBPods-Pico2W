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
