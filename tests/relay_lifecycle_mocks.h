
#include <stdatomic.h>
#include "relay_rtp.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#define HCI_EVENT_PACKET 4
#define HCI_EVENT_A2DP_META 0xd1
#define ERROR_CODE_SUCCESS 0
#define A2DP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED 9
#define A2DP_SUBEVENT_SIGNALING_MEDIA_CODEC_SBC_CONFIGURATION 1
#define A2DP_SUBEVENT_SIGNALING_MEDIA_CODEC_MPEG_AAC_CONFIGURATION 2
#define A2DP_SUBEVENT_STREAM_ESTABLISHED 3
#define A2DP_SUBEVENT_STREAM_STARTED 4
#define A2DP_SUBEVENT_STREAM_SUSPENDED 5
#define A2DP_SUBEVENT_STREAM_STOPPED 6
#define A2DP_SUBEVENT_STREAM_RELEASED 7
#define A2DP_SUBEVENT_SIGNALING_CONNECTION_RELEASED 8
#define BD_ADDR_TYPE_ACL 0
#define RELAY_PKT_N 4   /* keep equal to production btstack_sink_relay.c */
#define AVDTP_SINK_FEATURE_MASK_HEADPHONE 1
typedef struct {int con_handle;} hci_connection_t;
typedef uint8_t bd_addr_t[6];
static uint8_t s_codec,s_channels,s_phone_addr[6],s_sdp_buf[160],s_pkt_head,s_pkt_tail,s_pkt[RELAY_PKT_N][1024];
static uint16_t s_rate,s_avdtp_cid,s_con_handle,s_pkt_len[RELAY_PKT_N];
static bool s_connected,s_streaming,s_stream_reset_pending,s_phone_stream_started,s_need_resample,s_sdp_registered=true;
static uint32_t s_connect_ms,s_first_pkt_ms,s_pkts,s_in_bytes,s_dec_us_last,s_dec_us_sum,s_dec_n,s_dec_us_max;
static int s_sbc_dec;
static uint32_t now_ms(void){return 10;}
static uint32_t time_us_32(void){return 10;}
static int hci_event_packet_get_type(uint8_t *p){return p[0];}
static int a2dp_subevent_signaling_media_codec_sbc_configuration_get_num_channels(uint8_t*p){return 2;}
static int a2dp_subevent_signaling_media_codec_sbc_configuration_get_sampling_frequency(uint8_t*p){return 48000;}
static int a2dp_subevent_signaling_media_codec_mpeg_aac_configuration_get_sampling_frequency(uint8_t*p){return 48000;}
static int a2dp_subevent_signaling_media_codec_mpeg_aac_configuration_get_num_channels(uint8_t*p){return 2;}
static int a2dp_subevent_stream_established_get_status(uint8_t*p){return 0;}
static void a2dp_subevent_stream_established_get_bd_addr(uint8_t*p,uint8_t*a){memset(a,1,6);}
static int a2dp_subevent_stream_established_get_a2dp_cid(uint8_t*p){return p[3];}
static hci_connection_t *hci_connection_for_bd_addr_and_type(uint8_t*a,int t){return NULL;}
static void settings_phone_add(uint8_t*a,char*s){}
static char *bd_addr_to_str(uint8_t*a){return "peer";}
int get_current_sample_rate(void){return 48000;}
static void pcm_reset(void){}
static void aac_close(void){}
static void aac_decode(const uint8_t*p,uint16_t n){}
static void btstack_sbc_decoder_process_data(int*s,int mode,const uint8_t*p,uint16_t n){}
static int sdp_create_service_record_handle(void){return 1;}
static void a2dp_sink_create_sdp_record(uint8_t*b,int h,int f,char*s,char*t){}
static int sdp_register_service(uint8_t*b){return 0;}

static _Atomic uint32_t s_epoch;
static uint32_t s_decode_epoch,s_pkt_epoch[RELAY_PKT_N];
static relay_rtp_assembly s_latm;
static void *cyw43_arch_async_context(void){return NULL;}
static void async_context_acquire_lock_blocking(void*p){(void)p;}
static void async_context_release_lock(void*p){(void)p;}
static uint16_t little_endian_read_16(uint8_t*p,int off){return p[off]|(uint16_t)p[off+1]<<8;}
/* Real event layout (pinned BTstack accessors): bd_addr at [5..10] is
   byte-reversed, status at [13]; a signaling-established event is 14 bytes. */
static void reverse_bytes(const uint8_t *src, uint8_t *dst, int len){
    for (int i = 0; i < len; i++) dst[i] = src[len - 1 - i];
}
static void a2dp_subevent_signaling_connection_established_get_bd_addr(uint8_t*p,uint8_t*a){reverse_bytes(&p[5],a,6);}
static int a2dp_subevent_signaling_connection_established_get_status(uint8_t*p){return p[13];}
/* Production attribution excludes the source peer and saved slots; the mock
   proves the decision is consulted by making only s_phone_mac a phone. */
static uint8_t s_phone_mac[6]={2,2,2,2,2,2};
static bool bt_sink_relay_is_phone_addr(uint8_t*a){return !memcmp(a,s_phone_mac,6);}

#define RELAY_PKT_MAX 1024
static uint32_t s_aacerr,s_sbcbad;
