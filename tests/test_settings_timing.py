"""Production debounce/retry paths at idle, relay and microphone loop rates."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
from test_source_boundaries import function, ROOT

SETTINGS_VERSION = int(re.search(r'#define\s+SETTINGS_VERSION\s+(\d+)',
                                 (ROOT/'src/settings.h').read_text()).group(1))
assert SETTINGS_VERSION == 2, SETTINGS_VERSION

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
static bool s_dirty,s_retrying,fail,change_during_commit;
static uint32_t s_dirty_ms,now,writes;
static uint32_t get_absolute_time(void){return now;}
static uint32_t to_ms_since_boot(uint32_t t){return t;}
static uint32_t save_and_disable_interrupts(void){return 0;}
static void restore_interrupts(uint32_t n){(void)n;}
static void settings_mark_dirty(void);
static bool commit_snapshot(void){
 writes++;
 if(change_during_commit){change_during_commit=false;settings_mark_dirty();}
 return !fail;
}
'''
tests = r'''
int main(void) {
 unsigned periods[]={2,10,50};
 for(unsigned p=0;p<3;p++) {
  s_dirty=s_retrying=false;now=100;writes=0;settings_mark_dirty();
  while(now<300){settings_tick();assert(!writes);now+=periods[p];}
  settings_tick();assert(writes==1 && !s_dirty);
 }
 // A second change extends debounce; real elapsed time survives timer wrap.
 now=UINT32_MAX-100;writes=0;settings_mark_dirty();now+=150;settings_mark_dirty();
 now+=199;settings_tick();assert(!writes);now++;settings_tick();assert(writes==1);
 // Failed explicit flush retains data and uses a full one-second retry delay.
 fail=true;settings_mark_dirty();assert(!settings_flush() && s_dirty && s_retrying);
 unsigned before=writes;now+=999;settings_tick();assert(writes==before);
 fail=false;now++;settings_tick();assert(writes==before+1 && !s_dirty && !s_retrying);
 // A callback update arriving during commit cannot be marked clean by success.
 change_during_commit=true;settings_mark_dirty();assert(settings_flush() && s_dirty);
 now+=200;settings_tick();assert(!s_dirty);
 puts("Settings real-time debounce, wrap, retry and concurrent-dirty retention passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)
    (path/'test.c').write_text(fixture+'\n'.join(function('src/settings.c',name) for name in ('settings_mark_dirty','settings_tick','settings_flush'))+tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})

# v2 record-version validation: a newer-version record with a valid CRC must
# be ignored so the older valid snapshot still loads (settings.c page_valid).
version_fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define SETTINGS_VERSION 2
#define REC_MAGIC 0x50535432u
#define REC_SIZE 512
#define FLASH_SECTOR_SIZE 4096
#define STORE_BASE 0u
static uint8_t flash[FLASH_SECTOR_SIZE*2];
#define XIP_BASE ((uintptr_t)flash)
typedef struct __attribute__((packed)) {
 uint32_t magic;uint16_t version,payload_len;uint32_t seq;
} rec_hdr_t;
static const uint8_t *flash_ptr(uint32_t off){return (const uint8_t*)(XIP_BASE+off);}
static uint32_t page_off(int sector,int page){
 return STORE_BASE+(uint32_t)sector*FLASH_SECTOR_SIZE+(uint32_t)page*REC_SIZE;
}
static uint32_t crc32(const uint8_t *p,size_t n){
 uint32_t c=0xFFFFFFFFu;
 for(size_t i=0;i<n;i++){c^=p[i];for(int b=0;b<8;b++)c=(c>>1)^(0xEDB88320u&(0u-(c&1u)));}
 return ~c;
}
static void make_rec(int sector,int page,uint16_t version,uint32_t seq,uint16_t marker){
 uint32_t off=page_off(sector,page);
 memset(flash+off,0xFF,REC_SIZE);
 rec_hdr_t *h=(rec_hdr_t*)(flash+off);
 h->magic=REC_MAGIC;h->version=version;h->payload_len=sizeof(marker);h->seq=seq;
 memcpy(flash+off+sizeof(rec_hdr_t),&marker,sizeof marker);
 uint32_t crc=crc32(flash+off,REC_SIZE-4);
 memcpy(flash+off+REC_SIZE-4,&crc,4);
}
'''
version_tests = r'''
int main(void){
 uint32_t seq=0;
 memset(flash,0xFF,sizeof flash);
 make_rec(0,0,SETTINGS_VERSION,1,0x1111);          // older, valid
 make_rec(0,1,SETTINGS_VERSION+1,2,0x2222);        // newer, valid CRC
 assert(page_valid(0,0,&seq) && seq==1);
 assert(!page_valid(0,1,&seq));                    // newer version rejected
 // settings_init's scan (settings.c:194-201): highest valid seq wins.
 uint32_t best=0;int best_page=-1;
 for(int pg=0;pg<8;pg++){
  uint32_t s;if(page_valid(0,pg,&s)&&s>=best){best=s;best_page=pg;}
 }
 assert(best==1 && best_page==0);
 // Even alone, a newer-version record is not adopted.
 memset(flash,0xFF,sizeof flash);
 make_rec(1,0,SETTINGS_VERSION+1,7,0x3333);
 assert(!page_valid(1,0,&seq));
 // Same magic + current version + valid CRC still loads.
 make_rec(1,1,SETTINGS_VERSION,8,0x4444);
 assert(page_valid(1,1,&seq) && seq==8);
 puts("Settings v2 record-version validation and older-record fallback passed");
}
'''
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)
    (path/'version.c').write_text(version_fixture+function('src/settings.c','page_valid')+version_tests)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    str(path/'version.c'),'-o',str(path/'version')],check=True)
    subprocess.run([str(path/'version')],check=True,
                   env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
