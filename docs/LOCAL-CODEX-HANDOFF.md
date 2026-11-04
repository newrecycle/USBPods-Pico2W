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
No audio triggers STOP then START, with three retries per capture generation
(a generation also changes on AACP wire transitions). Only successful sends
commit a retry. A late AU can cancel an unsent retry; USB close/reopen and
disconnect cancel obsolete work. Exhaustion sends a final STOP, holds a visible
capture fault until a new capture generation or a new AACP channel session
(teardown clears it so a reconnect can retry; the retry counters are per
channel attempt), and leaves playback running. Stale queued AU/PCM history is
invalidated on wire transitions.
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

### Local continuation result (2026-11-03)

A local worktree (`work/local-mic-routing`) continued the review offline. With
native FDK on Ubuntu clang 22.1.2 the maintained host suite passed 56/56 at
that pass; the first run failed one generated C fixture under `-Wsign-compare`
(clang only; the CI gcc build had passed) and the fixture now uses an explicit
unsigned cast. The archived ignored-START baseline still fails as expected and
the current probe passes, preserving the before/after proof on this host. After
the static-review fixes recorded below the suite is 59/59. `7de2130` is an
ancestor of the worktree HEAD and the only later source changes are the review
fixes; the reviewed metadata remains current.

The three target compatibility-matrix builds and both SCO diagnostic probes
were then reproduced offline on the same host with project-local toolchains
(Arm GNU Toolchain 13.2.rel1 under `.tools/arm-gnu`, pinned SDK
`bddd20f928ce76142793bef434d4f75f4af6e433`, Rust 1.85.1 in a project-local
`RUSTUP_HOME`, host tools built with gcc-14/g++-14). Configure, build,
controller-image selection, `uart0076` audit and `tools/verify_build.py`
passed for all variants; commands, versions, deviations and the exact
ELF/BIN/UF2 hashes are recorded in
[`docs/evidence/local-target-builds.json`](evidence/local-target-builds.json).
This is build/link/UF2 evidence only: no device was flashed or executed.

Deviations from CI: the local host is Ubuntu 26.04 with CMake 4.2.3, so
`-DCMAKE_POLICY_VERSION_MINIMUM=3.5` was required by the legacy
`3rd-party/ldacBT` CMake file; `/usr/bin/c++` here is clang 22, so host
`pioasm`/`elf2uf2` were built with gcc-14/g++-14 instead. ccache, GitHub
Actions caches and the optional 32-bit codec-allocation audit were not
reproduced (the host has no 32-bit multilib and no sudo). Hardware behavior,
live packaging and the physical left/right symptom remain unreproduced and
rest on the physical limits above.

