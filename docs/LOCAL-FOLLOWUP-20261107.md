# Local Windows follow-up — 2026-11-07

Started from `origin/main` at `018685157ab8c5dedc66008e2e54ae3a38994e25`,
in a new `work/local-windows-followup-20261107` worktree. Existing checkouts,
local commits and unfinished core-1 probe files were preserved. The task order
is [the November 7 handoff](LOCAL-AGENT-TASKS-20261107.md). No device was flashed
and no firmware or codec test/build was run locally during this pass.

## Evidence and plan before selecting changes

The last physical laptop source is `880dc318`, not integrated main. With
MaxxAudio disabled, mic close produced left silence/right correct; reopen
restored stereo. Saved-bond reconnect restored left with capture closed. The
192 kbps failure had 186 dropped AUs and 95,168 missing USB samples in about
20.6 seconds; a separate 45-second interval had no new loss. Keep both facts
and the earlier completed ten-minute run. CI does not supersede them.

The integrated code was compared with the pinned han-um `d18d083` snapshots,
their provenance in `references/manifest.json`, and the history recorded in
`MIC-ROUTING-REFERENCE-REVIEW.md` and `references/research-history.json`:

- `usb_capture_close()` only clears capture intent. AACP sends the same five
  command byte sequences as the pinned source. Ordinary START/STOP performs a
  microphone generation discontinuity, not an A2DP reset or jitter write.
- `eld_profile_select()` does not read capture intent. The mic-capable build
  uses CBR/core-only encoding regardless of whether Windows opens the mic.
- `codec_fdk_fill()` sends one interleaved stereo input to FDK. Playback uses
  one stereo media payload, not separate per-ear streams. The existing USB
  tap precedes gain/mixing; the TX header walker validates framing, not audio
  content. Neither proves that valid left audio reaches the encoder or peer.
- Foreground encoding, already merged, alternates one playback AU with a
  bounded mic worker pass. The mic AU ring holds 32 frames (240 ms at the
  observed 7.5 ms cadence); PCM holds 16 (120 ms). A worker stops when PCM is
  full without consuming the current AU. Queue saturation alone cannot say
  whether the worker was starved, delivery was bursty, or USB backpressured it.

Falsifiable causes and next measurements:

| Hypothesis | Evidence needed / falsifier |
| --- | --- |
| Host or local gain/mixing loses left PCM on mic close | Compare isolated-tone USB `[tap]` and post-gain `[eld-pcm]` windows with capture confirmed closed. Correct left at both points falsifies loss before FDK. |
| Encoder/packet corruption or peer state loses left | Correct pre-encoder PCM plus valid AU framing is necessary but insufficient. Retain TX diagnostics; compressed-content decoding or a wire capture remains necessary before attributing the failure to the peer. Recovery by reconnect alone does not localize it. |
| 192 kbps worker starvation / burst backlog | Compare AU arrival/burst counters, residence times, decoder/encoder duration and work-pass duration across short same-host 256/192 intervals. A large queue wait with free PCM supports delayed service; device timestamps include preemption. |
| USB/PCM backpressure causes compressed overflow | Count worker exits on full PCM and compressed drops observed with full PCM, alongside PCM depth and missing USB samples. Fullness observations are correlation, not a causal diagnosis. |
| Explicit refresh still fails after integrated SDK fixes | Exercise OPENED guards, one bounded unanswered START retry, stale labels and acceptance-label retirement in CI, then perform one physical refresh while preserving first fault and local/remote disconnect reason. |

Choose diagnostics before changing undocumented protocol bytes, microphone
clocks, routing policy or queue capacities. The existing foreground scheduler
and restart repairs need a new physical comparison; adding another recovery
policy now would obscure that comparison.

## Candidate changes

Reconciled historical authorization/evidence scope and removed stale retained-
branch/current-probe descriptions without erasing old measurements or permission.
The public build remains Lite; Full sources are still unavailable here.

The existing `U` tap also enables `[eld-pcm]`: a 500 ms summary of the actual
stereo input passed to FDK after gain/mixing/resampling. It reports per-channel
peaks, frame count, mic state and generation; a window spanning a generation
change is marked `transition`. It does not modify PCM or dump raw audio and
does not establish compressed-output or acoustic correctness. Enable only for
short routing probes, then disable it for scheduling comparisons to avoid
diagnostic overhead. The production-body CI fixture checks left/right
isolation, -32768, generation changes, clock wrap and disabled reset.

