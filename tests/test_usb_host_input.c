// SPDX-License-Identifier: GPL-3.0-only
// Host fixture uses the PRODUCTION USB session and HID queue helpers.
// It stubs only the radio capture-intent sink and TinyUSB report submission.
#include "usb_capture_lifecycle.h"
#include "usb_hid_media.h"
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

static bool requested_capture;
static uint32_t changes;
void aacp_mic_set_capture(bool on) {
 if(requested_capture!=on) changes++;
 requested_capture=on;
}
static void expect_capture(bool on) {
 assert(requested_capture==on);
 assert(usb_capture_running()==on);
 assert(usb_capture_snapshot().capture_running==on);
}
static void test_capture(void) {
 usb_capture_unmount(); expect_capture(false);
 usb_capture_set_alt(true); expect_capture(false); // stale after unmount
 usb_capture_resume(); expect_capture(false);
 usb_capture_mount(); expect_capture(false); // new configuration starts at alt 0
 usb_capture_set_alt(true); expect_capture(true);
 usb_capture_suspend(); expect_capture(false);
 assert(usb_capture_snapshot().alt_active); // preserve host intent on suspend
 usb_capture_resume(); expect_capture(true);
 usb_capture_close(); expect_capture(false); // close_EP alt 0 may be final
 usb_capture_resume(); expect_capture(false); // no phantom restart
 usb_capture_set_alt(true); expect_capture(true);
 usb_capture_set_alt(false); expect_capture(false);
 usb_capture_set_alt(true); expect_capture(true);
 usb_capture_suspend(); expect_capture(false);
 usb_capture_close(); expect_capture(false);
 usb_capture_resume(); expect_capture(false); // close during suspension wins
 usb_capture_set_alt(true); expect_capture(true);
 usb_capture_unmount(); expect_capture(false);
 usb_capture_resume(); expect_capture(false); // resume after unplug must not start
 usb_capture_mount(); expect_capture(false);
 for(int n=0;n<100;n++) {
  usb_capture_set_alt(true); expect_capture(true);
  usb_capture_close(); expect_capture(false);
  usb_capture_suspend(); expect_capture(false);
  usb_capture_resume(); expect_capture(false);
 }
 usb_capture_set_alt(true); expect_capture(true);
 usb_capture_mount(); expect_capture(false); // repeated configuration resets alt
 usb_capture_note_tx(0,128);
 usb_capture_note_tx(32,64);
 usb_capture_note_tx(64,128);
 usb_capture_snapshot_t s=usb_capture_snapshot();
 assert(s.usb_packets==3 && s.pcm_samples==96);
 assert(s.underrun_packets==2 && s.missing_samples==96 && s.short_writes==1);
 assert(changes>=210);
}

static uint16_t reports[256];
static unsigned report_count, fail_next;
static bool submit(uint16_t usage) {
 if(fail_next) { fail_next--; return false; }
 assert(report_count<sizeof(reports)/sizeof(reports[0]));
 reports[report_count++]=usage;
 return true;
}
static void tick(unsigned count) {
 for(unsigned i=0;i<count;i++) usb_hid_media_poll(true,submit);
}
static void test_hid(void) {
 usb_hid_media_init();
 assert(!usb_hid_media_enqueue(0xCD)); // no USB session
 usb_hid_media_new_session(true);
 usb_hid_media_poll(false,submit); // busy startup release
 assert(report_count==0);
 tick(1); assert(report_count==1 && reports[0]==0);
 assert(usb_hid_media_enqueue(0xCD));
 assert(usb_hid_media_enqueue(0xCD)); // duplicate press must not be coalesced
 assert(usb_hid_media_enqueue(0xB5));
 fail_next=1; tick(1);
 assert(report_count==1 && usb_hid_media_snapshot().queue_depth==3);
 tick(1); assert(reports[1]==0xCD);
 usb_hid_media_poll(false,submit); // busy release must be retried
 fail_next=1; tick(1);
 assert(report_count==2);
 tick(1); assert(reports[2]==0);
 tick(3);
 assert(report_count==6);
 assert(reports[3]==0xCD && reports[4]==0 && reports[5]==0xB5);
 tick(1); assert(reports[6]==0 && usb_hid_media_idle());
 // Saturate queue: bounded, drop-new, preserve FIFO across busy polls.
 unsigned accepted=0;
 for(unsigned i=0;i<USB_HID_MEDIA_CAPACITY+10;i++)
  if(usb_hid_media_enqueue((uint16_t)(0xB0+i))) accepted++;
 assert(accepted==USB_HID_MEDIA_CAPACITY);
 usb_hid_media_poll(false,submit);
 unsigned before=report_count;
 tick(2*USB_HID_MEDIA_CAPACITY);
 assert(report_count==before+2*USB_HID_MEDIA_CAPACITY);
 for(unsigned i=0;i<USB_HID_MEDIA_CAPACITY;i++) {
  assert(reports[before+2*i]==0xB0+i);
  assert(reports[before+2*i+1]==0);
 }
 assert(usb_hid_media_idle());
 usb_hid_media_snapshot_t s=usb_hid_media_snapshot();
 assert(s.high_water==USB_HID_MEDIA_CAPACITY);
 assert(s.dropped_full==10 && s.busy_ticks>=3 && s.send_failures==2);
 // An old-generation key must not be emitted after USB reconnection.
 assert(usb_hid_media_enqueue(0xCD));
 assert(usb_hid_media_enqueue(0xB6));
 usb_hid_media_new_session(false);
 assert(!usb_hid_media_enqueue(0xCD));
 usb_hid_media_poll(false,submit);
 usb_hid_media_new_session(true);
 before=report_count;
 tick(2);
 assert(report_count==before+1 && reports[before]==0);
 assert(usb_hid_media_snapshot().stale>=2);
 assert(usb_hid_media_enqueue(0xE9));
 tick(2);
 assert(reports[report_count-2]==0xE9 && reports[report_count-1]==0);
 // Press followed by a suspend before release: force neutral on resume.
 assert(usb_hid_media_enqueue(0xB5)); tick(1);
 assert(reports[report_count-1]==0xB5);
 usb_hid_media_set_active(false);
 before=report_count; tick(2); assert(report_count==before);
 usb_hid_media_set_active(true);
 tick(1); assert(reports[report_count-1]==0);
 assert(usb_hid_media_idle());
}
int main(void) {
 test_capture(); test_hid();
 puts("USB capture lifecycle and HID queue host regressions passed");
 return 0;
}
