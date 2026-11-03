# Offline triage findings — 2026-11-03

Scope: implement the [offline plan](OFFLINE-TRIAGE-PLAN.md), reproduce failures
before fixing them, and use target builds only as the final compatibility gate.
Live packaging is paused. This report does not request another physical run.

## Current evidence

Native Windows microphone use and simultaneous playback were confirmed by the
user. The latest 101a970b capture also contains working WASAPI 48 kHz stereo
WAVs and decoded microphone frames without decoder errors. Its audio matrix
failed on a source transition, not on opening the microphone.

The initial bass-regression impression was revised after a better track and
A/B comparison: the user reports quality on par, with a possible slight
soundstage difference. A firmware-specific bass defect is unconfirmed. No EQ,
microphone clock or decoder-gain change was made in this pass.

## Reproduced defects and fixes

| Defect | Evidence before changing code | Correction and offline proof |
| --- | --- | --- |
| Redundant ELD restart | 220546 capture: at 22:07:14 UTC the rate change built VBR5/SBR1; a game-level write while game mode was off requested an identical profile, causing another SUSPEND/build/START. The peer rejected START with 263. Production-adapter replay failed before the fix. | Compare effective profiles field by field; identical requested profiles do not signal or rebuild. Explicit recovery uses a separate forced API. The captured sequence now performs one rebuild and starts the pump. |
| Multi-field profile application/restoration | Rate, game and level were independent RPCs, each capable of restarting the encoder; cleanup had the same problem. | `:profile RATE GAME LEVEL` (ID 165) updates all three under one owner lock, dirties settings once and requests one effective change. The runner and cleanup use this transaction. Invalid, unchanged and changed transactions are tested. |
| Batched AACP notifications discarded | The supplied Full parser splits multiple messages in one L2CAP SDU. Our fixed-length single-message parser rejected a valid three-notification SDU; the production channel regression failed before the fix. | Validate the structure of supported fixed-format batches before callbacks; then process each notification. Tests cover controls, typed double/triple presses, truncated tails and header-like bytes inside values. Unknown/encoded payloads are not searched for magic headers. |
| Duplicate AACP/AVRCP host keys | Both handlers could independently forward one physical gesture, especially after repairing batch parsing. | With stem forwarding enabled and AACP confirmed, hold native media events for the existing 250 ms debounce window. Explicit typed gestures take precedence; absent a typed event, preserve the exact native command. Production-handler tests exercise both arrival orders, relay CID rejection and disconnect cancellation. Queue overflow and suppression are counted. This does not infer a double/triple press from repeated PLAY events. |
| Invalid Off-mode probe | The runner always tried Off first, even though AirPods expose a separate AllowOff option. The latest capture reports fresh Adaptive notifications after an Off request. | Parse AllowOff readback without changing the option. Skip Off unless explicitly allowed; skip probing when the current Off state could not safely be restored. Other supported modes can still be checked. The capture alone does not prove this option caused every control failure. |
| External capture treated as runner-owned | In the latest capture `capture=1` before the runner opened an input stream. Closing its handle could not establish a global USB capture close; the resulting timeout obscured the earlier START rejection. | Record initial capture ownership. External capture makes the close/reopen endpoint check SKIP/UNVERIFIED, not a hardware FAIL. Closing one input handle still leaves output open. Owned/external full-matrix replays pass. |
| First fault lost during cleanup | The runner waited for convergence after the disconnected source had already reported error stage 2 / 263, then inspected state after stream close. | Detect failed/off error state immediately. Save the first audio fault before closing streams; never overwrite it with a later fallback snapshot. The recorded rejection replay confirms capture was still active in the saved fault and avoids the previous 15-second wait. |
| Startup measurement raced microphone recovery | Initial microphone START deliberately queues playback recovery after 800 ms; beginning a strict traffic check immediately after confirmation could misclassify that expected transition. | Expose microphone START/recovery state over USB. Settle the initial lifecycle before starting the sustained traffic window, while still failing immediately on a fault or disconnect. A timed runner fixture reproduces the delayed recovery. |
| Probe order contaminated audio baseline | Peer controls and gain probes ran before priority audio verification. | Complete the audio matrix first. Run control probes afterward; skip further mutations/prompts if the matrix aborts. |

The arbitration queue is bounded to four native events. A typed event arriving
outside the 250 ms correlation window cannot be retrospectively merged with an
already delivered native command. The window applies only to the opt-in stem
path with confirmed AACP; generic/native fallback remains available. Real
cross-channel timing and actual received gesture types remain unconfirmed.

