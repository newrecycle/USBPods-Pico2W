"""Exercise codec send callbacks at the Bluetooth SDK boundary."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/btstack'
engine = SOURCE / 'btstack_avdtp_source.c'


def definition(path, name):
    source = path.read_text()
    start = re.search(r'^(?:static )?(?:void|int|uint32_t) ' + name + r'\(', source, re.M)
    assert start, name
    return source[start.start():source.index('\n}', start.end()) + 2]


fixture = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define ERROR_CODE_SUCCESS 0
#define LDACBT_ENC_LSU 128
#define LHDC_FRAME_SAMPLES 480
#define SBC_MAX_PACKET_FRAMES 15
#define SBC_PAYLOAD_HDR 1
typedef struct {
    int max_media_payload_size;
    uint16_t avdtp_cid, codec_storage_count;
    uint8_t local_seid, codec_storage[1500], codec_num_frames, codec_ready_to_send;
    uint32_t rtp_timestamp, samples_ready;
} a2dp_media_sending_context_t;
static a2dp_media_sending_context_t media_tracker;
static uint8_t frame_data[4];
static bool audio_slot_pop(uint8_t *slot) { *slot=0; return true; }
static int16_t *audio_slot_data(uint8_t slot) { (void)slot; return NULL; }
static void audio_slot_release(uint8_t slot) { (void)slot; }
static void btstack_sbc_encoder_process_data(int16_t *data) { (void)data; }
static uint8_t *btstack_sbc_encoder_sbc_buffer(void) { return frame_data; }
static uint32_t now_ms, observed_stamp, submissions, src_tx_pkts, src_send_fails;
static uint16_t observed_length;
static uint8_t next_rc, src_send_fail_rc;
static bool src_rtp_clock_started, src_auto_kick_pending, src_eld_tap;
static uint32_t src_rtp_ms_base, src_eld_last_send_ms, src_started_ms, src_ts_snaps;
static uint32_t src_splice_last_ms, src_tx_malformed, src_splice_dump;
static uint16_t src_mal_len, src_mal_nfr, src_mal_walkoff, src_mal_walkn, src_mal_seqctr;
static uint16_t aaceld_frame_sequence, rtp_samples_per_frame = 1024;
static uint8_t src_mal_snap[40];
static uint32_t btstack_run_loop_get_time_ms(void) { return now_ms; }
static int btstack_sbc_encoder_sbc_buffer_length(void) { return 4; }
static int btstack_sbc_encoder_num_audio_frames(void) { return 128; }
static uint8_t a2dp_source_stream_send_media_payload_rtp(uint16_t cid, uint8_t seid,
        uint8_t marker, uint32_t stamp, uint8_t *data, uint16_t length) {
    assert(cid == 42 && seid == 2 && marker == 0 && data == media_tracker.codec_storage);
    observed_stamp = stamp;
    observed_length = length;
    submissions++;
    return next_rc;
}
"""
checks = r"""
static void eld_packet(uint32_t now, uint32_t expected) {
    const uint8_t au[] = {0xb0, 1, 0x10, 1, 0x90};
    memcpy(media_tracker.codec_storage, au, sizeof au);
    media_tracker.codec_num_frames = 1;
    media_tracker.codec_storage_count = sizeof au;
    now_ms = now;
    a2dp_source_eld_send();
    assert(observed_stamp == expected && observed_length == sizeof au);
    assert(!src_tx_malformed && !media_tracker.codec_storage_count);
}
int main(void) {
    media_tracker.avdtp_cid = 42;
    media_tracker.local_seid = 2;
    eld_packet(0, 0);
    eld_packet(20, 20);
    next_rc = 12;
    eld_packet(45, 45);
    assert(src_tx_pkts == 2 && src_send_fails == 1 && src_send_fail_rc == 12);
    src_rtp_clock_started = false;
    next_rc = 0;
    eld_packet(UINT32_MAX - 9, 0);
    eld_packet(11, 21);
    void (*send[])(void) = {a2dp_demo_send_media_packet_sbc, a2dp_demo_send_media_packet_aac,
                            ldac_send, lhdc_send};
    for (unsigned i = 0; i < sizeof send / sizeof send[0]; i++) {
        for (unsigned reject = 0; reject <= 1; reject++) {
            uint32_t previous_count = src_tx_pkts, failures = src_send_fails, calls = submissions;
            uint32_t stamp = media_tracker.rtp_timestamp;
            media_tracker.codec_storage_count = 8;
            media_tracker.codec_num_frames = 2;
            next_rc = reject ? 12 : 0;
            send[i]();
            assert(submissions == calls + 1 && observed_stamp == stamp);
            assert(observed_length == (i == 0 ? 9 : 8));
            assert(src_tx_pkts == previous_count + !reject && src_send_fails == failures + reject);
        }
    }
    const int budgets[] = {656, 22, 4};
    const int expected_frames[] = {15, 5, 0};
    for (unsigned i = 0; i < 3; i++) {
        media_tracker.max_media_payload_size = budgets[i];
        media_tracker.samples_ready = 128 * 32;
        int samples = fill_sbc_audio_buffer(&media_tracker);
        assert(samples == expected_frames[i] * 128);
        assert(media_tracker.codec_ready_to_send == (expected_frames[i] > 0));
        if (media_tracker.codec_ready_to_send) {
            a2dp_demo_send_media_packet_sbc();
            assert(media_tracker.codec_storage[0] == expected_frames[i]);
            assert(observed_length == 1 + 4 * expected_frames[i]);
        }
    }
    uint8_t vendor[] = {0x78,0x56,0x34,0xff};
    assert(get_vendor_id(vendor) == UINT32_C(0xff345678));
}
"""
functions = [definition(engine, name) for name in
             ('a2dp_source_send_payload', 'a2dp_source_eld_send', 'get_vendor_id')]
for codec, name in [('sbc', 'a2dp_demo_send_media_packet_sbc'),
                    ('aac', 'a2dp_demo_send_media_packet_aac'),
                    ('ldac', 'ldac_send'), ('lhdc', 'lhdc_send')]:
    functions.append(definition(SOURCE / 'codec' / f'codec_{codec}.c', name))
functions.append(definition(SOURCE / 'codec/codec_sbc.c', 'fill_sbc_audio_buffer'))
with tempfile.TemporaryDirectory() as directory:
    src = Path(directory) / 'media.c'
    binary = src.with_suffix('')
    src.write_text('\n'.join([fixture, *functions, checks]))
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                    '-fno-sanitize-recover=undefined', str(src), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('All five codecs reported accepted and rejected submissions. ELD timestamps passed start, restart and wrap checks.')
