// SPDX-License-Identifier: GPL-3.0-only
// AirPods AACP mic transport. Commands/layout: han-um (2026), librepods.
// This module owns ONE PSM 0x1001 channel in the public Lite build.
#include "btstack.h"
#include "aacp_control.h"
#include "../settings.h"
extern bool a2dp_source_is_playing(void);
extern void a2dp_source_on_aap_wake(void);
extern void a2dp_source_apply_eld_rate(void);
extern void a2dp_source_queue_jitter(uint8_t);
#include "../tinyusb/uac.h"
#include "pico/cyw43_arch.h"
#include "pico/async_context.h"
#include "btstack_aap.h"
#include "aacp_mic.h"
#include "aacp_mic_protocol.h"
#include "classic/device_id_server.h"
#include <stdio.h>
#include "pico/time.h"
#include <string.h>
static uint8_t device_id[100];
static bd_addr_t peer;
static uint16_t cid;
static bool desired, opened, requested;
static unsigned attempts, send_errors;
static uint32_t due, deadline, last_report;
static aacp_mic_session session;
static aacp_control controls;
static bool initialized;
static bool paused_by_ear;
/* Upstream resets A2DP after 0x58 START (+800 ms) and STOP. A successful
 * wire transition replaces the previous request; the main-loop poll submits
 * recovery through the source's serialized SUSPEND/rebuild/START owner. */
