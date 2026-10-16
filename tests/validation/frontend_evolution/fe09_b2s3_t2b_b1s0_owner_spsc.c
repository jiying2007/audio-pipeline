/* FE09 T2-B B1-S0 #776: actual per-source owner SPSC, paired source
 * EVENT decisions with continuous first-party capture-only BF. NO recorder.
 * No thread synchronization is inferred from logical sequence timestamps.
 */
#include "fe09_b2s3_t2b_b1s0_owner_spsc.h"
#include <limits.h>
#include <stdint.h>
#include <string.h>

#if UINT_MAX != UINT32_MAX
#error "B1-S0 requires exact 32-bit atomic unsigned ring counters"
#endif

#define B1S0_FNV0 UINT64_C(14695981039346656037)
#define B1S0_FNVPRIME UINT64_C(1099511628211)

static uint64_t pcm_hash(const int16_t *pcm, size_t count) {
    uint64_t h = B1S0_FNV0;
    size_t i;
    for (i=0u; i<count; ++i) {
        uint16_t x = (uint16_t)pcm[i];
        h=(h^(uint8_t)x)*B1S0_FNVPRIME;
        h=(h^(uint8_t)(x>>8u))*B1S0_FNVPRIME;
    }
    return h;
}
static int separate(const void *a,size_t na,const void *b,size_t nb) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if (!a || !b || !na || !nb) return 1;
    if(na>UINTPTR_MAX-x || nb>UINTPTR_MAX-y) return 0;
    return x+na<=y || y+nb<=x;
}
static int valid_cfg(const fe_b1s0_config *c) {
    return c && (c->depth==2u || c->depth==4u) &&
        (c->physical_mics==1u || c->physical_mics==2u ||
         c->physical_mics==4u) &&
        (c->input_hz==16000u || c->input_hz==32000u ||
         c->input_hz==48000u) && c->render_enabled<=1u &&
        c->source_generation!=0u && c->source_generation!=UINT64_MAX &&
        c->capture_source_id!=0u &&
        (c->render_enabled ?
            (c->render_source_id!=0u &&
             c->render_source_id!=c->capture_source_id) :
            (c->render_source_id==0u));
}
static int state_ok(const fe_b1s0_state *q) {
    return q && valid_cfg(&q->cfg) && q->core &&
        q->core->capture_bf &&
        q->core->input_hz==q->cfg.input_hz &&
        q->core->physical_mics==q->cfg.physical_mics &&
        q->core->capture_state_bytes>0u &&
        q->core->capture_state_bytes<=16384u &&
        q->core->capture_work_bytes>0u &&
        q->core->capture_work_bytes<=32768u &&
        separate(q,sizeof(*q),q->core,sizeof(*q->core)) &&
        separate(q,sizeof(*q),q->core->capture_bf,
                 q->core->capture_state_bytes);
}
fe_b1s0_status fe_b1s0_init(fe_b1s0_state *q,
    const fe_b1s0_config *c, fe_t2b_b0 *core) {
    fe_b1b1_info info;
    if(!q || !valid_cfg(c) || !core || !core->capture_bf ||
       !separate(q,sizeof(*q),c,sizeof(*c)) ||
       !separate(q,sizeof(*q),core,sizeof(*core)) ||
       !separate(q,sizeof(*q),core->capture_bf,core->capture_state_bytes) ||
       !separate(core,sizeof(*core),c,sizeof(*c)) ||
       !separate(core->capture_bf,core->capture_state_bytes,c,sizeof(*c)) ||
       fe_b1b1_get_info(core->capture_bf,&info)!=FE_B1B1_OK ||
       info.input_rate_hz!=c->input_hz ||
       info.physical_mics!=c->physical_mics ||
       info.render_channels!=0u || info.accepted_frames!=0u ||
       info.source.accepted_frames!=0u ||
       core->input_hz!=c->input_hz ||
       core->physical_mics!=c->physical_mics ||
       core->capture_state_bytes!=info.state_bytes ||
       core->capture_work_bytes!=info.work_bytes ||
       core->capture_sequence || core->accepted_capture ||
       core->render_sequence || core->accepted_render ||
       core->render_epoch!=1u)
        return FE_B1S0_REJECT;
    memset(q,0,sizeof(*q));
    q->cfg=*c;
    q->core=core;
    q->producer_ref_epoch=c->render_enabled ? 1u:0u;
    atomic_init(&q->cap_head,0u);
    atomic_init(&q->cap_tail,0u);
    atomic_init(&q->ref_head,0u);
    atomic_init(&q->ref_tail,0u);
    return FE_B1S0_OK;
}
fe_b1s0_status fe_b1s0_seed_wrap_before_start(fe_b1s0_state *q,
                                               uint32_t value) {
    if(!state_ok(q)||q->cap_last||q->ref_last||q->processed||
       q->actual_render_frames ||
       atomic_load_explicit(&q->cap_head,memory_order_acquire)!=
           atomic_load_explicit(&q->cap_tail,memory_order_acquire) ||
       atomic_load_explicit(&q->ref_head,memory_order_acquire)!=
           atomic_load_explicit(&q->ref_tail,memory_order_acquire))
        return FE_B1S0_REJECT;
    /* Qualified ONLY before spawning any producer or worker. */
    atomic_store_explicit(&q->cap_head,value,memory_order_relaxed);
    atomic_store_explicit(&q->cap_tail,value,memory_order_relaxed);
    atomic_store_explicit(&q->ref_head,value,memory_order_relaxed);
    atomic_store_explicit(&q->ref_tail,value,memory_order_relaxed);
    return FE_B1S0_OK;
}
fe_b1s0_status fe_b1s0_capture_submit(fe_b1s0_state *q,
    uint32_t id,uint64_t generation,uint64_t seq,
    const int16_t *pcm,size_t samples) {
    uint32_t h,t;
    fe_b1s0_capture_slot *slot;
    size_t n;
    if(!state_ok(q)) return FE_B1S0_REJECT;
    n=(size_t)(q->cfg.input_hz/100u)*q->cfg.physical_mics;
    if(id!=q->cfg.capture_source_id ||
       generation!=q->cfg.source_generation ||
       !seq || q->cap_last==UINT64_MAX || seq!=q->cap_last+1u ||
       !pcm || samples!=n ||
       !separate(q,sizeof(*q),pcm,n*sizeof(int16_t)) ||
       !separate(q->core,sizeof(*q->core),pcm,n*sizeof(int16_t)) ||
       !separate(q->core->capture_bf,q->core->capture_state_bytes,
                 pcm,n*sizeof(int16_t)))
        return FE_B1S0_REJECT;
    h=atomic_load_explicit(&q->cap_head,memory_order_relaxed);
    t=atomic_load_explicit(&q->cap_tail,memory_order_acquire);
    if(h-t>=q->cfg.depth) return FE_B1S0_FULL;
    slot=&q->cap[h%q->cfg.depth];
    memcpy(slot->pcm,pcm,n*sizeof(int16_t));
    slot->sequence=seq;
    slot->pcm_hash=pcm_hash(slot->pcm,n);
    q->cap_last=seq;
    atomic_store_explicit(&q->cap_head,h+1u,memory_order_release);
    return FE_B1S0_OK;
}
static fe_b1s0_status ref_submit(fe_b1s0_state *q,
    uint32_t id,uint64_t generation,uint64_t seq,
    uint32_t epoch,uint32_t flag,uint32_t kind,uint32_t reason,
    const int16_t *pcm,size_t count) {
    uint32_t h,t,expected_epoch;
    fe_b1s0_render_slot *slot;
    size_t n;
    if(!state_ok(q)||!q->cfg.render_enabled) return FE_B1S0_REJECT;
    n=(size_t)q->cfg.input_hz/100u;
    if(id!=q->cfg.render_source_id ||
       generation!=q->cfg.source_generation ||
       !seq || q->ref_last==UINT64_MAX || seq!=q->ref_last+1u ||
       (kind!=FE_B1S0_RENDER_PRESENT && kind!=FE_B1S0_RENDER_ABSENT))
        return FE_B1S0_REJECT;
    if(kind==FE_B1S0_RENDER_PRESENT) {
        if(!pcm || count!=n || reason || (flag!=0u&&flag!=FE_B1S0_RENDER_GAP) ||
           !separate(q,sizeof(*q),pcm,n*sizeof(int16_t)) ||
           !separate(q->core,sizeof(*q->core),pcm,n*sizeof(int16_t)) ||
           !separate(q->core->capture_bf,q->core->capture_state_bytes,
                     pcm,n*sizeof(int16_t)))
            return FE_B1S0_REJECT;
    } else if(pcm || count || flag || reason!=FE_B1S0_ABSENT_SOURCE_REPORTED) {
        return FE_B1S0_REJECT;
    }
    expected_epoch=q->producer_ref_epoch;
    if(q->ref_last==0u) {
        if(epoch!=1u || flag) return FE_B1S0_REJECT;
    } else {
        if(kind==FE_B1S0_RENDER_PRESENT &&
           q->producer_prior_absent && flag!=FE_B1S0_RENDER_GAP)
            return FE_B1S0_REJECT;
        if(flag && expected_epoch==UINT32_MAX) return FE_B1S0_REJECT;
        expected_epoch+=(uint32_t)(flag!=0u);
        if(epoch!=expected_epoch) return FE_B1S0_REJECT;
    }
    h=atomic_load_explicit(&q->ref_head,memory_order_relaxed);
    t=atomic_load_explicit(&q->ref_tail,memory_order_acquire);
    if(h-t>=q->cfg.depth) return FE_B1S0_FULL;
    slot=&q->ref[h%q->cfg.depth];
    slot->sequence=seq;
    slot->event_type=kind;
    slot->reason=reason;
    slot->epoch=epoch;
    slot->gap_flag=flag;
    if(kind==FE_B1S0_RENDER_PRESENT) {
        memcpy(slot->pcm,pcm,n*sizeof(int16_t));
        slot->pcm_hash=pcm_hash(slot->pcm,n);
    } else slot->pcm_hash=0u; /* Old slot PCM remains unreachable/ignored. */
    q->ref_last=seq;
    q->producer_ref_epoch=epoch;
    q->producer_prior_absent=(uint32_t)(kind==FE_B1S0_RENDER_ABSENT);
    atomic_store_explicit(&q->ref_head,h+1u,memory_order_release);
    return FE_B1S0_OK;
}
fe_b1s0_status fe_b1s0_render_present(fe_b1s0_state *q,
    uint32_t id,uint64_t generation,uint64_t seq,
    uint32_t epoch,uint32_t flag,const int16_t *pcm,size_t n) {
    return ref_submit(q,id,generation,seq,epoch,flag,
        FE_B1S0_RENDER_PRESENT,0u,pcm,n);
}
fe_b1s0_status fe_b1s0_render_absent(fe_b1s0_state *q,
    uint32_t id,uint64_t generation,uint64_t seq,
    uint32_t epoch,uint32_t reason) {
    return ref_submit(q,id,generation,seq,epoch,0u,
        FE_B1S0_RENDER_ABSENT,reason,NULL,0u);
}
fe_b1s0_status fe_b1s0_process_one(fe_b1s0_state *q,
    float *beam,size_t beam_count,float *refout,size_t ref_count,
    void *work,size_t work_bytes,fe_b1s0_receipt *receipt) {
    uint32_t ch,ct,rh=0u,rt=0u,kind=FE_B1S0_RENDER_DISABLED;
    const fe_b1s0_capture_slot *cap;
    const fe_b1s0_render_slot *ref=NULL;
    size_t cn,rn;
    fe_t2b_b0 before;
    fe_b1s0_receipt next;
    float btmp[FE_T2B_B0_FRAMES],rtmp[FE_T2B_B0_FRAMES];
    uint64_t render_ordinal=0u;
    uint32_t gap=0u;
    if(!state_ok(q)) return FE_B1S0_REJECT;
    if(!beam||beam_count!=FE_T2B_B0_FRAMES||
       (q->cfg.render_enabled ?
          (!refout||ref_count!=FE_T2B_B0_FRAMES):
          (refout||ref_count)) ||
       !work||work_bytes<q->core->capture_work_bytes||
       work_bytes>32768u||(uintptr_t)work%FE_B1B1_ALIGNMENT||
       !receipt || !separate(q,sizeof(*q),work,work_bytes) ||
       !separate(q,sizeof(*q),beam,beam_count*sizeof(float)) ||
       !separate(q,sizeof(*q),refout,ref_count*sizeof(float)) ||
       !separate(q,sizeof(*q),receipt,sizeof(*receipt)) ||
       !separate(q->core,sizeof(*q->core),work,work_bytes) ||
       !separate(q->core,sizeof(*q->core),beam,beam_count*sizeof(float)) ||
       !separate(q->core,sizeof(*q->core),refout,ref_count*sizeof(float)) ||
       !separate(q->core,sizeof(*q->core),receipt,sizeof(*receipt)) ||
       !separate(q->core->capture_bf,q->core->capture_state_bytes,
                 beam,beam_count*sizeof(float)) ||
       !separate(q->core->capture_bf,q->core->capture_state_bytes,
                 refout,ref_count*sizeof(float)) ||
       !separate(q->core->capture_bf,q->core->capture_state_bytes,
                 work,work_bytes) ||
       !separate(q->core->capture_bf,q->core->capture_state_bytes,
                 receipt,sizeof(*receipt)) ||
       !separate(receipt,sizeof(*receipt),work,work_bytes) ||
       !separate(receipt,sizeof(*receipt),beam,beam_count*sizeof(float)) ||
       !separate(receipt,sizeof(*receipt),refout,ref_count*sizeof(float)) ||
       !separate(work,work_bytes,beam,beam_count*sizeof(float)) ||
       !separate(work,work_bytes,refout,ref_count*sizeof(float)) ||
       !separate(beam,beam_count*sizeof(float),refout,ref_count*sizeof(float)) ||
       q->processed==UINT64_MAX)
        return FE_B1S0_REJECT;
    ch=atomic_load_explicit(&q->cap_head,memory_order_acquire);
    ct=atomic_load_explicit(&q->cap_tail,memory_order_relaxed);
    if(ch==ct) return FE_B1S0_EMPTY;
    if(ch-ct>q->cfg.depth) return FE_B1S0_CORE;
    cap=&q->cap[ct%q->cfg.depth];
    if(cap->sequence!=q->processed+1u) return FE_B1S0_MISMATCH;
    cn=(size_t)(q->cfg.input_hz/100u)*q->cfg.physical_mics;
    rn=(size_t)q->cfg.input_hz/100u;
    if(pcm_hash(cap->pcm,cn)!=cap->pcm_hash)
        return FE_B1S0_MISMATCH;
    if(q->cfg.render_enabled) {
        rh=atomic_load_explicit(&q->ref_head,memory_order_acquire);
        rt=atomic_load_explicit(&q->ref_tail,memory_order_relaxed);
        if(rh==rt) return FE_B1S0_EMPTY; /* PENDING, not missing Render! */
        if(rh-rt>q->cfg.depth) return FE_B1S0_CORE;
        ref=&q->ref[rt%q->cfg.depth];
        if(ref->sequence!=cap->sequence) return FE_B1S0_MISMATCH;
        kind=ref->event_type;
        if(kind==FE_B1S0_RENDER_PRESENT) {
            if(q->actual_render_frames==UINT64_MAX||
               pcm_hash(ref->pcm,rn)!=ref->pcm_hash||
               ref->reason || (ref->gap_flag &&
                 ref->gap_flag!=FE_B1S0_RENDER_GAP) ||
               (q->worker_prior_absent &&
                 ref->gap_flag!=FE_B1S0_RENDER_GAP))
                return FE_B1S0_MISMATCH;
            render_ordinal=q->actual_render_frames+1u;
            /* Original first-party reference SRC has an independent
             * delivered-frame ordinal, not a shared capture sample clock.
             * Initial real reference starts from zero history even if prior
             * Render ABSENT events preceded its first physical PCM.
             */
            gap=(render_ordinal==1u)?0u:ref->gap_flag;
        } else if(kind==FE_B1S0_RENDER_ABSENT) {
            if(ref->pcm_hash || ref->reason!=
                   FE_B1S0_ABSENT_SOURCE_REPORTED ||
               ref->gap_flag) return FE_B1S0_MISMATCH;
        } else return FE_B1S0_MISMATCH;
    }
    if(q->core->capture_sequence!=q->processed ||
       q->core->accepted_capture!=q->processed ||
       q->core->accepted_render!=q->actual_render_frames)
        return FE_B1S0_CORE;
    before=*q->core;
    if(kind==FE_B1S0_RENDER_PRESENT &&
       fe_t2b_b0_render(q->core,render_ordinal,gap,
           ref->pcm,rn,rtmp,FE_T2B_B0_FRAMES)!=FE_T2B_B0_OK)
        return FE_B1S0_CORE;
    if(fe_t2b_b0_capture(q->core,cap->sequence,cap->pcm,cn,
            btmp,FE_T2B_B0_FRAMES,work,work_bytes)!=FE_T2B_B0_OK) {
        /* First-party B0 Capture rolls back BF on failure; restore only
         * our independently advanced Render SRC and counters.
         */
        *q->core=before;
        return FE_B1S0_CORE;
    }
    memset(&next,0,sizeof(next));
    next.source_generation=q->cfg.source_generation;
    next.capture_source_id=q->cfg.capture_source_id;
    next.render_source_id=q->cfg.render_source_id;
    next.capture_sequence=cap->sequence;
    next.capture_pcm_hash=cap->pcm_hash;
    next.render_event=kind;
    next.render_epoch=ref?ref->epoch:0u;
    next.render_reason=ref?ref->reason:0u;
    next.render_pcm_hash=(ref&&kind==FE_B1S0_RENDER_PRESENT)?
         ref->pcm_hash:0u;
    next.reference_actual_pcm=(uint32_t)(kind==FE_B1S0_RENDER_PRESENT);
    next.mic_bf_progressed=1u;
    /* All physical, recorder, device and public SDK fields remain zero. */
    memcpy(beam,btmp,sizeof(btmp));
    if(kind==FE_B1S0_RENDER_PRESENT)
        memcpy(refout,rtmp,sizeof(rtmp));
    *receipt=next;
    ++q->processed;
    if(kind==FE_B1S0_RENDER_PRESENT) ++q->actual_render_frames;
    q->worker_prior_absent=(uint32_t)(kind==FE_B1S0_RENDER_ABSENT);
    atomic_store_explicit(&q->cap_tail,ct+1u,memory_order_release);
    if(q->cfg.render_enabled)
        atomic_store_explicit(&q->ref_tail,rt+1u,memory_order_release);
    return FE_B1S0_OK;
}
