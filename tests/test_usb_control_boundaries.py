"""Execute production UAC2 control callbacks against invalid host requests."""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path
from test_source_boundaries import ROOT, function

fixture = r'''
#include <assert.h>
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
#define UAC2_ENTITY_SPK_FEATURE_UNIT 2
#define ITF_NUM_AUDIO_STREAMING_SPK 1
#define ITF_NUM_AUDIO_STREAMING_MIC 2
#define CFG_TUD_AUDIO_FUNC_1_N_CHANNELS_RX 2
#define CFG_TUD_AUDIO_FUNC_1_N_FORMATS 2
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
static bool need_change_bt_volume,usb_pcm_tap,capture;
static uint32_t current_sample_rate=48000,sample_rates[]={48000};
static uint32_t blink_interval_ms=BLINK_MOUNTED;
static int spk_data_size=32;
static uint16_t usb_stop_delay=50;
static uint8_t current_resolution=16;
static const uint8_t resolutions_per_format[]={16,24};
static unsigned flushes,resets,grace_cancels,speaker_stops,xfers;
void aacp_mic_set_capture(bool on){capture=on;}
void usb_pcm_tap_session_reset(void){resets++;}
void audio_slot_request_flush(bool live){assert(live);flushes++;}
void audio_slot_grace_cancel(void){grace_cancels++;}
static void set_usb_streaming(bool on){assert(!on);speaker_stops++;}
static bool tud_audio_buffer_and_schedule_control_xfer(uint8_t rhport,const tusb_control_request_t *r,const void *data,uint16_t size){
 (void)rhport;(void)r;assert(data && size);xfers++;return true;
}
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
 }else if(!strcmp(which,"alternate")){
  usb_capture_mount();usb_capture_set_alt(true);assert(capture);
  r.wIndex=ITF_NUM_AUDIO_STREAMING_SPK;
  for(unsigned alt=3;alt<256;alt++){
   r.wValue=(uint16_t)alt;assert(!tud_audio_set_itf_cb(0,&r));
   assert(!tud_audio_set_itf_close_EP_cb(0,&r));
  }
  r.wValue=256;assert(!tud_audio_set_itf_cb(0,&r));
  assert(!tud_audio_set_itf_close_EP_cb(0,&r));
  r.wIndex=256;r.wValue=0;
  assert(!tud_audio_set_itf_cb(0,&r) && !tud_audio_set_itf_close_EP_cb(0,&r));
  r.wIndex=99;r.wValue=0;
  assert(!tud_audio_set_itf_cb(0,&r) && !tud_audio_set_itf_close_EP_cb(0,&r));
  r.wIndex=ITF_NUM_AUDIO_STREAMING_MIC;r.wValue=2;
  assert(!tud_audio_set_itf_cb(0,&r) && !tud_audio_set_itf_close_EP_cb(0,&r));
  assert(capture && spk_data_size==32 && current_resolution==16);
  assert(!flushes && !resets && !grace_cancels && !speaker_stops);
 }else if(!strcmp(which,"valid")){
  assert(tud_audio_feature_unit_set_request(0,&r,(uint8_t*)&value));
  assert(volume[0]==-256 && need_change_bt_volume);
  assert(tud_audio_feature_unit_get_request(0,&r) && xfers==1);
  for(unsigned c=0;c<3;c++){
   r.bChannelNumber=(uint8_t)c;assert(tud_audio_feature_unit_get_request(0,&r));
  }
  r.wIndex=ITF_NUM_AUDIO_STREAMING_SPK;r.wValue=2;
  assert(tud_audio_set_itf_cb(0,&r) && current_resolution==24 && !spk_data_size);
  usb_capture_mount();usb_capture_set_alt(true);assert(capture);
  r.wValue=0;assert(tud_audio_set_itf_close_EP_cb(0,&r));
  assert(capture && speaker_stops==1); // Speaker close cannot close the mic.
  r.wIndex=ITF_NUM_AUDIO_STREAMING_MIC;
  assert(tud_audio_set_itf_close_EP_cb(0,&r) && !capture);
  assert(speaker_stops==1); // Mic close cannot stop the speaker.
  spk_data_size=32;r.wValue=1;
  assert(tud_audio_set_itf_cb(0,&r) && capture);
  assert(spk_data_size==32 && current_resolution==24 && speaker_stops==1);
  r.wValue=0;assert(tud_audio_set_itf_cb(0,&r) && !capture);
  assert(spk_data_size==32 && current_resolution==24 && speaker_stops==1);
 }else assert(!"unknown case");
 printf("Production UAC2 %s boundaries and state isolation passed\n",which);
}
'''
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--case', choices=('channel', 'clock', 'alternate', 'valid'))
args = parser.parse_args()
names = ('tud_audio_clock_set_request', 'tud_audio_feature_unit_get_request',
         'tud_audio_feature_unit_set_request', 'tud_audio_set_itf_close_EP_cb', 'tud_audio_set_itf_cb')
with tempfile.TemporaryDirectory() as temp:
    out = Path(temp)
    (out/'controls.c').write_text(fixture+'\n'.join(function('src/tinyusb/uac.c', n) for n in names)+tests)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-I', str(ROOT/'src/tinyusb'), str(out/'controls.c'),
                    str(ROOT/'src/tinyusb/usb_capture_lifecycle.c'), '-o', str(out/'test')], check=True)
    cases = [args.case] if args.case else ['channel', 'clock', 'alternate', 'valid']
    for case in cases:
        r = subprocess.run([str(out/'test'), case], capture_output=True, text=True,
                           env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
        if r.returncode:
            print((r.stdout+r.stderr)[-3000:])
            raise SystemExit(r.returncode)
        print(r.stdout.strip())
