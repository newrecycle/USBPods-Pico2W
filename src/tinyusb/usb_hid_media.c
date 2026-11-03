// SPDX-License-Identifier: GPL-3.0-only
#include "usb_hid_media.h"
#include <stdatomic.h>
#include <stdint.h>
#include <limits.h>
/* Per-slot publication avoids torn data and a spinlock in the BT/USB IRQ.
 * Bounded CAS attempts also prevent unbounded producer spins. */
typedef struct {
 _Atomic uint32_t seq;
 uint32_t session;
 uint16_t usage;
} slot_t;
static slot_t slots[USB_HID_MEDIA_CAPACITY];
static _Atomic uint32_t wr, rd, epoch;
static _Atomic bool active;
static _Atomic uint32_t accepted, full, inactive, stale, sent, released, busy, failed, highwater;
/* Poll is only called by the serialized USB control task. */
static uint32_t seen_epoch;
static bool release_due;
void usb_hid_media_init(void) {
 for(uint32_t i=0;i<USB_HID_MEDIA_CAPACITY;i++) atomic_store(&slots[i].seq,i);
 atomic_store(&wr,0); atomic_store(&rd,0); atomic_store(&epoch,1);
 atomic_store(&active,false);
 atomic_store(&accepted,0); atomic_store(&full,0); atomic_store(&inactive,0);
 atomic_store(&stale,0); atomic_store(&sent,0); atomic_store(&released,0);
 atomic_store(&busy,0); atomic_store(&failed,0); atomic_store(&highwater,0);
 seen_epoch=UINT32_MAX; release_due=true;
}
void usb_hid_media_new_session(bool on) {
 atomic_store(&active,on); atomic_fetch_add(&epoch,1);
}
void usb_hid_media_set_active(bool on) {
 if(atomic_exchange(&active,on)!=on) atomic_fetch_add(&epoch,1);
}
bool usb_hid_media_enqueue(uint16_t usage) {
 if(!usage || !atomic_load(&active)) { atomic_fetch_add(&inactive,1); return false; }
 uint32_t gen=atomic_load(&epoch),pos=atomic_load(&wr);
 for(uint32_t n=0;n<2*USB_HID_MEDIA_CAPACITY;n++) {
  slot_t *slot=&slots[pos%USB_HID_MEDIA_CAPACITY];
  int32_t dif=(int32_t)(atomic_load_explicit(&slot->seq,memory_order_acquire)-pos);
  if(dif==0) {
   if(!atomic_compare_exchange_weak(&wr,&pos,pos+1)) continue;
   slot->usage=usage; slot->session=gen;
   atomic_store_explicit(&slot->seq,pos+1,memory_order_release);
   atomic_fetch_add(&accepted,1);
   uint32_t depth=pos+1-atomic_load(&rd), old=atomic_load(&highwater);
   while(depth>old && !atomic_compare_exchange_weak(&highwater,&old,depth)) {}
   return true;
  }
  if(dif<0) break;
  pos=atomic_load(&wr);
 }
 atomic_fetch_add(&full,1); return false;
}
static bool peek(uint16_t *usage,uint32_t *gen) {
 uint32_t pos=atomic_load(&rd);
 slot_t *slot=&slots[pos%USB_HID_MEDIA_CAPACITY];
 if((int32_t)(atomic_load_explicit(&slot->seq,memory_order_acquire)-(pos+1))!=0) return false;
 *usage=slot->usage; *gen=slot->session; return true;
}
static void pop(void) {
 uint32_t pos=atomic_load(&rd);
 atomic_store_explicit(&slots[pos%USB_HID_MEDIA_CAPACITY].seq,
                       pos+USB_HID_MEDIA_CAPACITY,memory_order_release);
 atomic_store(&rd,pos+1);
}
void usb_hid_media_poll(bool ready, bool (*send)(uint16_t)) {
 uint32_t gen=atomic_load(&epoch);
 if(gen!=seen_epoch) { seen_epoch=gen; release_due=true; }
 if(!atomic_load(&active)) return;
 if(!ready) {
  if(release_due || atomic_load(&wr)!=atomic_load(&rd)) atomic_fetch_add(&busy,1);
  return;
 }
 if(release_due) {
  if(send && send(0)) { release_due=false; atomic_fetch_add(&released,1); }
  else atomic_fetch_add(&failed,1);
  return;
 }
 for(uint32_t i=0;i<USB_HID_MEDIA_CAPACITY;i++) {
  uint16_t usage; uint32_t session;
  if(!peek(&usage,&session)) break;
  if(session!=gen) { pop(); atomic_fetch_add(&stale,1); continue; }
  if(send && send(usage)) {
   pop(); release_due=true; atomic_fetch_add(&sent,1);
  } else atomic_fetch_add(&failed,1);
  return;
 }
}
bool usb_hid_media_idle(void) {
 return atomic_load(&active) && !release_due && atomic_load(&wr)==atomic_load(&rd);
}
usb_hid_media_snapshot_t usb_hid_media_snapshot(void) {
 return (usb_hid_media_snapshot_t) {
  .active=atomic_load(&active),.release_pending=release_due,
  .queue_depth=atomic_load(&wr)-atomic_load(&rd),.high_water=atomic_load(&highwater),
  .accepted=atomic_load(&accepted),.dropped_full=atomic_load(&full),
  .dropped_inactive=atomic_load(&inactive),.stale=atomic_load(&stale),
  .presses_sent=atomic_load(&sent),.releases_sent=atomic_load(&released),
  .busy_ticks=atomic_load(&busy),.send_failures=atomic_load(&failed)
 };
}
