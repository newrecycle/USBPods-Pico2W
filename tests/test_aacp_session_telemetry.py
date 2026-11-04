"""Compile the production metadata serializer and validate its bounded JSON."""
import json
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import ROOT, function

fixture=r'''
#include "aacp_mic.h"
#include <stdio.h>
static unsigned mode;
void aacp_mic_get_session_diagnostics(aacp_mic_session_diagnostics *out) {
 *out=(aacp_mic_session_diagnostics){.open=mode,.cid=mode?77:0,.age_ms=30120,
 .init_sent=3,.init_mask=7,.peer_seen=1,.handshake_ack=mode,
 .rx_packets=40,.rx_unhandled=8,.logged_headers=16,.last_opcode=0x127,
 .last_length=1600,.last_rx_age_ms=30000,.last_tx_command=255,.last_tx_age_ms=UINT32_MAX};
}
'''
with tempfile.TemporaryDirectory() as temp:
 p=Path(temp);source=p/'session.c'
 source.write_text(fixture+function('src/device_control.c','session_telemetry')+
                   '\nint main(void){session_telemetry();mode=1;session_telemetry();}\n')
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'src/btstack'),str(source),'-o',str(p/'session')],check=True)
 lines=subprocess.check_output([str(p/'session')],text=True).splitlines()
 rows=[json.loads(x[len('[control] '):]) for x in lines if x.startswith('[control] ')]
 assert len(rows)==2
 for mode,row in enumerate(rows):
  assert row['kind']=='aacpsession' and row['open']==mode and row['handshake_ack']==mode
  assert row['init_mask']==7 and row['init_sent']==3 and row['age_ms']==30120
  assert row['last_opcode']==0x127 and row['last_tx_age_ms']==4294967295 and row['logged_headers']==16
 assert max(map(len,lines))<600
 print('Production AACP session JSON: open/closed, explicit ack, bounded metadata and 32-bit ages passed')
