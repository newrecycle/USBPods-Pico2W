# End-to-end verification of the 5a4ea5e live candidate

The delivered live package pins firmware source
`5a4ea5e7f72b0208c060d5621678e51abff6383f`, from successful Pico CI run
[41766248409](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41766248409).
It includes the AAC-ELD microphone build, matching Windows runner and USB-only
diagnostic instructions. The added test and this record do not change firmware
or the runner in that package. Keep that package for the ongoing physical run.

## Package identity

| Item | SHA-256 |
| --- | --- |
| CI artifact, rpi0065/AAC-ELD mic | `0fa4c592d5775eaaaa99f534637878c0e265dcb4a1e32817e730359e0423d7bc` |
| Delivered live ZIP | `58a76de5c453389d611fd37bc6e8ba650a34217d0b1a2043d31682bb7ee0828b` |
| Included UF2 | `48c6f8a5f53961bca4f2dff1885cedc86519984796d1443b6e18230f051bc8d9` |

The CI artifact digest, packaged runner-file hashes, verified binary hash,
embedded source SHA, UF2 family/payload structure and positive build/heap audit
were checked. The ZIP contains the unmodified CI candidate, plus a quick-start
file and repair evidence. It contains no captures or pairing keys.

## Coverage

| Path | Executed evidence | Boundary |
| --- | --- | --- |
| Delivered runner entry point through result ZIP | Nine scenarios execute actual `live_test.main()`, `Link`, threaded `Recorder`, `run_matrix`, `AudioSession`, WAV writer, cleanup and ZIP creation. CDC bytes are fragmented; telemetry order alternates; an unrelated HID device is rejected. | Device responses, Windows host APIs, input samples and elapsed test time are simulated. |
| CDC command and profile contracts | The runner's actual bytes are parsed by compiled production `control_command.c`; expected profile parameters come from production `eld_profile.c`. ACK IDs/values are checked against the real parser. | Dispatch side effects and status counters are modeled. |
| Simultaneous AAC-ELD playback/mic | Real FDK tests encode/decode the playback profiles with production mic queues/decoder active. The production PCM-to-Apple-AU path checks gain, stereo ordering, sequence wrap and MTU. | Synthetic host samples and AUs; no radio or acoustic measurement. |
| Mic STOP/START and reconnect history | Twelve generations match a fresh real FDK decoder sample for sample; stale compressed and decoded data is rejected. | Generation changes are driven offline, not by a live AirPod. |
| USB intent, AACP liveness and ELD ownership | The coupled fixture executes production helpers for capture intent, bounded AACP retries, profile races, rejected START, teardown and crossed deferred START/SUSPEND. Queue ownership survives 640 simulated IRQ/state combinations. | SDK/peer and encoder allocation are mocked in the coupled fixture. |
| USB diagnostic and HID paths | CDC collector logs continue while simulated playback/capture callbacks run. Production USB lifecycle/HID tests cover busy endpoints, release delivery, suspend and mount transitions. | Firmware submission and collected reports do not prove a Windows app received the intended media action. |
| Target compatibility/resources | All three Pico CI variants, UF2/image verification, SCO probe builds and 32-bit codec allocation audit passed for the pinned source. | Build/link evidence, not target execution or measured runtime heap/timing. |

The maintained offline suite passes **61/61 checks, zero failures or skips**
with the added CLI test. The CLI replay was
also run against the exact extracted, hash-verified package, not just the repo's
runner files. Detailed sanitized outcomes are in
[live-candidate-5a4ea5e-e2e.json](evidence/live-candidate-5a4ea5e-e2e.json).

## Nine CLI scenarios

1. Complete 256 kbps-ceiling run: unsupported 320 kbps is SKIP; supported profiles,
   both game modes, mic close/reopen, three reconnects and soak complete.
2. Complete 320 kbps-ceiling run: the 320 kbps profile also runs and passes.
3. Capture held by another client: closing our handle does not claim exclusive
   capture shutdown; ownership-dependent checks remain SKIP/UNVERIFIED.
4. Control writes without peer echoes: submission succeeds, readback stays
   UNVERIFIED rather than becoming PASS from cached state.
5. Running firmware identity mismatch: no pairing/audio begins; failure ZIP saved.
6. Pairing rejection: failure ZIP preserves the error and CDC diagnostics.
7. Profile START rejected with code 263: first-failure state is preserved before
   capture cleanup; subsequent controls are skipped.
8. Mic watchdog exhausted while playback continues: capture fault is preserved
   before cleanup and the run fails.
9. Descriptor/settings normalization: requests replug/rerun before attempting
   pairing, with a failure bundle explaining the intentional stop.

All cases assert the intended exit code, result-ZIP integrity, handle/stream
closure and absence of collector/restoration errors. Completed cases also check
settings/control restoration and actual WAV headers. Physical listening prompts
receive no simulated affirmative answers; completeness remains false.

## Reproduction

Linux/WSL with a native C compiler and NumPy:

```sh
python3 tests/test_live_cli_e2e.py
python3 tests/test_live_cli_e2e.py --candidate /path/to/extracted/USBPods-Live-Verification-5a4ea5e --output build-live-cli-e2e
python3 tools/run_offline_checks.py --fdk-lib /absolute/path/to/asan/libfdk-aac.a
```

The default CLI test creates an explicitly synthetic manifest/UF2 fixture.
`--candidate` verifies and runs the delivered package instead. Raw simulated
results contain the production runner's `hardware_run` field because the runner
is unchanged; the outer test report always marks them simulated and excludes
them from physical acceptance. Do not present those raw results as device runs.
Choose a fresh `--output` directory for each replay.

No new production blocker was reproduced in this pass. Remaining physical
acceptance is the user's Windows/Pico/AirPods run: bonding, actual negotiation,
stereo independence with mic closed/reopened, speech pitch/quality, RF timing,
USB drift and HID host actions. The withdrawn bass complaint is not a confirmed
defect. The runner's optional quality-comparison prompt may be left unverified.
