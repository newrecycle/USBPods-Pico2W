# Local Codex handoff

Start with [the resume prompt](LOCAL-CODEX-RESUME-PROMPT.md). This repository
contains the implementation and tests, pinned public references and licenses,
research notes, portable host-check commands and offline evidence. The cloud
workspace path is not required to continue.

## Goal, hardware and evidence

Priority: simultaneous AAC-ELD playback/microphone, negotiated multiple bitrates
and both game modes. User setup: Windows 11, Pico 2 W, AirPods Pro 3. Diagnostics
are USB-only: a single CDC COM port (previously COM3) plus USB audio/HID. Do not
ask for a USB-to-UART adapter. Native microphone use was confirmed by actual
dictation; concurrent playback was reported working to the user's knowledge.

Unresolved physical behavior: closing/disabling the microphone silences the
left AirPod; reopening output gives right-only playback, and activating the
microphone restores left playback. All recorded AVRCP multi-press attempts
looked like PLAY. Do not infer gesture type from timing between those commands.
The user revised the bass complaint after better A/B listening: quality on par,
possibly a slightly wider soundstage. No EQ change is justified by that claim.

The supplied Full bundle is incomplete, has no microphone implementation, and
contains further disassembly plus reconstructed source. It is suggested input,
not authoritative private code, a verified baseline or a proven best design.
The live runner previously overclaimed readiness; do not repeat that mistake.

## Current implementation and important chronology

| Revision | Meaning |
| --- | --- |
| `25ec7794` | Native mic/concurrent playback reported working; left/right symptom and Windows runner-format failure reported. |
| `101a970b` | Added automatic mic-triggered playback recovery and fixed Windows shared capture. Later capture exposed redundant profile restarts and peer START rejection 263. |
| `e5215bf7` | Idempotent effective profiles, atomic profile transaction, batched controls, host media arbitration, capture ownership and first-fault preservation. All three target jobs passed. |
| `b683ef44` | USB control bounds/rates/lengths and coupled mic/playback tests. All three target jobs passed. |
| `46ab10f1` | Documentation-only fork history review. Firmware code remained the preceding revision. |
| This handoff's source commit | Removes unconditional mic-triggered playback resets; adds received-audio liveness and bounded AACP-only retry. Exact source commit and CI outcome are in `evidence/current-validation.json`. |

The original left/right symptom predates automatic resets. Removing that
later policy cannot by itself be described as a demonstrated fix. The new
change follows the hardware fork's lifecycle and fixes a concrete missing
first-audio recovery path, while isolating its effect from codec/RTP changes.

The watchdog starts its two-second deadline after a successful START send.
Only a fully framed AU from the active AACP channel establishes reception.
No audio triggers STOP then START, with three retries per capture generation.
Only successful sends commit a retry. A late AU can cancel an unsent retry;
USB close/reopen and disconnect cancel obsolete work. Exhaustion sends a final
STOP, holds a visible capture fault until a new capture session, and leaves
playback running. Stale queued AU/PCM history is invalidated on wire transitions.
Selected jitter/game policy is reapplied through the existing delayed control
path without rebuilding playback. Explicit playback recovery remains available.

`:status` adds `mic_audio_seen`, `mic_watchdog_failed`, `mic_retry_count`,
`mic_restarts`, `mic_watchdog_failures` and `mic_audio_age_ms`; unknown age is
4294967295. `mic_started` still means START submitted locally.
`mic_recovery_pending` includes waiting for first audio or a current lifecycle
transition. Framed reception is not successful decoding; use decoded/error and
USB counters too. The runner saves exhausted-retry faults before stream cleanup.

## Where the work is

