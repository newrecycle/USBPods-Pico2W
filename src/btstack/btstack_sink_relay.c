// SPDX-License-Identifier: GPL-3.0-only
// Reconstructed reference adapter, corrected for current shared source/mic tree.
/*
 * btstack_sink_relay.c — phone -> Pico -> headset A2DP relay (Full only).
 *
 * The Pico registers SBC and AAC-LC SINK stream endpoints next to its SOURCE
 * endpoints.  A phone pairs to it like a speaker; its audio is decoded (SBC by
 * BTstack's decoder, AAC-LC/LATM by FDK), resampled 44.1 -> 48 when the source
 * pipeline runs at 48 k, and mixed into the always-running source stream.
 *
 * Event attribution: BTstack broadcasts connection-level AVDTP events to both
 * roles.  A peer is a HEADSET iff its address is one of our saved slots; every
 * other inbound connection is a phone, and the source handlers consult
 * is_phone_addr()/owns_cid() before acting.
 */
#include <stdatomic.h>
#include "pico/cyw43_arch.h"
#include "pico/async_context.h"
#include "relay_rtp.h"
#include "aacp_mic.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "btstack.h"
#include "classic/a2dp_sink.h"
#include "classic/btstack_sbc.h"
#include "btstack/btstack_sink_relay.h"
#include "btstack/btstack_avdtp_source.h"
#include "btstack/btstack_hci.h"
#include "settings.h"
#include "pico_w_led.h"
#include "pico/time.h"
#include "resamp44.h"

#include "aacdecoder_lib.h"

#define RELAY_PKT_MAX      1024
#define RELAY_PKT_N        4
#define RELAY_PCM_FRAMES   2048
#define RELAY_AAC_MAX      (1152 * 2)

static uint8_t  s_sdp_buf[160];
static bool     s_sdp_registered;

static uint8_t  s_sbc_seid;
static uint8_t  s_aac_seid;
static avdtp_stream_endpoint_t *s_sbc_ep;
static avdtp_stream_endpoint_t *s_aac_ep;

static bd_addr_t s_phone_addr;
static uint16_t  s_avdtp_cid;
static uint16_t  s_con_handle;
static bool      s_connected;
static _Atomic uint32_t s_epoch;
static uint32_t s_decode_epoch;
static relay_rtp_assembly s_latm;
static uint32_t s_pkt_epoch[RELAY_PKT_N];
static bool      s_streaming;
static bool      s_phone_stream_started;
static uint32_t  s_connect_ms;
static uint32_t  s_first_pkt_ms;
static uint8_t   s_codec;          /* 1 SBC, 2 AAC-LC */
static uint16_t  s_rate;           /* phone sample rate */
static uint8_t   s_channels;
static uint8_t   s_vol_pct = 100;
static uint16_t  s_vol_gain = 32768;

static resamp44_t s_rs;
static bool       s_need_resample;
static volatile bool s_stream_reset_pending;

/* IRQ -> main-loop packet queue (RTP packets, as received). */
static uint8_t  s_pkt[RELAY_PKT_N][RELAY_PKT_MAX];
static uint16_t s_pkt_len[RELAY_PKT_N];
static volatile uint8_t s_pkt_head, s_pkt_tail;
static volatile uint32_t s_pkt_drops;

/* Decoded PCM ring (stereo interleaved).  Producer: main loop. Consumer: the
 * source pump's audio_slot_pop() (BTstack/IRQ context). */
static int16_t  s_pcm[RELAY_PCM_FRAMES * 2];
static volatile uint32_t s_pcm_w, s_pcm_r;
static volatile uint32_t s_underruns;

static btstack_sbc_decoder_state_t s_sbc_dec;
static HANDLE_AACDECODER s_aac;
#ifndef USBPODS_MIC_DECODE
static int16_t s_aac_pcm[RELAY_AAC_MAX];
#endif

static uint32_t s_pkts, s_frames, s_dropped, s_aacerr, s_sbcbad;
static uint32_t s_mix_calls, s_mix_frames;
static uint32_t s_dec_us_last, s_dec_us_max, s_dec_us_sum, s_dec_n;
static uint32_t s_in_bytes, s_in_t0;
static bool     s_logged_first_aac;

