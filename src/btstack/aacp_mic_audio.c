// SPDX-License-Identifier: GPL-3.0-only
// AACP AAC-ELD microphone. Single producer/consumer AU and PCM queues;
// USB IRQ never decodes, allocates, logs, or waits for the Bluetooth lock.
#include "aacp_mic.h"
#include "mic_clock.h"
#include <stdatomic.h>
#include <string.h>
#include <stdio.h>

static _Atomic bool capture;
static _Atomic uint32_t generation;
void aacp_mic_set_capture(bool on) {
    if (atomic_exchange_explicit(&capture,on,memory_order_acq_rel) != on)
        atomic_fetch_add_explicit(&generation,1,memory_order_acq_rel);
}
void aacp_mic_discontinuity(void) {
    atomic_fetch_add_explicit(&generation,1,memory_order_acq_rel);
}
bool aacp_mic_capture(void) {
    return atomic_load_explicit(&capture,memory_order_acquire);
}
uint32_t aacp_mic_generation(void) {
    return atomic_load_explicit(&generation,memory_order_acquire);
}

/* Monotonic lifetime counters. BT is the sole writer of the non-atomic
 * history fields; snapshots only read atomic fields. No guess is made about
 * the AACP timestamp units, whether they are sample ticks, or their epoch. */
static struct {
    _Atomic uint32_t observed, intervals, bursts, cadence_7500, cadence_10000;
    _Atomic uint32_t other, gaps, arrival_last, arrival_min, arrival_max;
    _Atomic uint32_t ts_last, ts_step_ref, ts_step_last, ts_step_min, ts_step_max;
    _Atomic uint32_t ts_dups, ts_backwards, ts_changes, ts_gaps;
    _Atomic uint32_t measured_rate,clock_windows;
    uint32_t clock_start,clock_units;
    uint32_t history_epoch, previous_us, previous_ts, reference_step;
    bool history_valid;
} arrival={ .arrival_min=UINT32_MAX, .ts_step_min=UINT32_MAX };

static void sample_min(_Atomic uint32_t *p,uint32_t value) {
    uint32_t old=atomic_load_explicit(p,memory_order_relaxed);
    if (value<old) atomic_store_explicit(p,value,memory_order_relaxed);
}
static void sample_max(_Atomic uint32_t *p,uint32_t value) {
    uint32_t old=atomic_load_explicit(p,memory_order_relaxed);
    if (value>old) atomic_store_explicit(p,value,memory_order_relaxed);
}
void aacp_mic_audio_note_au(uint32_t timestamp,uint32_t arrival_us) {
    uint32_t epoch=aacp_mic_generation();
    atomic_fetch_add_explicit(&arrival.observed,1,memory_order_relaxed);
    atomic_store_explicit(&arrival.ts_last,timestamp,memory_order_relaxed);
    if (!arrival.history_valid || arrival.history_epoch!=epoch) {
        arrival.history_valid=true;
        arrival.history_epoch=epoch;
        arrival.previous_us=arrival_us;
        arrival.previous_ts=timestamp;
        arrival.reference_step=0;
        arrival.clock_start=arrival_us;arrival.clock_units=1;
        atomic_store(&arrival.measured_rate,0);atomic_store(&arrival.clock_windows,0);
        atomic_store_explicit(&arrival.ts_step_ref,0,memory_order_relaxed);
        return; /* never compare timestamps/arrival time across generations */
    }

    uint32_t dt=arrival_us-arrival.previous_us; /* time_us_32 wrap-safe */
    /* Measure complete SDU groups rather than treating every AU in a burst
       as a new clock edge. No units are inferred from the peer timestamp. */
    uint32_t span=arrival_us-arrival.clock_start;
    if(dt>=1000u && span>=1000000u) {
        uint32_t rate=(uint32_t)((uint64_t)arrival.clock_units*MIC_AU_SAMPLES*1000000u/span);
        atomic_store(&arrival.measured_rate,rate);atomic_fetch_add(&arrival.clock_windows,1);
        arrival.clock_start=arrival_us;arrival.clock_units=0;
    }
    arrival.clock_units++;
    arrival.previous_us=arrival_us;
    atomic_fetch_add_explicit(&arrival.intervals,1,memory_order_relaxed);
    atomic_store_explicit(&arrival.arrival_last,dt,memory_order_relaxed);
    sample_min(&arrival.arrival_min,dt);
    sample_max(&arrival.arrival_max,dt);
    if (dt<1000u)
        atomic_fetch_add_explicit(&arrival.bursts,1,memory_order_relaxed);
    else if (dt>=6500u && dt<=8500u)
        atomic_fetch_add_explicit(&arrival.cadence_7500,1,memory_order_relaxed);
    else if (dt>=9000u && dt<=11000u)
        atomic_fetch_add_explicit(&arrival.cadence_10000,1,memory_order_relaxed);
    else if (dt>=15000u)
        atomic_fetch_add_explicit(&arrival.gaps,1,memory_order_relaxed);
    else
        atomic_fetch_add_explicit(&arrival.other,1,memory_order_relaxed);

    uint32_t step=timestamp-arrival.previous_ts; /* supports u32 wrap */
    arrival.previous_ts=timestamp;
    if (!step) {
        atomic_fetch_add_explicit(&arrival.ts_dups,1,memory_order_relaxed);
    } else if (step & 0x80000000u) {
        atomic_fetch_add_explicit(&arrival.ts_backwards,1,memory_order_relaxed);
    } else {
        atomic_store_explicit(&arrival.ts_step_last,step,memory_order_relaxed);
        sample_min(&arrival.ts_step_min,step);
        sample_max(&arrival.ts_step_max,step);
        if (!arrival.reference_step) {
            arrival.reference_step=step;
            atomic_store_explicit(&arrival.ts_step_ref,step,memory_order_relaxed);
        } else if (step!=arrival.reference_step) {
            atomic_fetch_add_explicit(&arrival.ts_changes,1,memory_order_relaxed);
            /* Heuristic only: a >=2x step may be a missing frame. */
            if (arrival.reference_step<=UINT32_MAX/2u &&
                step>=arrival.reference_step*2u)
                atomic_fetch_add_explicit(&arrival.ts_gaps,1,memory_order_relaxed);
        }
    }
}

