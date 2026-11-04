// SPDX-License-Identifier: GPL-3.0-only
#include "eld_encoder.h"
#include "resamp44.h"
#include <aacdecoder_lib.h>
#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define CODEC_ID_AACELD 4
#define AUDIO_SLOT_MAX_SAMPLES 480
#define SRC_FADE_FRAMES 240
#define SRC_ELD_PEAK_BITRATE 256000u
#define btstack_assert assert
typedef struct {uint8_t data[9],read,write,count;} queue_t;
static bool queue_try_remove(queue_t *q,uint8_t *v){if(!q->count)return false;*v=q->data[q->read++%9];q->read%=9;q->count--;return true;}
static bool queue_try_add(queue_t *q,const uint8_t *v){if(q->count==9)return false;q->data[q->write++%9]=*v;q->write%=9;q->count++;return true;}
static unsigned queue_get_level(queue_t *q){return q->count;}
static struct {int16_t data[960];} slot_pool[9];
static queue_t free_queue,ready_queue;
static bool slot_pool_frozen,filling_slot_valid,is_streaming,is_usb_streaming;
static bool src_prime_pending,src_fade_in_pending,src_fade_out_pending,src_eld_reset_pending,eld_resample;
static uint8_t filling_slot_idx,cur_codec=4;
static uint16_t filling_offset,slot_frame_int16=960,usb_sw_gain_q15=32768,aaceld_frame_sequence;
static uint32_t usb_slot_push_drops,usb_slot_ready_full_drops,slot_real_waits;
static uint32_t src_encode_last_us,src_encode_max_us;
static uint32_t time_us_32(void){static uint32_t ticks;return ++ticks;}
static int16_t src_tail[480],eld_rs_buf[960];
static unsigned acc_num_simples=480;
static HANDLE_AACENCODER handleAAC;
static AACENC_InfoStruct aacinf;
static eld_transition src_eld_change={.phase=ELD_READY};
static eld_profile profile;
static uint32_t src_eld_bitrate(void){return profile.bitrate;}
static uint8_t src_eld_vbr_now(void){return profile.vbr;}
static bool bt_sink_relay_streaming(void){return false;}
static void bt_sink_relay_mix(int16_t *pcm,unsigned frames){(void)pcm;(void)frames;}
static bool aap_get_game(void){return false;}
static struct {uint32_t scratch[8];} hw;
#define watchdog_hw (&hw)
typedef struct {
 uint32_t samples_ready;int max_media_payload_size;
 uint8_t codec_storage[1500];uint16_t codec_storage_count,codec_num_frames;
} a2dp_media_sending_context_t;
