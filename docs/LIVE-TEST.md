# Pico 2 W reconstruction: controlled hardware acceptance

This package is an **offline-verified test candidate**, not a claim of working
hardware. It reconstructs controls/settings, AACP notifications, wear/stem
policy and phone relay on top of the 0065/microphone fork. It uses CDC instead
of recreating the vendor WebHID/activation system. The bundled manifest pins
the UF2 hash and source commit; the runner refuses a different running commit.

## Windows setup

1. Save your known-working UF2. Flash the package's `Reconstructed` UF2 to the
   Pico **2 W**, using BOOTSEL. Do not flash an RP2350 application onto Pico W.
2. Connect USB directly. Close other COM terminals and apps using the dongle's
   microphone. Use UAC2 and manual connect mode for the automatic run. The
   runner saves UAC2/manual/48 kHz preferences and asks for one replug/rerun if
   needed. The distinct 192/256/320 kbps profiles require 48 kHz USB playback.
3. For physical UART capture, use a **3.3 V logic** USB-to-UART adapter. Pico
   GP0/TX (physical pin 1) goes to adapter RX; Pico GND (pin 3) goes to GND.
   UART RX is GP1 (pin 2); it is optional for read-only capture. Do not connect
   adapter power or 5 V serial signals. The script opens this separate COM
   port at 115200 baud and enables the firmware's UART mirror over CDC.
4. In PowerShell, from the extracted package, run:

   ```powershell
   .\Run-Test.ps1 -TargetName "Your exact AirPods Bluetooth name" -CdcPort COM7 -UartPort COM9
   ```

   Replace the names/ports. Omit `-TargetName` to select the intended AirPods
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
   .\.venv\Scripts\python.exe live_test.py --target-name "Your exact AirPods Bluetooth name" --cdc COM7 --uart COM9
   ```

   `--target-mac AA:BB:CC:DD:EE:FF` can replace the name. Name matching is exact,
   and duplicate matches are refused. The script cannot physically put the
   AirPods case into pairing mode; it prompts you, scans without auto-pairing,
   stops discovery and pairs only the selected target. Both occupied favorites
   may cause a favorite reassignment; saved history remains available.

5. Follow the prompts. The audio matrix plays quiet stereo 440/660 Hz tones
   with broadband sections. Speak/count as prompted. WAV clips contain up to
   12 seconds per phase; counters cover the full run. If Windows audio endpoint
   names are ambiguous, rerun
   with `--input-device N --output-device N`, using the captured device list.
   The runner selects named USBPods/TinyUSB endpoints and does not fall back to
   the PC's default microphone or speakers.
6. Return `USBPods-results-<UTC>.zip`, including failures. Automatic check or collection
   failures return a nonzero exit code.
   `automated_pass` is separate from `complete`; skipped or unverified physical
   coverage remains explicit even when automatic checks pass. Inspect
   `summary.json`. Do not interpret a
   queued command, an opened COM/HID handle, or nonzero PCM as proof of correct
   acoustics. Pairing, notified control readbacks, host audio, manual listening,
   and unverified coverage have separate entries.

The automatic sequence keeps microphone capture open through 256/192/320 kbps,
standard and low-buffer game modes, return to default, three Bluetooth reconnects,
and a ten-minute duplex soak. Applied encoder state must match each requested
profile before its steady interval begins. Snapshots include microphone cadence,
queue/drop/decode counters, USB actual/missing samples, HID delivery statistics,
allocator use and encoder setup/rebuild duration. Steady-interval missing samples,
decode errors and unexpected microphone generations are failures, rather than
being hidden by padded silence. The first run may expose the unresolved clock
question; return failed results too. Configuration readback does not measure
end-to-end acoustic latency or actual average VBR throughput.

The Pico UART connection is the application log mirror at 115200 baud; it does
not claim access to a separate controller HCI UART. The raw HID reader may be
blocked by Windows, so successful firmware submission logs and counters are
collected separately. Listen to the WAV clips before answering the pitch/speed
question; hearing your own voice directly does not validate recorded timing.

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
  over CDC/UART. Firmware logs mean TinyUSB accepted the report, not that the
  host app acted on it. Confirm the resulting behavior manually.
- AAC-LC relay receives RTP/LATM directly, with bounded fragment assembly and
  sequence/timestamp checks. Unsupported malformed/oversized/fractured streams
  are rejected. Marker behavior on real phones remains part of live acceptance.
- The inherited mic ASC reports 48 kHz while the reference USB mic clock is
  64 kHz. Cadence, pitch and drift are still hardware questions. Saved speech,
  timestamps and decoder counters are needed to resolve this.

## Additional guided matrix

These checks need your physical inputs or a second device; the automatic run
does not mark them passed just because it sent a command. Keep CDC and UART
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