#ifdef USBPODS_MIC_DECODE
#include <aacdecoder_lib.h>
#include <malloc.h>
#include "pico/time.h"
_Static_assert(sizeof(INT_PCM)==sizeof(int16_t), "microphone requires 16-bit FDK PCM");
#define AU_SLOTS 32u
#define PCM_SLOTS 16u
#define FRAME 480u

static struct { uint32_t epoch, queued_us; uint8_t len, data[255]; } aus[AU_SLOTS];
static struct { uint32_t epoch; int16_t data[FRAME]; } pcm[PCM_SLOTS];
static _Atomic uint32_t aw, ar, pw, pr;
static _Atomic uint32_t au_high, pcm_high, au_overflows, pcm_overflows;
static _Atomic uint32_t au_stale, pcm_stale, au_inactive;
static _Atomic uint32_t au_wait_last_us, au_wait_max_us, work_max_us;
static _Atomic uint32_t pcm_blocked, au_overflow_pcm_full;
static _Atomic uint32_t decoded, errors, flush_errors, max_us, last_us, ema_us;
static _Atomic uint32_t last_rate, last_channels, last_frame;
static _Atomic bool ready;
static uint32_t pcm_offset; /* USB consumer only */
static mic_clock packet_clock; /* USB consumer only */
static _Atomic bool pcm_primed;
static HANDLE_AACDECODER decoder; /* initialized before BT starts; main owns */
static INT_PCM scratch[960];
static uint32_t last_epoch=UINT32_MAX; /* decoder/main only */
/* USB-owned transient state; the immutable first-fault publication and the
 * cross-core timestamps/counters are atomic for race-safe diagnostics. */
static uint32_t usb_packet_generation=UINT32_MAX,usb_packet_available;
static bool usb_primed_this_generation,usb_packet_rebuffered,usb_first_written;
static _Atomic uint32_t last_admitted_au_us,last_published_pcm_us;
static _Atomic bool seen_admitted_au,seen_published_pcm;
static _Atomic uint32_t usb_postprime_underruns,usb_rebuffers;
static struct {
    _Atomic uint32_t generation,at_us,requested,supplied,au_depth,pcm_depth;
    _Atomic uint32_t available,au_age_us,pcm_age_us,rebuffer;
    _Atomic bool valid;
} first_usb_fault;

