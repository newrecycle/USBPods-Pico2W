# Branch and pull-request integration review — 2026-11-05

The user requested review and integration of all branches and pull requests.
The inventory contained 19 branches and two open draft PRs. Baseline main:
`551d94bda9bf83b283512f98d2c35047d87ba6be`.

## New work integrated

| Source branch | Reviewed head | Work retained |
| --- | --- | --- |
| work/local-windows-20261104 | 18be74cfe99f2584bcf26a0c0f0571c75a7f7bec | Saved pairing, readiness evidence, foreground bounded ELD encoding, one unanswered START retry |
| work/local-windows-playback-restart-20261104-gpt6 | 1bc7093660a2f176670c38e9450b6351854b14d0 | SDK OPENED precondition, stale response labels, reentrant acceptance ordering, production-source negative controls |
| work/local-windows-20261104-mic-close-cloud-audit-01 | 2d16f2d341b13f3929b3cdf5975194f38c04cea6 | Capture-window PCM tap correlation and sent/observed lifecycle diagnostics |
| work/local-windows-evidence-audit-20261104-gpt6 | 05dde86d80da963c26d7beaf39e7a531b7469c13 | Operator observations, capture ownership, continuous readiness, first fault, preflight truth, launcher and packaging contracts |
| work/dualcore-mic-flash-safe-20261104 (PR #3) | e21c46969fd6af4fefa04473b1316485790c445d | Opt-in core-1 mic decoder, early flash lockout, safe QSPI commands, stack limit, concurrent real-FDK host tests |
| audit/duplex-192k-profile-gpt6-20261104 (PR #4) | 97db0195bdd1b5cdd3a77f393852c9921f643309 | Applied jitter diagnostics and strict actual profile matching |

`work/playback-start-contract-20261104-gpt6` is contained in the playback-restart
head. All other historical branches were already ancestors of main (or equal
to it). Exact inventory is in
[evidence/integration-review-20261105.json](evidence/integration-review-20261105.json).
Branch refs are retained.

## Review findings and resolutions

1. Main-loop overlap: preserve foreground playback service in both core layouts.
   Neither layout sleeps over pending foreground playback work. Only the
   single-core path gates sleep on the mic decode queue.
2. Validation overlap: preserve continuous readiness, recovery visibility,
   first-fault snapshots and strict loss counters while enforcing the new
   selected/applied profile predicate.
3. Sampled steady windows previously checked readiness but could miss an applied
   profile drift that recovered before the endpoint snapshot. Every sampled
   steady window now verifies the requested profile. Mic-reopened and optional
   relay steady windows retain sampled faults too. Sampling cannot prove
   absence of interruptions between samples.
4. Host test setup used the pristine SDK reference for a test that now requires
   the production transport patch. The offline runner patches a disposable
   reference copy; comparison files remain unchanged. A caller-supplied
   `--sdk-source` is expected to be already patched, like target CI.
5. Two runner fixtures omitted new applied-policy fields; the CLI simulation
   also claimed nonzero active VBR/SBR while declaring duplex CBR. Fixtures now
   report coherent applied state; fail-closed production checks are unchanged.
6. Configure-time SDK checks now require the START guard, stale-label guard and
   pre-callback label retirement, preventing an older partial SDK patch from
   silently configuring.
7. Test manifest and workflow unions preserve all unique tests, Windows branch
   triggers and the experimental parallel codec target. The validation audit
   runs through the portable offline manifest too.

## Verification and release boundary

The combined offline suite passed **75/75**, zero failures and zero skips.
This includes ASan/UBSan production-source contracts, 15 simulated CLI scenarios,
real-FDK duplex/profile tests, threaded queue and concurrent codec tests, and
packaging/tamper validation. See the sanitized evidence record for individual
results. All eight CI jobs passed on published source `3ba230c93de32703ee93b81fff0c9c9252add5e8`:
[four Pico variants and Windows launcher](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41971938672),
[runner and Windows regressions](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41971938681),
and [USB/HID regressions](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41971938722).
The subsequent evidence-record commit changes only this report and its JSON;
firmware, tests, build policy and dependencies remain byte-identical.

`USBPODS_DUAL_CORE_MIC` remains **OFF by default**, requires microphone decoding,
and its distinctive experimental target remains excluded from automatic live
packaging. The old core-1 playback encoder remains disabled. No new physical
release claim or packaging authorization is created by this integration.

The physical left/right symptom on microphone close remains unresolved.
The latest 192 kbps capture had 186 AU drops and 95,168 missing samples over
about 20.6 seconds, despite approximately 50 playback packets/s; this integration
does not establish a cure. Another approximately 45-second interval had 6,089
decoded mic AUs without new loss. Existing ten-minute evidence is retained;
no replacement soak was performed. No device was flashed from this workspace.
See the Windows handoff and profile/dual-core audit documents for competing
hypotheses and required on-target scheduling, memory and flash-lockout evidence.

## Publication method

Remote source heads are preserved as merge parents of the reviewed tree.
The local review used isolated source snapshots because authenticated Git
transport was unavailable; those temporary import commits are not published.
The reviewed tree is first published on an isolated integration branch for CI,
then integrated through the existing stacked PRs (#4 into #3, #3 into main).