/* Two FDK decoder heaps cannot coexist on RP2350. The microphone build
 * advertises SBC relay only; the transport/full-relay build also offers AAC. */
static bool relay_aac_supported(void) {
#ifdef USBPODS_MIC_DECODE
 return false;
#else
 return true;
#endif
}

/* ------------------------------------------------------------------ utils */

static uint32_t now_ms(void) { return btstack_run_loop_get_time_ms(); }

static bool mac_empty(const uint8_t *m)
{
    uint8_t a = 0xFF, o = 0;
    for (int i = 0; i < 6; i++) { a &= m[i]; o |= m[i]; }
    return a == 0xFF || o == 0x00;
}

static uint32_t pcm_avail(void)
{
    return s_pcm_w - s_pcm_r;
}

static void pcm_reset(void)
{
    s_pcm_w = s_pcm_r = 0;
    s_need_resample = false;
    resamp44_reset_st(&s_rs);
}

static void pcm_push(const int16_t *frames, uint32_t n)
{
    if (n == 0 || s_decode_epoch != atomic_load(&s_epoch)) return;
    if (pcm_avail() + n > RELAY_PCM_FRAMES) {
        /* The consumer owns s_pcm_r; never advance it from this side.  Drop
         * the incoming frames instead (bounded latency, no torn indices). */
        s_dropped += n;
        return;
    }
    for (uint32_t i = 0; i < n; i++) {
        uint32_t idx = (s_pcm_w + i) % RELAY_PCM_FRAMES;
        s_pcm[idx * 2]     = frames[i * 2];
        s_pcm[idx * 2 + 1] = frames[i * 2 + 1];
    }
    __asm volatile("dmb" ::: "memory");
    s_pcm_w += n;
    s_frames += n;
}

static void pcm_push_resampled(const int16_t *in, uint32_t in_frames)
{
    if (!s_need_resample) {
        pcm_push(in, in_frames);
        return;
    }
    static int16_t out[RELAY_AAC_MAX];
    size_t n = resamp44_process_st(&s_rs, in, in_frames, out, RELAY_AAC_MAX / 2);
    pcm_push(out, (uint32_t)n);
}

/* --------------------------------------------------------------- decoders */

static void sbc_pcm_cb(int16_t *data, int num_samples, int num_channels,
                       int sample_rate, void *context)
{
    (void)context; (void)sample_rate;
    if (num_channels == 1) {
        static int16_t tmp[RELAY_AAC_MAX];
        if (num_samples > RELAY_AAC_MAX / 2) num_samples = RELAY_AAC_MAX / 2;
        for (int i = 0; i < num_samples; i++) {
            tmp[i * 2] = data[i];
            tmp[i * 2 + 1] = data[i];
        }
        pcm_push_resampled(tmp, (uint32_t)num_samples);
    } else {
        pcm_push_resampled(data, (uint32_t)num_samples);
    }
}

#ifndef USBPODS_MIC_DECODE
static bool aac_open(void)
{
    if (s_aac) return true;
    s_aac = aacDecoder_Open(TT_MP4_LATM_MCP1, 1);
    if (!s_aac) {
        printf("[relay] AAC decoder open FAILED (heap?)\n");
        return false;
    }
    s_logged_first_aac = false;
    printf("[relay] AAC decoder open AAC-LC\n");
    return true;
}

static void aac_close(void)
{
    if (s_aac) {
        aacDecoder_Close(s_aac);
        s_aac = NULL;
    }
}