`micstats` adds `au_wait_last_us`, `au_wait_max_us`, `work_max_us`,
`pcm_blocked` and `au_drop_pcm_full`. Wait is enqueue-to-decode start for current
AUs only; stale AUs are excluded. Work duration includes preemption. Counts are
lifetime wrapping totals; maxima are lifetime values, so an unchanged maximum
does not establish a good new interval. Use interval counter deltas and fresh
sessions for comparable maxima. The AU ring adds 128 bytes of timestamp storage;
CI map/heap evidence must be checked. Queue capacities, work bounds, PCM clock,
loss thresholds and codec/profile policy are unchanged. Host threaded mocks use
an atomic clock because the producer now reads enqueue time too.

Firmware and firmware/codec regression execution stays in Actions, including
the production mic queue fixture, parallel experimental queue test, real FDK
duplex/profile tests, 32-bit allocation audit, transport negative controls and
the new post-gain tap fixture. USB host push path filters were removed so the
exact-source watcher cannot wait for a required workflow that never triggers.
Experimental dual-core mic decode stays OFF by default and outside automatic
live packaging. No core-1 playback encoder was enabled.

## CI checkpoint and continuation

Only watcher tests run locally. The watcher now checks the exact session log's
identity and unfinished turns before callback; it refuses unknown/busy state.
No `--last`, approval bypass or public listener is used. Machine-specific paths,
session UUID, exact candidate SHA, watcher PID and completion output belong in
the sibling local CI checkpoint, not tracked evidence.

After callback, verify the exact candidate SHA and all three required push
workflows before selecting artifacts. Record run IDs, variant, artifact hash
and UF2 identity. Successful workflows are offline evidence, not physical
acceptance. Do not flash automatically from the callback. Prepare the short
same-host comparison in handoff order, enumerating current ports first. Avoid
the launcher's default full matrix/600-second soak; session-only also omits
isolated channel checks, so neither default is the complete targeted plan.

## Physical setup failure and response-ordering repair

All three required push workflows passed for `e9f548259cfc402db88a1e2ea7ca0a56ee99844a`
(firmware `42417493025`, USB host `42417493014`, runner `42417493056`). The
single-core Lite rpi0065 AAC-ELD artifact `13592137712` was downloaded and its
archive hash and every candidate manifest hash verified. Picotool loaded and
verified it; COM4 reported the exact candidate identity. See
[sanitized setup evidence](evidence/local-windows-20261107-setup.json).

The attempted 256 kbps baseline never reached steady playback. AVDTP signaling
and AACP authentication/control succeeded, but the media endpoint remained
unset: `codec=0`, `transition=off`, `active_bitrate=0`, `negotiated_bitrate=0`,
`local_seid=0`, `remote_seid=0`, no TX packets. One explicitly requested
disconnect/saved-bond reconnect reproduced this state. The runner preserved
both failures and stopped. No fresh pairing was needed. Microphone-only
reception is not a duplex result; its setup losses cannot be labeled a 192 kbps
steady failure. No isolated listening, game profile, explicit K refresh or
replacement soak was measured. The hardware failures remain unresolved.

Source review found a concrete reentrancy defect in the integrated SDK patch.
It retired an accepted response's label before the final generic ACCEPT event,
but after `avdtp_signaling_emit_sep_done()` and
`avdtp_signaling_emit_capabilities()`. The application's synchronous callbacks
there call `avdtp_source_get_all_capabilities()` for the next endpoint. That
assigns a new transaction label; the old handler's later retirement overwrites
it. With the new common stale-label guard, a legitimate capability response
can then be discarded. This is a falsifiable cause for the observed setup
stall, not wire-level proof that every observed stall took that path.

The repair moves retirement to the beginning of the accepted-response arm,
before any event callback. The old DISCOVER-local label check is removed
because the common guard has already validated it; comparing again after
retirement would reject the valid discovery response itself. OPENED guards,
bounded START retry and stale-response filtering remain. Configure requires
the stronger patch marker. `test_sdk_response_reentry.py` executes the actual
production response prelude, DISCOVER/capability arms and generic ACCEPT tail
with synchronous next-command callbacks at all 15 label positions. It also
compiles the exact e9f5482 patch, reconstructed against the unmodified licensed
reference, and requires its specific overwritten-label assertion failure;
compile errors cannot count as a successful negative control. All execution
is deferred to Actions. The fixture contains no raw hardware data.

The next physical candidate must first pass exact-source CI and establish
media/configuration readiness before restarting the planned audio comparison.

## Observed callback limitation

