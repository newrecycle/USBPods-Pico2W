// SPDX-License-Identifier: GPL-3.0-only
#ifndef USB_CAPTURE_LIFECYCLE_H
#define USB_CAPTURE_LIFECYCLE_H
#include <stdbool.h>
#include <stdint.h>
/* Cumulative since boot; uint32_t counters wrap. Actual PCM samples exclude
 * zero padding used to fill a 64-sample USB microphone packet. */
typedef struct {
 bool mounted, suspended, alt_active, capture_running;
 uint32_t usb_packets, pcm_samples, underrun_packets, missing_samples, short_writes;
} usb_capture_snapshot_t;
void usb_capture_mount(void);
void usb_capture_unmount(void);
void usb_capture_suspend(void);
void usb_capture_resume(void);
void usb_capture_set_alt(bool open);
void usb_capture_close(void);
bool usb_capture_running(void);
void usb_capture_note_tx(uint32_t pcm_samples, uint32_t written_bytes);
usb_capture_snapshot_t usb_capture_snapshot(void);
#endif
