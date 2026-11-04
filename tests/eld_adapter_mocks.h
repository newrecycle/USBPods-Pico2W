// SPDX-License-Identifier: GPL-3.0-only
#include "eld_profile.h"
#include "eld_encoder.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define CODEC_ID_AACELD 4
#define ERROR_CODE_SUCCESS 0
#define ERROR_CODE_COMMAND_DISALLOWED 12
#define AVDTP_SI_START 7
#define AVDTP_SI_SUSPEND 9
#define AVDTP_SI_OPEN 6
#define PLOG(...) ((void)0)
typedef struct timer {
 void (*handler)(struct timer*);
 uint32_t deadline;
 bool active;
} btstack_timer_source_t;
typedef struct {
 uint16_t avdtp_cid;uint8_t local_seid,remote_seid;
 uint32_t rtp_timestamp,time_audio_data_sent,acc_num_missed_samples,samples_ready;
 unsigned streaming,codec_storage_count,codec_ready_to_send;
 btstack_timer_source_t audio_timer;
} a2dp_media_sending_context_t;
static a2dp_media_sending_context_t media_tracker;
static eld_transition src_eld_change;
static bool src_eld_setup_pending,src_eld_early_start,src_stream_established,eld_resample,src_relay_rate_low;
static uint16_t src_eld_setup_cid;
static uint32_t src_vbr_mode,current_sample_rate,rtp_samples_per_frame,audio_timer_interval;
static bool src_eld_reset_pending,src_codec_release_pending,is_streaming,a2dp_is_connected_flag;
static bool src_start_accepted_pending;
static bool src_eld_timer_armed,src_user_dc_hold,src_auto_kick_pending,src_prime_pending;
static bool src_session_streamed,src_wedge_hold,finish_scan_avdtp_codec,core1_encoder_active;
static bool suspend_recovery_pending,game,relay;
static uint16_t phone_cid;
static bool bt_sink_relay_owns_cid(uint16_t cid){return cid==phone_cid;}
static unsigned src_resume_tries,src_nostream_run;
static uint32_t src_suspend_ms,src_started_ms,src_dial_window_ms,now,src_full_bitrate;
static uint32_t src_eld_failures,src_eld_rebuilds,src_eld_last_error,src_eld_max_rebuild_us;
static uint8_t src_eld_error_stage,src_pending_jitter,cur_codec;
static uint16_t src_con_handle,aaceld_frame_sequence;
static unsigned acc_num_simples=480,active_slot_count=6;
static eld_phase src_eld_timer_phase;
static btstack_timer_source_t src_eld_change_timer,src_jitter_timer,suspend_recovery_timer;
static eld_profile src_active_eld,src_requested_eld;
static bool src_requested_eld_valid;
static HANDLE_AACENCODER handleAAC;
static AACENC_InfoStruct aacinf;
static unsigned suspends,starts,pumps,disconnects,rebuild_calls,jitters;
static unsigned suspend_rc,start_rc,encode_rc,locks,leds;
static unsigned opens,open_rc;
static uint8_t last_jitter;
static uint32_t built_bitrate;
static struct {uint8_t eld_rate,game_level;} config;
static uint32_t btstack_run_loop_get_time_ms(void){return now;}
static uint32_t time_us_32(void){static uint32_t us;return us+=37;}
static void btstack_run_loop_remove_timer(btstack_timer_source_t *t){t->active=false;}
static void btstack_run_loop_set_timer(btstack_timer_source_t *t,uint32_t ms){t->deadline=now+ms;}
static void btstack_run_loop_add_timer(btstack_timer_source_t *t){t->active=true;}
static void btstack_run_loop_set_timer_handler(btstack_timer_source_t *t,void(*f)(btstack_timer_source_t*)){t->handler=f;}
static uint8_t avdtp_source_suspend(uint16_t cid,uint8_t seid){assert(cid==0x42&&seid==1);suspends++;return suspend_rc;}
static uint8_t avdtp_source_start_stream(uint16_t cid,uint8_t seid){assert(cid==0x42&&seid==1);starts++;return start_rc;}
static uint8_t avdtp_source_open_stream(uint16_t cid,uint8_t seid,uint8_t remote){assert(cid==0x42&&seid==1);(void)remote;opens++;return open_rc;}
static void gap_disconnect(uint16_t h){assert(h==0x123);disconnects++;}
static void a2dp_demo_timer_start(a2dp_media_sending_context_t *c){assert(c==&media_tracker);pumps++;}
static void start_led_blink(void){leds++;}
static void src_sig_disallowed(const char *why){(void)why;}
static void aap_set_jitter_raw(uint8_t ms){jitters++;last_jitter=ms;}
static void *cyw43_arch_async_context(void){return &locks;}
static void async_context_acquire_lock_blocking(void *p){assert(p==&locks);locks++;}
static void async_context_release_lock(void *p){assert(p==&locks&&locks);locks--;}
static void __dmb(void){}
static void audio_slot_queue_configure_with_count(unsigned frames,unsigned slots){assert(frames==480);active_slot_count=slots;}
static eld_profile src_eld_profile(void){return eld_profile_select(config.eld_rate,game,config.game_level,false,relay,5,1);}
static uint32_t src_eld_bitrate(void){return src_eld_profile().bitrate;}
static unsigned src_eld_slot_count(void){return src_eld_profile().slots;}
static unsigned usb_pipeline_rate(void){return 48000;}
static void resamp44_reset(void){}
AACENC_ERROR eld_encoder_open(HANDLE_AACENCODER *h,AACENC_InfoStruct *info,const eld_profile *p) {
 assert(locks && (src_eld_change.phase==ELD_REBUILD || src_eld_change.phase==ELD_WAIT_START) && !is_streaming);
 rebuild_calls++;*h=encode_rc?NULL:(void*)1;memset(info,0,sizeof(*info));
 if(!encode_rc){info->frameLength=480;info->inputChannels=2;built_bitrate=p->bitrate;}
 return encode_rc;
}
typedef struct {void (*release)(void);} codec_ops_t;
static unsigned registry_releases;
static void registry_release(void){registry_releases++;handleAAC=NULL;}
static const codec_ops_t registry_entry={registry_release};
static const codec_ops_t *codec_registry[]={&registry_entry,NULL};
static void src_eld_abort(uint8_t,uint32_t);
static void src_eld_execute(unsigned);
static uint8_t src_start_stream(uint16_t,uint8_t);
static void src_stream_start_accepted(void);
void a2dp_source_apply_eld_rate(void);

static void a2dp_source_transport_report(void) {}

static unsigned src_codec_setup_pending;
static bool src_codec_early_start;
static void src_codec_setup_main(void){}

static bool src_fault_hold;