static void aac_decode(const uint8_t *p, uint16_t n)
{
    if (!aac_open()) return;
    if (n < 4) return;

    /* A2DP carries LATM directly, not MPEG4-GENERIC AU headers. */
    const uint8_t *au = p;
    UINT au_len = n;

    if (!s_logged_first_aac) {
        s_logged_first_aac = true;
        printf("[relay] first AAC payload (%u B): ", n);
        for (int i = 0; i < n && i < 16; i++) printf("%02x", p[i]);
        printf("\n");
    }

    UCHAR *in = (UCHAR *)au;
    UINT valid = au_len;
    AAC_DECODER_ERROR err = aacDecoder_Fill(s_aac, &in, &au_len, &valid);
    if (err != AAC_DEC_OK || valid) {
        printf("[relay] AAC fill err 0x%x\n", err);
        s_aacerr++;
        return;
    }
    err = aacDecoder_DecodeFrame(s_aac, s_aac_pcm, RELAY_AAC_MAX, 0);
    if (err != AAC_DEC_OK) {
        if (err != AAC_DEC_NOT_ENOUGH_BITS) {
            printf("[relay] AAC decode err 0x%x\n", err);
            s_aacerr++;
        }
        return;
    }
    CStreamInfo *si = aacDecoder_GetStreamInfo(s_aac);
    if (!si || (si->numChannels!=1 && si->numChannels!=2) ||
        si->sampleRate!=s_rate) { s_aacerr++; return; }
    uint32_t frames = (uint32_t)si->frameSize;
    if (frames == 0 || frames > RELAY_AAC_MAX / 2) return;
    if (si->numChannels == 1) {
        static int16_t tmp[RELAY_AAC_MAX];
        for (uint32_t i = 0; i < frames; i++) {
            tmp[i * 2] = s_aac_pcm[i];
            tmp[i * 2 + 1] = s_aac_pcm[i];
        }
        pcm_push_resampled(tmp, frames);
    } else {
        pcm_push_resampled(s_aac_pcm, frames);
    }
}

#else
static void aac_close(void) {}
static void aac_decode(const uint8_t *p,uint16_t n) {(void)p;(void)n;}
#endif

/* ------------------------------------------------------------ media queue */

static void media_handler(uint8_t seid, uint8_t *packet, uint16_t size)
{
    (void)seid;
    if (!s_phone_stream_started || size == 0 || size > RELAY_PKT_MAX ||
        (seid!=s_sbc_seid && seid!=s_aac_seid)) return;
    uint8_t next = (uint8_t)((s_pkt_head + 1) % RELAY_PKT_N);
    if (next == s_pkt_tail) {
        s_pkt_drops++;
        return;
    }
    memcpy(s_pkt[s_pkt_head], packet, size);
    s_pkt_len[s_pkt_head] = size;
    s_pkt_epoch[s_pkt_head] = atomic_load(&s_epoch);
    __asm volatile("dmb" ::: "memory");
    s_pkt_head = next;
}

/* ---------------------------------------------------------- event handler */