The e9f5482 watcher correctly recorded successful CI, but its one CLI callback
was refused: Desktop's thread store still had an active writer. A logged
`task_complete` does not release Desktop's persistent writer. No second CLI
resume was attempted. Continue in the original chat from `completion.json`;
do not retry a CLI resume against this Desktop-owned session or add an approval
bypass. Subsequent watches here must record completion without CLI resumption
unless a supported native completion notification is actually established.
## Physical comparison on repaired source 1979ae6

All three required workflows passed for firmware source 1979ae6be1c2daf9e1db8024763504d4061c4588 (firmware 42419581145, USB 42419581084, runner 42419581191). Single-core Lite artifact 13592873692 was hash-verified, flashed and identified on COM4. Saved-bond playback setup succeeded. See evidence/local-windows-20261107-live.json for identities, interval counters, phase-matched PCM windows and local archive hashes.

Each short 256 kbps, 192 kbps and both game-mode interval passed with zero new AU drops and zero missing USB samples. Applied jitter was 150/150/90/60 ms. Normal 192 kbps recorded 1,412 PCM-full worker exits without AU loss. 320 kbps was skipped at the negotiated 256 kbps ceiling. No replacement long soak was run.

The mic-close channel defect remains: with one continuously open playback endpoint, the user heard left-only with mic open, silence with mic closed, and left-only again after reopening. Phase-matched encoder-input windows retained left peaks about 316 and right about 1. One explicit K refresh with capture closed completed without disconnecting and restored left-ear sound. Saved-bond reconnect also retained audible left-only playback with capture closed, without fresh pairing. These are manual recovery results, not an automatic lifecycle repair. Compressed content and peer rendering remain unverified alternatives; pre-encoder loss is not supported by these measured windows.

Wi-Fi/runner interruptions invalidated an intermediate fresh-open silence report. The final accepted sequence used current heartbeats and synchronized tap state. Lifetime AU drops reached 248 across startup/interrupted/lifecycle activity; zero-loss claims apply only to the measured steady intervals, not the whole session. Audio stopped, capture closed and standard 256 kbps/game-off/level-1 preferences were restored without cleanup errors. Raw recordings and addresses remain local.

The owner subsequently requested an explicit Pico 2 W dual-core execution comparison. This authorizes the separate opt-in experiment, not a default change or automatic packaging-gate bypass.

## Explicit dual-core experiment and final disposition

After the single-core comparison finished, the owner explicitly requested a Pico 2 W dual-core execution test. The existing CI-built experimental artifact 13592997637 from the same source/run was downloaded and its archive digest verified. Its CMake cache selected DUAL_CORE_MIC=ON, map reserved a 16 KiB worker stack, build/allocation verification passed, and compile commands contained no global PICO_FLASH_ASSUME_CORE1_SAFE=1 bypass. The automatic packaging exclusion and default-OFF build option were unchanged. A separate opt-in bundle was produced with the existing package_live_test.py from an exact git-archive source snapshot; all existing authorization/build/allocation/hash gates remained enabled. Windows required Python -X utf8 for document packaging. This was packaging/integrity verification, not a local firmware build or codec test.

The distinctly named experimental UF2 was loaded and verified with picotool on COM4. Its 256 kbps interval passed with zero AU drops and zero missing USB samples. Its 192 kbps interval FAILED: zero AU drops, but 2,816 additional missing USB samples. The single-core 192 kbps interval had passed with zero missing samples. The experiment stopped at that failure; neither game mode, channel lifecycle, soak nor power-cycle persistence was tested on dual-core. First-fault snapshots and raw recordings remain local. See evidence/local-windows-20261107-dualcore.json for exact identities, sanitized before/after metrics and limits.

Decoded AUs progressed with the binary whose core-0 mic worker is compiled out, supporting functional core-1 decoder execution. This does not measure core utilization, stack high-water, allocator/FDK-global safety on all workloads or complete flash-lockout qualification. Profile setting changes occurred during duplex without an observed reset, but dedicated lockout result telemetry/persistence qualification was not collected. Dual-core is not recommended as a production replacement on these results. Audio/capture were stopped and preferences restored after the failed interval; the known single-core candidate is restored as cleanup, with the flash report recorded in the evidence JSON.

The final callback experiment also did not demonstrate automatic continuation. The native tool accepted a delayed message, but it surfaced only after another human message. Accepted delivery is not proof that a new turn started. No further callback or competing CLI resume was armed. Future agents must not promise automatic continuation until an actual idle-to-running transition has been observed.
