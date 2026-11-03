"""Production JSON list serializer: maximum counts and escaped 24-byte names."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import function

fixture=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SETTINGS_SAVED_LIMIT 8
static struct {struct {uint8_t mac[6];char name[24];} saved[8];} config;
#define settings() (&config)
static unsigned bt_scan_count(void){return 16;}
static bool bt_scan_get(unsigned i,uint8_t *mac,int8_t *rssi,char *name){
 if(i>=16)return false;
 memset(mac,0,6);*rssi=-128;
 memset(name,i%2?'\\':'"',24); // Deliberately no NUL, maximum escape expansion.
 return true;
}
static const char *bd_addr_to_str(const uint8_t *m){(void)m;return "AA:BB:CC:DD:EE:FF";}
'''
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)
    (path/'test.c').write_text(fixture+function('src/device_control.c','quoted')+function('src/device_control.c','list')+'\nint main(void){list(true);list(false);}\n')
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
    result=subprocess.run([str(path/'test')],check=True,text=True,capture_output=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
    records=[json.loads(line.removeprefix('[control] ')) for line in result.stdout.splitlines() if line]
    assert len(records)==2 and len(records[0]['items'])==16 and len(records[1]['items'])==8
    assert records[0]['items'][0]['name']=='"'*24
    assert records[0]['items'][1]['name']=='\\'*24
    print('Production CDC JSON list records: bounded full lists and escaping passed')
