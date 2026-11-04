"""Production AACP + AVRCP handlers: one host action across both event orders."""
from pathlib import Path
import os
import subprocess
import tempfile
from test_source_boundaries import ROOT,function
fixture=r'''
#define UNUSED(x) ((void)(x))
#define HCI_EVENT_AVRCP_META 0xc0
#define AVRCP_SUBEVENT_PLAY_STATUS_QUERY 1
#define AVRCP_SUBEVENT_OPERATION 2
#define AVRCP_OPERATION_ID_PLAY 0x44
#define AVRCP_OPERATION_ID_PAUSE 0x46
#define AVRCP_OPERATION_ID_STOP 0x45
#define AVRCP_OPERATION_ID_FORWARD 0x4b
#define AVRCP_OPERATION_ID_BACKWARD 0x4c
typedef uint8_t avrcp_operation_id_t;
static struct {uint16_t avrcp_cid,avdtp_cid;uint8_t local_seid,volume;} media_tracker={0x91,0x42,1,100};
static struct {uint32_t song_length_ms,song_position_ms;uint8_t status;} play_info;
static uint32_t src_avrcp_op_ms;
static bool is_muted,_bt_sink_volume_changed;
static uint16_t little_endian_read_16(uint8_t *p,unsigned i){return p[i]|(uint16_t)p[i+1]<<8;}
static uint8_t avrcp_subevent_operation_get_operation_id(uint8_t *p){return p[5];}
static uint8_t avrcp_subevent_operation_get_button_pressed(uint8_t *p){return p[6];}
static const char *avrcp_operation2str(uint8_t p){(void)p;return "fixture";}
static uint8_t avrcp_target_play_status(uint16_t c,uint32_t a,uint32_t b,uint8_t d){(void)c;(void)a;(void)b;(void)d;return 0;}
static uint8_t avrcp_controller_set_absolute_volume(uint16_t c,uint8_t v){(void)c;(void)v;return 0;}
static uint8_t avdtp_source_stop_stream(uint16_t c,uint8_t v){(void)c;(void)v;return 0;}
'''
test=r'''
int main(void) {
 assert(transport_baseline()==0);
 bd_addr_t addr={1,2,3,4,5,6};aap_connect(addr);now+=3000;aacp_mic_poll();
 request_rc=0;send_rc=0;capture=false;event(L2CAP_EVENT_CHANNEL_OPENED,0x42);
 send_now();send_now();send_now();uint8_t ack[]={1,0,4,0,0,0,1,0,2,0,0,0,0,0,0,0,0,0};callback(L2CAP_DATA_PACKET,0x42,ack,sizeof ack);
 config.stem_hid=1;
 uint8_t native[]={HCI_EVENT_AVRCP_META,5,AVRCP_SUBEVENT_OPERATION,0x91,0,AVRCP_OPERATION_ID_PLAY,1};
 unsigned keys=host_keys;
 avrcp_target_packet_handler_inner(HCI_EVENT_PACKET,0,native,sizeof native);assert(host_keys==keys);
 now+=50;uint8_t typed[]={4,0,4,0,0x19,0,6,1};callback(L2CAP_DATA_PACKET,0x42,typed,8);
 assert(host_keys==keys+1 && last_usage==0xb5);
 now+=300;aacp_mic_poll();assert(host_keys==keys+1);
 typed[6]=7;callback(L2CAP_DATA_PACKET,0x42,typed,8);assert(host_keys==keys+2 && last_usage==0xb6);
 now+=50;avrcp_target_packet_handler_inner(HCI_EVENT_PACKET,0,native,sizeof native);
 now+=300;aacp_mic_poll();assert(host_keys==keys+2);
 now+=1000;native[5]=AVRCP_OPERATION_ID_FORWARD;
 avrcp_target_packet_handler_inner(HCI_EVENT_PACKET,0,native,sizeof native);
 now+=250;aacp_mic_poll();assert(host_keys==keys+3 && last_usage==0xb5);
 native[3]=0x43;avrcp_target_packet_handler_inner(HCI_EVENT_PACKET,0,native,sizeof native);
 now+=300;aacp_mic_poll();assert(host_keys==keys+3); // Relay CID cannot drive host keys.
 native[3]=0x91;native[5]=AVRCP_OPERATION_ID_BACKWARD;
 avrcp_target_packet_handler_inner(HCI_EVENT_PACKET,0,native,sizeof native);
 aap_disconnect();now+=300;aacp_mic_poll();assert(host_keys==keys+3); // Old session cancelled.
 puts("Production AACP/AVRCP arbitration: typed precedence, fallback, role filtering and cancellation passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp);baseline=(ROOT/'tests/test_aacp_transport.c').read_text().replace('int main(void){','static int transport_baseline(void){').replace(' assert(locks==0);puts(', ' assert(locks==0);puts(')
 # The baseline's implicit int main return becomes explicit in a normal function.
 end=baseline.rfind('\n}');baseline=baseline[:end]+'\n return 0;'+baseline[end:]
 code=baseline+'\n'+fixture+function('src/btstack/btstack_avdtp_source.c','src_host_media_key')
 code+=function('src/btstack/btstack_avdtp_source.c','avrcp_target_packet_handler_inner')+test
 (p/'wiring.c').write_text(code)
 args=['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'tests/transport_mocks'),'-I',str(ROOT/'src/btstack'),'-I',str(ROOT/'tests'),str(p/'wiring.c')]
 args +=[str(ROOT/'src/btstack'/x) for x in ('aacp_mic.c','aacp_control.c','media_input.c','aacp_mic_protocol.c')]
 args+=['-o',str(p/'wiring')];subprocess.run(args,check=True)
 r=subprocess.run([str(p/'wiring')],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
 print(r.stdout.splitlines()[-1])
