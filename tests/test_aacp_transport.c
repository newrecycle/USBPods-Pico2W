// SPDX-License-Identifier: GPL-3.0-only
// Actual channel implementation, fake SDK events/transport. No AirPods used.
#include "btstack.h"
#include "btstack_aap.h"
#include "aacp_mic.h"
#include "aacp_control.h"
#include "../src/settings.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static user_settings_t config;
user_settings_t *settings(void){return &config;}
static unsigned dirties;
void settings_mark_dirty(void){dirties++;}
static unsigned host_keys;static uint16_t last_usage;
void usb_hid_consumer(uint16_t usage){host_keys++;last_usage=usage;}
bool a2dp_source_is_playing(void){return true;}
void a2dp_source_on_aap_wake(void){}
static unsigned rate_sequence,jitter_sequence,sequence,rate_calls;
void a2dp_source_apply_eld_rate(void){rate_sequence=++sequence;rate_calls++;}
void a2dp_source_recover_eld_stream(void){rate_sequence=++sequence;rate_calls++;}
void a2dp_source_queue_jitter(uint8_t ms){assert(ms==60 || ms==90 || ms==150);jitter_sequence=++sequence;}
static btstack_packet_handler_t callback;
static uint32_t now,epochs;
static int locks;
static uint8_t send_rc,request_rc,last[32];static uint16_t last_len;
static bool capture=true;
uint32_t btstack_run_loop_get_time_ms(void){return now;}
uint8_t l2cap_create_channel(btstack_packet_handler_t cb,bd_addr_t addr,uint16_t psm,uint16_t mtu,uint16_t*out){
 (void)addr;assert(psm==0x1001 && mtu==1691);callback=cb;*out=0x42;return 0;
}
uint8_t l2cap_send(uint16_t cid,uint8_t*p,uint16_t n){assert(cid==0x42 && n<=32);memcpy(last,p,n);last_len=n;return send_rc;}
uint8_t l2cap_disconnect(uint16_t cid){(void)cid;return 0;}
uint8_t l2cap_request_can_send_now_event(uint16_t cid){assert(cid==0x42);return request_rc;}
uint8_t sdp_register_service(const uint8_t*p){(void)p;return 0;}
void device_id_create_sdp_record(uint8_t*p,uint32_t h,uint16_t a,uint16_t b,uint16_t c,uint16_t d){(void)p;(void)h;(void)a;(void)b;(void)c;(void)d;}
void *cyw43_arch_async_context(void){return NULL;}
void async_context_acquire_lock_blocking(void*p){(void)p;locks++;}
void async_context_release_lock(void*p){(void)p;assert(locks>0);locks--;}
bool aacp_mic_capture(void){return capture;}
uint32_t aacp_mic_generation(void){return epochs;}
bool aacp_mic_audio_ready(void){return true;}
void aacp_mic_discontinuity(void){epochs++;}
void aacp_mic_audio_enqueue(const uint8_t*p,uint8_t n){(void)p;(void)n;}
void aacp_mic_audio_note_au(uint32_t ts,uint32_t us){(void)ts;(void)us;}
void aacp_mic_audio_report(void){}
static void event(uint8_t code,uint16_t cid){uint8_t p[]={code,0,cid&255,cid>>8,0,1,2,3,4,5,6};callback(HCI_EVENT_PACKET,0,p,sizeof p);}
static void send_now(void){aacp_mic_poll();event(L2CAP_EVENT_CAN_SEND_NOW,0x42);}
int main(void){
 assert(!aacp_control_submit(0x0d,2));assert(aap_get_noise_mode()==0);
 uint8_t battery[3];aap_get_battery(battery);assert(battery[0]==255 && locks==0);
 aacp_mic_init();
 bd_addr_t addr={1,2,3,4,5,6};aap_connect(addr);now=1500;aacp_mic_poll();
 event(L2CAP_EVENT_CHANNEL_OPENED,0x42);assert(aap_channel_open());
 send_rc=1;send_now();assert(last_len==16); // retry same init command
 send_rc=0;send_now();assert(last_len==16);send_now();assert(last_len==14);send_now();assert(last_len==10);
 uint8_t bad[]={4,0,4,0,9,0};callback(L2CAP_DATA_PACKET,0x42,bad,6);assert(!aap_protocol_seen());
 uint8_t ack[]={1,0,4,0,1,0};callback(L2CAP_DATA_PACKET,0x41,ack,6);assert(!aap_protocol_seen());
 callback(L2CAP_DATA_PACKET,0x42,ack,6);assert(aap_protocol_seen());
 aap_set_noise_mode(2);assert(aap_get_noise_mode()==0);send_now();assert(last_len==19); // mic START first
 assert(!rate_calls);now+=800;aacp_mic_poll();assert(!rate_calls);
 capture=false;send_now();assert(last_len==12); // STOP before control writes
 aacp_mic_poll();assert(!rate_calls); // Capture never rebuilds the playback encoder.
 send_rc=1;send_now();assert(last_len==11 && last[6]==0x0d && last[7]==2);
 assert(!aap_control_diagnostics().transmitted);
 send_rc=0;send_now();assert(last_len==11 && last[6]==0x0d);
 assert(aap_control_diagnostics().transmitted==1 && aap_control_diagnostics().last_value==2);
 now+=100;send_now();assert(last_len==10); // refresh notifications after successful write
 uint8_t reply[]={4,0,4,0,9,0,0x0d,2,0,0,0};
 callback(L2CAP_DATA_PACKET,0x41,reply,11);assert(aap_get_noise_mode()==0);
 callback(L2CAP_DATA_PACKET,0x42,reply,11);assert(aap_get_noise_mode()==2);
 assert(aap_control_diagnostics().observed[1]==1);
 // Vendor parser accepts several notifications in one L2CAP SDU.
 uint8_t batch[]={4,0,4,0,9,0,0x0d,3,0,0,0,
                  4,0,4,0,9,0,0x28,1,0,0,0,
                  4,0,4,0,9,0,0x26,1,0,0,0};
 callback(L2CAP_DATA_PACKET,0x42,batch,sizeof batch);
 assert(aap_get_noise_mode()==3 && aap_get_ca()==1 && aap_get_pvol()==1);
 // Failed wire sends and rapid capture toggles never reset playback.
 unsigned calls=rate_calls;capture=true;send_rc=1;send_now();assert(last_len==19);
 now+=800;aacp_mic_poll();assert(rate_calls==calls);
 send_rc=0;send_now();now+=400;capture=false;send_now();assert(last_len==12);
 aacp_mic_poll();assert(rate_calls==calls);
 capture=true;send_now();now+=799;aacp_mic_poll();assert(rate_calls==calls);
 now++;aacp_mic_poll();assert(rate_calls==calls);
 now+=1000;aacp_mic_poll();assert(rate_calls==calls); // exactly once
 // A new USB intent blocks an old recovery before its command can be sent.
 capture=false;send_now();capture=true;aacp_mic_poll();assert(rate_calls==calls);
 send_now();now+=800;aacp_mic_poll();assert(rate_calls==calls);
 capture=false;send_now();aacp_mic_poll();assert(rate_calls==calls);
 aap_set_game(true);assert(rate_sequence<jitter_sequence);assert(aap_get_game());
 aap_set_game(false);assert(rate_sequence<jitter_sequence);assert(!aap_get_game());
 unsigned old_dirties=dirties,old_calls=rate_calls;
 assert(aap_set_eld_profile(3,true,2));assert(dirties==old_dirties+1 && rate_calls==old_calls+1);
 assert(config.eld_rate==3 && config.game_level==2 && aap_get_game());
 old_dirties=dirties;old_calls=rate_calls;
 assert(aap_set_eld_profile(3,true,2) && dirties==old_dirties && rate_calls==old_calls);
 assert(!aap_set_eld_profile(0,false,1) && dirties==old_dirties);
 aap_set_ear_pause(true);
 uint8_t ear[]={4,0,4,0,6,0,0,1};callback(L2CAP_DATA_PACKET,0x42,ear,8);assert(!host_keys);
 ear[6]=1;callback(L2CAP_DATA_PACKET,0x42,ear,8);assert(host_keys==1 && last_usage==0xb1);
 ear[7]=0;callback(L2CAP_DATA_PACKET,0x42,ear,8);assert(host_keys==2 && last_usage==0xb0);
 config.stem_hid=1;unsigned keys=host_keys;
 uint8_t stems[]={4,0,4,0,9,0,0xaa,4,0,4,0,
                  4,0,4,0,0x19,0,6,1,4,0,4,0,0x19,0,7,2};
 callback(L2CAP_DATA_PACKET,0x42,stems,sizeof stems);
 assert(host_keys==keys+2 && last_usage==0xb6);
 callback(L2CAP_DATA_PACKET,0x42,stems,sizeof stems-1);assert(host_keys==keys+2);
 assert(aap_control_diagnostics().batches==2 && aap_control_diagnostics().framing_errors>=1);
 event(L2CAP_EVENT_CHANNEL_CLOSED,0x41);assert(aap_channel_open());
 aap_set_aa(50);capture=true;send_now();calls=rate_calls;
 uint32_t before=epochs;event(L2CAP_EVENT_CHANNEL_CLOSED,0x42);capture=false;
 assert(!aap_channel_open() && epochs>before && aap_get_noise_mode()==0 && aap_get_aa()==-1);
 now+=3000;aacp_mic_poll();assert(rate_calls==calls);event(L2CAP_EVENT_CHANNEL_OPENED,0x42);
 send_now();send_now();send_now();callback(L2CAP_DATA_PACKET,0x42,ack,6);
 last_len=0;send_now();assert(!last_len); // stale control not replayed after reconnect
 aap_set_ca(true);request_rc=1;for(int i=0;i<3;i++)aacp_mic_poll();assert(!aap_channel_open());
 assert(locks==0);puts("AACP channel lifecycle, failed sends, shared controls and stale events passed");
}
