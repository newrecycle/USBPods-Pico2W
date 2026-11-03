"""Exercise the whole production ELD codec module with a bounded SDK shim."""
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import ROOT
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "eld_codec_config.h"
#define PLOG(...) ((void)0)
#define AVDTP_CODEC_NON_A2DP 255
#define AVDTP_AUDIO 0
#define AVDTP_MEDIA_CODEC 7
#define CODEC_ID_AACELD 4
#define ERROR_CODE_SUCCESS 0
#define ERROR_CODE_UNSUPPORTED_FEATURE_OR_PARAMETER_VALUE 17
#define btstack_assert assert
typedef unsigned avdtp_media_codec_type_t;
typedef struct {struct {unsigned media_type,media_codec_type,media_codec_information_len;uint8_t *media_codec_information;}media_codec;} avdtp_capabilities_t;
typedef struct {unsigned remote_configuration_bitmap;avdtp_capabilities_t remote_configuration;uint8_t *media_codec_configuration_info;unsigned media_codec_configuration_len;} avdtp_stream_endpoint_t;
static avdtp_stream_endpoint_t ep;
static struct {unsigned vendor_id,codec_id;struct {struct {struct {unsigned media_codec_type;}media_codec;}capabilities;unsigned seid;}sep;uint8_t media_codec_event[100];}remote_seps[1];
static uint16_t num_remote_seps=1;
static unsigned selected_remote_sep_index;
static struct {unsigned avdtp_cid,local_seid,remote_seid;}media_tracker={0x42,0,0};
static struct {avdtp_stream_endpoint_t *local_stream_endpoint;}sc;
static uint8_t media_codec_config_data[16],sent[14];
static unsigned media_codec_config_len,offers,created;
static uint8_t send_rc;
static unsigned read16(const uint8_t *p,unsigned i){return p[i]|(unsigned)p[i+1]<<8;}
static unsigned avdtp_subevent_signaling_media_codec_other_capability_get_media_codec_information_len(const uint8_t *p){return read16(p,9);}
static const uint8_t *avdtp_subevent_signaling_media_codec_other_capability_get_media_codec_information(const uint8_t *p){return p+11;}
static unsigned avdtp_subevent_signaling_media_codec_other_configuration_get_media_codec_information_len(const uint8_t *p){return read16(p,11);}
static const uint8_t *avdtp_subevent_signaling_media_codec_other_configuration_get_media_codec_information(const uint8_t *p){return p+13;}
static avdtp_stream_endpoint_t *a2dp_source_create_stream_endpoint(unsigned m,unsigned c,uint8_t *caps,unsigned n,uint8_t *out,unsigned len){
 (void)m;(void)c;(void)out;assert(n==14 && len==14 && caps[11]==0x84 && caps[12]==0xe2);created++;return &ep;
}
static unsigned avdtp_local_seid(avdtp_stream_endpoint_t *p){assert(p==&ep);return 2;}
static void avdtp_source_register_delay_reporting_category(unsigned s){assert(s==2);}
static unsigned store_bit16(unsigned n,unsigned bit,unsigned value){return value?n|(1u<<bit):n&~(1u<<bit);}
static uint8_t avdtp_source_set_configuration(unsigned cid,unsigned local,unsigned remote,unsigned bitmap,avdtp_capabilities_t c){
 assert(cid==0x42 && local==2 && remote==7 && bitmap==(1u<<AVDTP_MEDIA_CODEC));
 assert(c.media_codec.media_codec_information_len==14);memcpy(sent,c.media_codec.media_codec_information,14);offers++;return send_rc;
}
static void codec_fdk_release(void){}
static int codec_fdk_fill(void *p){(void)p;return 0;}
static void a2dp_source_eld_send(void){}
typedef struct {unsigned id;const char *name;bool(*available)(void);uint8_t(*configure)(void);void(*release)(void);int(*fill)(void*);void(*send)(void);}codec_ops_t;
'''
tests=r'''
static unsigned rate(void){return ((unsigned)(sent[11]&127)<<16)|((unsigned)sent[12]<<8)|sent[13];}
static void caps(unsigned max,bool vbr) {
 uint8_t *p=remote_seps[0].media_codec_event;
 memset(p,0,100);p[9]=14;uint8_t value[]={0x4c,0,0,0,1,0x80,0,0x80,0,0x8c,0,0,0,0};
 value[11]=(vbr?0x80:0)|(max>>16);value[12]=max>>8;value[13]=max;
 memcpy(p+11,value,14);remote_seps[0].vendor_id=0x4c;remote_seps[0].codec_id=0x8001;
 remote_seps[0].sep.capabilities.media_codec.media_codec_type=255;remote_seps[0].sep.seid=7;
 codec_aaceld_note_capability(false);codec_aaceld_note_capability(true);
}
int main(void) {
 caps(0,true);assert(!codec_aaceld_max_bitrate());
 assert(codec_aaceld_ops.configure()==0 && rate()==320000);
 assert(codec_aaceld_retry_configuration() && rate()==256000);
 uint8_t event[27]={0};event[11]=14;memcpy(event+13,sent,14);
 assert(codec_aaceld_on_configuration(event) && codec_aaceld_max_bitrate()==256000 && codec_aaceld_vbr_allowed());
 assert(codec_aaceld_retry_configuration() && rate()==192000);
 unsigned before=offers;assert(!codec_aaceld_retry_configuration() && offers==before);
 assert(created==1); // All ceiling offers reuse one endpoint.
 caps(192000,false);assert(codec_aaceld_ops.configure()==0 && rate()==192000 && !(sent[11]&0x80));
 assert(!codec_aaceld_retry_configuration());
 caps(256000,true);assert(codec_aaceld_ops.configure()==0 && rate()==256000);
 assert(codec_aaceld_retry_configuration() && rate()==192000);
 caps(320000,true);send_rc=12;assert(codec_aaceld_ops.configure()==12);
 before=offers;assert(!codec_aaceld_retry_configuration() && offers==before+2);
 caps(128000,true);send_rc=0;before=offers;assert(codec_aaceld_ops.configure()!=0 && offers==before);
 puts("Production ELD negotiation: peer caps, accepted ceiling, VBR and bounded 320/256/192 retry passed");
}
'''
source=(ROOT/'src/btstack/codec/codec_aaceld.c').read_text()
source='\n'.join(line for line in source.splitlines() if not line.startswith('#include'))
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp);(path/'test.c').write_text(fixture+source+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'src/btstack'),str(path/'test.c'),str(ROOT/'src/btstack/eld_codec_config.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
