"""Execute production UAC2 control callbacks against invalid host requests."""
import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path
from test_source_boundaries import ROOT, function

config = (ROOT / 'tusb_config.h').read_text()
formats = int(re.search(r'#define\s+CFG_TUD_AUDIO_FUNC_1_N_FORMATS\s+(\d+)',
                        config).group(1))
assert formats == 1, formats
assert re.search(r'#define\s+CFG_TUD_AUDIO_FUNC_1_FORMAT_1_RESOLUTION_RX\s+16\b', config)
descriptor = (ROOT / 'src/tinyusb/usb_descriptors.h').read_text()
assert re.findall(r'TUD_AUDIO_DESC_STD_AS_INT\(ITF_NUM_AUDIO_STREAMING_SPK,\s*(0x0[01])',
                  descriptor) == ['0x00', '0x01']
assert re.findall(r'TUD_AUDIO_DESC_STD_AS_INT\(ITF_NUM_AUDIO_STREAMING_MIC,\s*(0x0[01]|\d)',
                  descriptor) == ['0', '1']
speaker_clock = re.search(
    r'TUD_AUDIO_DESC_CLK_SRC\(/\*_clkid\*/\s*UAC2_ENTITY_CLOCK,\s*'
    r'/\*_attr\*/\s*\d+,\s*/\*_ctrl\*/\s*([A-Z0-9_]+)', descriptor)
assert speaker_clock and speaker_clock.group(1) == 'AUDIO_CTRL_RW', speaker_clock
mic_clock = re.search(r'TUD_AUDIO_DESC_CLK_SRC\(\s*UAC2_ENTITY_MIC_CLOCK,\s*'
                      r'\d+,\s*(\d+)', descriptor)
assert mic_clock and mic_clock.group(1) == '1', mic_clock