## Microphone-fork comparison

Reviewed the complete han-um implementation at
[d18d083](https://github.com/han-um/USBPods-Pico2W-2-way-audio-implement/tree/d18d083bc52de3143d8d922c4abaae865cc0dc28),
including source playback, microphone decoder/channel, USB descriptors/callbacks,
main loop and README. This is the fork's current head at review time.

| Area | Fork/reference | Decision here |
| --- | --- | --- |
| Microphone | Inherited `F8 E6 30 00` ASC; 480-sample mono frames, independent 64 kHz USB clock | Preserve the native-working decoder/clock. LibrePods distinguishes 48 kHz coding from 64 kHz PCM consumption. |
| Playback encoder | AOT 39, stereo/48 kHz, 480 samples, CBR 265 kbps, SBR off | Do not blindly copy a rate above the accepted 256 kbps ceiling. Retain supported profiles and prove their effective application. |
| Microphone lifecycle | START/STOP from main under the Bluetooth lock | Preserve that ownership. Explicit recovery remains separate from idempotent preference writes. |
| SDP identity | Apple vendor 0x004c; separate device ID record | Retain Apple identity with our non-colliding record handle. |
| Logging and buttons | Nonblocking USB CDC; main-loop button actions | Existing corrections already follow this pattern. Diagnostics remain USB-only. |
| Apple AU framing | Four-byte B0/10 header, 12-bit sequence and AU length | The production packetizer is exercised with actual FDK output, sequence wrap and negotiated packet capacity. |
| RTP policy | Fork uses sample-count timestamps; suggested Full source uses its established millisecond policy | Record the difference; do not change transport clocks from a subjective quality impression. No radio-level timing equivalence is claimed. |

The supplied disassembly/reconstructed Full source remains a reference, not
private authoritative source or a proven best implementation. Its message-
splitting behavior revealed a concrete unsupported input case, which was then
reproduced and fixed with bounded parsing rather than copied wholesale.

## Offline verification

- Production transition replay fails on the captured duplicate request before
  the fix and passes afterward. Existing rejection, timeout, allocation-failure,
  stale-event and main-loop ownership checks remain active.
- Production channel tests reproduce dropped batched controls before the fix;
  complete controls and typed gestures now arrive. Truncated batches publish
  no callbacks. Unknown IDs and header-like value bytes cannot create events.
- Production AACP/AVRCP handler tests verify typed-event precedence in both
  arrival orders, exact native fallback, relay CID filtering and cancellation.
- The actual runner traverses supported profiles, both game modes, capture
  transitions, three Bluetooth reconnects and a soak using stateful simulated
  host/device backends. It uses real AudioSession stream contexts and WAV
  writing. Owned capture, external capture and recorded START-rejection cases
  pass. These are not Windows or AirPods execution results.
- Real FDK through the production PCM queue, cubic gain, channel ordering and
  Apple AU packetizer completes 1,080 decoded multitone frames. Irregular USB
  chunk sizes conserve samples, 100/50/0 percent gains preserve expected PCM
  bytes, sequence wrap is correct and packet capacity is respected.
- Isolated tone response checks cover 40/80/160/1000/6000 Hz across the supported
  encoder profiles. Additional local fixed-peer ASC probes tested SBR and bare
  ELD reference configurations without a large low-frequency loss. These narrow
  synthetic results do not establish acoustic quality or every peer behavior.
- All 47 local host compile/test commands passed after the final changes,
  including 21 runner unit cases and three complete stateful matrix scenarios.
  Sanitizers, parser/USB/HID/cadence fixtures and allocation checks run before
  the target compatibility builds. Target checks
  are recorded in the commit's GitHub Actions, rather than treated as protocol
  acceptance or physical success.

## Remaining limits

The physical left/right result of microphone close/reopen and actual gesture
semantics on this AirPods session are not established by these offline fixes.
Supported fixed-format AACP batching is handled; unknown variable-length or
mixed encoded/control payloads remain opaque rather than being guessed from
byte patterns. Missing control echoes remain UNVERIFIED. Host simulation does
not prove Windows scheduling, RF behavior, acoustic quality or live clock drift.

These are explicit limits of available evidence. They do not justify another
speculative package in this offline-only pass. The corrected code, replay tests
and this report are committed for review; hardware packaging stays disabled.
