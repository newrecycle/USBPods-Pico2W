"""Execute production status serializer and check fresh-control evidence fields."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import ROOT,function
fixture=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "aacp_control.h"
static aacp_control_diagnostics aap_control_diagnostics_fixture(void) {
 return (aacp_control_diagnostics){.transmitted=0xffffffffu,.last_id=0x28,.last_value=2,.observed={1,2,3,4,0xffffffffu}};
}
#define aap_control_diagnostics aap_control_diagnostics_fixture
static void aap_get_battery(uint8_t *b){b[0]=50;b[1]=60;b[2]=70;}
static const uint8_t *a2dp_source_peer_addr(void){static const uint8_t p[6]={1};return p;}
static const char *bd_addr_to_str(uint8_t *p){(void)p;return "01:00:00:00:00:00";}
#define aap_channel_open() 1
#define aap_protocol_seen() 1
#define get_a2dp_connected_flag() 1
#define check_is_streaming() 1
#define a2dp_source_tx_packets() 100
#define a2dp_source_send_failures() 0
#define get_cur_codec() 4
#define aap_get_noise_mode() 2
#define aap_get_pvol() 1
#define aap_get_ca() 0
#define aap_get_aa() 50
#define aacp_mic_capture() 1
#define aacp_mic_audio_ready() 1
#define bt_sink_relay_connected() 0
#define bt_sink_relay_streaming() 0
#define a2dp_source_fault_hold() 0
'''
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp);(p/'status.c').write_text(fixture+function('src/device_control.c','status')+'\nint main(void){status();}\n')
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'src/btstack'),str(p/'status.c'),'-o',str(p/'status')],check=True)
 r=subprocess.run([str(p/'status')],check=True,capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
 d=json.loads(r.stdout.strip().removeprefix('[control] '))
 assert d['control_tx']==0xffffffff and d['control_rx_seq']==[1,2,3,4,0xffffffff]
 assert d['control_last_id']==0x28 and d['control_last_value']==2
 assert d['connected'] and d['capture'] and d['codec']==4
 print('Production status serializer: wire submission and per-control freshness passed')
