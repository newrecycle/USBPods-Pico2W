#pragma once
#include <stdint.h>
typedef unsigned char UCHAR;
typedef unsigned int UINT;
typedef int16_t INT_PCM;
typedef void *HANDLE_AACDECODER;
typedef int AAC_DECODER_ERROR;
typedef struct { int sampleRate, numChannels, frameSize; } CStreamInfo;
enum {TT_MP4_RAW=0,AAC_DEC_OK=0,AAC_DEC_UNKNOWN=1,AACDEC_CLRHIST=8,AACDEC_INTR=4,AAC_TPDEC_CLEAR_BUFFER=0x0603};
HANDLE_AACDECODER aacDecoder_Open(int,int);
AAC_DECODER_ERROR aacDecoder_ConfigRaw(HANDLE_AACDECODER,UCHAR **,UINT *);
void aacDecoder_Close(HANDLE_AACDECODER);
AAC_DECODER_ERROR aacDecoder_SetParam(HANDLE_AACDECODER,int,int);
AAC_DECODER_ERROR aacDecoder_Fill(HANDLE_AACDECODER,UCHAR **,UINT *,UINT *);
AAC_DECODER_ERROR aacDecoder_DecodeFrame(HANDLE_AACDECODER,INT_PCM *,int,int);
CStreamInfo *aacDecoder_GetStreamInfo(HANDLE_AACDECODER);

