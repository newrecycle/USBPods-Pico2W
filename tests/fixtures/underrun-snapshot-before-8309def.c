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
