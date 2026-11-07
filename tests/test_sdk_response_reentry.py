"""Exercise production discovery/capability response ordering in Actions.

The SDK dispatch keeps its actual prelude, DISCOVER/capability arms and generic
ACCEPT tail. Unrelated codec/stream arms are omitted from this narrow fixture.
Callbacks model synchronous next-request submission. Both the current SDK and
the exact previous integration patch are compiled; compilation errors cannot
count as the expected old-source assertion failure.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source-dir',type=Path)
a=p.parse_args()
sdk=a.source_dir or Path(os.environ['PICO_SDK_PATH'])/'lib/btstack/src/classic'

def dispatch(source):
    start=source.index('void avdtp_initiator_stream_config_subsm(')
    accept=source.index('case AVDTP_RESPONSE_ACCEPT_MSG:',start)
    reject=source.index('case AVDTP_RESPONSE_REJECT_MSG:',accept)
    prelude=source[start:accept]
    arm=source[accept:reject]
    # Keep the original dispatch entry, complete DISCOVER/capability arms,
    # default arm and the complete generic acceptance/retirement tail.
    begin=arm.index('                case AVDTP_SI_RECONFIGURE:')
    end=arm.index('                default:',arm.index('                case AVDTP_SI_DELAYREPORT:'))
    arm=arm[:begin]+arm[end:]
    return prelude+arm+'default: break;\n}\n}\n'

fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#define AVDTP_SIGNALING_CONNECTION_INITIATOR_IDLE 0
#define AVDTP_SIGNALING_CONNECTION_INITIATOR_W4_ANSWER 1
#define AVDTP_INITIATOR_W4_ANSWER 2
#define AVDTP_INITIATOR_STREAM_CONFIG_IDLE 0
#define AVDTP_RESPONSE_ACCEPT_MSG 2
#define AVDTP_SI_DISCOVER 1
#define AVDTP_SI_GET_CAPABILITIES 2
#define AVDTP_SI_GET_ALL_CAPABILITIES 12
#define AVDTP_SI_GET_CONFIGURATION 4
#define log_info(...) ((void)0)
#define log_error(...) ((void)0)
#define log_debug(...) ((void)0)
typedef unsigned avdtp_media_type_t;
typedef unsigned avdtp_sep_type_t;
typedef struct {uint8_t seid,in_use;unsigned media_type,type,registered_service_categories;int capabilities;} avdtp_sep_t;
typedef struct {unsigned initiator_config_state;} avdtp_stream_endpoint_t;
typedef struct {
 uint16_t avdtp_cid;
 uint8_t initiator_transaction_label,initiator_connection_state,initiator_local_seid,initiator_remote_seid;
 struct {uint8_t transaction_label,message_type,signal_identifier;} initiator_signaling_packet;
} avdtp_connection_t;
static avdtp_connection_t connection;
static avdtp_stream_endpoint_t endpoint;
static unsigned counter,sep_events,done_events,cap_events,accept_events,queued_label;
static bool queue_capability,queue_generic;
static avdtp_stream_endpoint_t *avdtp_get_stream_endpoint_for_seid(unsigned seid){(void)seid;return &endpoint;}
static uint8_t avdtp_get_next_transaction_label(void){if(++counter==16)counter=1;return (uint8_t)counter;}
static void queue_next(void){
 assert(connection.initiator_connection_state==AVDTP_SIGNALING_CONNECTION_INITIATOR_IDLE);
 connection.initiator_transaction_label=avdtp_get_next_transaction_label();
 queued_label=connection.initiator_transaction_label;
 // Model an immediate CAN_SEND_NOW: the new request is on the wire before
 // returning to the old response handler, exactly the reentrancy boundary.
 connection.initiator_connection_state=AVDTP_SIGNALING_CONNECTION_INITIATOR_W4_ANSWER;
}
static void avdtp_signaling_emit_sep(uint16_t cid,avdtp_sep_t sep){assert(cid==0x42 && sep.seid==3);sep_events++;}
static void avdtp_signaling_emit_sep_done(uint16_t cid){assert(cid==0x42);done_events++;queue_next();}
static unsigned avdtp_unpack_service_capabilities(avdtp_connection_t *c,unsigned signal,int *caps,uint8_t *packet,unsigned size){
 assert(c==&connection && signal==AVDTP_SI_GET_ALL_CAPABILITIES);(void)packet;(void)size;*caps=42;return 7;
}
static void avdtp_signaling_emit_capabilities(uint16_t cid,unsigned seid,int *caps,unsigned categories){
 assert(cid==0x42 && seid==3 && *caps==42 && categories==7);cap_events++;
 if(queue_capability)queue_next();
}
static void avdtp_signaling_emit_accept(uint16_t cid,unsigned seid,unsigned signal,bool accepted){
 assert(cid==0x42 && accepted);(void)seid;accept_events++;
 if(queue_generic){assert(signal==AVDTP_SI_GET_CONFIGURATION);queue_next();}
}
static void avdtp_signaling_emit_accept_for_stream_endpoint(avdtp_stream_endpoint_t *ep,unsigned seid,unsigned signal,bool accepted){
 assert(ep==&endpoint);avdtp_signaling_emit_accept(connection.avdtp_cid,seid,signal,accepted);
}
'''
checks=r'''
static void response(unsigned label,unsigned signal){
 uint8_t packet[]={0,0,3<<2,0};
 connection.initiator_signaling_packet.transaction_label=(uint8_t)label;
 connection.initiator_signaling_packet.message_type=AVDTP_RESPONSE_ACCEPT_MSG;
 connection.initiator_signaling_packet.signal_identifier=(uint8_t)signal;
 avdtp_initiator_stream_config_subsm(&connection,packet,sizeof packet,2);
}
int main(void){
 for(unsigned seed=1;seed<=15;seed++){
  counter=seed;sep_events=done_events=cap_events=accept_events=0;
  queue_capability=true;queue_generic=false;
  connection=(avdtp_connection_t){.avdtp_cid=0x42,.initiator_transaction_label=seed,
   .initiator_connection_state=AVDTP_SIGNALING_CONNECTION_INITIATOR_W4_ANSWER,.initiator_remote_seid=3};
  response(seed,AVDTP_SI_DISCOVER);
  assert(sep_events==1 && done_events==1);
  assert(connection.initiator_transaction_label == queued_label);
  unsigned next=queued_label;
  // Old/duplicate discovery response must not clear the new wait state.
  response(seed,AVDTP_SI_DISCOVER);
  assert(sep_events==1 && done_events==1 && connection.initiator_transaction_label==next);
  assert(connection.initiator_connection_state==AVDTP_SIGNALING_CONNECTION_INITIATOR_W4_ANSWER);
  response(next,AVDTP_SI_GET_ALL_CAPABILITIES);
  assert(cap_events==1 && connection.initiator_transaction_label==queued_label);
  unsigned last=queued_label;queue_capability=false;
  response(next,AVDTP_SI_GET_ALL_CAPABILITIES);assert(cap_events==1);
  response(last,AVDTP_SI_GET_ALL_CAPABILITIES);assert(cap_events==2);
  assert(connection.initiator_connection_state==AVDTP_SIGNALING_CONNECTION_INITIATOR_IDLE);
  response(last,AVDTP_SI_GET_ALL_CAPABILITIES);assert(cap_events==2);
  // Also preserve the previously repaired generic ACCEPT callback boundary.
  connection.initiator_connection_state=AVDTP_SIGNALING_CONNECTION_INITIATOR_W4_ANSWER;
  unsigned generic=connection.initiator_transaction_label;queue_generic=true;
  response(generic,AVDTP_SI_GET_CONFIGURATION);
  assert(connection.initiator_transaction_label==queued_label);
 }
 puts("SDK discovery, chained capability and generic ACCEPT reentry: all 15 label positions passed");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    old=root/'src/classic/avdtp_initiator.c';old.parent.mkdir(parents=True)
    old.write_text((ROOT/'references/btstack/avdtp_initiator.c').read_text())
    # Immutable pre-repair integration data from e9f5482; no reference edited.
    baseline=json.loads((ROOT/'tests/fixtures/avdtp-retirement-before-e9f5482.json').read_text())
    assert baseline['source_commit']=='e9f548259cfc402db88a1e2ea7ca0a56ee99844a'
    assert hashlib.sha256(baseline['patch'].encode()).hexdigest()==baseline['patch_sha256']
    patch=root/'before.patch';patch.write_text(baseline['patch'])
    subprocess.run(['git','apply',str(patch)],cwd=root,check=True)
    for name,source in [('before',old.read_text()),('current',(sdk/'avdtp_initiator.c').read_text())]:
        code=root/(name+'.c');exe=root/name
        code.write_text(fixture+dispatch(source)+checks)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(code),'-o',str(exe)],check=True)
        result=subprocess.run([str(exe)],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
        if name=='before':
            assert result.returncode==-signal.SIGABRT and 'connection.initiator_transaction_label == queued_label' in result.stderr, result.stderr
            print('Archived integration reproduced the overwritten next-request label (SIGABRT)')
        else:
            assert result.returncode==0,result.stderr
            print(result.stdout.strip())
