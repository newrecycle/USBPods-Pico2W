"""Production endpoint adoption, deferred allocator owner and peer constraints."""
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import ROOT,function

fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "eld_profile.h"
#define CODEC_ID_NONE 0
#define CODEC_ID_SBC 1
#define CODEC_ID_AAC 2
#define CODEC_ID_LDAC 3
#define CODEC_ID_LHDC 5
#define AVDTP_SOURCE 0
#define ERROR_CODE_MEMORY_CAPACITY_EXCEEDED 7
#define HCI_LINK_TYPE_ACL_CONNECTION 1
typedef uint8_t bd_addr_t[6];
typedef unsigned hci_link_type_t;
typedef struct {uint16_t avdtp_cid;} connection_t;
typedef struct {struct {unsigned type;}sep;connection_t *connection;} avdtp_stream_endpoint_t;
static connection_t connection={0x42};
static avdtp_stream_endpoint_t endpoint={{AVDTP_SOURCE},&connection};
static struct {uint16_t avdtp_cid;uint8_t local_seid,remote_seid;} media_tracker={0x42,1,7};
static struct {avdtp_stream_endpoint_t *local_stream_endpoint;}sc;
static bool src_codec_configured,is_streaming,a2dp_is_connected_flag,src_codec_early_start;
static bool src_stream_established,src_codec_release_pending,src_user_dc_hold,src_fault_hold;
static uint8_t src_codec_setup_pending,cur_codec,src_codec_setup_packet[100];
static uint16_t src_codec_setup_cid,src_con_handle=0x123;
static unsigned locks,allocs,releases,starts,opens,pumps,disconnects;
static bool fail;
static uint32_t ceiling=320000;
static bool vbr=true,game;
static uint8_t src_eld_vbr_mode=5,src_eld_sbr=1;
static struct {uint8_t eld_rate,game_level;} config={3,1};
static uint32_t codec_aaceld_max_bitrate(void){return ceiling;}
static bool codec_aaceld_vbr_allowed(void){return vbr;}
static unsigned usb_pipeline_rate(void){return 48000;}
static bool bt_sink_relay_streaming(void){return false;}
static bool aap_get_game(void){return game;}
#define settings() (&config)
static void *cyw43_arch_async_context(void){return &locks;}
static void async_context_acquire_lock_blocking(void *p){assert(p==&locks && !locks);locks++;}
static void async_context_release_lock(void *p){assert(p==&locks && locks==1);locks--;}
static uint16_t little_endian_read_16(const uint8_t *p,unsigned n){return p[n]|(uint16_t)p[n+1]<<8;}
static avdtp_stream_endpoint_t *avdtp_get_stream_endpoint_for_seid(uint8_t seid){return seid==2?&endpoint:NULL;}
static bool bt_sink_relay_owns_cid(uint16_t cid){return cid==0x43;}
static void a2dp_demo_timer_stop(void *p){assert(p==&media_tracker);}
static void src_eld_link_reset(void){}
static void release(void){assert(locks && !is_streaming);releases++;}
static struct {void(*release)(void);} entry={release};
static const typeof(entry) *codec_registry[]={&entry,NULL};
static void build(unsigned id,const uint8_t *p){assert(locks==1 && !is_streaming && p[10]==99);allocs++;if(!fail)cur_codec=id;}
static void codec_sbc_on_configuration(const uint8_t *p){build(1,p);}
static void codec_aac_on_configuration(const uint8_t *p){build(2,p);}
static void codec_ldac_on_configuration(const uint8_t *p){build(3,p);}
static void codec_lhdc_on_configuration(const uint8_t *p){build(5,p);}
static void codec_aac_on_media_open(void){}
static void codec_ldac_on_media_open(void){}
static void src_stream_start_accepted(void){assert(locks==1 && cur_codec);is_streaming=true;pumps++;}
static uint8_t src_start_stream(uint16_t cid,uint8_t seid){assert(locks==1 && cid==0x42 && seid==2);starts++;return 0;}
static uint8_t avdtp_source_open_stream(uint16_t cid,uint8_t seid,uint8_t remote){assert(locks==1 && cid==0x42 && seid==2 && remote==7);opens++;return 0;}
static void gap_disconnect(uint16_t handle){assert(handle==0x123);disconnects++;}
static bool a2dp_source_fault_hold(void){return src_fault_hold;}
static bool bt_sink_relay_is_phone_addr(const uint8_t *addr){return addr[0]==2;}
'''
tests=r'''
int main(void) {
 uint8_t packet[101]={0};packet[3]=0x42;packet[5]=2;packet[6]=7;packet[10]=99;
 unsigned codecs[]={1,2,3,5};a2dp_is_connected_flag=true;
 for(unsigned i=0;i<4;i++) {
  src_stream_established=false;is_streaming=true;
  unsigned before=allocs,old_opens=opens;
  src_schedule_codec_setup(codecs[i],packet,14);
  assert(allocs==before && !is_streaming && media_tracker.local_seid==2 && sc.local_stream_endpoint==&endpoint);
  packet[10]=12;src_codec_setup_main();packet[10]=99;
  assert(allocs==before+1 && opens==old_opens+1 && !src_codec_setup_pending && cur_codec==codecs[i]);
 }
 // Early MEDIA/START is preserved, but never starts a pump before allocation.
 src_schedule_codec_setup(2,packet,14);src_stream_established=true;src_codec_early_start=true;
 unsigned old=pumps;src_codec_setup_main();assert(pumps==old+1 && is_streaming);
 src_schedule_codec_setup(3,packet,14);src_stream_established=true;old=starts;
 src_codec_setup_main();assert(starts==old+1);
 // Stale CID, sink endpoint, unknown SEID and oversized records cannot build.
 packet[3]=0x43;src_schedule_codec_setup(2,packet,14);assert(!src_codec_setup_pending);packet[3]=0x42;
 endpoint.sep.type=1;src_schedule_codec_setup(2,packet,14);assert(!src_codec_setup_pending);endpoint.sep.type=0;
 packet[5]=9;src_schedule_codec_setup(2,packet,14);assert(!src_codec_setup_pending);packet[5]=2;
 src_schedule_codec_setup(2,packet,101);assert(!src_codec_setup_pending);
 src_schedule_codec_setup(2,packet,14);old=allocs;media_tracker.avdtp_cid=0x55;
 src_codec_setup_main();assert(allocs==old);media_tracker.avdtp_cid=0x42;
 src_schedule_codec_setup(2,packet,14);fail=true;old=starts;src_codec_setup_main();
 assert(disconnects==1 && starts==old && src_fault_hold && src_user_dc_hold && !is_streaming);
 // Fatal setup hold blocks automatic headset ACLs but still permits phones.
 bd_addr_t headset={1},phone={2};
 assert(!classic_accept(headset,HCI_LINK_TYPE_ACL_CONNECTION));
 assert(classic_accept(phone,HCI_LINK_TYPE_ACL_CONNECTION));
 src_fault_hold=false;assert(classic_accept(headset,HCI_LINK_TYPE_ACL_CONNECTION));
 // Execute the production profile selector against the negotiated ceiling.
 eld_profile profile=src_eld_profile();assert(profile.bitrate==320000);
 ceiling=256000;profile=src_eld_profile();assert(profile.bitrate==256000 && !profile.vbr && !profile.sbr);
 config.eld_rate=2;vbr=false;profile=src_eld_profile();assert(profile.bitrate==256000 && !profile.vbr);
 game=true;ceiling=192000;config.game_level=2;profile=src_eld_profile();assert(profile.bitrate==192000 && profile.slots==4);
 puts("Production codec owner: endpoint binding, main-only setup, early events, stale events, failure hold and negotiated policy passed");
}
'''
names=['src_event_matches_headset','src_adopt_configuration','src_schedule_codec_setup','src_codec_setup_main','src_eld_profile']
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)
    code=fixture+'\n'.join(function('src/btstack/btstack_avdtp_source.c',n) for n in names)
    code+=function('src/btstack/btstack_hci.c','classic_accept')+tests
    (path/'test.c').write_text(code)
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'src/btstack'),str(path/'test.c'),str(ROOT/'src/btstack/eld_profile.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