fixture = r'''
#include <assert.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "usb_capture_lifecycle.h"
#define TU_VERIFY(x) do{if(!(x))return false;}while(0)
#define TU_ASSERT(x) TU_VERIFY(x)
#define TU_LOG1(...) ((void)0)
#define TU_LOG2(...) ((void)0)
#define tu_htole16(x) ((uint16_t)(x))
#define tu_le16toh(x) ((uint16_t)(x))
#define tu_le32toh(x) ((uint32_t)(x))
#define tu_u16_low(x) ((uint8_t)(x))
#define AUDIO_CS_REQ_CUR 1
#define AUDIO_CS_REQ_RANGE 2
#define AUDIO_FU_CTRL_MUTE 1
#define AUDIO_FU_CTRL_VOLUME 2
#define AUDIO_CS_CTRL_SAM_FREQ 1
#define UAC2_ENTITY_CLOCK 4
#define UAC2_ENTITY_MIC_CLOCK 0x14
#define UAC2_ENTITY_SPK_FEATURE_UNIT 2
#define ITF_NUM_AUDIO_STREAMING_SPK 1
#define ITF_NUM_AUDIO_STREAMING_MIC 2
#define CFG_TUD_AUDIO_FUNC_1_N_CHANNELS_RX 2
#define CFG_TUD_AUDIO_FUNC_1_N_FORMATS 1
#define N_SAMPLE_RATES 1
#define VOLUME_CTRL_50_DB 12800
#define VOLUME_CTRL_0_DB 0
#define BLINK_MOUNTED 1
#define BLINK_STREAMING 2
typedef struct {
 uint8_t bEntityID,bRequest,bControlSelector,bChannelNumber;
 uint16_t wLength,wIndex,wValue;
} audio_control_request_t;
typedef audio_control_request_t tusb_control_request_t;
typedef struct{int8_t bCur;} audio_control_cur_1_t;
typedef struct{int16_t bCur;} audio_control_cur_2_t;
typedef struct{int32_t bCur;} audio_control_cur_4_t;
#define audio_control_range_2_n_t(n) struct{uint16_t wNumSubRanges;struct{int16_t bMin,bMax,bRes;} subrange[n];}
static int8_t mute[3];
static int16_t volume[3];
static bool usb_pcm_tap,capture;
static _Atomic bool need_change_bt_volume;
static int16_t volume0_last;
static int8_t mute0_last;
static uint32_t current_sample_rate=48000,sample_rates[]={48000};
static uint32_t blink_interval_ms=BLINK_MOUNTED;
static int spk_data_size=32;
static uint16_t usb_stop_delay=50;
static uint8_t current_resolution=16;
static const uint8_t resolutions_per_format[]={16};
static unsigned flushes,resets,grace_cancels,speaker_stops,xfers;
static unsigned capture_calls,capture_false_calls,capture_generation;
void aacp_mic_set_capture(bool on){
 if(capture!=on)capture_generation++;
 capture=on;capture_calls++;if(!on)capture_false_calls++;
}
void usb_pcm_tap_session_reset(void){resets++;}
void audio_slot_request_flush(bool live){assert(live);flushes++;}
void audio_slot_grace_cancel(void){grace_cancels++;}
static void set_usb_streaming(bool on){assert(!on);speaker_stops++;}
static bool inject_set_cur;static int16_t bt_volume_arg;
static void set_bt_volume(int16_t v){
 bt_volume_arg=v;
 if(inject_set_cur){inject_set_cur=false;need_change_bt_volume=true;volume[0]=-512;}
}
static uint8_t host_fu_to_pct(int16_t db){return db==0?100:50;}
static bool tud_audio_buffer_and_schedule_control_xfer(uint8_t rhport,const tusb_control_request_t *r,const void *data,uint16_t size){
 (void)rhport;(void)r;assert(data && size);xfers++;return true;
}
/* async-context lock helpers; here they only need to exist and succeed so the
   extracted apply_host_fu_volume() links. */
static bool bt_async_lock_take(void){return true;}
static void bt_async_lock_give(void){}
'''
tests = r'''
int main(int argc,char **argv){
 assert(argc==2);const char *which=argv[1];
 audio_control_request_t r={.bEntityID=UAC2_ENTITY_SPK_FEATURE_UNIT,.bRequest=AUDIO_CS_REQ_CUR,
   .bControlSelector=AUDIO_FU_CTRL_VOLUME,.wLength=2};
 audio_control_cur_2_t value={-256};
 if(!strcmp(which,"channel")){
  for(unsigned c=3;c<256;c++){
   r.bChannelNumber=(uint8_t)c;
   assert(!tud_audio_feature_unit_set_request(0,&r,(uint8_t*)&value));
   assert(!tud_audio_feature_unit_get_request(0,&r));
   r.bControlSelector=AUDIO_FU_CTRL_MUTE;r.wLength=1;
   assert(!tud_audio_feature_unit_set_request(0,&r,(uint8_t*)&value));
   assert(!tud_audio_feature_unit_get_request(0,&r));
   r.bControlSelector=AUDIO_FU_CTRL_VOLUME;r.wLength=2;
  }
  assert(!need_change_bt_volume && !xfers);
 }else if(!strcmp(which,"clock")){
  r.bEntityID=UAC2_ENTITY_CLOCK;r.bControlSelector=AUDIO_CS_CTRL_SAM_FREQ;r.wLength=4;
  const uint32_t invalid[]={0,1,44100,64000,96000,0xffffffffu};
  for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++){
   audio_control_cur_4_t rate={(int32_t)invalid[i]};
   assert(!tud_audio_clock_set_request(0,&r,(uint8_t*)&rate));assert(current_sample_rate==48000);
  }
  audio_control_cur_4_t rate={48000};assert(tud_audio_clock_set_request(0,&r,(uint8_t*)&rate));
  sample_rates[0]=44100;rate.bCur=44100;
  assert(tud_audio_clock_set_request(0,&r,(uint8_t*)&rate) && current_sample_rate==44100);
  // The mic clock is read-only in the descriptor and rejected by the handler.
  r.bEntityID=UAC2_ENTITY_MIC_CLOCK;rate.bCur=64000;
  assert(!tud_audio_clock_set_request(0,&r,(uint8_t*)&rate));
  assert(current_sample_rate==44100);
  // AUDIO_CTRL_RW speaker clock (checked against the descriptor in Python)
  // means SET_CUR is advertised for exactly this handler's supported rates.
 }else if(!strcmp(which,"alternate")){
  usb_capture_mount();usb_capture_set_alt(true);assert(capture);
  r.wIndex=ITF_NUM_AUDIO_STREAMING_SPK;
  for(unsigned alt=2;alt<256;alt++){
   r.wValue=(uint16_t)alt;assert(!tud_audio_set_itf_cb(0,&r));
   assert(!tud_audio_set_itf_close_EP_cb(0,&r));
   assert(spk_data_size==32 && current_resolution==16);
  }
  r.wValue=256;assert(!tud_audio_set_itf_cb(0,&r));
  assert(!tud_audio_set_itf_close_EP_cb(0,&r));
  r.wIndex=256;r.wValue=0;
  assert(!tud_audio_set_itf_cb(0,&r) && !tud_audio_set_itf_close_EP_cb(0,&r));
  r.wIndex=99;r.wValue=0;
  assert(!tud_audio_set_itf_cb(0,&r) && !tud_audio_set_itf_close_EP_cb(0,&r));
  unsigned gen=capture_generation,false_calls=capture_false_calls;
  r.wIndex=ITF_NUM_AUDIO_STREAMING_MIC;r.wValue=2;
  assert(!tud_audio_set_itf_cb(0,&r) && !tud_audio_set_itf_close_EP_cb(0,&r));
  assert(capture && capture_generation==gen && capture_false_calls==false_calls);
  assert(spk_data_size==32 && current_resolution==16);
  assert(!flushes && !resets && !grace_cancels && !speaker_stops);
 }else if(!strcmp(which,"valid")){
  assert(tud_audio_feature_unit_set_request(0,&r,(uint8_t*)&value));
  assert(volume[0]==-256 && need_change_bt_volume);
  assert(tud_audio_feature_unit_get_request(0,&r) && xfers==1);
  for(unsigned c=0;c<3;c++){
   r.bChannelNumber=(uint8_t)c;assert(tud_audio_feature_unit_get_request(0,&r));
  }
  r.wIndex=ITF_NUM_AUDIO_STREAMING_SPK;r.wValue=1;
  assert(tud_audio_set_itf_cb(0,&r) && current_resolution==16 && !spk_data_size);
  usb_capture_mount();usb_capture_set_alt(true);assert(capture);
  r.wValue=0;assert(tud_audio_set_itf_close_EP_cb(0,&r));
  assert(capture && speaker_stops==1); // Speaker close cannot close the mic.
  r.wIndex=ITF_NUM_AUDIO_STREAMING_MIC;
  assert(tud_audio_set_itf_close_EP_cb(0,&r) && !capture);
  assert(speaker_stops==1); // Mic close cannot stop the speaker.
  spk_data_size=32;r.wValue=1;
  assert(tud_audio_set_itf_cb(0,&r) && capture);
  assert(spk_data_size==32 && current_resolution==16 && speaker_stops==1);
  // TinyUSB calls close_EP(alt=1) before a redundant SET_INTERFACE alt 1.
  // Capture must stay published on (no AACP generation bump, no PCM flush).
  unsigned const gen=capture_generation,false_calls=capture_false_calls;
  r.wValue=1;
  assert(tud_audio_set_itf_close_EP_cb(0,&r) && capture);
  assert(tud_audio_set_itf_cb(0,&r) && capture);
  assert(capture_generation==gen && capture_false_calls==false_calls);
  // Positive close path: alt 1 -> alt 0 still clears the capture intent.
  r.wValue=0;assert(tud_audio_set_itf_close_EP_cb(0,&r) && !capture);
  assert(capture_generation==gen+1 && capture_false_calls==false_calls+1);
  assert(spk_data_size==32 && current_resolution==16 && speaker_stops==1);
 }else if(!strcmp(which,"volume_apply")){
  volume[0]=-256;mute[0]=0;volume0_last=0;mute0_last=0;
  need_change_bt_volume=true;inject_set_cur=true;
  assert(apply_host_fu_volume());
  // set_bt_volume() simulated a SET_CUR landing during the apply: the flag
  // must still be set and the newer volume[0] must be applied next pass.
  assert(need_change_bt_volume && volume[0]==-512);
  assert(volume0_last==-256);
  assert(apply_host_fu_volume());
  assert(!need_change_bt_volume && volume0_last==-512);
  assert(bt_volume_arg==-50+50/2);
 }else assert(!"unknown case");
 printf("Production UAC2 %s boundaries and state isolation passed\n",which);
}
'''
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--case', choices=('channel', 'clock', 'alternate', 'valid',
                                      'volume_apply'))
args = parser.parse_args()
names = ('tud_audio_clock_set_request', 'tud_audio_feature_unit_get_request',
         'tud_audio_feature_unit_set_request', 'tud_audio_set_itf_close_EP_cb',
         'tud_audio_set_itf_cb', 'apply_host_fu_volume')
with tempfile.TemporaryDirectory() as temp:
    out = Path(temp)
    (out/'controls.c').write_text(fixture+'\n'.join(function('src/tinyusb/uac.c', n) for n in names)+tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-I', str(ROOT/'src/tinyusb'), str(out/'controls.c'),
                    str(ROOT/'src/tinyusb/usb_capture_lifecycle.c'), '-o', str(out/'test')], check=True)
    cases = [args.case] if args.case else ['channel', 'clock', 'alternate', 'valid',
                                           'volume_apply']
    for case in cases:
        r = subprocess.run([str(out/'test'), case], capture_output=True, text=True,
                           env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
        if r.returncode:
            print((r.stdout+r.stderr)[-3000:])
            raise SystemExit(r.returncode)
        print(r.stdout.strip())