void aacp_mic_audio_init(void) {
    /* Preserve the inherited F8 E6 30 00 ASC (48kHz, 480 samples)
     * and the existing independent USB 64kHz clock. */
    UCHAR asc[]={0xf8,0xe6,0x30,0};
    UCHAR *config[]={asc}; UINT length=sizeof(asc);
    decoder=aacDecoder_Open(TT_MP4_RAW,1);
    if (decoder && aacDecoder_ConfigRaw(decoder,config,&length)!=AAC_DEC_OK) {
        aacDecoder_Close(decoder); decoder=NULL;
    }
    atomic_store_explicit(&ready,decoder!=NULL,memory_order_release);
#ifdef __GLIBC__
    struct mallinfo2 heap=mallinfo2();
#else
    struct mallinfo heap=mallinfo();
#endif
    printf("[mic] heap inuse=%lu free_in_arena=%lu (excludes unclaimed heap)\n",
           (unsigned long)heap.uordblks,(unsigned long)heap.fordblks);
    printf("[mic] AAC-ELD decoder %s (48kHz ASC, 64kHz USB clock, experimental)\n",
           decoder?"ready":"allocation/configuration FAILED");
}
bool aacp_mic_audio_ready(void) {
    return atomic_load_explicit(&ready,memory_order_acquire);
}
void aacp_mic_audio_enqueue(const uint8_t *au,uint8_t len) {
    if (!aacp_mic_capture() || !aacp_mic_audio_ready()) {
        atomic_fetch_add_explicit(&au_inactive,1,memory_order_relaxed);
        return;
    }
    uint32_t epoch=aacp_mic_generation();
    uint32_t w=atomic_load_explicit(&aw,memory_order_relaxed);
    uint32_t r=atomic_load_explicit(&ar,memory_order_acquire);
    if (w-r>=AU_SLOTS) {
        atomic_fetch_add_explicit(&au_overflows,1,memory_order_relaxed);
        if (atomic_load_explicit(&pw,memory_order_acquire)-
            atomic_load_explicit(&pr,memory_order_acquire)==PCM_SLOTS)
            atomic_fetch_add_explicit(&au_overflow_pcm_full,1,memory_order_relaxed);
        return;
    }
    aus[w%AU_SLOTS].epoch=epoch;
    aus[w%AU_SLOTS].queued_us=time_us_32();
    aus[w%AU_SLOTS].len=len;
    memcpy(aus[w%AU_SLOTS].data,au,len);
    atomic_store_explicit(&aw,w+1,memory_order_release);
    atomic_store_explicit(&last_admitted_au_us,aus[w%AU_SLOTS].queued_us,memory_order_relaxed);
    atomic_store_explicit(&seen_admitted_au,true,memory_order_release);
    sample_max(&au_high,w-r+1);
}

/* Process at most eight decoder frames per main-loop pass, but skip up to
 * thirty-two stale queued AUs first so a reconnect cannot starve new data. */