Review outcomes: retry bounds, capture-generation handling, sent-versus-received
status and playback independence were audited; the coupled test now also pins
that a channel teardown clears an exhausted fault (required for reconnect) and
that the counters are per channel attempt. The only remaining mic-lifecycle
write that reaches the sink beyond START/STOP is the delayed AACP `0x0b` jitter
control, which the pinned working fork does not send. Unresolved asymmetry
hypotheses and proposed single-variable checks are recorded in
[the reference review](MIC-ROUTING-REFERENCE-REVIEW.md#offline-re-review-after-the-isolation-change).
That isolation-review pass changed tests, documentation and one misleading
source comment only; no firmware behavior changed. The later static-review pass
did change firmware behavior, as recorded next.

### Static offline review (2026-11-03)

A whole-tree static review then ran on top of the local reproduction: three
scoped reviewers (USB/control, AVDTP/playback, ELD/mic/codec) plus one
main-loop/concurrency reviewer, followed by a single whole-codebase pass. Every
high/medium finding was reproduced against the source and fixed with a
regression that executes production bodies where practical. Fixed areas:
AVDTP pump-start-after-early-START, one-shot AVRCP volume seeding, teardown
flag clearing, checked discovery/capability/AVRCP/SDP returns and faithful
relay lifecycle mocks; USB mic-capture close only on a real alt-0 close,
atomic host-volume requests, a single advertised UAC2 format, RW speaker clock,
settings version validation and corrected console/storage comments; main-loop
audio slot queues allocated once (no `calloc` from the BTstack IRQ), cyw43
async-context locking for main-loop BT/AVRCP mutations, radio-absent guards and
a correct watchdog `scratch[7]` legend; ELD/mic resampler undersized-cap
refusal, one bounded rebuild on peer SUSPEND during managed WAIT_START,
transactional AAC-LC setup cleanup, idempotent ELD retry ladder, mic decoder
flush retry, and the 63/64/65-sample USB capture contract. A second pass on
the pinned candidate additionally bounded the untrusted inquiry-name copy,
made host mute a state (not a toggle), serialized main-loop TinyUSB writes
against the timer-IRQ `tud_task()`, matched the UAC1 44.1 kHz endpoint maximum
(180) to its advertised rate, and made the packaging gate require the 32-bit
codec-heap audit.

Finding-by-finding evidence, deferred items and limits are in
[STATIC-REVIEW-2026-11-03.md](STATIC-REVIEW-2026-11-03.md); the candidate
artifact hashes are in
[evidence/static-review-candidate-2026-11-03.json](evidence/static-review-candidate-2026-11-03.json).
Final end-to-end checks also found that two clean target builds of the same
commit had produced different UF2 hashes: FDK-AAC embeds its build date/time
in diagnostic strings and the boot banner printed `__DATE__`/`__TIME__`.
Commit `e8b6320` suppresses the FDK strings and prints `USBPODS_BUILD_SHA` in
the banner instead; two independent clean builds now produce byte-identical
firmware. Hashes stay tied to the embedded source SHA, so a later docs-only
commit rebuilds with a different SHA field, not different firmware sources.

Verification at the repair commit: host suite 59/59 with native FDK/ASan/UBSan,
all three target matrix builds and both SCO probes re-verified (UAC1 44.1
rate/endpoint check active), and the archived ignored-START baseline still
fails while the current probe passes. No live run, flashing or packaging was
performed, and the physical left/right symptom remains unverified.

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

For a rootless local reproduction (used 2026-11-03), the toolchains can live in
the git-ignored project tree: extract the Arm GNU Toolchain 13.2.rel1 tarball
under `.tools/arm-gnu`, install Rust 1.85.1 into project-local `RUSTUP_HOME` and
`CARGO_HOME`, and configure with `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` plus host
`CC=/usr/bin/gcc-14 CXX=/usr/bin/g++-14`. Those two extra flags compensate for
this host (Ubuntu 26.04, CMake 4.2, `/usr/bin/c++` = clang 22), not for the
project. See `docs/evidence/local-target-builds.json` for the exact commands,
pinned versions and artifact hashes of the rpi0065/AAC-ELD,
stock0031/transport and rpi0065/transport builds plus both SCO probes.

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

The physical 035227 capture supersedes the earlier offline throughput optimism:
pairing and mic-active stereo checks passed, but 256 kbps VBR+SBR lost over
80% of USB samples, and CBR/game modes still lost about 6–7%. USB disappeared
before capture-close/reconnect/soak coverage. Read
[DUPLEX-THROUGHPUT-035227.md](DUPLEX-THROUGHPUT-035227.md) for sanitized evidence,
the CBR mic-build policy, PCM backpressure and catch-up servicing repairs,
matching runner changes, and the remaining physical limits.

The cloud independent review of main `6be2889` found and reproduced three more
defects: a PCM queue reset/USB producer race, stale deferred START after SUSPEND,
and an ineffective empty-input FDK mic history clear. The subsequent repairs,
60-check offline result, real-FDK restart comparison and reproduction commands
are recorded in [INDEPENDENT-REVIEW-REPAIRS.md](INDEPENDENT-REVIEW-REPAIRS.md).
Use its source hashes and target CI record when identifying the repaired tree.
The physical left/right symptom remains unverified.

1. Read `current-validation.json`, inspect local state and run applicable checks.
   The host suite and the three target matrix builds have both been reproduced
   offline; `docs/evidence/local-target-builds.json` records the local toolchain,
   deviations and artifact hashes, and the before/after mic probe is preserved in
   `build-offline-evidence/` (ignored).
2. Re-check retry bounds, capture generation races, sent-versus-received status,
   and playback independence (audited offline in the continuation result above);
   preserve the before/after proof.
3. Remaining channel asymmetry needs physical evidence; the offline re-review in
   [the reference review](MIC-ROUTING-REFERENCE-REVIEW.md#offline-re-review-after-the-isolation-change)
   records the unresolved hypotheses, limits and proposed log-only checks. RTP
   sample-count versus wall-clock policy, encoder profile differences and reset
   semantics stay unresolved; avoid changing them all together.
4. Keep physical left/right, HID gesture semantics, RF timing and actual clock
   drift unverified until there is matching evidence. Live verification was
   authorized by repository-owner order on 2026-11-03 after the offline review
   and green CI build; candidate packaging is produced by the CI packaging
   step and still requires `build_verified` plus the 32-bit codec-heap audit.
5. Keep future logs and captured keys out of commits. Commit useful code/tests,
   sanitized evidence and explanations rather than generating another speculative
   package from build success alone.
