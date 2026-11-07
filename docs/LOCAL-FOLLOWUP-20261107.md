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
