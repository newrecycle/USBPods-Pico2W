# Repairs following the independent review

These changes address the three reproduced defects in
[the review of main 6be2889](INDEPENDENT-REVIEW-6be2889.md). They preserve the
USB-only diagnostic policy, codec rates/game profiles, mic clocks, and separation
between capture lifecycle and explicit playback recovery. No hardware was used.

## Changes and evidence

| Defect | Repair | Regression evidence |
| --- | --- | --- |
| PCM queue reset can duplicate slot ownership | Freeze the USB producer before reset; exclude same-core interrupts across drain, repopulation and filling-slot reset; restore the previous freeze and IRQ states. Keep boot-only allocation outside that IRQ-off window. | Production reset/push bodies run through 640 queue-operation/IRQ/state combinations, including partial/full queues and already-disabled IRQs. Allocation remains exactly twice over repeated resets. |
| A deferred START survives SUSPEND | SUSPEND clears the permission; pump startup consumes it. Scan completion also requires a live, unfaulted session, completed codec setup, and ELD READY where applicable. | Accepted early START still starts once; crossed SUSPEND does not start the pump; current owner/session gates are checked, including SBC. The coupled USB/AACP/ELD fixture repeats the crossed sequence with microphone traffic active. |
| Mic history clear is called without input and never completes | Clear FDK's transport buffer at a generation boundary, Fill the first current AU, then decode that AU with CLRHIST/INTR. Advance the cleared epoch only on success. Failed reset/Fill/decode publishes silence and retries on the next AU. | Actual FDK duplex test exercises 3,072 playback frames with the mic active, plus 12 mic STOP/START/discontinuity generations. Every restarted generation's PCM matches a fresh reference decoder sample for sample. Old queued AU/PCM is rejected. Deterministic tests cover reset, Fill and first-decode failure/retry. |

The reference decoder is closed before measuring production restart allocations,
so it does not inflate the existing 32-bit codec heap audit. The production mic
decoder is retained across resets; reset does not add open/free operations in
USB or Bluetooth callbacks. The queue fix relies on the existing architecture:
USB processing and the lower-priority BT worker run on core 0; the core-1 encoder
launch remains disabled. A future multicore producer requires a different
cross-core ownership protocol.

## Validation

The maintained offline suite passes **60/60 checks, zero skipped**, with native
in-tree FDK and ASan/UBSan where configured. The additional review runner passes
all three original defect probes. Its real-FDK observation is now 3,468 decoded
mic frames, zero decode errors, zero history-clear errors, and cleared/current
generation both 19. Before repair, the original probe observed 3,072 clear
errors and an uncleared epoch. The enhanced PCM restart fixture also fails
against the unchanged pre-repair production decoder, establishing a negative
control independent of the mock decoder.

The repaired source at `5a4ea5e7f72b0208c060d5621678e51abff6383f` also passed all three
[Pico target CI jobs](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41766248409)
and the [USB/HID CI job](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41766248265).
The 32-bit codec audit passed with a requested peak of 303,110 bytes, excluding
allocator and BT overhead. Target builds, linked-image/UF2 verification and the
SCO diagnostic probe builds passed; no target execution is claimed.

Portable commands:

```sh
python3 tools/run_offline_checks.py --fdk-lib /absolute/path/to/libfdk-aac.a
python3 tools/review_regressions_6be2889.py --fdk-lib /absolute/path/to/libfdk-aac.a
```

Use an ASan-instrumented native archive of the in-tree FDK. The maintained runner
can build it with `--build-fdk` instead. The new queue regression is also wired
into the Pico firmware CI workflow. Sanitized evidence, production source
hashes, and target CI state are recorded in
[independent-review-repairs.json](evidence/independent-review-repairs.json).

These offline results establish the repaired invariants, not physical AirPod
routing or RF timing. The reported left/right symptom remains unverified. No
flashing, live test, or new physical readiness claim is part of these repairs.