void aacp_mic_audio_work(void) {
    if (!decoder) return;
    const uint32_t work_started=time_us_32();
    unsigned processed=0;
    for (unsigned scanned=0; scanned<AU_SLOTS+8u && processed<8u; scanned++) {
        uint32_t r=atomic_load_explicit(&ar,memory_order_relaxed);
        if (r==atomic_load_explicit(&aw,memory_order_acquire)) break;
        uint32_t epoch=aus[r%AU_SLOTS].epoch;
        if (epoch!=aacp_mic_generation() || !aacp_mic_capture()) {
            atomic_fetch_add_explicit(&au_stale,1,memory_order_relaxed);
            atomic_store_explicit(&ar,r+1,memory_order_release);
            continue;
        }
        /* Do not consume/decode a current AU unless its PCM can be retained.
           USB is the only consumer, so it can only increase available space
           during DecodeFrame. Stale AUs above are still drained when full. */
        uint32_t w=atomic_load_explicit(&pw,memory_order_relaxed);
        uint32_t pr_now=atomic_load_explicit(&pr,memory_order_acquire);
        if (w-pr_now>=PCM_SLOTS) {
            atomic_fetch_add_explicit(&pcm_blocked,1,memory_order_relaxed);
            break;
        }
        processed++;
        /* FDK reads an AU before applying CLRHIST/INTR: an empty DecodeFrame
           only returns NOT_ENOUGH_BITS and never clears ELD history. Discard
           any old compressed input, then apply the flags while decoding the
           first supplied AU. Retry on failure without publishing stale PCM. */
        const bool reset_history = last_epoch!=epoch;
        UCHAR *input[]={aus[r%AU_SLOTS].data};
        UINT size=aus[r%AU_SLOTS].len, valid=size;
        uint32_t t=time_us_32();
        uint32_t wait=t-aus[r%AU_SLOTS].queued_us; /* wrapping device clock */
        atomic_store_explicit(&au_wait_last_us,wait,memory_order_relaxed);
        sample_max(&au_wait_max_us,wait);
        AAC_DECODER_ERROR err=reset_history ?
            aacDecoder_SetParam(decoder,AAC_TPDEC_CLEAR_BUFFER,1) : AAC_DEC_OK;
        if (err==AAC_DEC_OK) err=aacDecoder_Fill(decoder,input,&size,&valid);
        if (err==AAC_DEC_OK && !valid)
            err=aacDecoder_DecodeFrame(decoder,scratch,960,
                                      reset_history ? AACDEC_CLRHIST|AACDEC_INTR : 0);
        else if (err==AAC_DEC_OK) err=AAC_DEC_UNKNOWN;
        if (reset_history) {
            if (err==AAC_DEC_OK) last_epoch=epoch;
            else atomic_fetch_add_explicit(&flush_errors,1,memory_order_relaxed);
        }
        uint32_t dt=time_us_32()-t;
        atomic_store_explicit(&last_us,dt,memory_order_relaxed);
        sample_max(&max_us,dt);
        uint32_t avg=atomic_load_explicit(&ema_us,memory_order_relaxed);
        avg=avg?(uint32_t)(((uint64_t)avg*7u+dt)/8u):dt;
        atomic_store_explicit(&ema_us,avg,memory_order_relaxed);
        atomic_store_explicit(&ar,r+1,memory_order_release);

        CStreamInfo *info=aacDecoder_GetStreamInfo(decoder);
        if (info) {
            atomic_store_explicit(&last_rate,(uint32_t)info->sampleRate,memory_order_relaxed);
            atomic_store_explicit(&last_channels,(uint32_t)info->numChannels,memory_order_relaxed);
            atomic_store_explicit(&last_frame,(uint32_t)info->frameSize,memory_order_relaxed);
        }
        bool ok=err==AAC_DEC_OK && info && info->sampleRate==48000 &&
                info->numChannels==1 && info->frameSize==FRAME;
        if (ok) atomic_fetch_add_explicit(&decoded,1,memory_order_relaxed);
        else atomic_fetch_add_explicit(&errors,1,memory_order_relaxed);
        if (epoch!=aacp_mic_generation() || !aacp_mic_capture()) continue;

        pcm[w%PCM_SLOTS].epoch=epoch;
        if (ok) memcpy(pcm[w%PCM_SLOTS].data,scratch,sizeof(pcm[0].data));
        else memset(pcm[w%PCM_SLOTS].data,0,sizeof(pcm[0].data));
        atomic_store_explicit(&pw,w+1,memory_order_release);
        atomic_store_explicit(&last_published_pcm_us,time_us_32(),memory_order_relaxed);
        atomic_store_explicit(&seen_published_pcm,true,memory_order_release);
        sample_max(&pcm_high,w-pr_now+1);
    }
    sample_max(&work_max_us,time_us_32()-work_started);
}
bool aacp_mic_audio_pending(void) {
    return aacp_mic_capture() && aacp_mic_audio_ready() &&
        atomic_load_explicit(&aw,memory_order_acquire)!=atomic_load_explicit(&ar,memory_order_relaxed) &&
        atomic_load_explicit(&pw,memory_order_relaxed)-atomic_load_explicit(&pr,memory_order_acquire)<PCM_SLOTS;
}
uint32_t aacp_mic_audio_read(int16_t *dst,uint32_t count) {
    uint32_t done=0,epoch=aacp_mic_generation();
    if (!aacp_mic_capture()) return 0;
    /* At most PCM_SLOTS stale frames are discarded; USB never blocks. */
    for (unsigned budget=0; done<count && budget<=PCM_SLOTS; budget++) {
        uint32_t r=atomic_load_explicit(&pr,memory_order_relaxed);
        if (r==atomic_load_explicit(&pw,memory_order_acquire)) break;
        if (pcm[r%PCM_SLOTS].epoch!=epoch) {
            pcm_offset=0;
            atomic_fetch_add_explicit(&pcm_stale,1,memory_order_relaxed);
            atomic_store_explicit(&pr,r+1,memory_order_release);
            continue;
        }
        uint32_t n=FRAME-pcm_offset;
        if (n>count-done) n=count-done;
        memcpy(dst+done,pcm[r%PCM_SLOTS].data+pcm_offset,n*sizeof(*dst));
        done+=n; pcm_offset+=n;
        if (pcm_offset==FRAME) {
            pcm_offset=0;
            atomic_store_explicit(&pr,r+1,memory_order_release);
        }
    }
    return done;
}
uint32_t aacp_mic_audio_packet_samples(void) {
    if(!aacp_mic_capture()){atomic_store(&pcm_primed,false);return 0;}
    uint32_t epoch=aacp_mic_generation();
    if(usb_packet_generation!=epoch) {
        usb_packet_generation=epoch;
        usb_primed_this_generation=false;
    }
    uint32_t r=atomic_load_explicit(&pr,memory_order_relaxed);
    uint32_t w=atomic_load_explicit(&pw,memory_order_acquire),available=0;
    /* A full stale ring must not block priming forever after a reconnect. */
    for(unsigned i=0;i<PCM_SLOTS && r!=w && pcm[r%PCM_SLOTS].epoch!=epoch;i++) {
        pcm_offset=0;atomic_fetch_add_explicit(&pcm_stale,1,memory_order_relaxed);
        atomic_store_explicit(&pr,++r,memory_order_release);
    }
    for(uint32_t i=0;i<PCM_SLOTS && r+i!=w;i++) {
        if(pcm[(r+i)%PCM_SLOTS].epoch==epoch)
            available+=FRAME-(!i?pcm_offset:0);
    }
    usb_packet_available=available;
    const bool was_primed=packet_clock.generation==epoch && packet_clock.primed;
    uint32_t n=mic_clock_packet(&packet_clock,epoch,available);
    usb_packet_rebuffered=was_primed && !packet_clock.primed;
    if(usb_packet_rebuffered)
        atomic_fetch_add_explicit(&usb_rebuffers,1,memory_order_relaxed);
    if(packet_clock.primed)usb_primed_this_generation=true;
    atomic_store_explicit(&pcm_primed,packet_clock.primed,memory_order_relaxed);
    return n;
}
void aacp_mic_audio_note_usb_packet(uint32_t requested,uint32_t supplied) {
    /* Startup prefill does not count as a post-prime fault. Strict USB
     * missing-sample accounting remains owned by usb_capture_note_tx. */
    if(!usb_primed_this_generation || supplied>=requested)return;
    atomic_fetch_add_explicit(&usb_postprime_underruns,1,memory_order_relaxed);
    if(usb_first_written)return;
    usb_first_written=true; /* single USB consumer; publish once */
    uint32_t now=time_us_32();
    uint32_t wa=atomic_load_explicit(&aw,memory_order_acquire);
    uint32_t ra=atomic_load_explicit(&ar,memory_order_acquire);
    uint32_t wp=atomic_load_explicit(&pw,memory_order_acquire);
    uint32_t rp=atomic_load_explicit(&pr,memory_order_acquire);
    uint32_t ad=wa-ra,pd=wp-rp;
    if(ad>AU_SLOTS)ad=AU_SLOTS;
    if(pd>PCM_SLOTS)pd=PCM_SLOTS;
#define F(k,v) atomic_store_explicit(&first_usb_fault.k,(v),memory_order_relaxed)
    F(generation,usb_packet_generation);F(at_us,now);
    F(requested,requested);F(supplied,supplied);
    F(au_depth,ad);F(pcm_depth,pd);
    F(available,usb_packet_available);
    F(au_age_us,atomic_load_explicit(&seen_admitted_au,memory_order_acquire)
        ? now-atomic_load_explicit(&last_admitted_au_us,memory_order_relaxed):UINT32_MAX);
    F(pcm_age_us,atomic_load_explicit(&seen_published_pcm,memory_order_acquire)
        ? now-atomic_load_explicit(&last_published_pcm_us,memory_order_relaxed):UINT32_MAX);
    F(rebuffer,usb_packet_rebuffered);
#undef F
    atomic_store_explicit(&first_usb_fault.valid,true,memory_order_release);
}
#else
/* Diagnostic-only transport keeps AU timing counters without FDK or queues. */
void aacp_mic_audio_init(void) {
    printf("[mic] transport diagnostics: USB microphone sends silence\n");
}
bool aacp_mic_audio_ready(void) { return true; }
void aacp_mic_audio_enqueue(const uint8_t *au,uint8_t len) { (void)au; (void)len; }
void aacp_mic_audio_work(void) {}
bool aacp_mic_audio_pending(void) { return false; }
uint32_t aacp_mic_audio_read(int16_t *dst,uint32_t count) {
    (void)dst; (void)count; return 0;
}
uint32_t aacp_mic_audio_packet_samples(void){return 0;}
void aacp_mic_audio_note_usb_packet(uint32_t requested,uint32_t supplied){
    (void)requested; (void)supplied;
}
#endif