| Area | Files |
| --- | --- |
| Mic wire protocol, liveness and channel | `src/btstack/aacp_mic_protocol.*`, `aacp_mic.c` |
| Decoder, PCM queues, clock telemetry | `src/btstack/aacp_mic_audio.c`, `mic_clock.*` |
| Playback owner and encoder policy | `src/btstack/btstack_avdtp_source.c`, `eld_transition.*`, `eld_profile.*`, `eld_encoder.*`, `eld_codec_config.*` |
| USB capture, stereo data, controls and CDC | `src/tinyusb/uac.c`, `uac1_device.c`, `usb_capture_lifecycle.c`, `usb_serial.c`, `usb_descriptors.*` |
| CDC commands and diagnostic serialization | `src/control_command.*`, `src/device_control.c` |
| Live runner and packaging guard | `tools/live_test.py`, `live_audio.py`, `package_live_test.py`, `docs/validation-status.json` |
| Coupled behavior proof | `tests/test_mic_recovery_integration.py`, `test_aacp_transport.c`, `test_aacp_mic.c` |
| Real codec/audio proof | `tests/test_eld_duplex_fdk.c`, `test_pcm_packet_path.py`, `test_eld_frequency.c`, `test_mic_fdk.c` |
| Host replay/control/USB bounds | `tests/test_live_matrix.py`, `test_live_runner.py`, `test_control_status.py`, `test_usb_control_boundaries.py`, `test_uac1_controls.py` |

Read [offline findings](OFFLINE-TRIAGE-FINDINGS.md),
[the routing reference review](MIC-ROUTING-REFERENCE-REVIEW.md),
[reconstruction status](RECONSTRUCTION.md), [transition design](ELD-TRANSITIONS.md)
and [physical findings](LIVE-FINDINGS-2026-11-03.md). Older documents describe
historical implementations; the current source and validation record prevail.

The atomic command is `:profile RATE GAME LEVEL`, with rate 1/2/3, game 0/1,
level 1/2. Legacy preferences remain supported. The peer accepted ceiling must
be respected: do not blindly force the other fork's 265 kbps or promise 320 kbps
when the negotiated ceiling is 256 kbps. Codec clocks remain 48 kHz stereo
playback and 48 kHz coding / 64 kHz mono PCM microphone consumption.

## Reference and evidence inventory

- [Reference snapshots](../references/README.md) and `manifest.json`: han-um
  `d18d083`, LibrePods `99b0e58`, pinned BTstack `501e6d2`; licenses retained.
- `references/research-history.json`: relevant history and primary discussion
  URLs, including the direct one-AirPod symptom and hardware no-reset report.
- `docs/evidence/offline-host-results.json`: final host results in portable form.
- `docs/evidence/offline-session-logs.tar.gz`: archived cloud host/probe logs and
  experimental fixtures, with workspace paths normalized. It excludes raw live
  captures and the supplied Full bundle. Extract into a temporary directory.
- `docs/evidence/external-inputs.json`: names/hashes/provenance of original live
  bundles, supplied Full/disassembly inputs and derived binaries. Those inputs
  may already be on the user's local PC. Their availability is not required to
  build this independent firmware. Do not substitute them as authoritative code.
- `docs/evidence/live-capture-facts.json`: sanitized facts and transition timeline.
- `docs/evidence/current-validation.json`: exact source/CI state and remaining
  physical limits. A documentation-only commit may be newer than the tested
  source commit; use this record rather than guessing from the latest title.

## Handoff validation result

The firmware source at `7de213042d82367401aedef3a0e9a864f9ab6773` passed all three
[target compatibility jobs](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41746700880)
and the separate
[USB host job](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41746700738).
The portable local suite passed 56 commands with zero failures/skips. References,
archive member hashes and local documentation links were also checked. A later
handoff-record commit changes documentation/metadata only. These results do not
prove the physical left/right symptom fixed; no live package is requested.

## Safe local checkout

If starting fresh, run from a directory that does not contain the user's
existing experiment. Linux/WSL examples:

```bash
git clone https://github.com/newrecycle/USBPods-Pico2W.git USBPods
cd USBPods
git worktree add ../USBPods-local-mic-routing -b work/local-mic-routing origin/main
cd ../USBPods-local-mic-routing
```

For an existing clone, inspect `git status` and remotes, fetch `origin`, then
create the separate worktree. Do not reset or overwrite a dirty checkout.
Use new names if the suggested branch/worktree already exists.

## Offline host checks

