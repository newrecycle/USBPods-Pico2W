// SPDX-License-Identifier: GPL-3.0-only
// AirPods AACP mic transport. Commands/layout: han-um (2026), librepods.
// This module owns ONE PSM 0x1001 channel in the public Lite build.
#include "btstack.h"
#include "aacp_control.h"
#include "media_input.h"
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
static media_input host_media;
/* The Pico reference keeps A2DP running during capture. Recover microphone
 * silence on AACP only; do not import the Linux card-profile reset policy. */
static aacp_mic_watch mic_watch;
static bool refresh_pending;
static uint32_t refresh_due;
static aacp_control_diagnostics wire_controls;
static uint32_t sdus, units, bytes, malformed, last_timestamp;
static aacp_mic_session_diagnostics session_diag;
static uint32_t session_open_ms, session_end_ms, session_rx_ms, session_tx_ms;
static uint32_t logged_headers[16];
static bool session_tx_seen;
static void session_report(const char *reason) {
 uint32_t now=btstack_run_loop_get_time_ms();
 printf("[aacp-session] reason=%s cid=%u age_ms=%lu init=%u mask=%lu peer_seen=%u handshake_ack=%u rx=%lu unhandled=%lu op=0x%04x len=%u rx_age_ms=%lu tx_cmd=%u tx_age_ms=%lu\n",
 reason,cid,(unsigned long)(now-session_open_ms),session.init_sent,
 (unsigned long)session_diag.init_mask,session.confirmed,session_diag.handshake_ack,
 (unsigned long)session_diag.rx_packets,(unsigned long)session_diag.rx_unhandled,
 session_diag.last_opcode,session_diag.last_length,
 (unsigned long)(session_diag.rx_packets?now-session_rx_ms:UINT32_MAX),
 session_diag.last_tx_command,(unsigned long)(session_tx_seen?now-session_tx_ms:UINT32_MAX));
}
static void session_note_control(const uint8_t *p,size_t n,bool handled) {
 if(n<6 || p[1] || p[2]!=4 || p[3] || (p[0]!=1 && p[0]!=4))return;
 session_diag.rx_packets++;session_rx_ms=btstack_run_loop_get_time_ms();
 session_diag.last_opcode=(uint16_t)p[4]|((uint16_t)p[5]<<8);
 session_diag.last_length=(uint16_t)n;
 if(!handled)session_diag.rx_unhandled++;
 if(aacp_connection_response_success(p,n))session_diag.handshake_ack=true;
 uint32_t key=((uint32_t)p[0]<<16)|session_diag.last_opcode;
 for(uint32_t i=0;i<session_diag.logged_headers;i++)if(logged_headers[i]==key)return;
 if(session_diag.logged_headers>=16)return;
 logged_headers[session_diag.logged_headers++]=key;
 /* Header classification only, once per type/opcode (16 per channel max).
    Unknown payloads can contain credentials; never print their bytes. */
 printf("[aacp-rx] age_ms=%lu type=%u op=0x%04x len=%u handled=%u\n",
 (unsigned long)(session_rx_ms-session_open_ms),p[0],session_diag.last_opcode,(unsigned)n,handled);
}
static void handler(uint8_t type,uint16_t channel,uint8_t *packet,uint16_t size);
static bool expired(uint32_t now,uint32_t when) { return (int32_t)(now-when)>=0; }
static void release_channel(const char *reason) {
 if(cid){
   session_report(reason);session_end_ms=btstack_run_loop_get_time_ms();
   session_diag.init_sent=session.init_sent;session_diag.peer_seen=session.confirmed;
 }
 aacp_mic_watch_reset(&mic_watch);refresh_pending=false;media_input_reset(&host_media);
 aacp_mic_discontinuity();
 uint16_t old=cid; cid=0; opened=requested=false;
 memset(&session,0,sizeof(session));
 aacp_control_reset(&controls);
 paused_by_ear=false;
 if (old) l2cap_disconnect(old);
 due=btstack_run_loop_get_time_ms()+3000;
}
void aap_disconnect(void) { desired=false; release_channel("host-disconnect"); }
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
static int next_command(uint32_t now) {
 bool failed=mic_watch.failed;aacp_mic_retry_phase retry=mic_watch.retry;
 bool target=aacp_mic_watch_target(&mic_watch,wanted(),session.started,aacp_mic_generation(),now);
 if(!failed && mic_watch.failed)
   printf("[mic] no audio after %u retries; capture fault held until next capture session\n",mic_watch.retries);
 else if(retry!=AACP_MIC_RETRY_STOP && mic_watch.retry==AACP_MIC_RETRY_STOP)
   printf("[mic] audio absent for %u ms; AACP STOP/START retry %u/%u\n",AACP_MIC_SILENCE_MS,mic_watch.retries+1,AACP_MIC_MAX_RETRIES);
 return aacp_mic_next(&session,target);
}
static void au(const uint8_t *data,uint8_t len,uint32_t timestamp,void *ctx) {
 (void)ctx; units++; bytes+=len; last_timestamp=timestamp;
 aacp_mic_audio_note_au(timestamp,time_us_32());
 if (session.started && wanted()) {
   /* Observe the latest USB generation before attributing this AU to capture. */
   if(!mic_watch.enabled || mic_watch.generation!=aacp_mic_generation())
     (void)aacp_mic_watch_target(&mic_watch,wanted(),session.started,aacp_mic_generation(),btstack_run_loop_get_time_ms());
   aacp_mic_watch_audio(&mic_watch,btstack_run_loop_get_time_ms());
   if(!mic_watch.failed)aacp_mic_audio_enqueue(data,len);
 }
}
static void control_notification(const uint8_t *p,size_t n,void *context) {
 (void)context;
 /* Bounded, non-secret diagnostics for otherwise unsupported button
    configuration and gestures. Never dump arbitrary AACP packets/keys. */
 if(n==11 && !memcmp(p,"\x04\x00\x04\x00\x09\x00",6) &&
    (p[6]==5 || (p[6]>=0x14 && p[6]<=0x18) || p[6]==0x39))
   printf("[aacp] button config id=0x%02x values=%u,%u,%u,%u\n",p[6],p[7],p[8],p[9],p[10]);
 if(n==8 && !memcmp(p,"\x04\x00\x04\x00\x19\x00",6))
   printf("[aacp] stem type=%u bud=%u\n",p[6],p[7]);
 bool valid=controls.ear_valid,worn=controls.worn;uint32_t stem=controls.stem_count;
 bool handled=aacp_control_receive(&controls,p,n);
 session_note_control(p,n,handled);
 if (handled) {
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
     uint32_t now=btstack_run_loop_get_time_ms();
     for(unsigned i=0;i<MEDIA_INPUT_QUEUE;i++) {
       uint16_t native=media_input_poll(&host_media,now);if(!native)break;
       usb_hid_consumer(native);
     }
     media_input_typed(&host_media,now);usb_hid_consumer(usage);
   }
 }

}