/* Unlocked, eventually consistent snapshot. All shared counters are atomic;
 * the AU/PCM depth fields may lag a concurrently advancing producer/consumer
 * and are saturated at capacity, never used to control the queues. */
void aacp_mic_audio_get_stats(aacp_mic_audio_stats *out) {
    if (!out) return;
    memset(out,0,sizeof(*out));
#define READ_A(field) atomic_load_explicit(&arrival.field,memory_order_relaxed)
    out->generation=aacp_mic_generation();
    out->capture=aacp_mic_capture();
    out->au_observed=READ_A(observed);
    out->arrival_intervals=READ_A(intervals);
    out->arrival_bursts=READ_A(bursts);
    out->arrival_7500us=READ_A(cadence_7500);
    out->arrival_10000us=READ_A(cadence_10000);
    out->arrival_other=READ_A(other);
    out->arrival_gaps=READ_A(gaps);
    out->arrival_last_us=READ_A(arrival_last);
    out->arrival_min_us=READ_A(arrival_min);
    if (!out->arrival_intervals) out->arrival_min_us=0;
    out->arrival_max_us=READ_A(arrival_max);
    out->timestamp_last=READ_A(ts_last);
    out->timestamp_step_reference=READ_A(ts_step_ref);
    out->timestamp_step_last=READ_A(ts_step_last);
    out->timestamp_step_min=READ_A(ts_step_min);
    if (out->timestamp_step_min==UINT32_MAX) out->timestamp_step_min=0;
    out->timestamp_step_max=READ_A(ts_step_max);
    out->timestamp_duplicates=READ_A(ts_dups);
    out->timestamp_backwards=READ_A(ts_backwards);
    out->timestamp_step_changes=READ_A(ts_changes);
    out->timestamp_gap_candidates=READ_A(ts_gaps);
    out->measured_sample_rate=READ_A(measured_rate);
    out->clock_windows=READ_A(clock_windows);
#undef READ_A
#ifdef USBPODS_MIC_DECODE
#define READ_D(field) atomic_load_explicit(&field,memory_order_relaxed)
    out->decoder_ready=aacp_mic_audio_ready();
    uint32_t a_w=READ_D(aw),a_r=READ_D(ar),p_w=READ_D(pw),p_r=READ_D(pr);
    out->au_depth=(a_w-a_r<=AU_SLOTS)?a_w-a_r:AU_SLOTS;
    out->pcm_depth=(p_w-p_r<=PCM_SLOTS)?p_w-p_r:PCM_SLOTS;
    out->au_high_water=READ_D(au_high);
    out->pcm_high_water=READ_D(pcm_high);
    out->au_overflows=READ_D(au_overflows);
    out->pcm_overflows=READ_D(pcm_overflows);
    out->au_stale=READ_D(au_stale);
    out->pcm_stale=READ_D(pcm_stale);
    out->au_inactive=READ_D(au_inactive);
    out->au_wait_last_us=READ_D(au_wait_last_us);
    out->au_wait_max_us=READ_D(au_wait_max_us);
    out->work_max_us=READ_D(work_max_us);
    out->pcm_blocked=READ_D(pcm_blocked);
    out->au_overflow_pcm_full=READ_D(au_overflow_pcm_full);
    out->decoded=READ_D(decoded);
    out->decode_errors=READ_D(errors);
    out->decode_last_us=READ_D(last_us);
    out->decode_max_us=READ_D(max_us);
    out->decode_ema_us=READ_D(ema_us);
    out->decoded_rate=READ_D(last_rate);
    out->decoded_channels=READ_D(last_channels);
    out->decoded_frame_samples=READ_D(last_frame);
    out->pcm_primed=READ_D(pcm_primed);
    out->usb_postprime_underruns=READ_D(usb_postprime_underruns);
    out->usb_rebuffers=READ_D(usb_rebuffers);
    out->usb_first_fault_valid=atomic_load_explicit(&first_usb_fault.valid,memory_order_acquire);
    if(out->usb_first_fault_valid){
        out->usb_first_fault_generation=READ_D(first_usb_fault.generation);
        out->usb_first_fault_at_us=READ_D(first_usb_fault.at_us);
        out->usb_first_fault_requested=READ_D(first_usb_fault.requested);
        out->usb_first_fault_supplied=READ_D(first_usb_fault.supplied);
        out->usb_first_fault_au_depth=READ_D(first_usb_fault.au_depth);
        out->usb_first_fault_pcm_depth=READ_D(first_usb_fault.pcm_depth);
        out->usb_first_fault_available=READ_D(first_usb_fault.available);
        out->usb_first_fault_au_age_us=READ_D(first_usb_fault.au_age_us);
        out->usb_first_fault_pcm_age_us=READ_D(first_usb_fault.pcm_age_us);
        out->usb_first_fault_rebuffer=READ_D(first_usb_fault.rebuffer);
    }
#undef READ_D
#endif
}
void aacp_mic_audio_report(void) {
    aacp_mic_audio_stats s;
    aacp_mic_audio_get_stats(&s);
#ifdef USBPODS_MIC_DECODE
    unsigned long flush=(unsigned long)atomic_load_explicit(&flush_errors,memory_order_relaxed);
#else
    unsigned long flush=0;
#endif
    printf("[mic-cad] gen=%lu au=%lu intervals=%lu burst=%lu 7p5ms=%lu 10ms=%lu other=%lu gap=%lu arrival_us=%lu/%lu/%lu ts=%lu step=%lu ref=%lu range=%lu..%lu dup=%lu back=%lu changed=%lu gap_candidate=%lu\n",
           (unsigned long)s.generation,(unsigned long)s.au_observed,
           (unsigned long)s.arrival_intervals,(unsigned long)s.arrival_bursts,
           (unsigned long)s.arrival_7500us,(unsigned long)s.arrival_10000us,
           (unsigned long)s.arrival_other,(unsigned long)s.arrival_gaps,
           (unsigned long)s.arrival_last_us,(unsigned long)s.arrival_min_us,
           (unsigned long)s.arrival_max_us,(unsigned long)s.timestamp_last,
           (unsigned long)s.timestamp_step_last,(unsigned long)s.timestamp_step_reference,
           (unsigned long)s.timestamp_step_min,(unsigned long)s.timestamp_step_max,
           (unsigned long)s.timestamp_duplicates,(unsigned long)s.timestamp_backwards,
           (unsigned long)s.timestamp_step_changes,(unsigned long)s.timestamp_gap_candidates);
    printf("[mic-dec] active=%lu ready=%lu au_q=%lu/%lu drop=%lu stale=%lu inactive=%lu pcm_q=%lu/%lu drop=%lu stale=%lu ok=%lu errors=%lu flush=%lu decode_us=%lu/max%lu/ema%lu fmt=%luHz/%luch/%lu\n",
           (unsigned long)s.capture,(unsigned long)s.decoder_ready,
           (unsigned long)s.au_depth,(unsigned long)s.au_high_water,
           (unsigned long)s.au_overflows,(unsigned long)s.au_stale,
           (unsigned long)s.au_inactive,(unsigned long)s.pcm_depth,
           (unsigned long)s.pcm_high_water,(unsigned long)s.pcm_overflows,
           (unsigned long)s.pcm_stale,(unsigned long)s.decoded,
           (unsigned long)s.decode_errors,flush,
           (unsigned long)s.decode_last_us,
           (unsigned long)s.decode_max_us,(unsigned long)s.decode_ema_us,
           (unsigned long)s.decoded_rate,(unsigned long)s.decoded_channels,
           (unsigned long)s.decoded_frame_samples);
}