static void packet_handler(uint8_t packet_type, uint16_t channel, uint8_t *packet, uint16_t size)
{
    (void)channel; (void)size;
    if (packet_type != HCI_EVENT_PACKET) return;
    if (hci_event_packet_get_type(packet) != HCI_EVENT_A2DP_META) return;

    if (size<5) return;
    uint16_t event_cid=little_endian_read_16(packet,3);
    if (packet[2]==A2DP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED) {
        bd_addr_t addr;
        a2dp_subevent_signaling_connection_established_get_bd_addr(packet,addr);
        if (a2dp_subevent_signaling_connection_established_get_status(packet)==0 &&
            bt_sink_relay_is_phone_addr(addr) && (!s_avdtp_cid || s_avdtp_cid==event_cid)) {
            s_avdtp_cid=event_cid;memcpy(s_phone_addr,addr,6);
        }
        return;
    }
    if (!s_avdtp_cid || event_cid!=s_avdtp_cid) return;
    switch (packet[2]) {
        case A2DP_SUBEVENT_SIGNALING_MEDIA_CODEC_SBC_CONFIGURATION: {
            uint8_t nch = a2dp_subevent_signaling_media_codec_sbc_configuration_get_num_channels(packet);
            uint32_t rate = a2dp_subevent_signaling_media_codec_sbc_configuration_get_sampling_frequency(packet);
            s_codec = 1;
            s_rate = (uint16_t)rate;
            s_channels = nch;
            printf("[relay] phone SBC config: %lu Hz, %u ch%s\n",
                   (unsigned long)rate, nch,
                   rate == 48000 ? "" : " (resampling to 48k)");
            /* The AVDTP acceptor has already accepted this configuration and
             * moved state; a2dp_sink_set_config_sbc() would return
             * COMMAND_DISALLOWED here.  The event fields are all we need. */
            break;
        }
        case A2DP_SUBEVENT_SIGNALING_MEDIA_CODEC_MPEG_AAC_CONFIGURATION: {
            uint32_t rate = a2dp_subevent_signaling_media_codec_mpeg_aac_configuration_get_sampling_frequency(packet);
            uint8_t  nch  = a2dp_subevent_signaling_media_codec_mpeg_aac_configuration_get_num_channels(packet);
            s_codec = 2;
            s_rate = (uint16_t)rate;
            s_channels = nch;
            printf("[relay] phone AAC-LC config: %lu Hz, %u ch%s\n",
                   (unsigned long)rate, nch,
                   rate == 48000 ? "" : " (resampling to 48k)");
            break;
        }
        case A2DP_SUBEVENT_STREAM_ESTABLISHED: {
            uint8_t status = a2dp_subevent_stream_established_get_status(packet);
            if (status != ERROR_CODE_SUCCESS) {
                printf("[relay] stream establishment FAILED status 0x%02x\n", status);
                break;
            }
            a2dp_subevent_stream_established_get_bd_addr(packet, s_phone_addr);
            s_avdtp_cid = a2dp_subevent_stream_established_get_a2dp_cid(packet);
            s_connected = true;
            s_connect_ms = now_ms();
            s_con_handle = 0;
            {
                hci_connection_t *c = hci_connection_for_bd_addr_and_type(s_phone_addr, BD_ADDR_TYPE_ACL);
                if (c) s_con_handle = c->con_handle;
            }
            settings_phone_add(s_phone_addr, "");
            printf("[relay] phone connected: %s (avdtp_cid 0x%02x)\n",
                   bd_addr_to_str(s_phone_addr), s_avdtp_cid);
            break;
        }
        case A2DP_SUBEVENT_STREAM_STARTED:
            s_streaming = false;
            atomic_fetch_add(&s_epoch,1);
            s_stream_reset_pending = true;
            s_phone_stream_started = true;
            s_first_pkt_ms = 0;
            {
                extern int get_current_sample_rate(void);
                int pipe = get_current_sample_rate();
                s_need_resample = (s_rate == 44100 && pipe != 44100);
            }
            printf("[relay] phone stream STARTED\n");
            break;
        case A2DP_SUBEVENT_STREAM_SUSPENDED:
        case A2DP_SUBEVENT_STREAM_STOPPED:
            s_streaming = false;
            s_phone_stream_started = false;
            s_stream_reset_pending = true;
            atomic_fetch_add(&s_epoch,1);
            s_need_resample = false;
            printf("[relay] phone stream stopped (%s)\n",
                   packet[2] == A2DP_SUBEVENT_STREAM_STOPPED ? "stopped" : "suspended");
            break;
        case A2DP_SUBEVENT_STREAM_RELEASED:
            s_streaming = false;
            s_phone_stream_started = false;
            s_stream_reset_pending = true;
            atomic_fetch_add(&s_epoch,1);
            s_connected = false;
            /* Retain ownership until the signaling channel is released. */
            s_con_handle = 0;
            printf("[relay] phone media channel released\n");
            break;
        case A2DP_SUBEVENT_SIGNALING_CONNECTION_RELEASED:
            s_streaming = false;
            s_phone_stream_started = false;
            s_stream_reset_pending = true;
            atomic_fetch_add(&s_epoch,1);
            s_connected = false;
            s_avdtp_cid = 0;
            s_con_handle = 0;
            printf("[relay] phone disconnected\n");
            break;
        default:
            break;
    }
}

/* ---------------------------------------------------------------- public */

