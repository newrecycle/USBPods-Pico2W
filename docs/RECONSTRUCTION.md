# Independent reconstruction status

Priority: AAC-ELD playback with multiple bitrates and game modes while retaining
the AirPods microphone. The transfer bundle is an addressed binary reference
and proposed source, not the implementation baseline. The base remains this
fork's 0065, microphone and current public upstream code.

The independent build now has one shared AACP owner, validated controls and
battery notifications, opt-in ear/stem host actions, persisted device settings
over CDC, eight saved headsets, and bounded phone relay. It does not recreate
the vendor account/activation service or claim access to the vendor's private
source. CDC replaces the vendor configuration surface. The firmware output
names use `Reconstructed`; CMake's Lite compatibility define still selects the
public USB descriptor family, which includes consumer HID and CDC.

## AAC-ELD configuration matrix

| Selection | Effective playback rate | VBR | SBR | Source slots | Jitter request |
| --- | ---: | ---: | ---: | ---: | ---: |
| 192 kbps, 48 kHz input | 192000 | 0 | 0 | 6 | 150 ms |
| Default 256 kbps, 48 kHz input | 256000 peak policy | 5 | 1, ratio 1 | 6 | 150 ms |
| 320 kbps, 48 kHz input | 320000 | 0 | 0 | 9 | 150 ms |
| Game, stable | 192000 | 0 | 0 | 6 | 90 ms |
| Game, latency | 192000 | 0 | 0 | 4 | 60 ms |
| 44.1 kHz USB input | 192000 maximum | 0 | 0 | menu/game policy | menu/game policy |
| Active phone relay | 164000 maximum | 0 | 0 | menu/game policy | menu/game policy |

The default VBR setting is not a promise of 256 kbps average throughput. Game
mode overrides the selected menu rate without overwriting that preference.
Turning game mode off restores the menu policy. 44.1 kHz and relay restrictions
are inherited conservative configurations, not newly measured limits. The mic
retains its independent mono RAW decoder and USB capture clock through these
playback profile changes.

`eld_profile.c` is the single policy implementation. `eld_encoder.c` is shared
by initial configuration and live rebuild. It checks allocation, every FDK
parameter, initialization and returned stream geometry. CBR profiles also set
an explicit peak rate; the first native duplex test exposed a 332-byte startup
AU at 192 kbps when the peak was left implicit (the transport reserved 304).
With the peak bound, the expanded fixture produces at most 241-byte AUs at
192 kbps and 401 at 320 kbps. The encoder output buffer is additionally limited by the
actual negotiated packet space, independently of the nominal estimate. Failure closes the
handle and clears the stream info instead of publishing a partial encoder.
The old handle is closed before allocating a new one, avoiding a temporary
double encoder heap alongside the mic decoder.

The embedded FDK encoder QC overlay is bounded to stereo, matching the source
codecs. Public and core entry points reject larger AAC/SBR channel allocations
before they can index the smaller overlay. This saves 57,312 requested bytes
in the 64-bit native fixture, reducing peak codec requests from 365,126 to
307,814 bytes. CBR/game profiles additionally omit the unused SBR encoder
module. Both native round trips and the complete duplex matrix run with an
AddressSanitizer-instrumented FDK build; the separate 32-bit audit supplies the
closer memory estimate. Host figures still exclude BT, allocator and target
runtime overhead.

Live rebuild is serialized with the CYW43 async context; it no longer masks all
USB interrupts during FDK allocation/configuration. TinyUSB can continue draining
the microphone PCM queue. BT scheduling and actual audio continuity during this
operation still need hardware acceptance. The profile uses the USB rate latched
at boot, so saving a rate preference cannot silently change the active profile
before USB descriptors are rebuilt.

Commands: `:eldrate 1/2/3`, `:game 0/1`, `:gamelevel 1/2`, `:eldstatus`.
The status response distinguishes selected/desired policy from the successfully
configured active encoder, rebuild-pending state and failure/rebuild counters.
A queued setting alone does not establish that it became active. Game-mode
jitter is queued through the source's post-START scheduler rather than emitted
during the rate-change suspend. A superseding mode cancels the old timer;
headset disconnect clears it, and channel reconnect reapplies current policy. `:eldstatus` also reports the target linker heap
region and current allocator use; CI records the linker region but does not
claim that dynamic allocations were exercised on the board.

## Offline acceptance

- 64 policy combinations: menu rate, game profile, 44.1 kHz and relay overrides.
- Failure injection into every encoder allocation/parameter/init/info step;
  failed transitions leave no live or overlapping encoder handle.
- Actual repository FDK: repeated 192/256/320, both game profiles, 44.1 kHz
  resampling, relay cap and return-to-default transitions. The actual microphone
  queue and decoder remain active; their capture generation must not change.
  Three complete cycles cover 24 transitions and 3,072 playback/microphone
  frames with tones, full-scale noise, silence and impulses.
  Playback frames are decoded and checked for stereo/480 samples/48 kHz; mic
  PCM is checked for non-silence and frame continuity; encoded AU bounds are
  checked against the packet budget.
- Existing protocol, queue, stale-connection, CDC-parser and UF2 checks remain.
- A 32-bit native FDK build runs the same duplex fixture with malloc/calloc/free
  tracking. The audit excludes the host-only playback reference decoder and
  allocator cache retention. CI compares requested codec bytes to the linked
  target heap region and records remaining space before allocator/BT overhead.
  A nonpositive remainder fails verification; the pre-optimization audit needed
  360,422 bytes against a 338,224-byte target region.
  This is a resource estimate, not proof of target allocation or deadlines.
- Relay regressions cover wrong-CID teardown, stop overriding pending start,
  preservation of signaling ownership, checked RTP extensions, fragments,
  sequence loss and bounded assembly.

These tests use synthetic audio and mocked event/time sources. They do not
verify RF interoperability, Cortex-M33 deadlines, electrical UART wiring,
Windows behavior or AirPods acoustic quality. CI must pass on the exact final
revision before selecting a hardware candidate.

## Resource and feature boundaries

The microphone-decoder application exposes SBC phone relay. A second AAC-LC
relay decoder is intentionally not advertised in that build. The separate
transport/full-relay application can decode SBC/AAC phone audio, while its USB
microphone sends diagnostic silence. No simultaneous dual-FDK-decoder heap is
claimed. Playback staging is bounded at nine maximum slots, with SBC/AAC/LDAC
using eight; this trades buffer headroom for the reconstruction's RAM needs.

Ear pause and stem-to-HID start disabled and are explicit settings. Initial ear
state produces no host key, either worn bud counts as worn, and reinsertion
only resumes a pause owned by the ear policy. Raw HID observation may depend on
host access; firmware records TinyUSB-accepted press/release events separately.

Further work before finalizing the hardware runner: verify active rate/game
transitions with the actual encoder/mic path, review resource headroom and
state telemetry, then consolidate the hardware matrix into as few sessions as
possible. The host-runner draft is not the acceptance milestone and is not yet
published as a live-test package. Mic cadence/pitch (48 kHz ASC versus 64 kHz
USB clock), RF coexistence, lifecycle timing and phone marker conventions remain
questions for that later hardware pass.
