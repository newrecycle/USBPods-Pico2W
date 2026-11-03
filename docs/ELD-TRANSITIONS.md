# AAC-ELD transition acceptance

This change is isolated on `codex/eld-integration`, based on `ac0512a`.
Microphone transport/decoder and TinyUSB/HID work remain separately owned.

Previously a rate/game request armed the main-loop rebuild before SUSPEND
acceptance. An immediate suspend error restarted the audio timer, allowing
the new encoder to be used without the peer first pausing its decoder.
Rapid requests could also send another SUSPEND while signaling was busy.

`eld_transition.c` now owns requested/built revisions and the transition phase.
Initial ELD setup is also deferred: the BT callback publishes intent and the
main loop performs FDK open/free under the CYW43 context lock. USB IRQs remain
enabled. A peer START arriving early is retained until initialization succeeds;
a later suspend cancels that early-start intent. Deferred setup is invalidated
on disconnect. Stale codec-family allocations can be released before the new
encoder exists. `max_rebuild_us` includes this initial setup cost as well.
The application adapters execute these actions:

1. Stop the playback pump and cancel any old jitter-settle timer.
2. Issue one SUSPEND; coalesce subsequent settings while waiting.
3. After acceptance, rebuild the latest profile in the main loop under the
   CYW43 context lock. USB IRQs remain enabled.
4. On successful initialization, reset playback sequence/timestamp and issue
   one START. The pump remains stopped until acceptance.
5. If another request arrived during START, suspend again before rebuilding
   that request. Otherwise resume the pump and delay jitter by 500 ms.

Peer suspension and ELD stall/self-heal rebuilds use the same ordering. A normal
initial START has a deadline that re-arms self-heal if no response arrives.
The transition adapters reject unrelated CIDs before mutating source state.
Headset teardown cancels pending work; a new codec setup starts a fresh session.

Each managed phase has a three-second deadline. Coalesced requests do not move
an existing phase's deadline. Signaling rejection/error, encoder failure or a
managed timeout stops playback, cancels pending jitter, records the error and
requests headset ACL disconnection. Automatic redial is held to avoid repeatedly
re-entering an allocation failure. An explicit reconnect starts a new attempt.
This policy deliberately replaces the previous live-apply fallback.

`:eldstatus` adds `transition`, `requested_revision`, `built_revision`,
`error_stage`, `last_error`, and `max_rebuild_us`. A built revision means the
encoder was configured; it does not acknowledge peer START or a jitter write.
Use the phase and `:status` streaming field as well. Failure sets `ready=0` and
`pending=0`; a remaining valid old handle is not advertised as usable.

| Error stage | Meaning | `last_error` |
| --- | --- | --- |
| 0 | No transition failure | 0 |
| 1 | SUSPEND | Immediate SDK status, or `0x100` OR signaling identifier |
| 2 | START | Immediate SDK status, or `0x100` OR signaling identifier |
| 3 | Rebuild | FDK error |
| 4 | Phase deadline | Phase enum: 2 suspend, 3 rebuild, 4 start |
| 5 | Initial encoder setup | FDK error |
| 6 | Initial media OPEN | SDK status, `0x100` OR rejected signal, or `0x200` OR timed-out signal |

Run the production controller and adapter tests from the repository root:

```sh
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  -I src/btstack tests/test_eld_transition.c src/btstack/eld_transition.c \
  -o /tmp/test-eld-transition
ASAN_OPTIONS=detect_leaks=0 /tmp/test-eld-transition
python3 tests/test_eld_adapter.py
```

The adapter fixture compiles production function bodies against deterministic
SDK timers/transport and a fault-injected encoder. It verifies actual callback
ordering, coalescing, missing/rejected SUSPEND/START, allocation failure, stale
START, late AACP jitter requests, timer wrap and teardown. Separate existing
real-FDK duplex, allocation, protocol and relay checks remain in CI. The existing
workflow also runs on this branch so review does not require pushing to main.

These are offline checks. RF behavior, timing on Cortex-M33, initial codec
allocation duration, live microphone continuity and the explicit 48 kHz coding / 64 kHz PCM cadence
question remain hardware or further integration acceptance items. No live-runner
package is finalized by this change.
