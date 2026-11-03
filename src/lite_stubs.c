/*
 * lite_stubs.c — the open-source (Lite) build's stand-ins for the private
 * modules: the WebHID/WebUSB config channel (webhid_cmd.c), the AirPods
 * remaining AirPods policy hooks and the license system (license.c).
 *
 * Compiled ONLY when USBPODS_LITE (CMake picks this file OR the real
 * modules — never both). Everything here is a no-op with the semantics
 * "feature absent" for WebHID, relay, ear/game policy and licensing.
 * The shared aacp_mic/control implementation owns the live AACP channel,
 * feature-report GETs stall so a probing host sees an empty channel.
 */
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "btstack/btstack_aap.h"
#include "btstack/btstack_sink_relay.h"

/* ---- WebHID/WebUSB config channel (HID feature-report callbacks, uac.c) - */

uint16_t webhid_get_report(uint8_t report_id, uint8_t *buf, uint16_t reqlen){
    (void)report_id; (void)buf; (void)reqlen;
    return 0;                              /* 0 = stall the GET */
}
void webhid_set_report(uint8_t report_id, const uint8_t *buf, uint16_t len){
    (void)report_id; (void)buf; (void)len;
}
void webhid_task(void){}

/* ---- A2DP phone sink relay (btstack_sink_relay.c) ------------------------
   No sink SEP/SDP is registered, so a phone can never connect: every query
   answers "no phone", the mixer adds nothing, and the pump keeps its full
   TX budget (the relay coex caps never engage). */

#ifndef USBPODS_RELAY
void bt_sink_relay_init(void){}
bool bt_sink_relay_is_phone_addr(const uint8_t *addr){ (void)addr; return false; }
bool bt_sink_relay_owns_cid(uint16_t avdtp_cid){ (void)avdtp_cid; return false; }
void bt_sink_relay_mix(int16_t *buf, uint16_t stereo_frames){ (void)buf; (void)stereo_frames; }
bool bt_sink_relay_connected(void){ return false; }
bool bt_sink_relay_streaming(void){ return false; }
bool bt_sink_relay_work(void){ return false; }          /* nothing queued, ever */
uint32_t bt_sink_relay_conn_age_ms(void){ return UINT32_MAX; }
uint16_t bt_sink_relay_con_handle(void){ return 0; }
void bt_sink_relay_set_vol_pct(uint8_t pct){ (void)pct; }
bool bt_sink_relay_dial(const uint8_t *mac){ (void)mac; return false; }
void bt_sink_relay_disconnect(void){}
void bt_sink_relay_dump(void){}
void bt_sink_relay_toggle_aac(void){}
void bt_sink_relay_sync_codec_pref(void){}
void bt_sink_relay_refresh_aac_caps(void){}

#endif

/* ---- license system ----------------------------------------------------- */

void     license_init(void){}
void     license_task(void){}
void     license_recheck(void){}
void     license_unbind_boot_check(bool was_power_cycle){ (void)was_power_cycle; }
uint8_t  license_state(void){ return 0; }          /* LICENSE_NONE */
uint8_t  license_key_id(void){ return 0; }
uint32_t license_features(void){ return 0; }
void     license_device_id(uint8_t out[22]){ memset(out, 0, 22); }

/* ---- AirPods AACP client ------------------------------------------------ */



void aap_cycle_jitter(void){}
void aap_probe_4c(void){}
void aap_send_09_03(uint8_t v){ (void)v; }


uint32_t aap_last_lock_ms(void){ return 0; }       /* never held the BT lock */
volatile bool aap_rx_log = false;                  /* 'A' key raw-frame logging */