The maintained host command manifest is `tests/offline-commands.json`.
The runner uses fresh temporary binaries and bounded subprocesses, writes full
logs to its output directory and prints concise results. Linux/WSL requires
native `cc`/`c++`, Python 3 and NumPy. CMake is needed to build native FDK.
The three SDK-contract fixtures use bundled reference snapshots by default;
`--sdk-source` can select a separate offline SDK source directory.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install numpy
python3 tools/run_offline_checks.py --build-fdk
```

Or supply an existing AddressSanitizer-instrumented native FDK archive:

```bash
python3 tools/run_offline_checks.py --fdk-lib /absolute/path/to/libfdk-aac.a
```

Without either FDK option, codec-dependent checks are explicitly listed as
skipped. See `build-offline-evidence/summary.json`. Do not call a partial run
full validation. ASan leak detection is disabled because the managed host
previously could not run LeakSanitizer; address/undefined checks remain enabled.
The suite is intended for Linux/WSL; native Windows sanitizer/toolchain support
has not been established. The Windows live runner remains a separate workflow.

For the old ignored-START regression, extract the archived `mic-watch-before.c`
and run `test_mic_recovery_integration.py --channel-source PATH --probe`;
that baseline is expected to fail. The current `--probe` is expected to pass.
The fixture uses deterministic SDK/peer/encoder mocks; real FDK is checked by
the separate duplex/PCM tests. None of these checks establishes radio behavior.

## Target build, using a dedicated SDK

The authoritative commands and package versions are in
`.github/workflows/pico-firmware.yml`. CI uses Ubuntu 24.04, a native compiler,
CMake/Ninja, Arm GCC/newlib, libusb/pkg-config and Rust 1.85.1 with target
`thumbv8m.main-none-eabi`. Install those locally before configuration.
Use a dedicated SDK checkout so patches/image selection cannot change another
project's SDK:

```bash
git clone https://github.com/raspberrypi/pico-sdk.git ../pico-sdk-usbpods
git -C ../pico-sdk-usbpods checkout bddd20f928ce76142793bef434d4f75f4af6e433
git -C ../pico-sdk-usbpods submodule update --init --depth 1
export PICO_SDK_PATH="$(cd ../pico-sdk-usbpods && pwd)"
export RUSTUP_TOOLCHAIN=1.85.1
rustup toolchain install 1.85.1 --profile minimal --target thumbv8m.main-none-eabi
git -C "$PICO_SDK_PATH/lib/btstack" apply "$PWD/sdk-patches/btstack-usbpods.patch"
git -C "$PICO_SDK_PATH/lib/tinyusb" apply "$PWD/sdk-patches/tinyusb-usbpods.patch"
python3 tools/btfw.py --sdk "$PICO_SDK_PATH" --image rpi0065 --output build-local-evidence
cmake -S . -B build-local -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DUSBPODS_BTFW=rpi0065 -DUSBPODS_MIC_DECODE=ON \
  -DUSBPODS_LITE=ON -DUSBPODS_REQUIRE_FULL=OFF -DUSBPODS_RELAY=ON
cmake --build build-local --parallel 2
stem="$(cat build-local/usbpods-output-name.txt)"
python3 tools/verify_build.py --build build-local --evidence build-local-evidence --stem "$stem"
```

Do not reapply patches blindly to an already patched SDK. Check its git diff
or start with a new dedicated checkout. CMake validates required patch markers.
Keep the project's default universal RP2350 board configuration; do not replace
it with a stock board name just to get configuration past an error.

The compatibility matrix also builds stock0031/transport and rpi0065/transport
(`USBPODS_MIC_DECODE=OFF`), plus diagnostic probes. CI separately checks 32-bit
codec allocation requests against the linked target heap region. Host estimates
do not prove target allocation deadlines or BT/USB scheduling.
This is an independent reconstructed build, not vendor Full. The required
Lite compatibility flags do not mean public vendor Full sources are present.

## Continue from here

1. Read `current-validation.json`, inspect local state and run applicable checks.
2. Review retry bounds, capture generation races, sent-versus-received status,
   and playback independence. Preserve the before/after proof.
3. Investigate remaining channel asymmetry using the reference review. RTP
   sample-count versus wall-clock policy, encoder profile differences and
   reset semantics are unresolved hypotheses; avoid changing all together.
4. Keep physical left/right, HID gesture semantics, RF timing and actual clock
   drift unverified until there is matching evidence. Current packaging is
   paused; this handoff does not request another live run or flashing operation.
5. Keep future logs and captured keys out of commits. Commit useful code/tests,
   sanitized evidence and explanations rather than generating another speculative
   package from build success alone.