static int create_sbc_endpoint(void)
{
    /* Advertise only rates the pipeline can actually consume.  The mixer has
     * a 44.1 -> 48 resampler, not the reverse, so a 44.1 pipeline must not
     * offer 48 kHz to the phone. */
    static uint8_t caps[4];
    caps[0] = (settings()->usbset & USBSET_RATE44) ? 0x2F : 0x3F;
    caps[1] = 0xFF;
    caps[2] = 2;
    caps[3] = 53;
    static uint8_t cfg[4]  = { 0x21, 0x15, 0x02, 0x35 };
    s_sbc_ep = a2dp_sink_create_stream_endpoint(AVDTP_AUDIO, AVDTP_CODEC_SBC,
                                                caps, sizeof(caps), cfg, sizeof(cfg));
    if (!s_sbc_ep) {
        printf("[relay] sink endpoint creation FAILED (MAX_NR_AVDTP_STREAM_ENDPOINTS?)\n");
        return -1;
    }
    s_sbc_seid = avdtp_local_seid(s_sbc_ep);
    return 0;
}

static int create_aac_endpoint(void)
{
    if (!relay_aac_supported()) return -1;
    uint8_t bitrate = settings()->relay_aac_rate == 1 ? 1 : 2;
    int rate44 = (settings()->usbset & USBSET_RATE44) != 0;
    static uint8_t caps[6];
    static uint8_t cfg[6];
    caps[0] = 0xC0;                 /* MPEG-2/4 AAC-LC */
    caps[1] = 0x01;                 /* 44.1 (+48 when the pump is 48 k) */
    caps[2] = rate44 ? 0x04 : 0x84; /* freq nibble + stereo */
    caps[3] = 0x01;
    caps[4] = bitrate == 1 ? 0x77 : 0xF4;
    caps[5] = 0x00;                 /* 96k / 128k */
    memcpy(cfg, caps, sizeof(cfg));
    s_aac_ep = a2dp_sink_create_stream_endpoint(AVDTP_AUDIO, AVDTP_CODEC_MPEG_2_4_AAC,
                                                caps, sizeof(caps), cfg, sizeof(cfg));
    if (!s_aac_ep) {
        printf("[relay] AAC sink endpoint creation FAILED \n");
        return -1;
    }
    s_aac_seid = avdtp_local_seid(s_aac_ep);
    return 0;
}

void bt_sink_relay_init(void)
{
    a2dp_sink_init();
    a2dp_sink_register_packet_handler(packet_handler);
    a2dp_sink_register_media_handler(media_handler);
    btstack_sbc_decoder_init(&s_sbc_dec, SBC_MODE_STANDARD, sbc_pcm_cb, NULL);

    create_sbc_endpoint();
    memset(s_sdp_buf,0,sizeof(s_sdp_buf));
    a2dp_sink_create_sdp_record(s_sdp_buf,0x10007,AVDTP_SINK_FEATURE_MASK_HEADPHONE,"USBPods Relay","USBPods");
    s_sdp_registered=sdp_register_service(s_sdp_buf)==ERROR_CODE_SUCCESS;
    if (relay_aac_supported() && !(settings()->usbset & USBSET_RELAY_SBC))
        create_aac_endpoint();

    printf("[relay] BT sink relay ready (SBC seid %u; AAC seid %u, 'N' toggles)\n",
           s_sbc_seid, s_aac_seid);
}

bool bt_sink_relay_is_phone_addr(const uint8_t *addr)
{
    if (!addr) return false;
    for (int s = 0; s < 2; s++)
        if (!mac_empty(settings()->slot[s].mac) &&
            memcmp(addr, settings()->slot[s].mac, 6) == 0) return false;
    for (int i = 0; i < SETTINGS_SAVED_N; i++)
        if (!mac_empty(settings()->saved[i].mac) &&
            memcmp(addr, settings()->saved[i].mac, 6) == 0) return false;
    return true;
}

bool bt_sink_relay_owns_cid(uint16_t avdtp_cid)
{
    return s_avdtp_cid && avdtp_cid == s_avdtp_cid;
}

