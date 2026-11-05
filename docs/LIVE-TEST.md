# Pico 2 W reconstruction: controlled hardware acceptance

**Evidence-integrity note (independent audit, 2026-11-04):** The source candidate at
18be74cfe99f2584bcf26a0c0f0571c75a7f7bec passed firmware and host CI,
but it **was not flashed or physically tested**. The last physical laptop
firmware was 880dc318072f191f1440d3f0b262d83e32729b59, normally CDC COM4.
It passed the 256 kbps rate phase but failed 192 kbps; both game modes were
unmeasured. Microphone-close left-ear silence persisted after MaxxAudioPro
was disabled. The previous 600.539-second duplex soak was **already completed**
at 2911a82; duration completion is not strict zero-loss PASS. Do not prescribe
another ten-minute soak for this audit. See
[the source-specific evidence ledger](VALIDATION-AUDIT-INITIAL-20261104.md)
and [audit/integration report](VALIDATION-AUDIT-REPORT-20261104.md).
A session-only probe does not run the manual isolated left/right checks.

**Hardware runs are authorized as of 2026-11-03 by repository-owner order**
after the offline static review, repairs and green CI build. Use only a package
produced by `tools/package_live_test.py` (CI packaging step) with matching
`candidate.json`; the runner refuses a package whose authorization,
`build_verified` or 32-bit codec-heap audit is missing. Background:
[OFFLINE-TRIAGE-PLAN.md](OFFLINE-TRIAGE-PLAN.md),
[OFFLINE-TRIAGE-FINDINGS.md](OFFLINE-TRIAGE-FINDINGS.md),
[STATIC-REVIEW-2026-11-03.md](STATIC-REVIEW-2026-11-03.md).

**The old 238ed609 package is withdrawn. Run-Test.ps1 installs this package's UF2 before testing.**
The engineering blockers from the first capture have targeted fixes and offline
regressions. See [the revalidation report](REVALIDATION-2026-11-03.md). The first replacement run and subsequent user observations are recorded in
[LIVE-FINDINGS-2026-11-03.md](LIVE-FINDINGS-2026-11-03.md). The new transition
recovery and Windows capture changes require the controlled run below.

This package is an **offline-verified test candidate**, not a claim of working
hardware. It reconstructs controls/settings, AACP notifications, wear/stem
policy and phone relay on top of the 0065/microphone fork. It uses CDC instead
of recreating the vendor WebHID/activation system. The bundled manifest pins
the UF2 hash and source commit; the runner refuses a different running commit.

## Windows setup

For the current 30-second connection failure, use the focused probe:

```powershell
.\Run-Test.ps1 -CdcPort COM3 -SessionOnly
```

It automatically flashes, pairs with the selected AirPods and records 45 seconds
of concurrent AAC-ELD playback, microphone capture, USB diagnostics and HID logs.
Your phone-speaker clip during the first 20 seconds is sufficient. No counting,
channel questions, control cycling or ten-minute soak is included. Return the
results ZIP even if it exits early. See [AACP-SESSION-0555.md](AACP-SESSION-0555.md).
This package diagnoses the repeatable disconnect; its physical cause is still
unresolved. Omit `-SessionOnly` for the complete matrix after that issue is closed.

After the first pairing, a package containing the local runner's new
`-ReusePairing` option can reuse the current or uniquely selected saved bond:

```powershell
.\Run-Test.ps1 -CdcPort COM4 -SessionOnly -ReusePairing
```

This mode does not scan, request case pairing mode, or send a fresh pairing
command. A disconnected selected device is dialed through `savedconnect`.
Ambiguous history requires `-TargetName` or `-TargetMac`; a different connected
headset is refused. The launcher's existing flash/identity checks still apply.
The verified `880dc31` package does not yet contain this new runner option.
The local supplemental probes reused its existing connection and saved bond.
See [the local Windows findings](LOCAL-WINDOWS-20261104.md).

