# Independent playback START restart audit (2026-11-04)

## Source boundary and evidence

Pinned parent: `18be74cfe99f2584bcf26a0c0f0571c75a7f7bec` on `work/local-windows-20261104`.
This investigation uses an independent branch and repository/public offline evidence only. No raw
archives, COM port, headset, target runtime, or other workers' branches were accessed.
The cloud execution container has no GitHub DNS access, so SDK/host checks must not be
represented as having run locally unless CI or a separate usable checkout executes them.

- **Application command intent:** explicit console `K` invoked forced ELD recovery.
  `eld_transition_request` stops the pump and schedules SUSPEND, then a rebuild and START.
- **Local API submission:** the physical `880dc318` log established SUSPEND acceptance
  and a successful local encoder rebuild. The pinned candidate adds at most one START
  retry in `eld_transition_retry_start`. `src_start_stream()` treats a zero
  `avdtp_source_start_stream` return as submission, **not radio transmission**.
- **Actual signaling transmission:** the SDK's `avdtp_start_stream()` queues
  `start_stream=1` and requests CAN_SEND_NOW. Its return zero does not cover the later
  `avdtp_initiator_send_signaling_cmd_with_seid()` / `l2cap_send()`; the caller
  ignores that return. The initiator clears `start_stream` before checking that the
  endpoint is OPENED, so an intervening state change can silently drop an enqueued START.
  Source code does not establish whether the failed hardware START left the radio.
- **Peer response:** no START accept is recorded for the explicit failed refresh;
  this is compatible with no send, lost send, no reply, or a misassociated response.
  The SDK initiator compares transaction labels only inside DISCOVER, and processes other
  ACCEPT/REJECT messages without that label check, allowing late/duplicate responses
  to mutate state or emit acceptance for another outstanding transaction.
- **SDK endpoint state:** SUSPEND ACCEPT changes STREAMING to OPENED; START ACCEPT
  changes OPENED to STREAMING. This state is distinct from the application
  `ELD_WAIT_START` phase and from a queued START flag.
- **Application transition state:** the physical refresh ended in `WAIT_START`,
  `stage=4 rc=4`, then the application locally disconnected the ACL with `0x16`.
  Pinned candidate: one retry, three-second managed-phase timers, bounded abort.
  START acceptance while a superseding profile is pending initiates another SUSPEND.
- **Running media-pump state:** encoder rebuild and SDK START queueing never start
  the pump; `src_stream_start_accepted` permits the pump only after managed READY,
  codec setup, and scan/session gates. The hardware refresh failed with playback stopped.

The distinct `055513` and `055648` ACL disconnects were remote-reported `0x13`
roughly 30.12/30.17 seconds after AACP open on `241dc18`. The later verified
`880dc31` laptop session advanced its AACP session from about 210.5 to 256.1 s
without that spontaneous termination; its manual `K` failure was a **local**
deadline/termination. They are not one established mechanism. AACP Connection Response
success is an 18-byte type-1/service-4/status-zero message, never the invented
six-byte status-one ACK.

## Competing diagnoses and offline falsifiers

1. **SDK queue accepted, START not transmitted (or transmitted too late).**
   Reproduce by calling the production SDK START API while an endpoint is not OPENED
   (current reference returns success), or changing endpoint state between queue and
   CAN_SEND_NOW (flag is cleared without send). Falsify on hardware with matching
   signaling-CID TX metadata/transaction label, not merely a zero API return.
2. **Late/duplicate SUSPEND/START response consumes newer state.**
   In pinned `avdtp_initiator.c`, label validation is scoped to DISCOVER.
   Reproduce by injecting an old-label START or SUSPEND accept while a newer command
   is in flight. Disprove by showing strict label/phase validation at the actual SDK
   receive point and an offline response-replay regression.
3. **Peer received START but did not answer or rejected it.**
   The one bounded retry is a mitigation, not proof of a reply or RF reliability.
   A second timed-out attempt must fail closed rather than reconnect silently.
   Distinguish on radio only with TX label and peer reply evidence.
4. **Application bookkeeping/deadline handling prevents a valid transition.**
   Exercise immediate SDK error, explicit rejection, late acceptance, superseding
   profile requests, teardown and deadline boundaries under repeated writes.
5. **Peer-initiated SUSPEND during a managed START** can cancel an outstanding
   START and require a bounded new rebuild. A duplicated stale initiator acceptance
   must not be treated as a new peer event; replay both paths separately.

## Repair plan (before production changes)

- Preserve the pinned one-retry policy; do **not** add reconnect, another rebuild
  for missing START replies, or extend the active phase timer for coalesced writes.
- Reject SDK START submissions against a non-OPENED endpoint immediately instead
  of reporting success for a flag the SDK would silently discard.
- In the SDK initiator response path, reject mismatched transaction labels
  *before* clearing the wait state or changing endpoint state/emitting callbacks.
  Apply this in the applied SDK patch, not by editing the pinned comparison copy.
- Add a production-SDK source extraction regression for invalid initial START
  queueing and transaction-label gate, and extend transition/adapter tests for
  exact single retry, second timeout, stale accepts, supersession and teardown.
- Keep OPEN-before-media and START-after-media deadlines separate; emit the
  original first failure, not a synthetic success. Retain the 18-byte AACP ACK.
- Validate host regressions and three target firmware variants in Actions.
  Record actual tool output and any unavailable checks separately.

## Hardware follow-up (not run by this worker)

On a *separately authorized* candidate, start at connected ELD READY with
capture closed and a known stereo left-only test tone; record one explicit
`K`, one `:eldstatus`, SDK endpoint/queued START/TX-label diagnostics and
one short left-only listening check. Stop on failure and retain first-fault
report; do not automatically reconnect, run a soak, or infer signaling TX from
the local submission return. No RF interoperability finding follows from host
simulation or a successful build.