static void handler(uint8_t type,uint16_t channel,uint8_t *p,uint16_t n) {
 if (type==L2CAP_DATA_PACKET) {
   if (!opened || channel!=cid) return;
   int frames=aacp_mic_parse(p,n,au,NULL);
   if (frames<0) malformed++;
   else if (frames>0) sdus++;
   else {
     int controls_in_sdu=aacp_control_walk(p,n,control_notification,NULL);
     if(controls_in_sdu==0)control_notification(p,n,NULL);
     else if(controls_in_sdu<0){wire_controls.framing_errors++;session_note_control(p,n,false);}
     else if(controls_in_sdu>1)wire_controls.batches++;
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
   if (l2cap_event_channel_opened_get_status(p)) { release_channel("open-failed"); return; }
   opened=true; requested=false; send_errors=0;
   memset(&session,0,sizeof(session));
   memset(&session_diag,0,sizeof(session_diag));session_tx_seen=false;
   session_open_ms=btstack_run_loop_get_time_ms();session_end_ms=session_open_ms;
   aacp_control_reset(&controls); deadline=btstack_run_loop_get_time_ms()+5000;
   /* Reapply current policy after a new channel handshake, never stale writes.
      The source defers this until playback has resumed after any rebuild. */
   a2dp_source_queue_jitter(aap_get_game()?aap_game_jitter():150);
   printf("[mic] AACP opened cid=%u mtu=%u\n",cid,l2cap_event_channel_opened_get_remote_mtu(p));
   break;
 }
 case L2CAP_EVENT_CHANNEL_CLOSED:
   if (l2cap_event_channel_closed_get_local_cid(p)==cid) release_channel("channel-closed-event");
   break;
 case L2CAP_EVENT_CAN_SEND_NOW: {
   if (!opened || l2cap_event_can_send_now_get_local_cid(p)!=cid) break;
   requested=false;
   /* Recompute from current USB intent; never queue a stale START. */
   int command=next_command(btstack_run_loop_get_time_ms());
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
     session_tx_seen=true;session_tx_ms=btstack_run_loop_get_time_ms();
     session_diag.last_tx_command=command>=0?(uint8_t)command:0xff;
     if(command>=0 && command<3) {
       session_diag.init_mask|=1u<<command;
       printf("[aacp-init] age_ms=%lu command=%d len=%u peer_seen=%u\n",
       (unsigned long)(session_tx_ms-session_open_ms),command,len,session.confirmed);
     }
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
       aacp_mic_watch_sent(&mic_watch,command,btstack_run_loop_get_time_ms());
       /* Flush stale AU/PCM history after each successful wire transition.
          Adopt only our own increment: concurrent USB changes stay visible. */
       aacp_mic_discontinuity();mic_watch.generation++;
       /* Capture lifecycle owns START/STOP only. Re-sending playback jitter
          here was an extra control absent from the working mic reference;
          the 042523 capture shows it immediately after STOP when a playback
          channel disappears. Explicit game/profile changes still own jitter. */
       printf("[mic] %s sent capture=%u mic_gen=%lu a2dp_streaming=%u\n",
              command==3?"START":"STOP", (unsigned)aacp_mic_capture(),
              (unsigned long)aacp_mic_generation(),
              (unsigned)a2dp_source_is_playing());
     }
   } else if (++send_errors>=3) release_channel("send-errors");
   break;
 }
 default: break;
 }
}
bool aap_forward_avrcp_media(uint16_t usage) {
 if(!initialized || !opened || !session.confirmed || !settings()->stem_hid ||
    (usage!=0xcd && usage!=0xb5 && usage!=0xb6))return false;
 media_input_avrcp(&host_media,usage,btstack_run_loop_get_time_ms());return true;
}
void aacp_mic_poll(void) {
 uint32_t now=btstack_run_loop_get_time_ms();
 if (desired && !cid && attempts<3 && expired(now,due)) {
   attempts++; deadline=now+10000;
   uint8_t status=l2cap_create_channel(handler,peer,0x1001,1691,&cid);
   if (status) { cid=0; due=now+3000; }
 }
 if (cid && (!opened || !session.confirmed || requested) && expired(now,deadline))
   release_channel(!opened?"open-timeout":!session.confirmed?"setup-timeout":"send-grant-timeout");
 int command=opened?next_command(now):-1;
 if (opened && !requested && (command>=0 || (session.confirmed && (controls.pending || (refresh_pending && expired(now,refresh_due)))))) {
   requested=true;
   if (session.confirmed) deadline=now+3000;
   if (l2cap_request_can_send_now_event(cid)!=ERROR_CODE_SUCCESS) {
     requested=false; if (++send_errors>=3) release_channel("send-request-errors");
   }
 }
 if(!opened || !session.confirmed || !settings()->stem_hid)media_input_reset(&host_media);
 else for(unsigned i=0;i<MEDIA_INPUT_QUEUE;i++) {
   uint16_t usage=media_input_poll(&host_media,now);if(!usage)break;usb_hid_consumer(usage);
 }
 if (now-last_report>=2000) {
   last_report=now;
   printf("[mic] open=%u confirmed=%u wanted=%u sent_start=%u attempts=%u sdu=%lu au=%lu bytes=%lu malformed=%lu ts=%lu\n",
   opened,session.confirmed,wanted(),session.started,attempts,(unsigned long)sdus,
   (unsigned long)units,(unsigned long)bytes,(unsigned long)malformed,(unsigned long)last_timestamp);
   aacp_mic_audio_report();
   if(cid && opened)session_report("periodic");
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
void aacp_mic_get_session_diagnostics(aacp_mic_session_diagnostics *out) {
 if(!out)return;
 memset(out,0,sizeof(*out));if(!control_lock())return;
 *out=session_diag;
 uint32_t now=opened?btstack_run_loop_get_time_ms():session_end_ms;
 out->age_ms=now-session_open_ms;out->cid=cid;out->open=opened;
 if(opened){out->init_sent=session.init_sent;out->peer_seen=session.confirmed;}
 out->last_rx_age_ms=session_diag.rx_packets?now-session_rx_ms:UINT32_MAX;
 out->last_tx_age_ms=session_tx_seen?now-session_tx_ms:UINT32_MAX;
 control_unlock();
}
aacp_control_diagnostics aap_control_diagnostics(void) {
 aacp_control_diagnostics out={.allow_off=-1};
 if(!control_lock())return out;
 out=wire_controls;memcpy(out.observed,controls.observed,sizeof out.observed);out.allow_off=controls.allow_off;
 out.mic_started=session.started;out.mic_audio_seen=mic_watch.seen;out.mic_watchdog_failed=mic_watch.failed;
 out.mic_retry_count=mic_watch.retries;out.mic_restarts=mic_watch.restarts;out.mic_watchdog_failures=mic_watch.failures;
 out.mic_audio_age_ms=mic_watch.seen?btstack_run_loop_get_time_ms()-mic_watch.last_audio:UINT32_MAX;
 out.mic_recovery_pending=opened && session.confirmed &&
     ((wanted() && !mic_watch.failed && (!session.started || !mic_watch.seen || mic_watch.retry!=AACP_MIC_RETRY_NONE)) ||
      (!wanted() && session.started));
 out.media_pending=host_media.count;out.media_suppressed=host_media.suppressed;out.media_dropped=host_media.dropped;
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
bool aap_set_eld_profile(uint8_t rate,bool on,uint8_t level) {
 if(rate<1||rate>3||level<1||level>2||!control_lock())return false;
 bool old_game=aap_get_game();uint8_t old_level=settings()->game_level;
 bool changed=settings()->eld_rate!=rate || old_game!=on || old_level!=level;
 if(changed) {
   settings()->eld_rate=rate;settings()->game_level=level;
   if(on)settings()->usbset|=USBSET_GAME;else settings()->usbset&=(uint8_t)~USBSET_GAME;
   settings_mark_dirty();a2dp_source_apply_eld_rate();
   if(opened && (old_game!=on || (on && old_level!=level)))
     a2dp_source_queue_jitter(on?aap_game_jitter():150);
 }
 control_unlock();return true;
}
void aap_set_game(bool on) {
 (void)aap_set_eld_profile(settings()->eld_rate?settings()->eld_rate:2,on,settings()->game_level?settings()->game_level:1);
}
