"""Exercise actual UAC1 control handlers and bounded EP0 transfer requests."""
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import ROOT, function

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define TU_VERIFY(x) do{if(!(x))return false;}while(0)
#define TU_U16_HIGH(x) ((uint8_t)((x)>>8))
#define TU_U16_LOW(x) ((uint8_t)(x))
#define tu_le16toh(x) ((uint16_t)(x))
#define UAC1_ITF_AC 0
#define UAC1_ITF_SPK 1
#define UAC1_ENT_SPK_FU 2
#define UAC1_FU_MUTE 1
#define UAC1_FU_VOLUME 2
#define UAC1_EP_SAMPLING_FREQ 1
#define UAC1_SET_CUR 1
#define UAC1_GET_CUR 0x81
#define UAC1_GET_MIN 0x82
#define UAC1_GET_MAX 0x83
#define UAC1_GET_RES 0x84
#define UAC1_VOL_MIN_256DB (-12800)
#define UAC1_VOL_MAX_256DB 0
#define UAC1_VOL_RES_256DB 256
#define CONTROL_STAGE_SETUP 0
#define CONTROL_STAGE_DATA 1
#define CONTROL_STAGE_ACK 2
#define SOF_CONSUMER_AUDIO 1
typedef struct{uint8_t bRequest;uint16_t wIndex,wValue,wLength;} tusb_control_request_t;
static struct{uint8_t alt_spk,ctrl_buf[8];} s_u1;
static struct{uint8_t bEndpointAddress;} s_ep_out_desc={1};
uint32_t sample_rates[]={48000};
int8_t mute[3];int16_t volume[3];bool need_change_bt_volume;
uint16_t usb_stop_delay=50;
static unsigned xfers,last_length,arms,stops;
bool usb_vol_nudge_active(void){return false;}
void audio_slot_grace_cancel(void){}
void audio_slot_request_flush(bool on){(void)on;}
void set_usb_streaming(bool on){assert(!on);stops++;}
void usb_pcm_tap_session_reset(void){}
static bool usbd_edpt_iso_activate(uint8_t port,const void *ep){(void)port;assert(ep==&s_ep_out_desc);return true;}
static void usbd_sof_enable(uint8_t port,unsigned consumer,bool on){(void)port;assert(consumer==1);(void)on;}
static void spk_arm(void){arms++;}
static bool tud_control_status(uint8_t port,const tusb_control_request_t *r){(void)port;(void)r;return true;}
static bool tud_control_xfer(uint8_t port,const tusb_control_request_t *r,void *data,uint16_t size){
 (void)port;(void)r;assert(data==s_u1.ctrl_buf);assert(size<=sizeof s_u1.ctrl_buf);
 xfers++;last_length=size;return true;
}
'''
tests = r'''
int main(void){
 tusb_control_request_t r={.bRequest=UAC1_SET_CUR,.wIndex=UAC1_ENT_SPK_FU<<8,
   .wValue=UAC1_FU_VOLUME<<8,.wLength=65535};
 // Host lengths must be checked before the driver supplies its 8-byte buffer.
 assert(!fu_request(0,&r,CONTROL_STAGE_SETUP) && !xfers);
 const uint16_t invalid[]={0,1,3,8,9,65535};
 for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++){
  r.wLength=invalid[i];assert(!fu_request(0,&r,CONTROL_STAGE_SETUP));
  assert(!fu_request(0,&r,CONTROL_STAGE_DATA));
 }
 r.wLength=2;assert(fu_request(0,&r,CONTROL_STAGE_SETUP) && last_length==2);
 s_u1.ctrl_buf[0]=0;s_u1.ctrl_buf[1]=0xff;
 assert(fu_request(0,&r,CONTROL_STAGE_DATA) && volume[0]==-256 && need_change_bt_volume);
 r.wValue=UAC1_FU_MUTE<<8;r.wLength=1;
 assert(fu_request(0,&r,CONTROL_STAGE_SETUP));s_u1.ctrl_buf[0]=1;
 assert(fu_request(0,&r,CONTROL_STAGE_DATA) && mute[0]==1);
 // All-channels GET_CUR must read back the master value, not the right one.
 volume[0]=-256; volume[1]=-512; volume[2]=-768;
 r.bRequest=UAC1_GET_CUR; r.wValue=(UAC1_FU_VOLUME<<8)|0xFF;
 r.wIndex=(UAC1_ENT_SPK_FU<<8); r.wLength=2;
 assert(fu_request(0,&r,CONTROL_STAGE_SETUP));
 assert((int16_t)(s_u1.ctrl_buf[0]|(s_u1.ctrl_buf[1]<<8))==volume[0]);
 r.bRequest=UAC1_SET_CUR; r.wValue=UAC1_FU_MUTE<<8;
 r.wValue=99<<8;assert(!fu_request(0,&r,CONTROL_STAGE_SETUP));
 r.wValue=UAC1_FU_MUTE<<8;r.wIndex=(UAC1_ENT_SPK_FU<<8)|UAC1_ITF_SPK;
 assert(!fu_request(0,&r,CONTROL_STAGE_SETUP));
 r.wIndex=1;r.wValue=UAC1_EP_SAMPLING_FREQ<<8;r.wLength=65535;
 assert(!ep_request(0,&r,CONTROL_STAGE_SETUP));
 r.wLength=3;assert(ep_request(0,&r,CONTROL_STAGE_SETUP) && last_length==3);
 s_u1.ctrl_buf[0]=0x80;s_u1.ctrl_buf[1]=0xbb;s_u1.ctrl_buf[2]=0;
 assert(ep_request(0,&r,CONTROL_STAGE_DATA));
 s_u1.ctrl_buf[1]=0xfa;assert(!ep_request(0,&r,CONTROL_STAGE_DATA)); // 64 kHz.
 r.wIndex=0x81;assert(!ep_request(0,&r,CONTROL_STAGE_SETUP));
 r.wIndex=UAC1_ITF_SPK;r.wValue=2;
 assert(!set_interface(0,&r) && !arms && !stops);
 r.wValue=256;assert(!set_interface(0,&r) && !arms && !stops);
 r.wIndex=256;r.wValue=0;assert(!set_interface(0,&r));
 r.wIndex=UAC1_ITF_AC;r.wValue=1;assert(!set_interface(0,&r));
 r.wIndex=UAC1_ITF_SPK;r.wValue=1;assert(set_interface(0,&r) && arms==1 && s_u1.alt_spk==1);
 r.wValue=0;assert(set_interface(0,&r) && stops==1 && !s_u1.alt_spk);
 puts("Production UAC1 control lengths, interfaces, endpoint rates and valid requests passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    out = Path(temp)
    source = fixture + '\n'.join(function('src/tinyusb/uac1_device.c', n)
                                  for n in ('set_interface', 'fu_request', 'ep_request')) + tests
    (out/'controls.c').write_text(source)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(out/'controls.c'), '-o', str(out/'test')], check=True)
    r = subprocess.run([str(out/'test')], capture_output=True, text=True,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
    if r.returncode:
        print((r.stdout+r.stderr)[-2000:])
        raise SystemExit(r.returncode)
    print(r.stdout.splitlines()[-1])