void bt_sink_relay_mix(int16_t *buf, uint16_t stereo_frames)
{
    s_mix_calls++;
    if (!s_streaming || !buf || stereo_frames == 0) return;
    uint32_t avail = pcm_avail();
    if (avail == 0) {
        s_underruns++;
        return;
    }
    uint32_t n = avail < stereo_frames ? avail : stereo_frames;
    uint32_t gain = s_vol_gain;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t idx = (s_pcm_r + i) % RELAY_PCM_FRAMES;
        for (int c = 0; c < 2; c++) {
            int32_t a = buf[i * 2 + c];
            int32_t b = s_pcm[idx * 2 + c];
            b = (b * (int32_t)gain) >> 15;
            int32_t v = a + b;
            if (v > 32767) v = 32767;
            if (v < -32768) v = -32768;
            buf[i * 2 + c] = (int16_t)v;
        }
    }
    s_pcm_r += n;
    s_mix_frames += n;
}

bool bt_sink_relay_connected(void) { return s_connected; }
bool bt_sink_relay_streaming(void) { return s_streaming; }

bool bt_sink_relay_work(void)
{
    /* Short state handoff only; FDK decode/allocation stays outside the lock. */
    async_context_acquire_lock_blocking(cyw43_arch_async_context());
    bool reset=s_stream_reset_pending;
    if(reset) {
        s_stream_reset_pending=false;
        pcm_reset();
        relay_rtp_reset(&s_latm);
        extern int get_current_sample_rate(void);
        s_need_resample=(s_rate==44100 && get_current_sample_rate()!=44100);
        s_streaming=s_phone_stream_started;
    }
    async_context_release_lock(cyw43_arch_async_context());
    if(reset) aac_close();
    if (s_pkt_tail == s_pkt_head) return false;
    uint8_t slot = s_pkt_tail;
    uint16_t len = s_pkt_len[slot];
    /* Copy before releasing the queue slot: IRQ producer never owns this copy. */
    static uint8_t packet[RELAY_PKT_MAX];
    memcpy(packet,s_pkt[slot],len);
    s_decode_epoch=s_pkt_epoch[slot];
    s_pkt_tail = (uint8_t)((s_pkt_tail + 1) % RELAY_PKT_N);
    if (!s_streaming || s_decode_epoch!=atomic_load(&s_epoch)) return true;

    uint32_t t0 = time_us_32();
    const uint8_t *payload;
    uint16_t plen;
    size_t payload_size;
    if (!relay_rtp_payload(packet,len,&payload,&payload_size)) { s_aacerr++; return true; }
    plen=(uint16_t)payload_size;

    s_pkts++;
    s_in_bytes += plen;
    if (!s_first_pkt_ms) s_first_pkt_ms = now_ms();

    if (s_codec == 1) {
        if (plen < 2) return true;
        if ((payload[0]&0xf0) || !(payload[0]&15)) { s_sbcbad++; return true; }
        uint8_t nframes = payload[0];
        const uint8_t *sbc = payload + 1;
        uint16_t slen = (uint16_t)(plen - 1);
        (void)nframes;
        btstack_sbc_decoder_process_data(&s_sbc_dec, 0, sbc, slen);
    } else if (s_codec == 2) {
        int result=relay_rtp_assemble(&s_latm,packet,len);
        if(result>0) aac_decode(s_latm.data,s_latm.length);
        else if(result<0) { s_aacerr++; aac_close(); }
    }

    uint32_t dt = time_us_32() - t0;
    s_dec_us_last = dt;
    s_dec_us_sum += dt;
    s_dec_n++;
    if (dt > s_dec_us_max) s_dec_us_max = dt;
    return true;
}

uint32_t bt_sink_relay_conn_age_ms(void)
{
    if (!s_connected) return UINT32_MAX;
    return now_ms() - s_connect_ms;
}

uint16_t bt_sink_relay_con_handle(void) { return s_con_handle; }

void bt_sink_relay_set_vol_pct(uint8_t pct)
{
    if (pct > 100) pct = 100;
    s_vol_pct = pct;
    s_vol_gain = (uint16_t)(((uint32_t)pct * pct * 32768u + 5000u) / 10000u);
    if (s_vol_gain > 32768) s_vol_gain = 32768;
}

