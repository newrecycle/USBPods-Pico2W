// SPDX-License-Identifier: GPL-3.0-only
#include "device_control.h"
#include "control_command.h"
#include "settings.h"
#include "pico_w_led.h"
#include "btstack/btstack_aap.h"
#include "btstack/aacp_control.h"
#include "btstack/aacp_mic.h"
#include "btstack/eld_profile.h"
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
#include <malloc.h>
extern char end[],__HeapLimit[];
extern uint8_t last_reset_kind,last_hang_phase,last_hang_irq;
extern uint32_t last_hang_ticks,last_fault_pc,last_fault_lr,last_fault_cfsr;
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
static void session_telemetry(void) {
 aacp_mic_session_diagnostics s;aacp_mic_get_session_diagnostics(&s);
 printf("\n[control] {\"kind\":\"aacpsession\",\"open\":%u,\"cid\":%u,\"age_ms\":%lu,\"init_sent\":%u,\"init_mask\":%lu,\"peer_seen\":%u,\"handshake_ack\":%u,\"rx_frames\":%lu,\"rx_unhandled\":%lu,\"logged_headers\":%lu,\"last_opcode\":%u,\"last_length\":%u,\"last_rx_age_ms\":%lu,\"last_tx_command\":%u,\"last_tx_age_ms\":%lu}\n",
 (unsigned)s.open,(unsigned)s.cid,(unsigned long)s.age_ms,(unsigned)s.init_sent,
 (unsigned long)s.init_mask,(unsigned)s.peer_seen,(unsigned)s.handshake_ack,
 (unsigned long)s.rx_packets,(unsigned long)s.rx_unhandled,(unsigned long)s.logged_headers,
 (unsigned)s.last_opcode,(unsigned)s.last_length,(unsigned long)s.last_rx_age_ms,
 (unsigned)s.last_tx_command,(unsigned long)s.last_tx_age_ms);
}
static atomic_bool reboot_requested;
static uint32_t reboot_at;
static void audio_telemetry(void) {
 session_telemetry();
 aacp_mic_audio_stats m;aacp_mic_audio_get_stats(&m);
 usb_capture_snapshot_t u=usb_capture_snapshot();
 usb_hid_media_snapshot_t h=usb_hid_media_snapshot();
#define U(v) (unsigned long)(v)
 printf("\n[control] {\"kind\":\"micstats\",\"generation\":%lu,\"capture\":%lu,\"decoder_ready\":%lu,\"au\":%lu,\"intervals\":%lu,\"bursts\":%lu,\"cadence7500\":%lu,\"cadence10000\":%lu,\"arrival_gaps\":%lu,\"timestamp\":%lu,\"timestamp_step\":%lu,\"timestamp_gap_candidates\":%lu,\"timestamp_duplicates\":%lu,\"timestamp_backwards\":%lu,\"au_depth\":%lu,\"au_high\":%lu,\"au_drop\":%lu,\"au_stale\":%lu,\"pcm_depth\":%lu,\"pcm_high\":%lu,\"pcm_drop\":%lu,\"pcm_stale\":%lu,\"decoded\":%lu,\"errors\":%lu,\"decode_max_us\":%lu,\"decode_last_us\":%lu,\"decode_ema_us\":%lu,\"decoded_rate\":%lu,\"decoded_frame_samples\":%lu,\"coding_rate\":48000,\"pcm_rate\":64000,\"measured_rate\":%lu,\"clock_windows\":%lu,\"primed\":%lu,\"au_wait_last_us\":%lu,\"au_wait_max_us\":%lu,\"work_max_us\":%lu,\"pcm_blocked\":%lu,\"au_drop_pcm_full\":%lu}\n",
 U(m.generation),U(m.capture),U(m.decoder_ready),U(m.au_observed),U(m.arrival_intervals),U(m.arrival_bursts),U(m.arrival_7500us),U(m.arrival_10000us),U(m.arrival_gaps),U(m.timestamp_last),U(m.timestamp_step_reference),U(m.timestamp_gap_candidates),U(m.timestamp_duplicates),U(m.timestamp_backwards),U(m.au_depth),U(m.au_high_water),U(m.au_overflows),U(m.au_stale),U(m.pcm_depth),U(m.pcm_high_water),U(m.pcm_overflows),U(m.pcm_stale),U(m.decoded),U(m.decode_errors),U(m.decode_max_us),U(m.decode_last_us),U(m.decode_ema_us),U(m.decoded_rate),U(m.decoded_frame_samples),U(m.measured_sample_rate),U(m.clock_windows),U(m.pcm_primed),U(m.au_wait_last_us),U(m.au_wait_max_us),U(m.work_max_us),U(m.pcm_blocked),U(m.au_overflow_pcm_full));
 printf("\n[control] {\"kind\":\"micunderrun\",\"after_prime\":%lu,\"rebuffers\":%lu,\"first_valid\":%lu,\"first_generation\":%lu,\"first_us\":%lu,\"first_want\":%lu,\"first_got\":%lu,\"first_au_depth\":%lu,\"first_pcm_depth\":%lu,\"first_available\":%lu,\"first_au_age_us\":%lu,\"first_pcm_age_us\":%lu,\"first_rebuffer\":%lu}\n",
  U(m.usb_postprime_underruns),U(m.usb_rebuffers),U(m.usb_first_fault_valid),
  U(m.usb_first_fault_generation),U(m.usb_first_fault_at_us),
  U(m.usb_first_fault_requested),U(m.usb_first_fault_supplied),
  U(m.usb_first_fault_au_depth),U(m.usb_first_fault_pcm_depth),
  U(m.usb_first_fault_available),U(m.usb_first_fault_au_age_us),
  U(m.usb_first_fault_pcm_age_us),U(m.usb_first_fault_rebuffer));
 printf("\n[control] {\"kind\":\"usbcapture\",\"mounted\":%u,\"suspended\":%u,\"alt\":%u,\"running\":%u,\"packets\":%lu,\"pcm_samples\":%lu,\"underruns\":%lu,\"missing_samples\":%lu,\"short_writes\":%lu,\"expected_samples\":%lu,\"packets63\":%lu,\"packets65\":%lu}\n",
 (unsigned)u.mounted,(unsigned)u.suspended,(unsigned)u.alt_active,(unsigned)u.capture_running,U(u.usb_packets),U(u.pcm_samples),U(u.underrun_packets),U(u.missing_samples),U(u.short_writes),U(u.expected_samples),U(u.packets_63),U(u.packets_65));
 printf("\n[control] {\"kind\":\"hidstats\",\"active\":%u,\"release_pending\":%u,\"depth\":%lu,\"high\":%lu,\"accepted\":%lu,\"full\":%lu,\"inactive\":%lu,\"stale\":%lu,\"presses\":%lu,\"releases\":%lu,\"busy\":%lu,\"failures\":%lu}\n",
 (unsigned)h.active,(unsigned)h.release_pending,U(h.queue_depth),U(h.high_water),U(h.accepted),U(h.dropped_full),U(h.dropped_inactive),U(h.stale),U(h.presses_sent),U(h.releases_sent),U(h.busy_ticks),U(h.send_failures));
#undef U
}
static void quoted(char out[51],const char *s) {
 char *p=out;*p++='"';for(size_t i=0;i<24&&s[i];i++) {
   unsigned char c=(unsigned char)s[i];
   if(c=='"'||c=='\\')*p++='\\';*p++=c<32?'_':c;
 }*p++='"';*p=0;
}
static void status(void) {
 uint8_t b[3];aap_get_battery(b);const uint8_t *peer=a2dp_source_peer_addr();
 aacp_control_diagnostics ctl=aap_control_diagnostics();
 printf("\n[control] {\"kind\":\"status\",\"version\":2,\"channel\":%u,\"confirmed\":%u,\"connected\":%u,\"streaming\":%u,\"tx_packets\":%lu,\"send_failures\":%lu,\"codec\":%u,\"noise\":%u,\"pvol\":%d,\"ca\":%d,\"aa\":%d,\"battery\":[%u,%u,%u],\"capture\":%u,\"decoder_ready\":%u,\"relay_connected\":%u,\"relay_streaming\":%u,\"fault_hold\":%u,\"peer\":\"%s\",\"control_tx\":%lu,\"control_last_id\":%u,\"control_last_value\":%u,\"control_rx_seq\":[%lu,%lu,%lu,%lu,%lu],\"control_batches\":%lu,\"control_framing_errors\":%lu,\"allow_off\":%d,\"media_pending\":%u,\"media_suppressed\":%lu,\"media_dropped\":%lu,\"mic_started\":%u,\"mic_recovery_pending\":%u,\"mic_audio_seen\":%u,\"mic_watchdog_failed\":%u,\"mic_retry_count\":%u,\"mic_restarts\":%lu,\"mic_watchdog_failures\":%lu,\"mic_audio_age_ms\":%lu}\n",
 aap_channel_open(),aap_protocol_seen(),get_a2dp_connected_flag(),check_is_streaming(),(unsigned long)a2dp_source_tx_packets(),(unsigned long)a2dp_source_send_failures(),get_cur_codec(),
 aap_get_noise_mode(),aap_get_pvol(),aap_get_ca(),aap_get_aa(),b[0],b[1],b[2],
 aacp_mic_capture(),aacp_mic_audio_ready(),bt_sink_relay_connected(),bt_sink_relay_streaming(),a2dp_source_fault_hold(),
 peer?bd_addr_to_str((uint8_t*)peer):"",(unsigned long)ctl.transmitted,ctl.last_id,ctl.last_value,
 (unsigned long)ctl.observed[0],(unsigned long)ctl.observed[1],(unsigned long)ctl.observed[2],(unsigned long)ctl.observed[3],(unsigned long)ctl.observed[4],(unsigned long)ctl.batches,(unsigned long)ctl.framing_errors,ctl.allow_off,ctl.media_pending,(unsigned long)ctl.media_suppressed,(unsigned long)ctl.media_dropped,(unsigned)ctl.mic_started,(unsigned)ctl.mic_recovery_pending,(unsigned)ctl.mic_audio_seen,(unsigned)ctl.mic_watchdog_failed,(unsigned)ctl.mic_retry_count,(unsigned long)ctl.mic_restarts,(unsigned long)ctl.mic_watchdog_failures,(unsigned long)ctl.mic_audio_age_ms);
}
static void list(bool scan) {
 /* Format one record before emitting it: background logs must not split
    the many putchar/printf calls of the old JSON serializer. */
 char line[3072];
 int used=snprintf(line,sizeof line,"{\"kind\":\"%s\",\"items\":[",scan?"scanlist":"savedlist");
 unsigned count=scan?bt_scan_count():SETTINGS_SAVED_LIMIT;
 for(unsigned i=0;i<count;i++) {
   uint8_t mac[6];char name[24];int8_t rssi=0;
   if(scan){if(!bt_scan_get(i,mac,&rssi,name))break;}
   else{memcpy(mac,settings()->saved[i].mac,6);memcpy(name,settings()->saved[i].name,24);}
   char escaped[51];quoted(escaped,name);
   int n=snprintf(line+used,sizeof line-(size_t)used,"%s{\"index\":%u,\"mac\":\"%s\",\"rssi\":%d,\"name\":%s}",i?",":"",i,bd_addr_to_str(mac),rssi,escaped);
   if(n<0 || (size_t)n>=sizeof line-(size_t)used) {
     printf("\n[control] {\"kind\":\"error\",\"error\":\"list-overflow\"}\n");return;
   }
   used+=n;
 }
 printf("\n[control] %s]}\n",line);
}
static bool dispatch(control_command c) {
 user_settings_t*s=settings();uint8_t v=c.value;
 switch(c.id) {
 case CONTROL_INFO:
   printf("\n[control] {\"kind\":\"info\",\"protocol\":2,\"sha\":\"%s\",\"board\":\"rp2350\",\"mic_decode\":%u,\"relay\":%u,\"relay_aac\":%u,\"uac1\":%u,\"uart_baud\":115200,\"uart_tx_gpio\":0,\"uart_rx_gpio\":1,\"reset_kind\":%u,\"reset_phase\":%u,\"reset_irq\":%u,\"reset_usb_ticks\":%lu,\"fault_pc\":%lu,\"fault_lr\":%lu,\"fault_cfsr\":%lu}\n",USBPODS_BUILD_SHA,MIC_DECODE,RELAY,RELAY&&RELAY_AAC,usb_uac1_active(),(unsigned)last_reset_kind,(unsigned)last_hang_phase,(unsigned)last_hang_irq,(unsigned long)last_hang_ticks,(unsigned long)last_fault_pc,(unsigned long)last_fault_lr,(unsigned long)last_fault_cfsr);return true;
 case CONTROL_ELDSTATUS: {
   eld_runtime_status state;a2dp_source_eld_status(&state);
   struct mallinfo heap=mallinfo();
   printf("\n[control] {\"kind\":\"eldstatus\",\"selected_rate\":%u,\"game\":%u,\"gamelevel\":%u,\"ready\":%u,\"pending\":%u,\"desired_bitrate\":%lu,\"active_bitrate\":%lu,\"active_vbr\":%u,\"active_sbr\":%u,\"active_slots\":%u,\"active_jitter\":%u,\"desired_jitter\":%u,\"input_rate\":%u,\"failures\":%lu,\"rebuilds\":%lu,\"heap_region\":%lu,\"heap_inuse\":%lu,\"heap_free_arena\":%lu,\"transition\":\"%s\",\"requested_revision\":%lu,\"built_revision\":%lu,\"error_stage\":%u,\"last_error\":%lu,\"max_rebuild_us\":%lu,\"negotiated_bitrate\":%lu,\"negotiated_vbr\":%u,\"duplex_cbr\":%u,\"encode_last_us\":%lu,\"encode_max_us\":%lu}\n",
      s->eld_rate?s->eld_rate:2,aap_get_game(),s->game_level?s->game_level:1,state.ready,state.pending,
      (unsigned long)state.desired.bitrate,(unsigned long)state.active.bitrate,state.active.vbr,state.active.sbr,state.active.slots,state.active.jitter,state.desired.jitter,state.active.input_rate,
      (unsigned long)state.failures,(unsigned long)state.rebuilds,(unsigned long)((uintptr_t)__HeapLimit-(uintptr_t)end),(unsigned long)heap.uordblks,(unsigned long)heap.fordblks,eld_transition_phase_name(state.phase),(unsigned long)state.requested_revision,(unsigned long)state.built_revision,state.error_stage,(unsigned long)state.last_error,(unsigned long)state.max_rebuild_us,(unsigned long)state.negotiated_bitrate,(unsigned)state.negotiated_vbr,(unsigned)state.duplex_cbr,(unsigned long)state.encode_last_us,(unsigned long)state.encode_max_us);return true;
 }
 case CONTROL_SETTINGS:
   printf("\n[control] {\"kind\":\"settings\",\"usbset\":%u,\"slot\":%u,\"connmode\":%u,\"usbvol\":%u,\"phvol\":%u,\"gamelevel\":%u,\"eldrate\":%u,\"earpause\":%u,\"stem\":%u,\"debug\":%u,\"btnmode\":%u,\"ldacq\":%u,\"lhdcrate\":%u}\n",s->usbset,read_uint8_last_flash(),s->connmode,s->usb_vol_p1?s->usb_vol_p1-1:100,s->relay_vol_p1?s->relay_vol_p1-1:100,s->game_level?s->game_level:1,s->eld_rate?s->eld_rate:2,s->ear_pause,s->stem_hid,s->dbg_mode,s->btn_mode?s->btn_mode:1,s->ldac_quality?s->ldac_quality:2,s->lhdc_rate?s->lhdc_rate:2);return true;
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
 case CONTROL_GAMELEVEL:if(v<1||v>2)return false;return aap_set_eld_profile(s->eld_rate?s->eld_rate:2,aap_get_game(),v);
 case CONTROL_ELDRATE:if(v<1||v>3||bt_sink_relay_connected())return false;return aap_set_eld_profile(v,aap_get_game(),s->game_level?s->game_level:1);
 case CONTROL_PROFILE:if(bt_sink_relay_connected())return false;return aap_set_eld_profile(v,c.game!=0,c.level);
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
 case CONTROL_TELEMETRY:audio_telemetry();a2dp_source_transport_report();aacp_mic_audio_report();bt_sink_relay_dump();usb_serial_diagnostics();return true;
 case CONTROL_REBOOT:atomic_store(&reboot_requested,true);return true;
 default:return aacp_control_submit(c.id,v);
 }
 settings_mark_dirty();return true;
}
bool device_control_character(char c) {
 control_command cmd;enum control_result r=control_input_feed(&input,c,&cmd);
 if(r==CONTROL_BYPASS)return false;if(r==CONTROL_WAIT)return true;
 if(r==CONTROL_INVALID){printf("\n[control] {\"kind\":\"error\",\"error\":\"invalid-command\"}\n");return true;}
 if(radio_is_absent()){printf("\n[control] {\"kind\":\"error\",\"error\":\"no-radio\"}\n");return true;}
 async_context_acquire_lock_blocking(cyw43_arch_async_context());
 if(cmd.status)status();else{
   bool ok=dispatch(cmd);
   if(cmd.id!=CONTROL_ELDSTATUS&&cmd.id!=CONTROL_INFO&&cmd.id!=CONTROL_SETTINGS&&cmd.id!=CONTROL_SCANLIST&&cmd.id!=CONTROL_SAVEDLIST)
     printf("\n[control] {\"kind\":\"ack\",\"queued\":%u,\"id\":%u,\"value\":%u,\"reboot_required\":%u}\n",ok,cmd.id,cmd.value,cmd.id==CONTROL_UAC1||cmd.id==CONTROL_RATE44);
 }
 async_context_release_lock(cyw43_arch_async_context());return true;
}
void device_control_task(void) {
 if(!atomic_load(&reboot_requested))return;
 uint32_t now=to_ms_since_boot(get_absolute_time());
 if(!reboot_at){reboot_at=now+500;return;}
 if((int32_t)(now-reboot_at)<0)return;
 if(!settings_flush()){printf("\n[control] {\"kind\":\"error\",\"error\":\"settings-flush\"}\n");atomic_store(&reboot_requested,false);reboot_at=0;return;}
 watchdog_reboot(0,0,0);
}
