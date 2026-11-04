"""Execute production discovery and favorite-selection code under ASan/UBSan."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def function(file, name):
    source = (ROOT/file).read_text()
    match = re.search(r'^[ \t]*(?:static )?(?:void|bool|int|uint8_t|uint32_t|eld_profile) '+name+r'\([^;]*?\)\s*\{',source,re.M)
    assert match, name
    begin = source.index('{',match.start())
    depth,end = 1,begin+1
    while depth:
        depth += (source[end]=='{')-(source[end]=='}')
        end += 1
    return source[match.start():end]

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define AVDTP_MAX_SEP_NUM 10
typedef struct {uint8_t seid;} avdtp_sep_t;
static struct {avdtp_sep_t sep; uint8_t media_codec_event[100];} remote_seps[AVDTP_MAX_SEP_NUM];
static uint16_t num_remote_seps;
static struct {uint8_t addr[6];char name[24];} s_found[16];
static uint8_t device_addr[6],s_found_n,slot=1,favorites[2][6];
static bool scan_active,s_list_mode,s_pairing;
static unsigned dials,clears;
static void a2dp_source_wedge_clear(void){clears++;}
static void gap_inquiry_stop(void){}
static uint8_t read_uint8_last_flash(void){return slot;}
static void write_uint8_last_flash(uint8_t v){slot=v;}
static void read_slot1_mac(uint8_t *m){memcpy(m,favorites[0],6);}
static void read_slot2_mac(uint8_t *m){memcpy(m,favorites[1],6);}
static void write_slot1_mac(const uint8_t *m){memcpy(favorites[0],m,6);}
static void write_slot2_mac(const uint8_t *m){memcpy(favorites[1],m,6);}
static void write_slot_name(uint8_t s,const char *n){(void)s;(void)n;}
static void settings_saved_add(const uint8_t *m,const char *n){(void)m;(void)n;}
#define slot_replace_purge(s,m) ((void)0)
static void get_link_keys(void){}
static void avdtp_source_establish_stream(void){dials++;}
static const char *bd_addr_to_str(const uint8_t *m){(void)m;return "fixture";}
static bool src_user_dc_hold;
static uint32_t src_dial_window_ms;
static unsigned src_dial_tries,src_dial_retry_timer;
static struct {uint16_t avdtp_cid,avrcp_cid;uint8_t volume;} media_tracker;
static uint16_t dropped_avdtp,dropped_avrcp;
/* Volume ownership + pump-start gating state exercised by the helpers below. */
static bool src_volume_known;
static uint32_t src_vol_cmds;
static uint8_t src_last_avrcp_volume;
static void avrcp_controller_set_absolute_volume(uint16_t c,uint8_t v){(void)c;src_last_avrcp_volume=v;}
static bool is_streaming,src_stream_established;
static bool finish_scan_avdtp_codec,src_start_accepted_pending;
enum {CODEC_ID_NONE=0,CODEC_ID_SBC=1};
static int cur_codec;
static void btstack_run_loop_remove_timer(unsigned *t){assert(t==&src_dial_retry_timer);}
static void a2dp_demo_timer_stop(void *context){assert(context==&media_tracker);}
static void a2dp_source_disconnect(uint16_t c){dropped_avdtp=c;}
static void avrcp_disconnect(uint16_t c){dropped_avrcp=c;}
static void aap_disconnect(void){}
static void audio_slot_queue_init(void){}
static void led_idle_unless_pairing(void){}
'''
tests = r'''
static void choose(uint8_t mac) {
 memset(s_found,0,sizeof s_found);s_found_n=1;memset(s_found[0].addr,mac,6);
 unsigned before=dials;assert(bt_pair_to(0));assert(dials==before+1 && !s_found_n);
 assert(!bt_pair_to(0));assert(dials==before+1);
}
int main(void) {
 // Empty favorites, same device repeated, free-other preference, full replacement.
 choose(1);assert(slot==1 && favorites[0][0]==1 && !favorites[1][0]);
 slot=2;choose(1);assert(slot==1 && !favorites[1][0]);
 choose(2);assert(slot==2 && favorites[0][0]==1 && favorites[1][0]==2);
 slot=1;choose(2);assert(slot==2 && favorites[0][0]==1);
 choose(3);assert(slot==2 && favorites[0][0]==1 && favorites[1][0]==3);
 assert(clears==5);
 // AVRCP and AVDTP are independent CID spaces, not interchangeable values.
 media_tracker.avdtp_cid=0x42;media_tracker.avrcp_cid=0x91;
 src_dial_window_ms=100;src_dial_tries=3;
 is_streaming=true;src_stream_established=true;finish_scan_avdtp_codec=true;
 src_start_accepted_pending=true;
 avdtp_disconnect_keep_pairing();
 assert(src_user_dc_hold && !src_dial_window_ms && !src_dial_tries);
 assert(!is_streaming && !src_stream_established && !finish_scan_avdtp_codec);
 assert(!src_start_accepted_pending);
 assert(dropped_avdtp==0x42 && dropped_avrcp==0x91);
 // Volume seeding is once-only: 0 (mute) and 127 (full) are real levels.
 assert(src_volume_seed_needed());
 media_tracker.volume=64;src_volume_known=true;
 assert(!src_volume_seed_needed());
 set_bt_volume(0);                 // host slider 100% -> absolute 127
 assert(media_tracker.volume==127 && src_last_avrcp_volume==127);
 assert(!src_volume_seed_needed());
 media_tracker.volume=0;           // explicit mute survives a reconnect too
 assert(!src_volume_seed_needed());
 // A START accepted during the capability scan starts the pump once ready.
 src_start_accepted_pending=true;src_stream_established=true;is_streaming=false;cur_codec=CODEC_ID_SBC;
 assert(src_pump_start_pending());
 is_streaming=true;assert(!src_pump_start_pending());
 is_streaming=false;src_stream_established=false;assert(!src_pump_start_pending());
 src_stream_established=true;cur_codec=CODEC_ID_NONE;assert(!src_pump_start_pending());
 // Duplicate endpoints cannot exhaust the bounded discovery table.
 for(uint8_t seid=1;seid<=10;seid++)assert(source_add_sep((avdtp_sep_t){seid}));
 for(uint8_t seid=1;seid<=63;seid++)assert(!source_add_sep((avdtp_sep_t){seid}));
 assert(num_remote_seps==AVDTP_MAX_SEP_NUM);
 uint8_t packet[256];memset(packet,0x5a,sizeof packet);
 for(unsigned n=0;n<=sizeof packet;n++) {
  int i=source_cache_capability(1,packet,n);
  assert((i==0)==(n<=sizeof remote_seps[0].media_codec_event));
  assert(source_cache_capability(63,packet,n)==-1);
 }
 // An inquiry/EIR name is untrusted (up to 255 B): copying it must clamp.
 for(int n=-2;n<=300;n++){
  char nb[8];
  memset(nb,0x5a,sizeof nb);
  uint8_t got=inquiry_name_copy(nb,(uint8_t)sizeof nb,"abcdefghijklmnop",n);
  assert(got<=7 && nb[got]==0 && strlen(nb)<=7);
 }
 { char nb[1]; assert(inquiry_name_copy(nb,0,"x",1)==0); }
 puts("Source discovery bounds and favorite reuse/replacement passed");
}
'''
names = [('src/btstack/btstack_avdtp_source.c',n) for n in ('find_remote_seid','source_add_sep','source_cache_capability','avdtp_disconnect_keep_pairing','set_bt_volume','src_volume_seed_needed','src_pump_start_pending')]
names += [('src/btstack/btstack_hci.c',n) for n in ('slot_mac_valid','bt_pair_to','inquiry_name_copy')]
# The disconnect/pairing helpers call audio_slot_queue_init() from the
# BTstack IRQ; queue_init() allocates through the SDK malloc mutex, so the
# production helper must allocate only once (boot path) and reset afterwards.
avdtp_text = (ROOT / 'src/btstack/btstack_avdtp_source.c').read_text() if 'ROOT' in globals() else Path('src/btstack/btstack_avdtp_source.c').read_text()
init_body = function('src/btstack/btstack_avdtp_source.c', 'audio_slot_queue_init')
assert 'slot_queue_storage_ready' in init_body, 'queue init must be allocation-once'
assert init_body.count('queue_init(&') == 2, init_body
guard = init_body.index('if (!slot_queue_storage_ready)')
else_branch = init_body.index('} else {')
assert init_body.index('queue_init(&') > guard
assert init_body.index('queue_init(&') < else_branch
assert init_body.index('queue_try_remove(&ready_queue') > else_branch
assert init_body.index('queue_try_remove(&free_queue') > else_branch

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)
        (path/'test.c').write_text(fixture+'\n'.join(function(f,n) for f,n in names)+tests)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
        result=subprocess.run([str(path/'test')],check=True,capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
        print(result.stdout.splitlines()[-1])
