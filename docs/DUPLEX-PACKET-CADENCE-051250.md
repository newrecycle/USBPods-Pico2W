# 051250 capture: complete-packet cadence and automatic flashing

The physical run on `2911a824d5a44d126234d4f63545a37051d71d5f` reached
the ten-minute duplex soak with USB diagnostics intact. Both 256 kbps steady
intervals were loss-free, microphone pitch was reported natural, and the
user described playback as clear. The runner kept that free-text quality
answer unverified because it was not its exact `yes` response. The soak still
failed strict zero-loss acceptance: 7 dropped mic AUs and 14,656 missing USB
samples. No decoder errors, PCM queue drops or short USB writes occurred in
those measured intervals. Raw audio, device identities and pairing keys are
not committed; the sanitized measurements and archive hash are in
[the evidence record](evidence/duplex-packet-cadence-051250.json).

## Diagnosed packet-bound defect

The previous repair capped `codec_fdk_fill()` at two AUs **per call**. The
production timer still waited for three AUs before requesting transmission.
At 192 kbps it accumulated two plus one across calls. The live capture confirms
33.3 packets/s in 192 kbps and both game profiles, compared with 50 packets/s
in each 256 kbps interval. Mic AU drops were 57, 54 and 70 respectively in the
lower-rate/game measurements, versus zero in both 256 kbps intervals.

The repaired mic build caps the **entire packet** at two AUs, including AUs
from earlier timer ticks. Its scheduling helper requests transmission at that
same bound and stops staging while a grant is pending. Music and silence use
the same policy, independent of microphone open/close. Transport-only builds
retain their three-AU bound; peer MTU constraints still apply. This corrects
an observed aggregation difference; it does not prove that radio loss or the
physical per-bud symptom is solved.

The real-FDK packet test now calls the production scheduling helper with
one-AU timer credits and preserves partial packets across ticks. It checks
the send request, delayed-grant immutability, framing, sequence wrap, MTU,
gain and stereo decode. The archived `2911a82` sender fails the new regression
at the second staged AU (`codec_ready_to_send` remains false). The current
mic build passes, as does the unchanged transport-only policy.

## Runner corrections

- Off is tested only after an affirmative `AllowOff=1` peer notification.
  This run had `allow_off=-1`; the fresh noise value remained 3 after the Off
  request. The user confirmed the AirPods sounded the unavailable-mode alert.
  The runner now records the Off subtest as skipped and exercises the other
  supported noise modes. An initial Off state still requires safe restoration.
- The second reconnect recovered through the existing initial-START timeout
  and self-heal, but its steady measurement began while playback was stopped.
  The runner now waits boundedly for both paths and progressing playback TX
  to remain ready before measuring the reconnect. It preserves startup logs,
  reports hard faults immediately and still fails sustained/steady loss.
  This is a measurement correction, not a fix for the peer's missed START.
- A clip played through the phone speaker near the AirPods is now an accepted
  microphone stimulus. PC-generated playback remains active. Sending phone
  audio over Bluetooth to the AirPods would not exercise acoustic mic input.
- `Run-Test.ps1` automatically flashes the verified bundled UF2 using picotool
  from PATH. It attempts picotool's forced BOOTSEL reboot for a running device;
  existing USBPods firmware needs its already-implemented 1200-baud CDC reset
  fallback because it lacks the SDK vendor reset interface. Already-BOOTSEL
  devices proceed directly to `picotool load -v -x`. The helper checks bundle
  hashes before reset, verifies the returning firmware SHA and follows COM
  changes. Flash/verification failures prevent a test run. The flash log is
  included in results. Only UF2 sectors are written, without erase-all.

Picotool's reboot, load verification and execute switches follow the
[Raspberry Pi documentation](https://github.com/raspberrypi/picotool#reboot)
and [load command](https://github.com/raspberrypi/picotool#load). Its forced
reboot requires a compatible reset interface; the legacy CDC fallback is our
existing USBPods hook, not a picotool capability.

## Verification and limits

The maintained native suite passes 65 checks with zero failures/skips, including
real ASan FDK packet/decode paths and simulated flash states/failures. The
PowerShell launcher has a Windows CI execution test with argument/path quoting,
changed COM, flash-failure stop and propagation of test failure exit codes.
Target CI, the allocation audit and the immutable package's CLI scenarios are
recorded with the final release identity in the evidence record after building.
Host/backend simulations do not establish physical USB reset or flash behavior.

Closing capture still failed the left playback-channel check in this run;
reopening capture restored both channels. The previous run affected the right
side instead. Removing post-START/STOP jitter did not establish a physical fix.
The pinned working microphone fork uses the same START/STOP bytes and one
stereo A2DP stream; there is no evidence for assigning each bud a separate
host stream. Do not introduce capture-triggered playback resets or speculative
EQ. Physical channel independence, missed initial START, remaining soak loss,
and actual flash/re-enumeration behavior remain live validation items.
