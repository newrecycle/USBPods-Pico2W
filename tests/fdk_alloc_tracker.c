// SPDX-License-Identifier: GPL-3.0-only
// Linker wrappers count requested codec bytes, excluding libc cache retention.
// This is host allocation evidence, not a Cortex-M33 runtime measurement.
#include "fdk_alloc_tracker.h"
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
void *__real_malloc(size_t);
void *__real_calloc(size_t,size_t);
void __real_free(void*);
static struct {void *pointer;size_t bytes;} allocations[4096];
static size_t used,peak;
static bool measuring;
static void *record(void *p,size_t n) {
 if(!p)return NULL;
 for(unsigned i=0;i<4096;i++)if(!allocations[i].pointer) {
   allocations[i].pointer=p;allocations[i].bytes=n;used+=n;
   if(measuring && used>peak)peak=used;
   return p;
 }
 abort();
}
void *__wrap_malloc(size_t n){return record(__real_malloc(n),n);}
void *__wrap_calloc(size_t n,size_t z){assert(!z || n<=SIZE_MAX/z);return record(__real_calloc(n,z),n*z);}
void __wrap_free(void *p) {
 if(p)for(unsigned i=0;i<4096;i++)if(allocations[i].pointer==p) {
   used-=allocations[i].bytes;allocations[i].pointer=NULL;break;
 }
 __real_free(p);
}
void fdk_alloc_begin(void){measuring=true;if(used>peak)peak=used;}
void fdk_alloc_end(void){if(used>peak)peak=used;measuring=false;}
void fdk_alloc_report(void) {
 const char *path=getenv("USBPODS_FDK_HEAP_REPORT");
 if(!path)return;
 FILE *f=fopen(path,"w");assert(f);
 fprintf(f,"{\"pointer_bytes\":%zu,\"codec_requested_peak\":%zu,\"runtime_allocation_verified\":false}\n",sizeof(void*),peak);
 assert(!fclose(f));
 printf("ELD codec allocation audit: pointer_bytes=%zu requested_peak=%zu (allocator/BT overhead excluded)\n",sizeof(void*),peak);
}
