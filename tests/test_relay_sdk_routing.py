"""Reproduce the pinned SDK's competing sink discovery before app filtering.

Executes the production raw-event gate, the SDK connection-event branch and
its actual discovery/timer functions. L2CAP and timer delivery are deterministic.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
from test_source_boundaries import function, ROOT

p=argparse.ArgumentParser();p.add_argument('--sdk-source',type=Path);args=p.parse_args()
directory=args.sdk_source or Path(os.environ['PICO_SDK_PATH'])/'lib/btstack/src/classic'
def read(name):
    path=directory/name
    if not path.exists():path=directory/('sdk-'+name)
    return path.read_text()
sdk=read('a2dp.c')
def extract(name):
    match=re.search(r'^(?:static )?(?:void|uint8_t) '+name+r'\([^;]*?\)\s*\{',sdk,re.M)
    assert match,name
    begin=sdk.index('{',match.start());depth=1;end=begin+1
    while depth:depth+=(sdk[end]=='{')-(sdk[end]=='}');end+=1
    return sdk[match.start():end]
branch=sdk.split('case AVDTP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED:',1)[1].split('case AVDTP_SUBEVENT_SIGNALING_SEP_FOUND:',1)[0]
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define HCI_EVENT_PACKET 4
#define HCI_EVENT_AVDTP_META 0xd1
#define AVDTP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED 1
#define AVDTP_SUBEVENT_SIGNALING_CONNECTION_RELEASED 2
#define A2DP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED 1
#define AVDTP_ROLE_SOURCE 0
#define AVDTP_ROLE_SINK 1
#define ERROR_CODE_SUCCESS 0
#define A2DP_CONNECTED 1
#define A2DP_DISCOVER_SEPS 2
#define AVDTP_MAX_SEP_NUM 10
#define A2DP_SET_CONFIG_DELAY_MS 200
#define btstack_assert assert
#define log_info(...) ((void)0)
typedef uint8_t bd_addr_t[6];
typedef unsigned avdtp_role_t;
typedef struct {unsigned seid;} avdtp_sep_t;
typedef struct {bool outgoing_active,discover_seps,stream_endpoint_configured;unsigned state;} a2dp_config_process_t;
typedef struct {uint16_t avdtp_cid;a2dp_config_process_t a2dp_source_config_process,a2dp_sink_config_process;} avdtp_connection_t;
typedef struct timer {void(*fn)(struct timer*);void *context;unsigned delay;bool active;} btstack_timer_source_t;
static avdtp_connection_t connection;
static uint16_t s_avdtp_cid,a2dp_config_process_sep_discovery_cid;
static unsigned a2dp_config_process_sep_discovery_index,a2dp_config_process_sep_discovery_count;
static avdtp_sep_t a2dp_config_process_sep_discovery_seps[10];
static avdtp_role_t a2dp_config_process_role;
static bool a2dp_config_process_set_config_timer_active;
static btstack_timer_source_t a2dp_config_process_set_config_timer;
static unsigned discovers,emitted,forwarded;
static avdtp_connection_t *avdtp_get_connection_for_avdtp_cid(uint16_t c){return c==connection.avdtp_cid?&connection:NULL;}
static a2dp_config_process_t *a2dp_config_process_for_role(unsigned role,avdtp_connection_t *c){return role?&c->a2dp_sink_config_process:&c->a2dp_source_config_process;}
static void a2dp_config_process_discover_seps_with_next_waiting_connection(void){}
static void avdtp_discover_stream_endpoints(uint16_t c){assert(c==connection.avdtp_cid);discovers++;}
static void *btstack_run_loop_get_timer_context(btstack_timer_source_t *t){return t->context;}
static void btstack_run_loop_set_timer_context(btstack_timer_source_t *t,void *c){t->context=c;}
static void btstack_run_loop_remove_timer(btstack_timer_source_t *t){t->active=false;}
static void btstack_run_loop_add_timer(btstack_timer_source_t *t){t->active=true;}
static void btstack_run_loop_set_timer_handler(btstack_timer_source_t *t,void(*fn)(btstack_timer_source_t*)){t->fn=fn;}
static void btstack_run_loop_set_timer(btstack_timer_source_t *t,unsigned ms){t->delay=ms;}
static uint16_t little_endian_read_16(const uint8_t *p,unsigned n){return p[n]|(uint16_t)p[n+1]<<8;}
static uint16_t avdtp_subevent_signaling_connection_established_get_avdtp_cid(const uint8_t *p){return little_endian_read_16(p,3);}
static uint8_t avdtp_subevent_signaling_connection_established_get_status(const uint8_t *p){return p[13];}
static void avdtp_subevent_signaling_connection_established_get_bd_addr(const uint8_t *p,uint8_t *a){for(unsigned i=0;i<6;i++)a[i]=p[10-i];}
static bool bt_sink_relay_is_phone_addr(const uint8_t *a){return a[0]==2;}
static void a2dp_replace_subevent_id_and_emit_for_role(unsigned r,uint8_t *p,uint16_t n,unsigned e){(void)r;(void)n;(void)e;emitted++;if(!p[13])s_avdtp_cid=little_endian_read_16(p,3);}
static void a2dp_emit_streaming_connection_failed_for_role(unsigned r,avdtp_connection_t *c,uint8_t s){(void)r;(void)c;(void)s;}
'''
wrapper='''
static void a2dp_config_process_avdtp_event_handler(unsigned role,uint8_t *packet,uint16_t size) {
 forwarded++;uint16_t cid;avdtp_connection_t *connection;a2dp_config_process_t *config_process;uint8_t status;
 switch(packet[2]){case AVDTP_SUBEVENT_SIGNALING_CONNECTION_ESTABLISHED:
'''+branch+'''
 default:break;}
}
'''
tests=r'''
static void reset(uint8_t *event,uint8_t peer) {
 memset(&connection,0,sizeof connection);connection.avdtp_cid=0x42;
 memset(&a2dp_config_process_set_config_timer,0,sizeof a2dp_config_process_set_config_timer);
 s_avdtp_cid=a2dp_config_process_sep_discovery_cid=0;discovers=emitted=forwarded=0;
 memset(event,0,14);event[0]=HCI_EVENT_AVDTP_META;event[1]=12;event[2]=1;event[3]=0x42;event[10]=peer;
}
int main(void) {
 uint8_t event[14];reset(event,1);
 // Original routing: app rejects the headset only AFTER this SDK code has
 // scheduled competing discovery. Raw AVDTP source never sets A2DP flags.
 a2dp_config_process_avdtp_event_handler(AVDTP_ROLE_SINK,event,14);
 assert(a2dp_config_process_set_config_timer.active && a2dp_config_process_set_config_timer.delay==200);
 a2dp_config_process_set_config_timer.fn(&a2dp_config_process_set_config_timer);assert(discovers==1);
 reset(event,1);relay_avdtp_handler(HCI_EVENT_PACKET,0,event,14);
 assert(!forwarded && !a2dp_config_process_set_config_timer.active && !discovers);
 // A real phone is still handed to the SDK process; source/headset events
 // and wrong-CID release/discovery cannot alter its state afterward.
 reset(event,2);relay_avdtp_handler(HCI_EVENT_PACKET,0,event,14);
 assert(forwarded==1 && emitted==1 && s_avdtp_cid==0x42);
 event[2]=2;event[3]=0x43;relay_avdtp_handler(HCI_EVENT_PACKET,0,event,14);assert(forwarded==1);
 event[3]=0x42;relay_avdtp_handler(HCI_EVENT_PACKET,0,event,14);assert(forwarded==2);
 reset(event,2);for(unsigned n=0;n<14;n++)relay_avdtp_handler(HCI_EVENT_PACKET,0,event,n);
 assert(!forwarded);
 puts("Pinned SDK competing sink discovery reproduced; production raw-event gate prevents it");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)
    funcs=['a2dp_config_process_timer_handler','a2dp_config_process_timer_start','a2dp_config_process_start_discovering_seps','a2dp_config_process_ready_for_sep_discovery']
    code=fixture+'\n'.join(extract(n) for n in funcs)+wrapper+function('src/btstack/btstack_sink_relay.c','relay_avdtp_handler')+tests
    (path/'test.c').write_text(code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
