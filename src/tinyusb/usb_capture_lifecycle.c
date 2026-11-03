// SPDX-License-Identifier: GPL-3.0-only
#include "usb_capture_lifecycle.h"
#include <stdatomic.h>
/* No Bluetooth commands on the USB callback path: publish intent only. */
extern void aacp_mic_set_capture(bool enabled);
enum { MOUNT = 1u, SUSPEND = 2u, ALT = 4u };
static _Atomic uint32_t state, packets, samples, underruns, missing, short_writes;
static bool wanted(uint32_t s) { return (s & (MOUNT|SUSPEND|ALT)) == (MOUNT|ALT); }
static void publish(void) { aacp_mic_set_capture(wanted(atomic_load(&state))); }
void usb_capture_mount(void) {
 atomic_store(&state,MOUNT); /* new configuration starts in alt 0 */
 publish();
}
void usb_capture_unmount(void) { atomic_store(&state,0); publish(); }
void usb_capture_suspend(void) { atomic_fetch_or(&state,SUSPEND); publish(); }
void usb_capture_resume(void) { atomic_fetch_and(&state,~(uint32_t)SUSPEND); publish(); }
void usb_capture_set_alt(bool on) {
 if(on) atomic_fetch_or(&state,ALT);
 else atomic_fetch_and(&state,~(uint32_t)ALT);
 publish();
}
void usb_capture_close(void) {
 /* close_EP may be the last callback for alt 0. Do not leave saved intent. */
 usb_capture_set_alt(false);
}
bool usb_capture_running(void) { return wanted(atomic_load(&state)); }
void usb_capture_note_tx(uint32_t got, uint32_t written) {
 if(got>64) got=64;
 atomic_fetch_add(&packets,1); atomic_fetch_add(&samples,got);
 if(got<64) { atomic_fetch_add(&underruns,1); atomic_fetch_add(&missing,64-got); }
 if(written!=128) atomic_fetch_add(&short_writes,1);
}
usb_capture_snapshot_t usb_capture_snapshot(void) {
 uint32_t s=atomic_load(&state);
 return (usb_capture_snapshot_t) {
  .mounted=(s&MOUNT)!=0, .suspended=(s&SUSPEND)!=0,
  .alt_active=(s&ALT)!=0, .capture_running=wanted(s),
  .usb_packets=atomic_load(&packets),.pcm_samples=atomic_load(&samples),
  .underrun_packets=atomic_load(&underruns),
  .missing_samples=atomic_load(&missing),.short_writes=atomic_load(&short_writes)
 };
}
