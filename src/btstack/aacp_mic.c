// SPDX-License-Identifier: GPL-3.0-only
// AirPods AACP mic transport. Commands/layout: han-um (2026), librepods.
// This module owns ONE PSM 0x1001 channel in the public Lite build.
#include "btstack.h"
#include "aacp_control.h"
#include "pico/cyw43_arch.h"
#include "pico/async_context.h"
#include "btstack_aap.h"
#include "aacp_mic.h"
#include "aacp_mic_protocol.h"
#include "classic/device_id_server.h"
#include <stdio.h>
#include <string.h>
static uint8_t device_id[100];
static bd_addr_t peer;
static uint16_t cid;
static bool desired, opened, requested;
static unsigned attempts, send_errors;
static uint32_t due, deadline, last_report;
static aacp_mic_session session;
static aacp_control controls;
static uint32_t sdus, units, bytes, malformed, last_timestamp;
static void handler(uint8_t type,uint16_t channel,uint8_t *packet,uint16_t size);
static bool expired(uint32_t now,uint32_t when) { return (int32_t)(now-when)>=0; }
static void release_channel(void) {
 aacp_mic_discontinuity();
 uint16_t old=cid; cid=0; opened=requested=false;
 memset(&session,0,sizeof(session));
 aacp_control_reset(&controls);
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
 /* Distinct from HFP's 0x10005. AirPods must rediscover SDP: re-pair. */
 device_id_create_sdp_record(device_id,0x10006,DEVICE_ID_VENDOR_ID_SOURCE_BLUETOOTH,0x004c,0,0);
 sdp_register_service(device_id);
}
static bool wanted(void) { return aacp_mic_capture() && aacp_mic_audio_ready(); }
static void au(const uint8_t *data,uint8_t len,uint32_t timestamp,void *ctx) {
 (void)ctx; units++; bytes+=len; last_timestamp=timestamp;
 if (session.started && wanted()) aacp_mic_audio_enqueue(data,len);
}
static void handler(uint8_t type,uint16_t channel,uint8_t *p,uint16_t n) {
 if (type==L2CAP_DATA_PACKET) {
   if (!opened || channel!=cid) return;
   int frames=aacp_mic_parse(p,n,au,NULL);
   if (frames<0) malformed++;
   else if (frames>0) sdus++;
   else if (aacp_control_receive(&controls,p,n)) session.confirmed=true;
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
     if (!session.confirmed || (slot=aacp_control_peek(&controls,ctl))<0) break;
     data=ctl;
   }
   if (l2cap_send(cid,(uint8_t *)data,len)==ERROR_CODE_SUCCESS) {
     if (command>=0) aacp_mic_sent(&session,command);
     else aacp_control_sent(&controls,slot,ctl[7]);
     send_errors=0;
     if (command>=3) printf("[mic] %s sent\n",command==3?"START":"STOP");
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
 if (opened && !requested && (aacp_mic_next(&session,wanted())>=0 || (session.confirmed && controls.pending))) {
   requested=true;
   if (session.confirmed) deadline=now+3000;
   if (l2cap_request_can_send_now_event(cid)!=ERROR_CODE_SUCCESS) {
     requested=false; if (++send_errors>=3) release_channel();
   }
 }
 if (now-last_report>=2000) {
   last_report=now;
   printf("[mic] open=%u confirmed=%u wanted=%u sent_start=%u attempts=%u sdu=%lu au=%lu bytes=%lu malformed=%lu ts=%lu\n",
   opened,session.confirmed,wanted(),session.started,attempts,(unsigned long)sdus,
   (unsigned long)units,(unsigned long)bytes,(unsigned long)malformed,(unsigned long)last_timestamp);
 }
}


/* Control intents and notifications share the microphone channel. Setters only
 * enqueue intent; observed state changes on a validated peer notification.
 * Locking also serializes main-loop callers against playback-recovery IRQs. */
static void control_lock(void) { async_context_acquire_lock_blocking(cyw43_arch_async_context()); }
static void control_unlock(void) { async_context_release_lock(cyw43_arch_async_context()); }
static void control_set(uint8_t id,uint8_t value) {
 control_lock();
 if (opened) (void)aacp_control_set(&controls,id,value);
 control_unlock();
}
void aap_set_jitter_raw(uint8_t v) { control_set(0x0b,v); }
void aap_set_noise_mode(uint8_t v) { control_set(0x0d,v); }
void aap_set_pvol(bool on) { control_set(0x26,on?1:2); }
void aap_set_ca(bool on) { control_set(0x28,on?1:2); }
void aap_set_aa(uint8_t v) { control_set(0x2e,v); }
void aap_get_battery(uint8_t out[3]) {
 control_lock();
 if (opened) memcpy(out,controls.battery,3); else memset(out,0xff,3);
 control_unlock();
}
uint8_t aap_get_noise_mode(void) {
 control_lock(); uint8_t v=opened?controls.noise:0; control_unlock(); return v;
}
int aap_get_pvol(void) { control_lock(); int v=opened?controls.pvol:-1; control_unlock(); return v; }
int aap_get_ca(void) { control_lock(); int v=opened?controls.ca:-1; control_unlock(); return v; }
int aap_get_aa(void) { control_lock(); int v=opened?controls.aa:-1; control_unlock(); return v; }
