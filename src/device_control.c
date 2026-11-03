// SPDX-License-Identifier: GPL-3.0-only
#include "device_control.h"
#include "control_command.h"
#include "settings.h"
#include "pico_w_led.h"
#include "btstack/btstack_aap.h"
#include "btstack/aacp_control.h"
#include "btstack/aacp_mic.h"
#include "btstack/btstack_avdtp_source.h"
#include "btstack/btstack_hci.h"
#include "btstack/btstack_sink_relay.h"
#include "btstack/codec/codec.h"
#include "tinyusb/uac.h"
#include "pico/cyw43_arch.h"
#include "pico/async_context.h"
#include "hardware/watchdog.h"
#include "pico/time.h"
extern void usb_serial_diagnostics(void);
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#ifndef USBPODS_BUILD_SHA
#define USBPODS_BUILD_SHA "unknown"
#endif
#ifdef USBPODS_MIC_DECODE
#define MIC_DECODE 1
#define RELAY_AAC 0
#else
#define MIC_DECODE 0
#define RELAY_AAC 1
#endif
#ifdef USBPODS_RELAY
#define RELAY 1
#else
#define RELAY 0
#endif
extern void bt_phone_pair_window(bool);
extern bool bt_phone_pair_window_open(void);
extern bool bt_connect_saved(const uint8_t*);
static control_input input;
static atomic_bool reboot_requested;
static uint32_t reboot_at;
static void quoted(const char *s,size_t n) {
 putchar('"');for(size_t i=0;i<n&&s[i];i++) {
   unsigned char c=(unsigned char)s[i];
   if(c=='"'||c=='\\')putchar('\\');putchar(c<32?'_':c);
 }putchar('"');
}
static void status(void) {
 uint8_t b[3];aap_get_battery(b);const uint8_t *peer=a2dp_source_peer_addr();
 printf("[control] {\"kind\":\"status\",\"version\":2,\"channel\":%u,\"confirmed\":%u,\"connected\":%u,\"streaming\":%u,\"codec\":%u,\"noise\":%u,\"pvol\":%d,\"ca\":%d,\"aa\":%d,\"battery\":[%u,%u,%u],\"capture\":%u,\"decoder_ready\":%u,\"relay_connected\":%u,\"relay_streaming\":%u,\"peer\":\"%s\"}\n",
 aap_channel_open(),aap_protocol_seen(),get_a2dp_connected_flag(),check_is_streaming(),get_cur_codec(),
 aap_get_noise_mode(),aap_get_pvol(),aap_get_ca(),aap_get_aa(),b[0],b[1],b[2],
 aacp_mic_capture(),aacp_mic_audio_ready(),bt_sink_relay_connected(),bt_sink_relay_streaming(),
 peer?bd_addr_to_str((uint8_t*)peer):"");
}
static void list(bool scan) {
 printf("[control] {\"kind\":\"%s\",\"items\":[",scan?"scanlist":"savedlist");
 unsigned count=scan?bt_scan_count():SETTINGS_SAVED_LIMIT;
 for(unsigned i=0;i<count;i++) {
   uint8_t mac[6];char name[24];int8_t rssi=0;
   if(scan){if(!bt_scan_get(i,mac,&rssi,name))break;}
   else{memcpy(mac,settings()->saved[i].mac,6);memcpy(name,settings()->saved[i].name,24);}
   if(i)putchar(',');printf("{\"index\":%u,\"mac\":\"%s\",\"rssi\":%d,\"name\":",i,bd_addr_to_str(mac),rssi);
   quoted(name,24);putchar('}');
 }
 printf("]}\n");
}
static bool dispatch(control_command c) {
 user_settings_t*s=settings();uint8_t v=c.value;
 switch(c.id) {
 case CONTROL_INFO:
   printf("[control] {\"kind\":\"info\",\"protocol\":2,\"sha\":\"%s\",\"board\":\"rp2350\",\"mic_decode\":%u,\"relay\":%u,\"relay_aac\":%u,\"uac1\":%u,\"uart_baud\":115200,\"uart_tx_gpio\":0,\"uart_rx_gpio\":1}\n",USBPODS_BUILD_SHA,MIC_DECODE,RELAY,RELAY&&RELAY_AAC,usb_uac1_active());return true;
 case CONTROL_SETTINGS:
   printf("[control] {\"kind\":\"settings\",\"usbset\":%u,\"slot\":%u,\"connmode\":%u,\"usbvol\":%u,\"phvol\":%u,\"gamelevel\":%u,\"eldrate\":%u,\"earpause\":%u,\"stem\":%u,\"debug\":%u,\"btnmode\":%u,\"ldacq\":%u,\"lhdcrate\":%u}\n",s->usbset,read_uint8_last_flash(),s->connmode,s->usb_vol_p1?s->usb_vol_p1-1:100,s->relay_vol_p1?s->relay_vol_p1-1:100,s->game_level?s->game_level:1,s->eld_rate?s->eld_rate:2,s->ear_pause,s->stem_hid,s->dbg_mode,s->btn_mode?s->btn_mode:1,s->ldac_quality?s->ldac_quality:2,s->lhdc_rate?s->lhdc_rate:2);return true;
 case CONTROL_SCAN:bt_scan_start_list();return true;
 case CONTROL_SCANSTOP:gap_inquiry_stop();return true;
 case CONTROL_SCANLIST:list(true);return true;
 case CONTROL_SAVEDLIST:list(false);return true;
 case CONTROL_PAIR:return bt_pair_to(v);
 case CONTROL_CONNECT:a2dp_source_wedge_clear();a2dp_source_reconnect();return true;
 case CONTROL_DISCONNECT:a2dp_source_console_disconnect();aap_disconnect();return true;
 case CONTROL_SLOT:if(v<1||v>2)return false;a2dp_source_switch_slot(v);return true;
 case CONTROL_SAVEDCONNECT:if(v>=SETTINGS_SAVED_LIMIT)return false;return bt_connect_saved(s->saved[v].mac);
 case CONTROL_SAVEDDELETE:if(v>=SETTINGS_SAVED_LIMIT)return false;settings_saved_remove(v);return true;
 case CONTROL_PHONEPAIR:if(!RELAY||v>1)return false;bt_phone_pair_window(v!=0);return true;
 case CONTROL_PHONEDISC:if(!RELAY)return false;bt_sink_relay_disconnect();return true;
 case CONTROL_PHONECONNECT:if(!RELAY||v>=SETTINGS_PHONES_N)return false;return bt_sink_relay_dial(s->phones[v].mac);
 case CONTROL_RELAYAAC:if(!RELAY_AAC||v<1||v>2)return false;s->relay_aac_rate=v;bt_sink_relay_refresh_aac_caps();break;
 case CONTROL_GAME:if(v>1)return false;aap_set_game(v!=0);return true;
 case CONTROL_EARPAUSE:if(v>1)return false;aap_set_ear_pause(v!=0);return true;
 case CONTROL_STEM:if(v>1)return false;s->stem_hid=v;break;
 case CONTROL_GAMELEVEL:if(v<1||v>2)return false;s->game_level=v;aap_set_game(aap_get_game());break;
 case CONTROL_ELDRATE:if(v<1||v>3||bt_sink_relay_connected())return false;s->eld_rate=v;a2dp_source_apply_eld_rate();break;
 case CONTROL_USBVOL:if(v>100)return false;s->usb_vol_p1=v+1;set_usb_sw_gain_pct(v);break;
 case CONTROL_PHVOL:if(v>100)return false;s->relay_vol_p1=v+1;bt_sink_relay_set_vol_pct(v);break;
 case CONTROL_CONNMODE:if(v<1||v>3)return false;s->connmode=v;break;
 case CONTROL_BTNMODE:if(v<1||v>4)return false;s->btn_mode=v;break;
 case CONTROL_LDACQ:if(v<1||v>3)return false;s->ldac_quality=v;codec_ldac_request_quality(v);break;
 case CONTROL_LHDCRATE:if(v<1||v>4)return false;s->lhdc_rate=v;codec_lhdc_request_rate(v);break;
 case CONTROL_DEBUG:if(v>1)return false;s->dbg_mode=v;a2dp_source_set_debug_mode(v!=0);break;
 case CONTROL_UART:case CONTROL_UAC1:case CONTROL_RATE44:case CONTROL_BOOTCONN:case CONTROL_PAUSEDC:case CONTROL_SWVOL: {
   if(v>1)return false;
   uint8_t bit=c.id==CONTROL_UART?USBSET_UART:c.id==CONTROL_UAC1?USBSET_UAC1:c.id==CONTROL_RATE44?USBSET_RATE44:c.id==CONTROL_BOOTCONN?USBSET_BOOTCONN:c.id==CONTROL_PAUSEDC?USBSET_PAUSEDC:USBSET_SWVOL;
   if(v)s->usbset|=bit;else s->usbset&=(uint8_t)~bit;break;
 }
 case CONTROL_TELEMETRY:aacp_mic_audio_report();bt_sink_relay_dump();usb_serial_diagnostics();return true;
 case CONTROL_REBOOT:atomic_store(&reboot_requested,true);return true;
 default:return aacp_control_submit(c.id,v);
 }
 settings_mark_dirty();return true;
}
bool device_control_character(char c) {
 control_command cmd;enum control_result r=control_input_feed(&input,c,&cmd);
 if(r==CONTROL_BYPASS)return false;if(r==CONTROL_WAIT)return true;
 if(r==CONTROL_INVALID){printf("[control] {\"kind\":\"error\",\"error\":\"invalid-command\"}\n");return true;}
 if(radio_is_absent()){printf("[control] {\"kind\":\"error\",\"error\":\"no-radio\"}\n");return true;}
 async_context_acquire_lock_blocking(cyw43_arch_async_context());
 if(cmd.status)status();else{
   bool ok=dispatch(cmd);
   if(cmd.id!=CONTROL_INFO&&cmd.id!=CONTROL_SETTINGS&&cmd.id!=CONTROL_SCANLIST&&cmd.id!=CONTROL_SAVEDLIST)
     printf("[control] {\"kind\":\"ack\",\"queued\":%u,\"id\":%u,\"value\":%u,\"reboot_required\":%u}\n",ok,cmd.id,cmd.value,cmd.id==CONTROL_UAC1||cmd.id==CONTROL_RATE44);
 }
 async_context_release_lock(cyw43_arch_async_context());return true;
}
void device_control_task(void) {
 if(!atomic_load(&reboot_requested))return;
 uint32_t now=to_ms_since_boot(get_absolute_time());
 if(!reboot_at){reboot_at=now+500;return;}
 if((int32_t)(now-reboot_at)<0)return;
 if(!settings_flush()){printf("[control] {\"kind\":\"error\",\"error\":\"settings-flush\"}\n");atomic_store(&reboot_requested,false);reboot_at=0;return;}
 watchdog_reboot(0,0,0);
}