1. Save your known-working UF2. Have `picotool` in PATH and connect the Pico
   **2 W**, either running the previous USBPods firmware or already in BOOTSEL.
   The launcher verifies the bundle, attempts `picotool reboot -u -f` for a
   running device, falls back to its existing 1200-baud CDC reset hook when
   needed, then runs `picotool load -v -x` on the bundled UF2. It waits for CDC
   and checks the returning firmware SHA before starting tests. It follows a
   changed COM number automatically and stops on flash/identity failure.
   Connect only the intended Pico 2 BOOTSEL target; an ambiguous selection is
   refused by picotool. Only UF2 sectors are written; no erase-all is used.
2. Connect USB directly. Close other COM terminals and apps using the dongle's
   microphone. Use UAC2 and manual connect mode for the automatic run. The
   runner saves UAC2/manual/48 kHz preferences and asks for one replug/rerun if
   needed. The distinct 192/256/320 kbps profiles require 48 kHz USB playback.
3. One USB connection and the Pico's **single CDC COM port** collect application,
   AACP, codec, USB and firmware HID submission logs. No USB-to-UART adapter is
   required and the runner does not prompt for one. Audio and HID endpoints
   are not additional COM ports.
4. In PowerShell, from the extracted package, run:

   ```powershell
   .\Run-Test.ps1 -CdcPort COM3
   ```

   Replace COM3 with the Pico's actual COM port. Add `-TargetName` for an exact
   name match, or omit it to select the intended AirPods
   explicitly from the scan results; duplicate or truncated names are not guessed.
   Add `-PhoneRelay` to include a phone while both USB audio streams remain open.
   `-StageSeconds 20 -SoakSeconds 600` are the defaults: allow about 13–15 minutes
   plus prompts, and keep the PC awake during the automatic soak.

   The launcher creates a local `.venv` and installs
   pySerial, HIDAPI, sounddevice and NumPy. It records installed versions in
   the results. Python 3 with pip is required. If PowerShell policy blocks this
   local script, use the Python commands below instead of changing policy.

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r live-requirements.txt
   .\.venv\Scripts\python.exe flash_candidate.py --cdc COM3 --port-file flashed-port.txt
   if ($LASTEXITCODE -ne 0) { throw 'Firmware update failed; see flash-log.json' }
   .\.venv\Scripts\python.exe live_test.py --cdc (Get-Content -Raw flashed-port.txt).Trim()
   ```

   `--target-mac AA:BB:CC:DD:EE:FF` can replace the name. Name matching is exact,
   and duplicate matches are refused. The script cannot physically put the
   AirPods case into pairing mode; it prompts you, scans without auto-pairing,
   stops discovery and connects only the selected target. At the pairing prompt,
   put both AirPods Pro 3 in the case, open the lid, and double-tap the front
   until the light flashes white. Press Enter, wait for the scan results, then
   enter the intended device's numeric index. The runner reports Bluetooth
   connection and AACP handshake separately. An existing stored key may be
   reused; this does not prove a new bond was created. Both occupied favorites
   may cause a favorite reassignment; saved history remains available.

5. Follow the prompts. Conversation Awareness is temporarily disabled during
   audio capture when its notified state is known, then restored. The audio matrix plays quiet stereo 440/660 Hz tones
   with broadband sections. Play a repeatable clip through the phone's speaker
   near the AirPods during each 20-second phase, or speak. The phone must not
   send that clip over Bluetooth to the AirPods; this is acoustic microphone
   input while the PC supplies playback. WAV clips contain up to
   12 seconds per phase; counters cover the full run. If Windows audio endpoint
   names are ambiguous, rerun
   with `--input-device N --output-device N`, using the captured device list.
   The runner selects named USBPods/TinyUSB endpoints and does not fall back to
   the PC's default microphone or speakers.
6. Return `USBPods-results-<UTC>.zip`, including failures. Automatic check or collection
   failures return a nonzero exit code.
   The ZIP also includes the matching flash log. If flashing fails before a
   test run starts, return `flash-log.json` from the package folder.
   `automated_pass` is separate from `complete`; skipped or unverified physical
   coverage remains explicit even when automatic checks pass. Inspect
   `summary.json`. Do not interpret a
   queued command, an opened COM/HID handle, or nonzero PCM as proof of correct
   acoustics. Pairing, notified control readbacks, host audio, manual listening,
   and unverified coverage have separate entries.

The automatic sequence keeps microphone capture open through the peer-supported
192/256/320 kbps profiles,
standard and low-buffer game modes, return to default, three Bluetooth reconnects,
and a ten-minute duplex soak. Applied encoder state must match each requested
profile before its steady interval begins. Snapshots include microphone cadence,
queue/drop/decode counters, USB actual/missing samples, HID delivery statistics,
allocator use and encoder setup/rebuild duration. Steady-interval missing samples,
decode errors and unexpected microphone generations are failures, rather than
being hidden by padded silence. A five-second connection preflight checks streaming and TX progression before
feature changes. Unsupported negotiated bitrates are explicitly skipped.
Microphone cadence must match the 64 kHz PCM timeline; return failed results too. Configuration readback does not measure
end-to-end acoustic latency or actual average VBR throughput.

The microphone-decoder candidate uses CBR/core-only AAC-ELD at the supported
rates. The 035227 capture exposed severe microphone starvation with the earlier
256 kbps VBR+SBR profile. Peer VBR permission remains visible separately from
the applied `duplex_cbr` policy; transport-only builds retain their VBR policy.
The 042523 repair also limits radio-context encoding to two AUs per call and
uses a 75 ms mic buffering target (30 ms more than before) in the existing
ring. The next run specifically checks lower-rate/game loss, both channels
while capture is closed, and full ACL reconnects. See
[DUPLEX-LIFECYCLE-042523.md](DUPLEX-LIFECYCLE-042523.md).

Diagnostics use **USB CDC only**. Leave COM3 open through the runner; do not
open another terminal on it. Application, codec, AACP and firmware HID logs are
recorded while playback and capture are active. Raw HID access may be blocked
by Windows; that limitation is reported separately from firmware submission.

Windows WASAPI shared capture uses the endpoint's reported mixer rate and
channel count (the first Windows run reports 48 kHz/two channels). WAVs preserve
that host format. Firmware microphone cadence still measures the independent
64 kHz mono USB timeline. Input volume is a separate Windows control; check its
meter before starting and close other microphone previews/dictation while the
runner owns capture. No recorded clip means the runner skips the pitch prompt.

The channel check keeps playback open while closing and reopening only
microphone capture, with isolated left/right listening prompts. Keep this
firmware plugged in throughout the run. The earlier bass comparison was
withdrawn; this run proceeds directly to capture close/reopen and reconnects.

Control writes are checked against actual L2CAP submission counters. A new
per-control notification sequence is required for automated readback PASS.
Missing echoes remain UNVERIFIED; a queued ACK or cached old value cannot
establish application. Known control writes trigger a bounded notification
refresh, and the previous state is restored by wire submission. Stem logs now
include any received gesture and button-configuration notifications; repeated
AVRCP PLAY messages are recorded without guessing missing gesture types.

The host runner has contract tests and simulated audio/WAV/failure-cleanup tests.
Windows PortAudio, native PowerShell launch and physical devices remain live
acceptance items. Firmware candidates must match the bundled SHA/hash and
passed Pico CI; this is not a claim of working AirPods audio.

The runner does not upload results, access account endpoints, install vendor
licenses, delete all pairings, or flash a different image automatically.

## Feature and resource policy

- The microphone-decoder build supports A2DP source playback plus AAC-ELD mic
  and **SBC phone relay**. It deliberately does not advertise AAC phone relay:
  a second FDK decoder heap cannot safely coexist with the mic decoder on the
  RP2350. Simultaneous playback/recording/relay still needs hardware measurement.
- The transport/full-relay build supports SBC/AAC phone relay but its USB mic
  intentionally sends silence. Use it for the separate AAC-relay test. There
  is no claim that both FDK decoders run simultaneously.
- Source staging is bounded at 9 slots (SBC/AAC/LDAC use 8; ELD uses 4/6/9).
  The relay uses bounded packet/PCM rings. Overflow is counted, not hidden.
- Ear policy is opt-in. Initial wear notifications prime state without a host
  key. Either bud worn counts as worn. Removal sends a dedicated Pause only
  while playback is active; reinsertion sends Play only for a pause the policy
  owned. Stem-to-HID is separately opt-in. HID send/release logs are included.
- Raw HID access can be blocked by Windows for system-owned media controls.
  The script records that limitation and still captures `[hid] sent ...` logs
  over CDC. Firmware logs mean TinyUSB accepted the report, not that the
  host app acted on it. Confirm the resulting behavior manually.
- AAC-LC relay receives RTP/LATM directly, with bounded fragment assembly and
  sequence/timestamp checks. Unsupported malformed/oversized/fractured streams
  are rejected. Marker behavior on real phones remains part of live acceptance.
- The upstream microphone separates the 48 kHz coding frequency from its
  64 kHz PCM timeline. Capture buffers bursts and uses adaptive 63/64/65-sample
  USB packets. Cadence, pitch and host clock drift still require hardware checks. Saved speech,
  timestamps and decoder counters are needed to resolve this.

## Additional guided matrix

These checks need your physical inputs or a second device; the automatic run
does not mark them passed just because it sent a command. Keep CDC
capture running while performing them and note the time/results in a text file
inside the returned results directory before zipping it again if necessary.

| Feature | Check | Evidence required |
| --- | --- | --- |
| Ear detection | Playback active; remove one bud, both buds, reinsert; repeat while already paused | No unwanted toggle/resume, HID press/release logs and listening result |
| Stem | Enable `:stem 1`; single/double/triple press | Correct host action, raw HID or firmware HID log, no duplicate action |
| Relay | `:phonepair 1`, pair/play a phone; mix with PC playback; suspend/restart phone | `[relay]` counters, no stale audio, matched CID, clear mixed audio |
| AAC relay | Flash the matching transport/full-relay candidate; repeat phone relay | AAC negotiation/decoder counters, correct 44.1/48 kHz pitch |
| Persistence | Save nondefault game/ear/settings, reboot/replug, read `:settings` | Same values after restart; restore original preferences |
| USB suspend | Suspend/resume Windows with mic open, then with mic closed | Open capture resumes; closed capture remains stopped; no stale voice |
| USB modes | `:uac1 1` + `:reboot`, test playback; restore UAC2 and reboot | USB enumeration and playback; UAC1 has no mic by design |
| Pipeline rate | `:rate44 1` + reboot, playback/relay; restore 48 kHz | Correct pitch and no resets in both modes |
| Connection modes | `:connmode 2` follows headset, 3 follows host playback; restore 1 | Expected reconnect/re-enumeration without loops |
| Favorites/history | `:savedlist`, `:slot 1/2`, `:savedconnect N` | Correct peer MAC; no unrelated history loss |
| Other codecs | Pair a matching SBC/AAC/LDAC/LHDC headset and test quality settings | Negotiated codec and audible output; AirPods cannot prove LDAC/LHDC |
| Buttons | Test each `:btnmode 1..4` with short/long presses | Expected action and logs; no pairing while streaming |

`uart`, `debug`, `game`, `earpause`, `stem`, `gamelevel`, `eldrate`, `usbvol`,
`phvol`, `connmode`, `slot`, `phonepair`, `relayaac`, `uac1`, `rate44`,
`bootconn`, `pausedc`, `swvol`, `btnmode`, `ldacq` and `lhdcrate` accept the
documented numeric settings via `:<name> <value>`. `:info`, `:status`,
`:settings`, `:scan`, `:scanstop`, `:scanlist`, `:savedlist`, `:connect`,
`:disconnect`, `:phonedisc`, `:telemetry` and `:reboot` need no argument.
The existing single-key console remains available for manual debugging.

The runner restores the settings it changes where the control link remains
available. Restoration failures are recorded. It preserves the new AirPods
pairing, because that is the intended result. Descriptor normalization is kept
for the test and may need manual restoration afterward.
