"""Exercise the pinned SDK's real START/SUSPEND and media-grant preconditions.

This isolates SDK API contracts, not radio interoperability. CI reads its pinned
SDK checkout; --source-dir supports an offline copy for an investigation.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-dir',type=Path)
args=parser.parse_args()
directory=args.source_dir or Path(os.environ['PICO_SDK_PATH'])/'lib/btstack/src/classic'

def read_sdk(file):
    path=directory/file
    if not path.exists():path=directory/('sdk-'+file)
    return path.read_text()

def response_label_guard():
    # Compile the exact first guard from the SDK's production initiator function.
    # An unpatched SDK has no guard and must fail this regression.
    source=read_sdk('avdtp_initiator.c')
    start=source.index('void avdtp_initiator_stream_config_subsm(')
    before_state=source.index('    if (connection->initiator_connection_state ==',start)
    prelude=source[start:before_state]
    guard_start=prelude.index('    if (connection->initiator_signaling_packet.transaction_label !=')
    return prelude[guard_start:]

def extract(file,name):
    path=directory/file
    if not path.exists():path=directory/('sdk-'+file)
    source=path.read_text()
    match=re.search(r'^(?:void|uint8_t) '+name+r'\([^;]*?\)\s*\{',source,re.M)
    assert match,name
    start=source.index('{',match.start());end=start+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[match.start():end]

fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#define ERROR_CODE_SUCCESS 0
#define ERROR_CODE_UNKNOWN_CONNECTION_IDENTIFIER 2
#define ERROR_CODE_COMMAND_DISALLOWED 12
#define AVDTP_STREAM_ENDPOINT_OPENED 1
#define AVDTP_STREAM_ENDPOINT_STREAMING 2
#define log_error(...) ((void)0)
#define log_info(...) ((void)0)
typedef struct {uint8_t transaction_label;} signaling_header_t;
typedef struct {uint8_t initiator_transaction_label;signaling_header_t initiator_signaling_packet;} label_connection_t;
static unsigned accepted_responses;
typedef struct {uint8_t initiator_local_seid,initiator_remote_seid;} avdtp_connection_t;
typedef struct {
 uint16_t l2cap_media_cid,sequence_number;
 struct {uint8_t seid;} remote_sep;
 uint8_t state,start_stream,suspend_stream;
} avdtp_stream_endpoint_t;
static avdtp_connection_t connection;
static avdtp_stream_endpoint_t endpoint;
static unsigned signals,grants;
static avdtp_connection_t *avdtp_get_connection_for_avdtp_cid(uint16_t cid){return cid==0x42?&connection:NULL;}
static avdtp_stream_endpoint_t *avdtp_get_stream_endpoint_for_seid(uint8_t seid){return seid==1?&endpoint:NULL;}
static bool is_avdtp_remote_seid_registered(avdtp_stream_endpoint_t *ep){return ep->remote_sep.seid!=0;}
static void avdtp_request_can_send_now_initiator(avdtp_connection_t *c){assert(c==&connection);signals++;}
static void avdtp_streaming_emit_can_send_media_packet_now(avdtp_stream_endpoint_t *ep,uint16_t seq){assert(ep==&endpoint);(void)seq;grants++;}
'''
tests=r'''
int main(void) {
 endpoint.l2cap_media_cid=0x80;endpoint.remote_sep.seid=3;endpoint.state=AVDTP_STREAM_ENDPOINT_STREAMING;
 // Negative control: the pinned unpatched SDK queues START even when the
 // endpoint is STREAMING, then silently clears the flag without sending.
 assert(avdtp_start_stream(0x42,1)==12 && signals==0 && !endpoint.start_stream);
 endpoint.state=0; // Configured but media not yet OPENED: never queue.
 assert(avdtp_start_stream(0x42,1)==12 && signals==0 && !endpoint.start_stream);
 endpoint.state=AVDTP_STREAM_ENDPOINT_OPENED;
 assert(avdtp_start_stream(0x42,1)==0 && signals==1);
 assert(avdtp_start_stream(0x42,1)==12 && signals==1); // START already pending.
 // A successful START request is not a media-grant proof.
 avdtp_initiator_stream_config_subsm_handle_can_send_now_stream_endpoint(&endpoint);assert(!grants);
 assert(avdtp_suspend_stream(0x42,1)==12); // OPENED, not STREAMING.
 endpoint.start_stream=0;endpoint.state=AVDTP_STREAM_ENDPOINT_STREAMING;
 avdtp_initiator_stream_config_subsm_handle_can_send_now_stream_endpoint(&endpoint);assert(grants==1);
 assert(avdtp_suspend_stream(0x42,1)==0 && signals==2);
 assert(avdtp_suspend_stream(0x42,1)==12 && signals==2); // SUSPEND already pending.
 endpoint.suspend_stream=0;endpoint.remote_sep.seid=0;
 assert(avdtp_suspend_stream(0x42,1)==12); // Missing remote association.
 endpoint.l2cap_media_cid=0;assert(avdtp_suspend_stream(0x42,1)==2);
 assert(avdtp_suspend_stream(0x99,1)==2);
 assert(avdtp_suspend_stream(0x42,9)==2);
 // The response guard must reject an old or duplicate transaction before
 // it can change SDK wait/endpoint state or emit a false application ACCEPT.
 label_connection_t lc={.initiator_transaction_label=6,
                        .initiator_signaling_packet={.transaction_label=5}};
 check_late_response(&lc);assert(accepted_responses==0);
 lc.initiator_signaling_packet.transaction_label=6;
 check_late_response(&lc);assert(accepted_responses==1);
 lc.initiator_transaction_label=7;
 check_late_response(&lc);assert(accepted_responses==1);
 puts("Pinned SDK START/SUSPEND and transaction-label guards passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)
    guard=response_label_guard()
    # The checked-in reference is the unmodified SDK comparison snapshot.
    # Ensure the negative control does not accidentally acquire the new guard.
    reference=(Path(__file__).resolve().parents[1]/'references/btstack/avdtp_initiator.c').read_text()
    before_state=reference.split('void avdtp_initiator_stream_config_subsm(',1)[1].split(
        '    if (connection->initiator_connection_state ==',1)[0]
    assert 'initiator_signaling_packet.transaction_label !=' not in before_state
    # A reentrant application callback can submit the next transaction.
    # Retire the old response label before emitting acceptance, or the SDK
    # overwrites that new transaction's label after returning from the callback.
    initiator=read_sdk('avdtp_initiator.c')
    accept_section=initiator.split('case AVDTP_RESPONSE_ACCEPT_MSG:',1)[1].split(
        'case AVDTP_RESPONSE_REJECT_MSG:',1)[0]
    advance='connection->initiator_transaction_label = avdtp_get_next_transaction_label();'
    emit='avdtp_signaling_emit_accept_for_stream_endpoint('
    assert accept_section.index(advance)<accept_section.index(emit)
    old_accept=reference.split('case AVDTP_RESPONSE_ACCEPT_MSG:',1)[1].split(
        'case AVDTP_RESPONSE_REJECT_MSG:',1)[0]
    assert old_accept.index(advance)>old_accept.index(emit)
    code=fixture+'static void check_late_response(label_connection_t *connection) {\n'+guard+' accepted_responses++;\n}\n'
    code+=extract('avdtp.c','avdtp_start_stream')+extract('avdtp.c','avdtp_suspend_stream')
    code+=extract('avdtp_initiator.c','avdtp_initiator_stream_config_subsm_handle_can_send_now_stream_endpoint')+tests
    (path/'test.c').write_text(code)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
