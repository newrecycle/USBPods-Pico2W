# Independent review of the local-agent changes

Reviewed main commit: `6be28899efba385d805e1c7c7cd3c3041b562b5b`.
Baseline handoff: `2503a52c1b8d3c3cc65b165e453bebe4dcd5131e`.
Review date: 2026-11-04. Recommendation: **request changes**.

This review examined the 51 changed files across the 11 commits since the
handoff, including production audio/control changes, their tests, packaging,
and validation claims. Materialized file blobs were checked against the remote
compare response. The separate review branch adds only this report, an evidence
summary, and regression probes. It does not change firmware, the live-validation
authorization, or main. No hardware was used.

## 1. P1: queue reset can give a PCM slot two owners

Location: [btstack_avdtp_source.c:797](https://github.com/newrecycle/USBPods-Pico2W/blob/6be28899efba385d805e1c7c7cd3c3041b562b5b/src/btstack/btstack_avdtp_source.c#L797).

The new allocate-once reset drains `ready_queue`, drains `free_queue`, and
repopulates every free slot without freezing the USB producer. Disconnect and
slot-switch paths call this reset while USB playback can still supply samples.
`audio_slot_push_samples()` is gated by `slot_pool_frozen`, not `is_streaming`.
Individual queue locks do not make this entire reset atomic.

After the ready queue has been drained, a USB interrupt between free-queue
removals can take a free slot and publish it to the ready queue. The reset then
re-adds that same index to the free queue. Playback can overwrite a slot still
awaiting encoding, violating the ownership invariant and risking corrupted PCM.

The probe executes the production reset and push functions with a bounded queue
mock. It injects one producer call after a free-queue removal has returned, when
its operation lock is no longer held. Result: **slot 1 has two owners**, and the
one-owner-per-slot assertion fails. This models one interrupt interleaving;
it does not claim target timing was measured.

Required fix: protect the whole drain/repopulate/filling-slot reset from the USB
producer, using a consistent freeze or interrupt-exclusion protocol. The nearby
queue-reconfiguration path already recognizes this need. Preserve a regression
that checks ownership under producer interleavings.

## 2. P2: SUSPEND leaves a deferred START eligible to restart transmission

Location: [btstack_avdtp_source.c:2872](https://github.com/newrecycle/USBPods-Pico2W/blob/6be28899efba385d805e1c7c7cd3c3041b562b5b/src/btstack/btstack_avdtp_source.c#L2872).
The predicate is used at [scan completion, line 4318](https://github.com/newrecycle/USBPods-Pico2W/blob/6be28899efba385d805e1c7c7cd3c3041b562b5b/src/btstack/btstack_avdtp_source.c#L4318).

An accepted START before capability-scan completion sets
`src_start_accepted_pending`. If the peer then SUSPENDs, the flag survives.
For ELD the transition owner moves from READY to REBUILD, but the pending-start
predicate still returns true: it checks connection/codec presence and pump
state, without checking whether the previous START is still valid. When scan
completion calls `src_pump_start()`, it bypasses the owner's current permission
and can resume transmission to a suspended peer.

The probe extends the existing production-adapter fixture with:
connected/configured -> scan incomplete -> START accepted -> SUSPEND accepted
-> scan complete. The owner is confirmed to be `ELD_REBUILD`, yet
`src_pump_start_pending()` is true and the assertion rejecting that restart
fails. Production adapter functions and the real ELD transition module run
against the existing SDK mocks. This is an offline ordering test, not a captured
over-the-air sequence.

Required fix: invalidate deferred START permission on SUSPEND, consume it when
used, and validate it against the current session/codec transition before
starting the pump. Preserve the working early-START case and other codecs.

## 3. P2: mic history-clear retry never completes with the real FDK decoder

Location: [aacp_mic_audio.c:198](https://github.com/newrecycle/USBPods-Pico2W/blob/6be28899efba385d805e1c7c7cd3c3041b562b5b/src/btstack/aacp_mic_audio.c#L198).

The generation-change clear calls `aacDecoder_DecodeFrame()` before supplying
the next access unit. With the actual in-tree FDK library this call returns
`0x1002` (`AAC_DEC_NOT_ENOUGH_BITS`). The decoder exits before its history-clear
and interruption handling, so this is not a successful clear with an unusual
return code. The subsequent normal data decode succeeds.

Because the new retry advances `last_epoch` only on `AAC_DEC_OK`, the epoch
never advances and every mic frame repeats the unsuccessful call. In the
real-FDK duplex fixture, **3,072 decoded frames produced 3,072 flush errors**,
with `last_epoch == UINT32_MAX` while the active generation was 1. Normal decode
errors remained zero. A read-only wrapper around the unchanged production
module exposes that epoch to the assertion. A separate diagnostic run recorded
the `0x1002` return; inspection of FDK's access-unit read/bail path confirms
that history handling was skipped.

The empty-buffer clear problem predates the new retry. The new retry does not
resolve it and now repeats indefinitely. Consequently, the intended clear of
previous-generation codec history is not established across capture restarts.
This review does not claim an audible artifact was demonstrated.

Required fix: use an FDK-supported reset sequence, and verify a successful
history reset per generation against the actual decoder. The mocked clear test
must not substitute for that check. Include STOP/START and reconnect cases.

## Verification and reproduction

The checked-in offline suite completed **59 checks: 59 passed, zero failed,
zero skipped**, using an ASan-instrumented native build of the in-tree FDK.
The remote [Pico firmware CI run](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41762239867)
also succeeded for the reviewed main commit. Those results do not cover the
three invariants above.

Run the additional probes from a Linux/WSL checkout of this review branch:

```sh
python3 tools/review_regressions_6be2889.py --fdk-lib /absolute/path/to/libfdk-aac.a
```

Supply an ASan-instrumented native archive from this tree's FDK build, as for
the existing offline duplex suite. Without `--fdk-lib`, the mic probe is skipped.
On the reviewed tree all three probes compile successfully and fail runtime
assertions (exit code 1 for the runner). Logs, generated C fixtures, and a JSON
summary are retained under `build-independent-review/`. The probe uses existing
test-source extraction and fixture anchors; if a fix changes those interfaces,
update the fixture while preserving the assertions' meaning. Compilation
failures are reported separately from failed invariants.

These findings should be corrected and rechecked offline before asking for
another live run. They do not prove the root cause of the reported left/right
AirPod behavior, nor do they verify physical stereo routing, negotiated on-air
codec operation, or simultaneous hardware playback/capture. The user's original
bass-quality complaint was withdrawn after a better A/B comparison and is not
treated as a confirmed defect here. USB-only diagnostics remain the constraint.
