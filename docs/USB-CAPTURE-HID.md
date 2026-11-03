# USB capture lifecycle and HID consumer delivery

The production TinyUSB callbacks in `src/tinyusb/uac.c` delegate to
`usb_capture_lifecycle.c` and `usb_hid_media.c`. Both helpers have native
host regression tests and require no Pico SDK to compile for those tests.

## Microphone intent and counters

Capture is permitted only when **mounted, not suspended, and microphone
alternate setting 1 is open**. The UAC2 microphone endpoint-close callback
immediately clears saved alternate-setting intent, including when it is the
final notification for alt 0. The set-interface callback records the new alt.
Mount/unmount or a soft replug invalidates previous intent; suspend parks it,
and resume restores it **only** if still mounted with alt 1 open.

`usb_capture_snapshot()` in `usb_capture_lifecycle.h` provides:

- `mounted`, `suspended`, `alt_active`, `capture_running`: the USB-side state.
- `usb_packets`: number of microphone IN preload packets attempted.
- `pcm_samples`: actual decoded PCM samples consumed by the USB path.
- `underrun_packets`: preloads that got fewer than 64 PCM samples.
- `missing_samples`: total zero-padded samples, excluding actual PCM.
- `short_writes`: `tud_audio_write()` responses other than 128 bytes.

Counters are cumulative 32-bit wraparound values, not per-session resets.
The USB microphone writes a 64-sample / 128-byte mono packet on each active
IN preload, padding short reads with silence. TinyUSB 0.18 passes the audio
function ID (0) to the preload callback, not the USB microphone interface
number (2); the callback gates on that ID and the tracked host intent. This does **not** change the
existing 48 kHz AACP/FDK decoder output format or the advertised 64 kHz
microphone USB clock. Physical tests are still needed to resolve cadence,
drift, sample-rate behavior and decode timing.

## HID

`usb_hid_media_snapshot()` in `usb_hid_media.h` provides:
`active`, `release_pending`, `queue_depth`, `high_water`, `accepted`,
`dropped_full`, `dropped_inactive`, `stale`, `presses_sent`,
`releases_sent`, `busy_ticks`, `send_failures`.

The 16-entry bounded MPSC queue preserves repeated media keys and order for
accepted events; it drops new events when full (counted), never blocks event
producers, and performs USB I/O only from the serialized control task.
An accepted press is never removed until TinyUSB accepts it, and a submitted
press is followed by a zero release before another press. Failed submissions
and busy endpoints are retried on subsequent control ticks. Session epoch
changes discard old keys. The first report after reconnection/resume is a
neutral (zero) release to prevent stuck keys where the host retained state.
A permanently busy/unmounted endpoint cannot be guaranteed to receive a
release: that requires the host to resume accepting reports.

## Host tests

Run from repository root:

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -Isrc/tinyusb \
  tests/test_usb_host_input.c src/tinyusb/usb_capture_lifecycle.c \
  src/tinyusb/usb_hid_media.c -o /tmp/usb-host-input
/tmp/usb-host-input
python3 tests/test_usb_input_wiring.py
```

The fixture exercises repeated alt-setting open/close, mount/unmount,
suspend/resume, close during suspension, stale resumed intent, undersupply,
short writes, busy HID endpoints, failed press/release submissions, duplicate
key events, queue saturation and stale events across USB reconnections.
This is not Pico hardware acceptance; host USB enumeration and physical
AirPods recording/HID behavior remain to be validated on-device.
