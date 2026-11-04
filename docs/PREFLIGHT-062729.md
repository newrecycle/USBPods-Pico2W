# 062729: preflight recovery race and connection-response framing

The physical run used `20475ab316223feb2d22a5407826295be40b49a8` and stopped
before capture. The selected session remained connected: at approximately
27.477 seconds in the CDC log, the existing damage-recovery policy suspended
playback, rebuilt ELD and restarted it at 27.707 seconds. Preflight sampled
that pause and exited. Later TX progressed and the recovery was confirmed.
This run does not reproduce the previous 30-second final ACL termination;
the one ACL termination recorded belongs to the earlier startup session.
The configured codec was AAC-ELD, 256 kbps, CBR/core-only, with six slots.

Preflight now requires a continuous stable interval within one fixed budget
of 15 seconds plus the requested measurement duration. A temporary setup
transition resets that interval and is retained in the preflight log and
`resettles` result count. Disconnects, fault holds and exhausted mic watchdogs
still fail immediately. No packet progress or media send failures still fail;
repeated recovery cannot extend the overall deadline indefinitely. Steady
audio-matrix acceptance remains strict. This is a runner repair, not proof
that the reason for the damage-recovery event has been eliminated.

The trace also contains an 18-byte type-1 response with service 4 and status
zero. The old parser incorrectly treated its status as a Message opcode and
expected value 1. The framing described by
[the protocol researcher](https://github.com/steam3d/MagicPodsCore/issues/14)
distinguishes a Connection Response (status, major, minor, feature bits) from
a type-4 Message (opcode and payload). The parser and diagnostic now share an
exact-length/service/type/status-zero check. Rejected, truncated, oversized
or foreign-service responses cannot establish this acknowledgment. The check
does not claim that all advertised features or versions were negotiated.
In the metadata log, the field formerly labeled opcode for type 1 is its
status; type-4 messages continue to use an opcode.

Production-transport tests cover the real 18-byte response and negative cases;
old invented six-byte status-1 ACK fixtures have been replaced. Preflight tests
reproduce a brief transition and verify a restarted stability window, bounded
failure on repeated transitions, and existing disconnect/no-progress failures.
The maintained offline suite and target/package results are recorded below
after verification. Physical session stability, the original 30-second
failure and mic-closed channel asymmetry remain unresolved hardware items.

Use the next packaged `Run-Test.ps1 -CdcPort COM3 -SessionOnly` for a 45-second
simultaneous playback/mic/USB-diagnostic/HID run. Phone-speaker input for the
first 20 seconds is sufficient. Return the results ZIP even on early failure.

Verified source `880dc318072f191f1440d3f0b262d83e32729b59` passed CI run
[41786883085](https://github.com/newrecycle/USBPods-Pico2W/actions/runs/41786883085)
with three firmware variants and the Windows launcher. All 66 offline checks
and 15 exact-package CLI scenarios passed. The archived parser rejected
success status zero and accepted error status one; the corrected parser
reverses both outcomes. The archived preflight also reproduced the false
failure. [Release evidence](evidence/preflight-062729.json) records the hashes.