bool bt_sink_relay_dial(const uint8_t *mac)
{
    if (!mac) return false;
    printf("[relay] dialing phone %s\n", bd_addr_to_str((uint8_t *)mac));
    memcpy(s_phone_addr, mac, 6);
    uint16_t cid = 0;
    uint8_t rc = a2dp_sink_establish_stream(s_phone_addr, &cid);
    if (rc != ERROR_CODE_SUCCESS) {
        printf("[relay] dial FAILED (rc=0x%02x)\n", rc);
        return false;
    }
    s_avdtp_cid = cid;
    return true;
}

void bt_sink_relay_disconnect(void)
{
    if (s_avdtp_cid) a2dp_sink_disconnect(s_avdtp_cid);
    s_streaming = false;
    s_phone_stream_started = false;
    s_stream_reset_pending = true;
    atomic_fetch_add(&s_epoch,1);
    s_connected = false;
    s_avdtp_cid = 0;
    s_con_handle = 0;
}

void bt_sink_relay_dump(void)
{
    uint32_t avg = s_dec_n ? s_dec_us_sum / s_dec_n : 0;
    printf("[relay] phone=%s cid=0x%02x codec=%s streaming=%d flowing=%d rate=%lu\n",
           s_connected ? bd_addr_to_str(s_phone_addr) : "none",
           s_avdtp_cid,
           s_codec == 1 ? "SBC" : s_codec == 2 ? "AAC-LC" : "none",
           s_streaming, s_streaming && pcm_avail() > 0,
           (unsigned long)s_rate);
    printf("[relay] pkts %lu frames %lu pcm %lu drops %lu underruns %lu sbcbad %d aacerr %lu rpktdrop %lu ring %lu/%u frames\n",
           (unsigned long)s_pkts, (unsigned long)s_frames,
           (unsigned long)(s_pcm_w - s_pcm_r), (unsigned long)s_dropped,
           (unsigned long)s_underruns, 0, (unsigned long)s_aacerr,
           (unsigned long)s_pkt_drops,
           (unsigned long)pcm_avail(), RELAY_PCM_FRAMES);
    printf("[relay] dec_us last %lu max %lu avg %lu (n=%lu)\n",
           (unsigned long)s_dec_us_last, (unsigned long)s_dec_us_max,
           (unsigned long)avg, (unsigned long)s_dec_n);
    printf("[relay] mix_calls %lu mix_frames %lu (mix dead = source pump not popping slots)\n",
           (unsigned long)s_mix_calls, (unsigned long)s_mix_frames);
}

void bt_sink_relay_toggle_aac(void)
{
    if (s_avdtp_cid) {
        printf("[relay] disconnect the phone first, then toggle\n");
        return;
    }
    if (!relay_aac_supported()) { printf("[relay] AAC relay unavailable in microphone-decoder builds\n"); return; }
    if (!s_aac_ep) {
        if (create_aac_endpoint() == 0) {
            printf("[relay] AAC sink SEP ON (seid %u)\n", s_aac_seid);
            settings()->usbset &= (uint8_t)~USBSET_RELAY_SBC;
            settings_mark_dirty();
        }
    } else {
        a2dp_sink_finalize_stream_endpoint(s_aac_ep);
        s_aac_ep = NULL;
        s_aac_seid = 0;
        printf("[relay] AAC sink SEP OFF \n");
    }
}

void bt_sink_relay_sync_codec_pref(void)
{
    if (relay_aac_supported() && !(settings()->usbset & USBSET_RELAY_SBC)) {
        if (!s_aac_ep) create_aac_endpoint();
    } else if (s_aac_ep && !s_connected) {
        a2dp_sink_finalize_stream_endpoint(s_aac_ep);
        s_aac_ep = NULL;
        s_aac_seid = 0;
    }
}

void bt_sink_relay_refresh_aac_caps(void)
{
    if (s_avdtp_cid) {
        printf("[relay] relay AAC cap takes effect at the next phone connection\n");
        return;
    }
    if (s_aac_ep) {
        a2dp_sink_finalize_stream_endpoint(s_aac_ep);
        s_aac_ep = NULL;
        s_aac_seid = 0;
        create_aac_endpoint();
    }
}
