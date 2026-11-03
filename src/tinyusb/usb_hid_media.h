// SPDX-License-Identifier: GPL-3.0-only
#ifndef USB_HID_MEDIA_H
#define USB_HID_MEDIA_H
#include <stdbool.h>
#include <stdint.h>
#define USB_HID_MEDIA_CAPACITY 16u
typedef struct {
 bool active, release_pending;
 uint32_t queue_depth, high_water, accepted, dropped_full, dropped_inactive;
 uint32_t stale, presses_sent, releases_sent, busy_ticks, send_failures;
} usb_hid_media_snapshot_t;
/* Multi-producer, single USB task consumer. Producers never call TinyUSB. */
void usb_hid_media_init(void);
bool usb_hid_media_enqueue(uint16_t usage);
void usb_hid_media_new_session(bool active);
void usb_hid_media_set_active(bool active);
void usb_hid_media_poll(bool ready, bool (*send)(uint16_t));
bool usb_hid_media_idle(void);
usb_hid_media_snapshot_t usb_hid_media_snapshot(void);
#endif
