# Physical findings and next verification candidate

## Evidence from 25ec7794

The results bundle `USBPods-results-20261103T212827Z.zip` establishes the running
firmware identity, target connection, AACP handshake and five seconds of AAC-ELD
TX progression without media submission errors. The peer accepted a 256 kbps
ceiling. Requested rate 320 therefore ran as 256 kbps CBR, SBR off, nine slots;
that differs from the reference default 256 kbps VBR5/SBR1 profile.

The runner failed before opening capture: its selected Windows WASAPI endpoint
reported a 48 kHz shared format/two input channels and rejected the forced
64 kHz request. No microphone AU/PCM was collected by that run and no WAV was
created. Subsequent user observations establish that the native Windows
microphone actually works (including speech dictation) and, to the user's best
knowledge, works concurrently with playback. The runner failure is not evidence
of a broken microphone decoder or a wrong firmware PCM clock.

User-observed remaining failures:

- Closing/disabling microphone capture silences the left playback AirPod.
  Re-enabling output restores the right; activating microphone capture restores
  the left. Output and capture lifecycle are therefore not independent.
- The initial bass/quality impression was subsequently withdrawn after a better
  track and A/B comparison: the user judged quality on par, with a possible
  slight soundstage difference. A firmware-specific bass regression is unconfirmed.
- Single/double/triple presses all toggle Play/Pause. The capture contains nine
  AVRCP PLAY presses, each more than 1.3 seconds apart. It does not encode which
  gesture produced each press; reconstructing double/triple from those timings
  would invent information.
- Control readbacks timed out. The prior runner incorrectly required every
  write to echo and sometimes inspected cached values. That cannot distinguish
  failed application from absent feedback.

Removing both buds paused and reinsertion resumed, with discrete HID Pause/Play
logs. Either-bud-worn policy explains why removing only one did not pause.
Input gain adjusted through Windows is a separate observation from playback
volume. No physical HCI/UART adapter is part of this workflow; all diagnostics
are through USB CDC and HID.

## Implemented corrections

### Capture format and continuous diagnostics

The runner checks/opens the selected WASAPI endpoint's reported shared format,
then preserves the actual host sample rate and channel count in WAV metadata.
For the captured Windows inventory that means 48 kHz/two channels. It does not
relabel those samples as 64 kHz, mix away a channel, change the firmware USB
clock, or select the PC's default microphone. Firmware telemetry independently
checks its 64 kHz mono PCM cadence. A missing WAV now skips the listening prompt.
The writer regression checks actual 48 kHz stereo WAV bytes and frame count.

[Sounddevice settings](https://python-sounddevice.readthedocs.io/en/0.5.3/api/platform-specific-settings.html)
and [Microsoft device formats](https://learn.microsoft.com/windows/win32/coreaudio/device-formats)
distinguish shared mixer formats from hardware/exclusive formats. This Windows
fix still needs native execution; Linux host mocks are not a Windows test.

### Microphone transition recovery

The pinned upstream implementation resets A2DP after microphone START (800 ms
later) and STOP, explicitly describing corrupted AirPods transport state:

- [Microphone lifecycle](https://github.com/LuanAdemi/librepods/blob/99b0e580a93f2a26647f89816895ca1e5f70a3ec/linux-rust/src/audio/hires_mic.rs)
- [A2DP reset implementation](https://github.com/LuanAdemi/librepods/blob/99b0e580a93f2a26647f89816895ca1e5f70a3ec/linux-rust/src/audio/output.rs)

Our channel now queues recovery only after a successful START/STOP wire send,
with the same START delay. Main-loop polling submits it to the existing bounded
SUSPEND/encoder rebuild/START owner. USB callbacks do not allocate or issue
Bluetooth commands. Rapid transitions supersede old requests; unsent newer USB
intent postpones obsolete recovery; channel release cancels pending work.
Fault/user-disconnect holds prevent restart. The Linux reference toggles its
card profile off/on, so our AVDTP recovery is an analogous implementation,
not proof that every AirPods model will recover identically. Physical channel
independence and tonal quality must be checked again.

### Controls and stem evidence

Successful L2CAP sends now publish an independent counter plus the actual
control ID/value. Per-control notification sequences establish fresh readback;
a cached matching field cannot pass a new write. A bounded notification refresh
follows transmitted control changes. Missing echo is UNVERIFIED; submission
failure or contradictory fresh readback is FAIL. The upstream implementation
also notes missing Conversation Awareness echoes:
[control implementation](https://github.com/LuanAdemi/librepods/blob/99b0e580a93f2a26647f89816895ca1e5f70a3ec/linux-rust/src/bluetooth/aacp.rs).
We retain observed peer state rather than pretending transmitted intent is an
acknowledgment. Restores are checked for wire submission. Conversation Awareness
capture suppression no longer aborts the entire audio matrix solely for no echo.

Targeted logs capture received stem type/bud and button configuration IDs,
including unsupported long-press notifications. Arbitrary AACP packets and
pairing keys are not dumped. No speculative button configuration is written,
and missing gesture semantics are not guessed. Stem mapping remains unresolved
until relevant peer events/configuration are observed.

## Bass investigation and verification

The source PCM/encoder settings were compared with the reconstructed reference,
which remains a suggested implementation rather than authoritative private
source. A new real-FDK test measures 40, 80, 160, 1000 and 6000 Hz through the
production encoder and actual decoder at 192 CBR, 256 VBR/SBR, 256 CBR and
320 CBR. Measured gain ranges from approximately +0.003 to -0.077 dB; bass loss
relative to 1 kHz is under 0.1 dB. Wrong-channel energy is below the test's
-40 dB limit. These results rule out a large bass rolloff in that synthetic
encoder path; they do not prove correct AirPods rendering, rule out complex
music artifacts, or validate acoustic quality. Firmware radio/decoder routing
and capture transition state remain plausible causes. No tonal correction is
claimed from these offline measurements.

## Next single-session coverage

The runner retains rate/game transitions, microphone-open Bluetooth reconnects,
a ten-minute duplex soak and continuous USB diagnostic queries. It adds:

1. Left-only/right-only listening while capture is active.
2. A familiar-music bass/depth comparison with Full while capture stays active.
3. Microphone-only close/reopen while the output stream remains open, with
   left/right listening in each state and a steady duplex counter check after
   reopen. Transition padding is separate from steady-interval failures.

Known physical failures remain listed in `validation-status.json`. A replacement
package is a controlled verification candidate after its exact target workflow
passes; this report does not claim those audible failures are already fixed.
