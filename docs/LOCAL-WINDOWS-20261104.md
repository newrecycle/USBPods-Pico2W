# Local Windows session, 2026-11-04 UTC

The current host is the user's **laptop**. Earlier captures were made on the
user's **PC with no audio enhancements**. MaxxAudioPro was enabled on the
laptop and caused channel mixing; the user disabled it during this session.
This explains that laptop mixing observation, not the earlier PC findings.
The microphone-close left-ear silence still reproduces with MaxxAudio off.

Firmware stayed at verified source `880dc318072f191f1440d3f0b262d83e32729b59`,
CI run `41786883085`. The CI artifact and UF2 hashes matched the published
records; picotool loaded and verified the firmware from BOOTSEL. CDC returned
on COM4. No subsequent firmware changes were flashed. All raw audio, addresses,
and diagnostic logs stay in the local sibling `live-880dc31` directory.
[Sanitized evidence](evidence/local-windows-20261104.json) records identities,
metrics, limits, and archive hashes.

## Physical findings

With laptop MaxxAudioPro disabled, pure isolated tones produced:

| Microphone state | Left-only tone | Right-only tone |
| --- | --- | --- |
| Open | Left ear only | Right ear only |
| Closed | Silent | Right ear only |
| Reopened | Left ear only | Right ear only |

The confirmed close/open sequence kept the playback endpoint and Bluetooth
connection open. Capture was confirmed closed by firmware status. The test
signal's earlier broadband noise was intentional stimulus, not a newly
identified static defect. One intermediate attempt was stopped because the
initial capture ownership observation was active; it must not be treated as
a completed close/open test. The user then closed other microphone users and
typed replies for the confirmed sequence.

One explicit console `K` refresh with capture closed accepted SUSPEND and
rebuilt the encoder, but timed out in WAIT_START (`stage=4`, `rc=4`). The
firmware locally terminated the ACL (`0x16`). This was a failed explicit
refresh, not another observed spontaneous 30-second peer termination.

An explicit `savedconnect` then reconnected without scanning, fresh pairing,
or putting the AirPods back in their case. The user heard the left-only tone
in the left ear while capture remained closed. This demonstrates saved-bond
reuse and a manual recovery path on this host; power-cycle bond persistence
and an automatic lifecycle repair were not established. No automatic
reconnect was used to hide the failed refresh.

## Measurements and retained coverage

The first packaged 45-second probe failed because its starting snapshot
caught an automatic damage refresh in WAIT_START. A supplemental interval
waited for continuous readiness with both audio endpoints open, then passed:
6,089 additional mic frames decoded, no decoder errors, AU/PCM drops, or
additional missing USB samples. Its AACP session age advanced from about
210.5 to 256.1 seconds on the existing connection. The historical 30-second
remote termination did not recur in that interval.

The later automatic rate probe passed 256 kbps, then failed 192 kbps with
186 mic AU drops and 95,168 missing USB samples. It stopped on that failure.
Neither game mode nor a new ten-minute soak was measured. These are laptop
observations; do not call their difference from earlier PC measurements a
firmware-only regression. Settings were restored to standard 256 kbps,
game off, level 1. A final explicit saved-bond reconnect left the headset
connected and confirmed, with capture closed and the original profile ready.

The earlier ten-minute run on `2911a82` is retained rather than repeated.
Its existing evidence distinguishes successful completion and clear reported
playback from strict zero-loss acceptance (7 AU drops and 14,656 missing USB
samples). The user's reminder that this soak was already completed is a
continuation constraint; no replacement soak was started here.

## Local runner changes

The profile measurement path now invokes the existing bounded duplex-ready
wait after the fixed settle delay, just as the reconnect path already did.
The new regression reproduces the delayed refresh with the old production
runner and passes with the change. Steady-interval loss checks remain strict.

`--reuse-pairing` / `-ReusePairing` reuses an existing selected session or
dials a selected saved bond without discovery or fresh pairing. It refuses
ambiguous history and a different connected headset. This is a local source
change; it has not been repackaged or shipped in the verified CI bundle.

Validation: five matrix replay tests, 27 runner contract tests, and the actual
Windows PowerShell launcher fixture passed. The before-change refresh fixture
failed as expected. The full simulated CLI suite could not start because this
Windows environment has no `cc` compiler; no full host-suite or new target-build
claim is made. Firmware source was not changed.
