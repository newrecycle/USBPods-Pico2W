// SPDX-License-Identifier: GPL-3.0-only
// Actual channel implementation, fake SDK events/transport. No AirPods used.
#include "btstack.h"
#include "btstack_aap.h"
#include "aacp_mic.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
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
bool aacp_mic_audio_ready(void){return true;}
void aacp_mic_discontinuity(void){epochs++;}
void aacp_mic_audio_enqueue(const uint8_t*p,uint8_t n){(void)p;(void)n;}
static void event(uint8_t code,uint16_t cid){uint8_t p[]={code,0,cid&255,cid>>8,0,1,2,3,4,5,6};callback(HCI_EVENT_PACKET,0,p,sizeof p);}
static void send_now(void){aacp_mic_poll();event(L2CAP_EVENT_CAN_SEND_NOW,0x42);}
int main(void){
 bd_addr_t addr={1,2,3,4,5,6};aap_connect(addr);now=1500;aacp_mic_poll();
 event(L2CAP_EVENT_CHANNEL_OPENED,0x42);assert(aap_channel_open());
 send_rc=1;send_now();assert(last_len==16); // retry same init command
 send_rc=0;send_now();assert(last_len==16);send_now();assert(last_len==14);send_now();assert(last_len==10);
 uint8_t bad[]={4,0,4,0,9,0};callback(L2CAP_DATA_PACKET,0x42,bad,6);assert(!aap_protocol_seen());
 uint8_t ack[]={1,0,4,0,1,0};callback(L2CAP_DATA_PACKET,0x41,ack,6);assert(!aap_protocol_seen());
 callback(L2CAP_DATA_PACKET,0x42,ack,6);assert(aap_protocol_seen());
 aap_set_noise_mode(2);assert(aap_get_noise_mode()==0);send_now();assert(last_len==19); // mic START first
 capture=false;send_now();assert(last_len==12); // STOP before control writes
 send_rc=1;send_now();assert(last_len==11 && last[6]==0x0d && last[7]==2);
 send_rc=0;send_now();assert(last_len==11 && last[6]==0x0d);
 uint8_t reply[]={4,0,4,0,9,0,0x0d,2,0,0,0};
 callback(L2CAP_DATA_PACKET,0x41,reply,11);assert(aap_get_noise_mode()==0);
 callback(L2CAP_DATA_PACKET,0x42,reply,11);assert(aap_get_noise_mode()==2);
 event(L2CAP_EVENT_CHANNEL_CLOSED,0x41);assert(aap_channel_open());
 aap_set_aa(50);uint32_t before=epochs;event(L2CAP_EVENT_CHANNEL_CLOSED,0x42);
 assert(!aap_channel_open() && epochs>before && aap_get_noise_mode()==0 && aap_get_aa()==-1);
 now+=3000;aacp_mic_poll();event(L2CAP_EVENT_CHANNEL_OPENED,0x42);
 send_now();send_now();send_now();callback(L2CAP_DATA_PACKET,0x42,ack,6);
 last_len=0;send_now();assert(!last_len); // stale control not replayed after reconnect
 aap_set_ca(true);request_rc=1;for(int i=0;i<3;i++)aacp_mic_poll();assert(!aap_channel_open());
 assert(locks==0);puts("AACP channel lifecycle, failed sends, shared controls and stale events passed");
}
