"""Actual firmware PCM queue/gain and Apple AU packetization with real FDK."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
from test_source_boundaries import ROOT,function
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fdk-lib',type=Path,required=True);a=p.parse_args()
body=r'''
#define PI 3.14159265358979323846
int main(void) {
 const unsigned gains[]={100,50,0};unsigned decoded_frames=0;
 for(unsigned mode=1;mode<=3;mode++)for(unsigned g=0;g<3;g++) {
  profile=eld_profile_select(mode,false,1,false,false,5,1);
  assert(eld_encoder_open(&handleAAC,&aacinf,&profile)==AACENC_OK);
  HANDLE_AACDECODER dec=aacDecoder_Open(TT_MP4_RAW,1);assert(dec);
  UCHAR *conf[]={aacinf.confBuf};UINT cn=aacinf.confSize;
  assert(aacDecoder_ConfigRaw(dec,conf,&cn)==AAC_DEC_OK);
  memset(&free_queue,0,sizeof free_queue);memset(&ready_queue,0,sizeof ready_queue);
  for(uint8_t i=0;i<9;i++)assert(queue_try_add(&free_queue,&i));
  filling_slot_valid=false;filling_offset=0;set_usb_sw_gain_pct(gains[g]);
  is_usb_streaming=is_streaming=true;aaceld_frame_sequence=4094;
  a2dp_media_sending_context_t ctx={.max_media_payload_size=986};
  unsigned seq=4094,total=0;double energy[2]={0};unsigned count=0;
  for(unsigned batch=0;batch<40;batch++) {
   INT_PCM input[2880],decoded[1920];
   for(unsigned i=0;i<1440;i++) {
    double t=(batch*1440+i)/48000.0;
    input[2*i]=(INT_PCM)(10000*sin(2*PI*40*t)+6000*sin(2*PI*1000*t));
    input[2*i+1]=(INT_PCM)(8000*sin(2*PI*120*t)+4000*sin(2*PI*4000*t));
   }
   const unsigned chunks[]={44,45,47,48,49};
   for(unsigned off=0,k=0;off<1440;k++) {
    unsigned n=chunks[k%5];if(n>1440-off)n=1440-off;
    audio_slot_push_samples(input+2*off,n);off+=n;
   }
   assert(ready_queue.count==3 && !filling_slot_valid);
   // Queue bytes and channel order must match the actual production gain.
   for(unsigned f=0;f<3;f++) {
    unsigned index=ready_queue.data[(ready_queue.read+f)%9];
    for(unsigned j=0;j<960;j++) {
     int16_t expected=(int16_t)(((int32_t)input[f*960+j]*usb_sw_gain_q15)>>15);
     assert(slot_pool[index].data[j]==expected);
    }
   }
   ctx.samples_ready+=1440;
   while(ctx.samples_ready) {
    int consumed=codec_fdk_fill(&ctx);assert(consumed>0 && consumed<=1440);
    assert(ctx.codec_storage_count<=ctx.max_media_payload_size && ctx.codec_num_frames<=3);
    unsigned off=0,frames=0;
    while(off<ctx.codec_storage_count) {
     uint8_t *p=ctx.codec_storage+off;
     assert((p[0]&0xf0)==0xb0 && (p[2]&0xf0)==0x10);
     /* Unsigned cast: clang -Wextra rejects int vs unsigned here under
        -Werror; the CI gcc build stayed silent. Same check either way. */
     assert((unsigned)(((p[0]&15)<<8)|p[1])==seq);seq=(seq+1)&4095;
     unsigned n=((p[2]&15)<<8)|p[3];assert(n && off+4+n<=ctx.codec_storage_count);
     UCHAR *payload[]={p+4};UINT size=n,valid=n;
     assert(aacDecoder_Fill(dec,payload,&size,&valid)==AAC_DEC_OK && !valid);
     assert(aacDecoder_DecodeFrame(dec,decoded,1920,0)==AAC_DEC_OK);
     if(total>20)for(unsigned i=0;i<480;i++) {
      energy[0]+=(double)decoded[2*i]*decoded[2*i];energy[1]+=(double)decoded[2*i+1]*decoded[2*i+1];count++;
     }
     off+=4+n;frames++;total++;
    }
    assert(frames==ctx.codec_num_frames);ctx.codec_storage_count=ctx.codec_num_frames=0;
   }
   assert(!ready_queue.count && free_queue.count==9);
  }
  assert(!usb_slot_push_drops && !usb_slot_ready_full_drops);
  double rms0=sqrt(energy[0]/count),rms1=sqrt(energy[1]/count);
  if(!gains[g])assert(rms0<1 && rms1<1);else assert(rms0>900*gains[g]/100.0/8 && rms1>600*gains[g]/100.0/8);
  printf("Production PCM->Apple AU path: mode=%u gain=%u frames=%u RMS=%.2f/%.2f sequence-wrap verified\n",mode,gains[g],total,rms0,rms1);
  decoded_frames+=total;aacDecoder_Close(dec);aacEncClose(&handleAAC);
 }
 printf("Production PCM/gain/channel order/framing/MTU: %u decoded frames passed\n",decoded_frames);
}
'''
names=['set_usb_sw_gain_pct','audio_slot_push_samples','audio_slot_pop','audio_slot_release','src_eld_au_space','codec_fdk_fill']
with tempfile.TemporaryDirectory() as temp:
 path=Path(temp)
 (path/'pipeline.c').write_text((ROOT/'tests/pcm_packet_mocks.h').read_text()+'\n'.join(function('src/btstack/btstack_avdtp_source.c',n) for n in names)+body)
 args=['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address','-I',str(ROOT/'src/btstack'),'-I',str(ROOT/'src')]
 for d in ('libAACdec','libAACenc','libSYS'):args+=['-isystem',str(ROOT/'3rd-party/fdk-aac'/d/'include')]
 args+=[str(path/'pipeline.c'),str(ROOT/'src/btstack/eld_profile.c'),str(ROOT/'src/btstack/eld_encoder.c'),str(ROOT/'src/resamp44.c'),str(a.fdk_lib.resolve()),'-lstdc++','-lm','-o',str(path/'pipeline')]
 subprocess.run(args,check=True)
 subprocess.run([str(path/'pipeline')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
