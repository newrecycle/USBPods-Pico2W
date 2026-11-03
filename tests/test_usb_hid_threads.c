// SPDX-License-Identifier: GPL-3.0-only
// Real concurrent producers exercise production slot publication and counters.
#include "usb_hid_media.h"
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
enum {PRODUCERS=4,PER_PRODUCER=2048};
static atomic_uint completed;
static unsigned seen[PRODUCERS],attempts,presses,releases;
static bool pressed;
static void *produce(void *arg) {
 uint16_t usage=(uint16_t)(0x100+(uintptr_t)arg);
 for(unsigned n=0;n<PER_PRODUCER;n++) {
   while(!usb_hid_media_enqueue(usage))sched_yield();
   usb_hid_media_snapshot_t s=usb_hid_media_snapshot();
   assert(s.queue_depth<=USB_HID_MEDIA_CAPACITY && s.high_water<=USB_HID_MEDIA_CAPACITY);
 }
 atomic_fetch_add(&completed,1);return NULL;
}
static bool send_report(uint16_t usage) {
 if(++attempts%11==0)return false;
 if(usage) {
   assert(!pressed && usage>=0x100 && usage<0x100+PRODUCERS);
   pressed=true;seen[usage-0x100]++;presses++;
 } else {pressed=false;releases++;}
 return true;
}
int main(void) {
 usb_hid_media_init();usb_hid_media_new_session(true);
 usb_hid_media_poll(true,send_report); // Startup neutral report.
 pthread_t threads[PRODUCERS];
 for(uintptr_t i=0;i<PRODUCERS;i++)assert(!pthread_create(&threads[i],NULL,produce,(void*)i));
 for(unsigned tick=0;atomic_load(&completed)<PRODUCERS || !usb_hid_media_idle();tick++) {
   assert(tick<20000000);usb_hid_media_poll(tick%7!=0,send_report);
   if(tick%16==0)sched_yield();
 }
 for(unsigned i=0;i<PRODUCERS;i++){assert(!pthread_join(threads[i],NULL));assert(seen[i]==PER_PRODUCER);}
 usb_hid_media_snapshot_t s=usb_hid_media_snapshot();
 assert(!pressed && presses==PRODUCERS*PER_PRODUCER && releases==presses+1);
 assert(s.accepted==presses && s.presses_sent==presses && s.releases_sent==releases);
 assert(!s.queue_depth && s.high_water<=USB_HID_MEDIA_CAPACITY);
 puts("Concurrent HID producers: 8192 presses/releases, retries and bounded snapshots passed");
}