static bool playback_reset_pending;
static uint32_t playback_reset_due;
static bool refresh_pending;
static uint32_t refresh_due;
static aacp_control_diagnostics wire_controls;
static uint32_t sdus, units, bytes, malformed, last_timestamp;
static void handler(uint8_t type,uint16_t channel,uint8_t *packet,uint16_t size);
static bool expired(uint32_t now,uint32_t when) { return (int32_t)(now-when)>=0; }
static void release_channel(void) {
 playback_reset_pending=false;refresh_pending=false;
 aacp_mic_discontinuity();
 uint16_t old=cid; cid=0; opened=requested=false;
 memset(&session,0,sizeof(session));
 aacp_control_reset(&controls);
 paused_by_ear=false;
 if (old) l2cap_disconnect(old);
 due=btstack_run_loop_get_time_ms()+3000;
}
void aap_disconnect(void) { desired=false; release_channel(); }
void aap_connect(bd_addr_t addr) {
 if (desired && !memcmp(peer,addr,6)) return;
 aap_disconnect(); memcpy(peer,addr,6); desired=true; attempts=0;
 due=btstack_run_loop_get_time_ms()+1500;
}
bool aap_channel_open(void) { return opened; }
bool aap_protocol_seen(void) { return opened && session.confirmed; }
void aacp_mic_init(void) {
 initialized=true;
 /* Distinct from HFP's 0x10005. AirPods must rediscover SDP: re-pair. */
 device_id_create_sdp_record(device_id,0x10006,DEVICE_ID_VENDOR_ID_SOURCE_BLUETOOTH,0x004c,0,0);
 sdp_register_service(device_id);
}
static bool wanted(void) { return aacp_mic_capture() && aacp_mic_audio_ready(); }
static void au(const uint8_t *data,uint8_t len,uint32_t timestamp,void *ctx) {
 (void)ctx; units++; bytes+=len; last_timestamp=timestamp;
 aacp_mic_audio_note_au(timestamp,time_us_32());
 if (session.started && wanted()) aacp_mic_audio_enqueue(data,len);
}
static void handler(uint8_t type,uint16_t channel,uint8_t *p,uint16_t n) {
 if (type==L2CAP_DATA_PACKET) {
   if (!opened || channel!=cid) return;
   int frames=aacp_mic_parse(p,n,au,NULL);
   if (frames<0) malformed++;
   else if (frames>0) sdus++;
   else {
     /* Bounded, non-secret diagnostics for otherwise unsupported button
        configuration and gestures. Never dump arbitrary AACP packets/keys. */
     if(n==11 && !memcmp(p,"\x04\x00\x04\x00\x09\x00",6) &&
        (p[6]==5 || (p[6]>=0x14 && p[6]<=0x18) || p[6]==0x39))
       printf("[aacp] button config id=0x%02x values=%u,%u,%u,%u\n",p[6],p[7],p[8],p[9],p[10]);
     if(n==8 && !memcmp(p,"\x04\x00\x04\x00\x19\x00",6))
       printf("[aacp] stem type=%u bud=%u\n",p[6],p[7]);
     bool valid=controls.ear_valid,worn=controls.worn;uint32_t stem=controls.stem_count;
     if (aacp_control_receive(&controls,p,n)) {
       session.confirmed=true;
       if(n==11 && p[4]==0x09)
         printf("[aacp] control notify id=0x%02x value=%u\n",p[6],p[7]);
       if (controls.ear_valid && valid && worn!=controls.worn && settings()->ear_pause) {
         if (!controls.worn && a2dp_source_is_playing()) {
           usb_hid_consumer(0x00b1);paused_by_ear=true;
         } else if (controls.worn && paused_by_ear) {
           usb_hid_consumer(0x00b0);paused_by_ear=false;a2dp_source_on_aap_wake();
         }
       }
       if (controls.stem_count!=stem && settings()->stem_hid) {
         uint16_t usage=controls.stem==5?0x00cd:controls.stem==6?0x00b5:0x00b6;
         usb_hid_consumer(usage);
       }
     }
   }
   return;
 }
 if (type!=HCI_EVENT_PACKET) return;
 switch (hci_event_packet_get_type(p)) {
 case L2CAP_EVENT_CHANNEL_OPENED: {
   uint16_t got=l2cap_event_channel_opened_get_local_cid(p);
   bd_addr_t addr; l2cap_event_channel_opened_get_address(p,addr);
   if (got!=cid || !desired || memcmp(peer,addr,6)) {
     if (!l2cap_event_channel_opened_get_status(p)) l2cap_disconnect(got);
     return;
   }
   if (l2cap_event_channel_opened_get_status(p)) { release_channel(); return; }
   opened=true; requested=false; send_errors=0;
   memset(&session,0,sizeof(session));
   aacp_control_reset(&controls); deadline=btstack_run_loop_get_time_ms()+5000;
   /* Reapply current policy after a new channel handshake, never stale writes.
      The source defers this until playback has resumed after any rebuild. */
   a2dp_source_queue_jitter(aap_get_game()?aap_game_jitter():150);
   printf("[mic] AACP opened cid=%u mtu=%u\n",cid,l2cap_event_channel_opened_get_remote_mtu(p));
   break;
 }
 case L2CAP_EVENT_CHANNEL_CLOSED:
   if (l2cap_event_channel_closed_get_local_cid(p)==cid) release_channel();
   break;
 case L2CAP_EVENT_CAN_SEND_NOW: {
   if (!opened || l2cap_event_can_send_now_get_local_cid(p)!=cid) break;
   requested=false;
   /* Recompute from current USB intent; never queue a stale START. */
   int command=aacp_mic_next(&session,wanted());
   uint8_t ctl[11]; int slot=-1;
   uint16_t len=11; const uint8_t *data;
   if (command>=0) data=aacp_mic_command(command,&len);
   else {
     if (!session.confirmed)break;
     slot=aacp_control_peek(&controls,ctl);
     if(slot>=0)data=ctl;
     else if(refresh_pending && expired(btstack_run_loop_get_time_ms(),refresh_due)) {
       command=2;data=aacp_mic_command(command,&len);
     } else break;
   }
   if (l2cap_send(cid,(uint8_t *)data,len)==ERROR_CODE_SUCCESS) {
     if (command>=0) aacp_mic_sent(&session,command);
     else {
       aacp_control_sent(&controls,slot,ctl[7]);
       wire_controls.transmitted++;wire_controls.last_id=ctl[6];wire_controls.last_value=ctl[7];
       refresh_pending=true;refresh_due=btstack_run_loop_get_time_ms()+100;
       printf("[aacp] control sent id=0x%02x value=%u\n",ctl[6],ctl[7]);
     }
     if(command==2)refresh_pending=false;
     send_errors=0;
     if (command>=3) {
       playback_reset_pending=true;
       playback_reset_due=btstack_run_loop_get_time_ms()+(command==3?800u:0u);
       printf("[mic] %s sent; playback recovery queued\n",command==3?"START":"STOP");
     }
   } else if (++send_errors>=3) release_channel();
   break;
 }
 default: break;
 }
}
void aacp_mic_poll(void) {
 uint32_t now=btstack_run_loop_get_time_ms();
 if (desired && !cid && attempts<3 && expired(now,due)) {
   attempts++; deadline=now+10000;
   uint8_t status=l2cap_create_channel(handler,peer,0x1001,1691,&cid);
   if (status) { cid=0; due=now+3000; }
 }
 if (cid && (!opened || !session.confirmed || requested) && expired(now,deadline)) release_channel();
 if (opened && !requested && (aacp_mic_next(&session,wanted())>=0 || (session.confirmed && (controls.pending || (refresh_pending && expired(now,refresh_due)))))) {
   requested=true;
   if (session.confirmed) deadline=now+3000;
   if (l2cap_request_can_send_now_event(cid)!=ERROR_CODE_SUCCESS) {
     requested=false; if (++send_errors>=3) release_channel();
   }
 }
 /* USB intent may change again before its wire command is sent. Wait for
    the latest successful state, never recover an obsolete START or STOP. */
 if (playback_reset_pending && opened && session.confirmed &&
     wanted()==session.started && expired(now,playback_reset_due)) {
   playback_reset_pending=false;
   printf("[mic] playback recovery after %s\n",session.started?"START":"STOP");
   a2dp_source_apply_eld_rate();
 }
 if (now-last_report>=2000) {
   last_report=now;
   printf("[mic] open=%u confirmed=%u wanted=%u sent_start=%u attempts=%u sdu=%lu au=%lu bytes=%lu malformed=%lu ts=%lu\n",
   opened,session.confirmed,wanted(),session.started,attempts,(unsigned long)sdus,
   (unsigned long)units,(unsigned long)bytes,(unsigned long)malformed,(unsigned long)last_timestamp);
   aacp_mic_audio_report();
 }
}


