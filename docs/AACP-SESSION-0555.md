# Repeatable session disconnect: 055513 / 055648

Both physical runs used source `241dc1863b96c9f79ac39c6469005c9bc2c8b190`.
Automatic flashing worked from BOOTSEL and from running firmware via the CDC
reset fallback, with the expected firmware identity returning on COM3.

| Capture | Final disconnect after AACP open | Last decoded mic frames | Decode errors / AU drops / PCM drops | Failed phase |
| --- | ---: | ---: | --- | --- |
| 055513 | 30.119535 s | 756 | 0 / 0 / 0 | Capture warmup |
| 055648 | 30.166869 s | 1,924 | 0 / 0 / 0 | First 256 kbps interval |

Both final HCI disconnections report reason `0x13` (remote termination).
Neither bundle records a firmware fault hold or collector/restore errors.
This identifies the reported termination direction, not the peer's decision
process: a peer can also terminate in reaction to our protocol behavior.
Microphone traffic continued until teardown. The first measured portion of
the second run showed no new missing USB samples before the link ended;
missing samples after teardown must not be attributed to ongoing codec loss.
The lower-rate/game cadence fix was not reached by these runs.

The user confirmed phone Bluetooth was disabled and input came from its
speaker. A possible Watch request was considered and then doubted; the
captures contain no evidence identifying another host. Do not attribute this
failure to a user's other device without supporting evidence.

Sanitized measurements and archive hashes are in
[the evidence record](evidence/aacp-session-0555.json). Raw voice, addresses,
pairing keys and the non-public reference bundle are not committed.

## Offline investigation and limits

The pinned working Pico fork uses the same three initialization command byte
arrays and the same Apple Device ID values (`004c:0000:0000`, Bluetooth vendor
source). Its SDP record handle is `0x10005`; ours uses `0x10006` to coexist with
the optional HFP record. Initialization order here registers SDP before DID.
Removing the Apple identity is not justified by a differentiating source bug.

[LibrePods' documentation](https://github.com/librepods-org/librepods/blob/main/linux/README.md#hearing-aid)
notes short disconnects when spoofing an Apple Device ID without implementing
all expected Apple traffic. That supports investigating unhandled protocol
messages, but does not establish this failure's cause or a 30-second deadline.
The suggested Full disassembly has additional initialization commands; it is
not authoritative private source or evidence that copying those commands would
repair the observed disconnect. No speculative commands were added.

The production transport test advances a confirmed open session beyond 30
seconds without a local channel expiry. Existing local setup/grant deadlines
are 5/3 seconds, not 30 seconds. This narrows the investigation; it does not
simulate the peer or prove an absent interaction with another profile.

## Diagnostic implementation

- Successful initial command submissions log command index, length, elapsed
  session time and whether peer traffic was already recognized. A successful
  local submission is not a peer acceptance.
- AACP control type/opcode/length is logged on first appearance, capped at
  16 distinct headers per channel. Microphone content and arbitrary control
  payloads are never printed. Counters and the last observed header continue
  updating after the log cap. Batched known controls retain their existing
  parsing; an unhandled batch records its first header and existing framing
  error counter rather than inventing a complete parse.
- Teardown records its local reason and session age before clearing state.
  Periodic summaries preserve the last receive/transmit ages. Existing
  teardown/retry policy and command bytes remain the same.
  A local `host-disconnect` label names the cleanup entry point; profile
  releases can precede the HCI disconnect notification, so that label alone
  does not establish who initiated the underlying termination.
- `aacp_mic_get_session_diagnostics()` returns a lock-protected, allocation-free
  metadata snapshot declared in `src/btstack/aacp_mic.h`. `:telemetry` includes
  JSON kind `aacpsession`: open/current CID, age, successful init mask/count,
  peer-seen state, matching handshake-ack header seen, control observations,
  unhandled count, logged-header count, last opcode/length and RX/TX ages.
  `init_mask=7` means three commands submitted locally, not negotiated success.
  TX command 255 denotes a generic control write; absent ages are UINT32_MAX.
  Teardown retains the final session metadata until the next channel opens.
- The old runner labeled any recognized peer traffic as `aacp_handshake: PASS`.
  It now reports that separately as `aacp_peer_response` and uses the explicit
  matching ACK-header diagnostic for the handshake result. Missing ACK evidence
  remains UNVERIFIED. This fixes a reporting defect, not physical termination.

## Focused live probe

```powershell
.\Run-Test.ps1 -CdcPort COM3 -SessionOnly
```

The launcher automatically flashes and continues into a 45-second simultaneous
AAC-ELD/microphone/USB diagnostic/HID logging interval. It starts after pairing
and preflight without another start prompt. Wear the AirPods; play your normal
phone-speaker clip during the first 20 seconds if convenient. No counting or
talking is required. It omits the channel prompts, control matrix and ten-minute
soak. An early disconnect preserves diagnostics before capture cleanup and
still produces the results ZIP. The full matrix remains available without
`-SessionOnly`, but is not needed for this investigation.

This is a diagnostic candidate. No physical fix for the 30-second disconnect,
mic-closed channel asymmetry or residual long-soak loss is claimed. A stable
probe would be new evidence requiring explanation, not proof that logging
repaired the underlying behavior.

## Verification

The maintained native suite passes 66 checks with zero failures/skips, including
production transport metadata lifecycle/bounds and the actual JSON serializer.
The CLI replay has 15 scenarios, including a successful session-only run,
preservation of a peer disconnect around 30 seconds, and a missing ACK that
must stay UNVERIFIED. Target CI and exact packaged CLI evidence are recorded
with the final source/artifact identity after building. These simulations do
not establish physical protocol acceptance.
