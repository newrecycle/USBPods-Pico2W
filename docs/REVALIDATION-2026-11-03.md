# Reconstruction revalidation — 2026-11-03

This revision is eligible for controlled physical verification only after its
Pico firmware workflow passes. It is not hardware success evidence. The old
238ed609 package remains withdrawn. Use the source SHA, CI run ID and UF2 hash
in the replacement package's `candidate.json`; the runner checks that identity.

## First capture and corrected connection ownership

The first capture reached authentication, encryption, media OPEN and START,
then stalled TX, received SUSPEND error 12 and disconnected locally. The runner
also missed a leading-space ACK and reapplied unchanged settings. Those runner
errors are fixed independently; a pairing sound is not a transport acceptance.

The pinned SDK broadcasts raw AVDTP events to source and sink roles. Our raw
source does not mark the SDK A2DP source configuration process active. The
phone-sink wrapper therefore scheduled its own 200 ms discovery on a headset
connection before the application rejected it. A regression executes the
actual pinned SDK discovery/timer paths: the old route starts competing
Discover; the new raw-role gate rejects headset events before the SDK sink
state machine. Phone-owned CIDs still route normally. This is a reproduced
negotiation defect, not proof of the sole cause of the original radio stall.

Configured events now bind the actual source endpoint and SEIDs. SBC, AAC,
LDAC, LHDC and ELD initialization runs in main-loop work under the CYW43 lock,
with USB interrupts enabled. Pending early OPEN/START events are retained;
stale CIDs and wrong request directions are rejected. Fatal setup/TX faults
hold automatic outbound and inbound headset reconnects until explicit user
connection. Dial timers and late START callbacks obey that hold. Button timer
interrupts only queue work; button Bluetooth actions run under the main lock.
Boot dialing and settings debounce use elapsed time rather than loop counts.

## AAC-ELD limits and game modes

The supported Apple vendor layout is parsed with explicit lengths and channel/
frequency masks. Local capabilities advertise a 320 kbps maximum. Peer ceilings
are retained only after valid accepted configuration; zero capability ceiling
means unspecified, never an accepted zero-bitrate configuration. Rejected offers
retry 320 → 256 → 192 before codec fallback. Encoder profiles clamp to the
accepted ceiling and VBR permission, including both game modes. The runner
skips unsupported rates explicitly and verifies applied state and TX progression.
No unknown vendor bytes or radio firmware are patched speculatively.

## Microphone clock and USB pacing

The upstream reconstruction explicitly separates 48 kHz coding frequency from
64 kHz PCM consumption with 480-sample AUs and the inherited ASC `F8 E6 30 00`:

- [Pinned LibrePods ELD implementation](https://github.com/LuanAdemi/librepods/blob/99b0e580a93f2a26647f89816895ca1e5f70a3ec/linux-rust/src/audio/eld.rs)
- [Pinned microphone timeline](https://github.com/LuanAdemi/librepods/blob/99b0e580a93f2a26647f89816895ca1e5f70a3ec/linux-rust/src/audio/hires_mic.rs)
- [Upstream implementation discussion](https://github.com/librepods-org/librepods/pull/655)

The ASC and USB clock remain unchanged. Capture primes 2880 samples, rejects
stale generations, smooths queue occupancy and sends 63/64/65-sample async USB
packets at nominal 64 samples/ms. It neither resamples nor duplicates samples.
The existing 130-byte endpoint accommodates 65 samples. Whole AU burst groups
measure the PCM sample rate over wall time independently of peer timestamp
units. The runner requires a 64 kHz cadence window and preserves WAVs, queue,
drop, decode, expected/actual sample and packet-size counters.

## Offline evidence

Host coverage includes production callback fixtures, the pinned SDK role race,
codec allocation ownership, endpoint binding, bounded discovery, favorite reuse,
codec negotiation retries, accepted bitrate limits, fault holds, button context,
protocol framing, controls, settings, capture lifecycle, HID, runner cleanup and
packaging contracts. ASan/UBSan are used where applicable. The workflow also
checks the linked descriptors, unchanged selected controller image, source SHA,
UF2 byte reconstruction and both wireless-board SCO diagnostic builds.

The real repository FDK tests exercise the exact ASC. A 1 kHz waveform on the
64 kHz PCM timeline decodes at approximately 1005.6 Hz when interpreted at
64 kHz, while the ASC reports the expected 48 kHz coding frequency. This is a
synthetic clock-contract test, not an AirPods packet capture. Actual FDK duplex
stress completes 24 profile transitions / 3072 playback frames with microphone
queue activity. The pacing simulation runs 600 seconds at each of −1500,
−250, 0, +250 and +1500 ppm with four-AU bursts and ±8 ms jitter, without
post-prime starvation or overflow (maximum queue 5105 of 7680 samples).

The final firmware workflow must pass all three matrix entries: stock0031
transport, rpi0065 transport and rpi0065 microphone decoder. Its exact run is
recorded in the delivered manifest. Windows PowerShell/PortAudio execution and
real RF/USB timing cannot be validated in this workspace.

## Controlled physical acceptance

Follow [LIVE-TEST.md](LIVE-TEST.md). Flash the replacement UF2 and run through
COM3 alone; no external UART adapter is required. The runner first disconnects
an existing session, prompts for case pairing mode, scans, stops discovery,
connects only the selected peer and checks AACP separately. Five seconds of
streaming/TX preflight precede feature changes. Conversation Awareness is
restored after temporary capture suppression when its state is known.

The run covers supported bitrates, both game modes, microphone-open reconnects,
a ten-minute duplex soak and notified control settings. Hardware acceptance
still requires stable TX, measured microphone cadence/pitch, no steady capture
starvation, audible playback and actual wear/stem host behavior. Unsupported
peer features and unavailable physical coverage remain explicit SKIP/UNVERIFIED.
Return the results ZIP even on failure; pre-cleanup snapshots preserve the fault.