/* Control intents and notifications share the microphone channel. Setters only
 * enqueue intent; observed state changes on a validated peer notification.
 * Locking also serializes main-loop callers against playback-recovery IRQs. */
static bool control_lock(void) {
 if (!initialized) return false;
 async_context_acquire_lock_blocking(cyw43_arch_async_context()); return true;
}
static void control_unlock(void) { async_context_release_lock(cyw43_arch_async_context()); }
aacp_control_diagnostics aap_control_diagnostics(void) {
 aacp_control_diagnostics out={0};
 if(!control_lock())return out;
 out=wire_controls;memcpy(out.observed,controls.observed,sizeof out.observed);
 control_unlock();return out;
}
bool aacp_control_submit(uint8_t id,uint8_t value) {
 if (!control_lock()) return false;
 bool queued=opened && aacp_control_set(&controls,id,value);
 control_unlock();
 return queued;
}
void aap_set_jitter_raw(uint8_t v) { (void)aacp_control_submit(0x0b,v); }
void aap_set_noise_mode(uint8_t v) { (void)aacp_control_submit(0x0d,v); }
void aap_set_pvol(bool on) { (void)aacp_control_submit(0x26,on?1:2); }
void aap_set_ca(bool on) { (void)aacp_control_submit(0x28,on?1:2); }
void aap_set_aa(uint8_t v) { (void)aacp_control_submit(0x2e,v); }
void aap_get_battery(uint8_t out[3]) {
 if (!control_lock()) { memset(out,0xff,3); return; }
 if (opened) memcpy(out,controls.battery,3); else memset(out,0xff,3);
 control_unlock();
}
uint8_t aap_get_noise_mode(void) {
 if (!control_lock()) return 0;
 uint8_t v=opened?controls.noise:0; control_unlock(); return v;
}
int aap_get_pvol(void) { if (!control_lock()) return -1; int v=opened?controls.pvol:-1; control_unlock(); return v; }
int aap_get_ca(void) { if (!control_lock()) return -1; int v=opened?controls.ca:-1; control_unlock(); return v; }
int aap_get_aa(void) { if (!control_lock()) return -1; int v=opened?controls.aa:-1; control_unlock(); return v; }

bool aap_get_ear_pause(void) { return settings()->ear_pause!=0; }
bool aap_get_game(void) { return (settings()->usbset&USBSET_GAME)!=0; }
void aap_set_ear_pause(bool on) {
 if (!control_lock()) return;
 settings()->ear_pause=on;settings_mark_dirty();if(!on)paused_by_ear=false;
 control_unlock();
}
uint8_t aap_game_jitter(void) { return settings()->game_level==2?60:90; }
void aap_set_game(bool on) {
 if (!control_lock()) return;
 if(on)settings()->usbset|=USBSET_GAME;else settings()->usbset&=(uint8_t)~USBSET_GAME;
 settings_mark_dirty();a2dp_source_apply_eld_rate();
 if(opened)a2dp_source_queue_jitter(on?aap_game_jitter():150);
 control_unlock();
}
