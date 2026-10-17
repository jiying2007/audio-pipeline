/* #789 FE09 S3-T3-S1: compact ORIGINAL-S2 APX3 source-owned staging.
 * Noninstalled, synthetic-hosted research only. The serializer, parser,
 * record/header CRC and SHA256 implementation are the frozen FIRST-PARTY
 * fe_s2_* and fe_b1s1_sha256: do not clone those algorithms here.
 * No callback or I/O runs on the Capture/BF worker path.
 */
#include "fe09_b2s3_t3s1_compact_handoff.h"
#include <limits.h>
#include <stdint.h>
#include <string.h>

#if UINT_MAX != UINT32_MAX
#error "T3-S1 requires 32-bit unsigned SPSC counters"
#endif

#define FNV0 UINT64_C(14695981039346656037)
#define FNV1 UINT64_C(1099511628211)

static int apart(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 1;
    if (na > UINTPTR_MAX-x || nb > UINTPTR_MAX-y) return 0;
    return x+na <= y || y+nb <= x;
}
static int valid_slots(uint32_t mics, const uint32_t *slots) {
    uint32_t seen = 0u, i;
    if (!slots || (mics!=1u && mics!=2u && mics!=4u)) return 0;
    for (i=0u; i<4u; ++i) {
        uint32_t n=slots[i];
        if (i>=mics) {
            if (n!=UINT32_MAX) return 0;
        } else {
            if (n>=mics || (seen & (1u<<n))) return 0;
            seen |= 1u<<n;
        }
    }
    return seen==((1u<<mics)-1u);
}
static int valid_cfg(const fe_b1s0_config *c) {
    return c && (c->depth==2u || c->depth==4u) &&
        (c->physical_mics==1u || c->physical_mics==2u ||
         c->physical_mics==4u) &&
        (c->input_hz==16000u || c->input_hz==32000u ||
         c->input_hz==48000u) &&
        c->render_enabled<=1u && c->capture_source_id!=0u &&
        c->source_generation>0u && c->source_generation!=UINT64_MAX &&
        (c->render_enabled ?
          (c->render_source_id!=0u &&
           c->render_source_id!=c->capture_source_id) :
          (c->render_source_id==0u));
}
static uint64_t witness_pcm(const int16_t *pcm, size_t count) {
    uint64_t h=FNV0;
    size_t i;
    for(i=0u; i<count; ++i) {
        uint16_t v=(uint16_t)pcm[i];
        h=(h^(uint8_t)v)*FNV1;
        h=(h^(uint8_t)(v>>8u))*FNV1;
    }
    return h;
}
static uint64_t witness_le(const uint8_t *pcm, size_t bytes) {
    uint64_t h=FNV0;
    size_t i;
    for (i=0u; i<bytes; ++i) h=(h^pcm[i])*FNV1;
    return h;
}
/* Canonical FBS1 sidecar fields, distinct from the original S2 APX3 codec.
 * This stage never implements another APX3 header, record, CRC or parser.
 */
static void p32(uint8_t *p,uint32_t value) {
    unsigned i;
    for (i=0u;i<4u;++i) p[i]=(uint8_t)(value>>(8u*i));
}
static void p64(uint8_t *p,uint64_t value) {
    unsigned i;
    for (i=0u;i<8u;++i) p[i]=(uint8_t)(value>>(8u*i));
}
static uint32_t g32(const uint8_t *p) {
    unsigned i;
    uint32_t x=0u;
    for (i=0u;i<4u;++i) x|=(uint32_t)p[i]<<(8u*i);
    return x;
}
static uint64_t g64(const uint8_t *p) {
    unsigned i;
    uint64_t x=UINT64_C(0);
    for (i=0u;i<8u;++i) x|=(uint64_t)p[i]<<(8u*i);
    return x;
}
static int pinned(const fe_t3s1_ring *s) {
    return s && valid_cfg(&s->pinned_cfg) && s->slot &&
        s->pinned_sink &&
        (s->slot_count==1u || s->slot_count==2u) &&
        s->slot_allocation_bytes==s->slot_count*sizeof(fe_t3s1_slot) &&
        apart(s,sizeof(*s),s->slot,s->slot_allocation_bytes) &&
        valid_slots(s->pinned_cfg.physical_mics,s->physical_to_slot);
}
static int worker_ok(const fe_t3s1_ring *s) {
    const fe_b1s0_state *q;
    if (!pinned(s) || !(q=s->source) || !q->core ||
        !q->core->capture_bf ||
        memcmp(&s->pinned_cfg,&q->cfg,sizeof(q->cfg))!=0 ||
        q->processed!=s->last_global_capture ||
        !apart(s,sizeof(*s),q,sizeof(*q)) ||
        !apart(s->slot,s->slot_allocation_bytes,q,sizeof(*q)) ||
        !apart(s->slot,s->slot_allocation_bytes,q->core,sizeof(*q->core)) ||
        !apart(s->slot,s->slot_allocation_bytes,q->core->capture_bf,
               q->core->capture_state_bytes) ||
        !apart(s,sizeof(*s),q->core,sizeof(*q->core)) ||
        !apart(s,sizeof(*s),q->core->capture_bf,
               q->core->capture_state_bytes))
        return 0;
    return 1;
}
fe_t3s1_status fe_t3s1_init(fe_t3s1_ring *s,fe_b1s0_state *q,
    const uint32_t slots[4],fe_t3s1_slot *storage,
    size_t storage_bytes,uint32_t physical_slots,
    fe_t3s1_outboard_sink outboard_sink,void *outboard_context) {
    fe_b1b1_info info;
    fe_s2_config sc;
    size_t n, stride;
    uint32_t i;
    if (!s||!q||!slots||!storage||!outboard_sink ||
        (physical_slots!=1u&&physical_slots!=2u) ||
        storage_bytes != physical_slots*sizeof(fe_t3s1_slot) ||
        !valid_cfg(&q->cfg)||
        !valid_slots(q->cfg.physical_mics,slots) ||
        !q->core || !q->core->capture_bf ||
        fe_b1b1_get_info(q->core->capture_bf,&info)!=FE_B1B1_OK ||
        info.input_rate_hz!=q->cfg.input_hz ||
        info.physical_mics!=q->cfg.physical_mics ||
        info.render_channels!=0u || info.accepted_frames!=0u ||
        q->processed || q->cap_last || q->ref_last ||
        q->core->capture_sequence || q->core->accepted_capture ||
        !apart(s,sizeof(*s),q,sizeof(*q)) ||
        !apart(s,sizeof(*s),slots,4u*sizeof(uint32_t)) ||
        !apart(s,sizeof(*s),storage,storage_bytes) ||
        !apart(storage,storage_bytes,slots,4u*sizeof(uint32_t)) ||
        !apart(storage,storage_bytes,q,sizeof(*q)) ||
        !apart(storage,storage_bytes,q->core,sizeof(*q->core)) ||
        !apart(storage,storage_bytes,q->core->capture_bf,
               q->core->capture_state_bytes) ||
        !apart(s,sizeof(*s),q->core,sizeof(*q->core)) ||
        !apart(s,sizeof(*s),q->core->capture_bf,
               q->core->capture_state_bytes) ||
        atomic_load_explicit(&q->cap_head,memory_order_acquire)!=
          atomic_load_explicit(&q->cap_tail,memory_order_acquire) ||
        atomic_load_explicit(&q->ref_head,memory_order_acquire)!=
          atomic_load_explicit(&q->ref_tail,memory_order_acquire))
        return FE_T3S1_REJECT;
    memset(&sc,0,sizeof(sc));
    sc.rate_hz=q->cfg.input_hz;
    sc.physical_mics=q->cfg.physical_mics;
    sc.render_channels=q->cfg.render_enabled;
    sc.capture_source_id=q->cfg.capture_source_id;
    sc.render_source_id=q->cfg.render_source_id;
    sc.capture_epoch=1u;
    sc.render_epoch=sc.render_channels?1u:0u;
    memcpy(sc.physical_to_capture_slot,slots,sizeof(sc.physical_to_capture_slot));
    if (fe_s2_layout(&sc,1u,&n,&stride)!=FE_S2_OK ||
        n>FE_T3S1_CHUNK_BYTES || stride==0u)
        return FE_T3S1_REJECT;
    memset(s,0,sizeof(*s));
    memset(storage,0,storage_bytes);
    s->slot=storage;
    s->slot_allocation_bytes=storage_bytes;
    s->source=q;
    s->pinned_cfg=q->cfg;
    s->pinned_sink=outboard_sink;
    s->pinned_sink_context=outboard_context;
    s->slot_count=physical_slots;
    for (i=0u;i<4u;++i) s->physical_to_slot[i]=slots[i];
    atomic_init(&s->head,0u);
    atomic_init(&s->tail,0u);
    return worker_ok(s)?FE_T3S1_OK:FE_T3S1_REJECT;
}
fe_t3s1_status fe_t3s1_seed_wrap_before_start(
    fe_t3s1_ring *s,uint32_t value) {
    uint32_t h,t;
    if (!worker_ok(s) || s->last_global_capture ||
        s->drained_global_capture ||
        atomic_load_explicit(&s->head,memory_order_relaxed)!=
          (h=atomic_load_explicit(&s->tail,memory_order_acquire)) ||
        s->source->cap_last || s->source->ref_last ||
        s->source->processed)
        return FE_T3S1_REJECT;
    t=h;
    if(t!=atomic_load_explicit(&s->head,memory_order_relaxed))
        return FE_T3S1_REJECT;
    atomic_store_explicit(&s->head,value,memory_order_relaxed);
    atomic_store_explicit(&s->tail,value,memory_order_relaxed);
    return FE_T3S1_OK;
}
static int make_row(uint8_t row[FE_T3S1_ROW_BYTES],
    const fe_t3s1_ring *s,const fe_b1s0_capture_slot *cap,
    const fe_b1s0_render_slot *ref,uint32_t event,size_t n,
    const uint8_t chunk_sha[32]) {
    const fe_b1s0_config *cfg=&s->pinned_cfg;
    uint32_t i;
    if (n==0u||n>UINT32_MAX) return 0;
    memset(row,0,FE_T3S1_ROW_BYTES);
    p32(row,FE_B1S1_MANIFEST_MAGIC);
    p32(row+4u,FE_B1S1_MANIFEST_VERSION);
    p32(row+8u,event);
    p32(row+12u,cfg->input_hz);
    p32(row+16u,cfg->physical_mics);
    p64(row+20u,cfg->source_generation);
    p32(row+28u,cfg->capture_source_id);
    p32(row+32u,cfg->render_source_id);
    p32(row+36u,1u);
    p32(row+40u,ref?ref->epoch:0u);
    p32(row+44u,ref?ref->reason:0u);
    p64(row+48u,cap->sequence);
    p64(row+56u,UINT64_C(1));
    p32(row+64u,1u);
    p32(row+68u,(uint32_t)n);
    p64(row+72u,cap->pcm_hash);
    p64(row+80u,ref&&event==FE_B1S0_RENDER_PRESENT?
        ref->pcm_hash:0u);
    for (i=0u;i<4u;++i)
        p32(row+88u+4u*i,s->physical_to_slot[i]);
    memcpy(row+104u,chunk_sha,32u);
    memcpy(row+136u,s->producer_prior_row_sha256,32u);
    return fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,
                           row+FE_B1S1_ROW_DIGEST_OFFSET)==0;
}
fe_t3s1_status fe_t3s1_step(fe_t3s1_ring *s,
    float *beam,size_t bcount,float *render_ref,size_t rcount,
    void *work,size_t wbytes,fe_b1s0_receipt *result) {
    fe_b1s0_state *q;
    const fe_b1s0_capture_slot *cap;
    const fe_b1s0_render_slot *ref=NULL;
    uint32_t head,tail,caphead,captail,refhead,reftail;
    uint32_t event=FE_B1S0_RENDER_DISABLED;
    size_t nc,nr,expected=0u,stride=0u,finished=0u;
    fe_s2_config config;
    fe_s2_frame frame;
    fe_s2_writer writer;
    fe_s2_stream decoded;
    uint8_t scratch[FE_T3S1_CHUNK_BYTES];
    uint8_t row[FE_T3S1_ROW_BYTES],chunk_sha[32],next_prior[32];
    fe_t3s1_slot *slot;
    if (!worker_ok(s) || s->last_global_capture==UINT64_MAX ||
        !beam || bcount!=160u || !work || !result ||
        (s->pinned_cfg.render_enabled?(!render_ref||rcount!=160u):
         (render_ref||rcount)) ||
        !apart(s,sizeof(*s),beam,bcount*sizeof(float)) ||
        !apart(s,sizeof(*s),render_ref,rcount*sizeof(float)) ||
        !apart(s,sizeof(*s),work,wbytes) ||
        !apart(s,sizeof(*s),result,sizeof(*result)) ||
        !apart(s->slot,s->slot_allocation_bytes,beam,bcount*sizeof(float)) ||
        !apart(s->slot,s->slot_allocation_bytes,render_ref,rcount*sizeof(float)) ||
        !apart(s->slot,s->slot_allocation_bytes,work,wbytes) ||
        !apart(s->slot,s->slot_allocation_bytes,result,sizeof(*result)) ||
        !apart(result,sizeof(*result),beam,bcount*sizeof(float)) ||
        !apart(result,sizeof(*result),render_ref,rcount*sizeof(float)) ||
        !apart(result,sizeof(*result),work,wbytes))
        return FE_T3S1_REJECT;
    q=s->source;
    head=atomic_load_explicit(&s->head,memory_order_relaxed);
    tail=atomic_load_explicit(&s->tail,memory_order_acquire);
    if (head-tail>s->slot_count) return FE_T3S1_SOURCE;
    if (head-tail==s->slot_count) return FE_T3S1_FULL;
    caphead=atomic_load_explicit(&q->cap_head,memory_order_acquire);
    captail=atomic_load_explicit(&q->cap_tail,memory_order_relaxed);
    if(caphead==captail)return FE_T3S1_PENDING;
    if(caphead-captail>q->cfg.depth)return FE_T3S1_SOURCE;
    cap=&q->cap[captail%q->cfg.depth];
    nc=(size_t)(q->cfg.input_hz/100u)*q->cfg.physical_mics;
    nr=(size_t)q->cfg.input_hz/100u;
    if(cap->sequence!=s->last_global_capture+UINT64_C(1)||
       witness_pcm(cap->pcm,nc)!=cap->pcm_hash)
        return FE_T3S1_SOURCE;
    if(q->cfg.render_enabled) {
        refhead=atomic_load_explicit(&q->ref_head,memory_order_acquire);
        reftail=atomic_load_explicit(&q->ref_tail,memory_order_relaxed);
        if(refhead==reftail)return FE_T3S1_PENDING;
        if(refhead-reftail>q->cfg.depth)return FE_T3S1_SOURCE;
        ref=&q->ref[reftail%q->cfg.depth];
        event=ref->event_type;
        if(ref->sequence!=cap->sequence ||
           (event!=FE_B1S0_RENDER_PRESENT &&
            event!=FE_B1S0_RENDER_ABSENT))
            return FE_T3S1_SOURCE;
        if(event==FE_B1S0_RENDER_PRESENT) {
            if(ref->reason || !ref->epoch ||
               (ref->gap_flag!=0u &&
                ref->gap_flag!=FE_B1S0_RENDER_GAP) ||
               witness_pcm(ref->pcm,nr)!=ref->pcm_hash)
                return FE_T3S1_SOURCE;
        } else if (ref->reason!=FE_B1S0_ABSENT_SOURCE_REPORTED ||
                   ref->pcm_hash || ref->gap_flag)
            return FE_T3S1_SOURCE;
    }
    memset(&config,0,sizeof(config));
    config.rate_hz=s->pinned_cfg.input_hz;
    config.physical_mics=s->pinned_cfg.physical_mics;
    config.render_channels=(uint32_t)(event==FE_B1S0_RENDER_PRESENT);
    config.capture_source_id=s->pinned_cfg.capture_source_id;
    config.render_source_id=config.render_channels?
        s->pinned_cfg.render_source_id:0u;
    config.capture_epoch=1u;
    config.render_epoch=config.render_channels?ref->epoch:0u;
    memcpy(config.physical_to_capture_slot,s->physical_to_slot,
           sizeof(config.physical_to_capture_slot));
    if(fe_s2_layout(&config,1u,&expected,&stride)!=FE_S2_OK ||
       expected>sizeof(scratch) || stride==0u ||
       fe_s2_writer_begin(&writer,scratch,sizeof(scratch),&config,1u)
         !=FE_S2_OK)
        return FE_T3S1_CODEC;
    memset(&frame,0,sizeof(frame));
    frame.sequence=UINT64_C(1);
    frame.capture_epoch=config.capture_epoch;
    frame.render_epoch=config.render_epoch;
    frame.capture=cap->pcm;
    frame.capture_count=nc;
    frame.render=config.render_channels?ref->pcm:NULL;
    frame.render_count=config.render_channels?nr:0u;
    if(fe_s2_writer_append(&writer,&frame)!=FE_S2_OK ||
       fe_s2_writer_finish(&writer,&finished)!=FE_S2_OK ||
       finished!=expected ||
       fe_s2_decode(scratch,finished,&decoded)!=FE_S2_OK ||
       decoded.frames!=1u || decoded.total_bytes!=finished ||
       decoded.config.capture_source_id!=config.capture_source_id ||
       decoded.config.render_source_id!=config.render_source_id ||
       fe_b1s1_sha256(scratch,finished,chunk_sha)!=0 ||
       !make_row(row,s,cap,ref,event,finished,chunk_sha) ||
       fe_b1s1_sha256(row,FE_T3S1_ROW_BYTES,next_prior)!=0)
        return FE_T3S1_CODEC;
    /* The only remaining fallible operation is ORIGINAL first-party B1S0.
     * Preflight has not mutated ring, BF, source tails or external outputs.
     */
    if(fe_b1s0_process_one(q,beam,bcount,render_ref,rcount,
                           work,wbytes,result)!=FE_B1S0_OK)
        return FE_T3S1_CORE;
    /* Pure bounded copies, then one release publication. No callback/I/O. */
    slot=&s->slot[head%s->slot_count];
    memcpy(slot->apx3,scratch,finished);
    memcpy(slot->canonical_row,row,sizeof(row));
    slot->apx3_bytes=(uint32_t)finished;
    s->last_global_capture=q->processed;
    memcpy(s->producer_prior_row_sha256,next_prior,sizeof(next_prior));
    atomic_store_explicit(&s->head,head+1u,memory_order_release);
    return FE_T3S1_OK;
}
typedef struct {
    uint64_t capture_hash,render_hash;
    uint32_t mics,render,visited;
} replay_witness;
static int replay(const fe_s2_stream *stream,uint32_t index,
    uint64_t seq,uint32_t capflags,uint32_t refflags,
    const uint8_t *cap,size_t ncap,const uint8_t *ref,size_t nref,
    void *context) {
    replay_witness *w=(replay_witness *)context;
    if(index || seq!=UINT64_C(1) || capflags || refflags ||
       stream->frames!=1u || stream->config.physical_mics!=w->mics ||
       stream->config.render_channels!=w->render ||
       ncap!=(size_t)stream->config.rate_hz*w->mics/50u ||
       nref!=(size_t)stream->config.rate_hz*w->render/50u ||
       w->capture_hash!=witness_le(cap,ncap) ||
       (nref ? (!ref||w->render_hash!=witness_le(ref,nref)):
        (ref!=NULL||w->render_hash!=0u)))
        return 1;
    w->visited=1u;
    return 0;
}
fe_t3s1_status fe_t3s1_drain_one(fe_t3s1_ring *s,
    fe_t3s1_outboard_sink sink,void *context,
    fe_t3s1_drain_receipt *receipt) {
    uint32_t head,tail,n,event,i;
    uint8_t chunk_sha[32],row_sha[32],next_prior[32];
    fe_s2_stream decoded;
    replay_witness witness;
    fe_t3s1_drain_receipt result;
    fe_t3s1_slot *slot;
    const uint8_t *row;
    size_t accounted=0u;
    uint32_t with_render;
    if(!pinned(s) || !sink || !receipt ||
       sink!=s->pinned_sink || context!=s->pinned_sink_context ||
       !apart(s,sizeof(*s),receipt,sizeof(*receipt)) ||
       !apart(s->slot,s->slot_allocation_bytes,receipt,sizeof(*receipt)))
        return FE_T3S1_REJECT;
    tail=atomic_load_explicit(&s->tail,memory_order_relaxed);
    head=atomic_load_explicit(&s->head,memory_order_acquire);
    if(head==tail)return FE_T3S1_PENDING;
    if(head-tail>s->slot_count)return FE_T3S1_SOURCE;
    slot=&s->slot[tail%s->slot_count];
    row=slot->canonical_row;
    n=slot->apx3_bytes;
    event=g32(row+8u);
    with_render=(uint32_t)(event==FE_B1S0_RENDER_PRESENT);
    if(n==0u||n>FE_T3S1_CHUNK_BYTES||
       g32(row)!=FE_B1S1_MANIFEST_MAGIC||
       g32(row+4u)!=FE_B1S1_MANIFEST_VERSION||
       event>FE_B1S0_RENDER_ABSENT||
       (s->pinned_cfg.render_enabled ?
          event==FE_B1S0_RENDER_DISABLED :
          event!=FE_B1S0_RENDER_DISABLED) ||
       g32(row+12u)!=s->pinned_cfg.input_hz||
       g32(row+16u)!=s->pinned_cfg.physical_mics||
       g64(row+20u)!=s->pinned_cfg.source_generation||
       g32(row+28u)!=s->pinned_cfg.capture_source_id||
       g32(row+32u)!=s->pinned_cfg.render_source_id||
       g32(row+36u)!=1u||
       (event==FE_B1S0_RENDER_DISABLED && g32(row+40u)!=0u) ||
       (event!=FE_B1S0_RENDER_DISABLED && g32(row+40u)==0u) ||
       (event==FE_B1S0_RENDER_ABSENT?
         g32(row+44u)!=FE_B1S0_ABSENT_SOURCE_REPORTED:
         g32(row+44u)!=0u) ||
       s->drained_global_capture==UINT64_MAX ||
       g64(row+48u)!=s->drained_global_capture+UINT64_C(1)||
       g64(row+56u)!=UINT64_C(1)||
       g32(row+64u)!=1u||
       g32(row+68u)!=n||
       memcmp(row+136u,s->consumer_prior_row_sha256,32u)!=0 ||
       fe_b1s1_sha256(slot->apx3,n,chunk_sha)!=0 ||
       memcmp(row+104u,chunk_sha,32u)!=0 ||
       fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,row_sha)!=0 ||
       memcmp(row+FE_B1S1_ROW_DIGEST_OFFSET,row_sha,32u)!=0)
        return FE_T3S1_TAMPER;
    for(i=0u;i<4u;++i)
        if(g32(row+88u+4u*i)!=s->physical_to_slot[i])
            return FE_T3S1_TAMPER;
    if(fe_s2_decode(slot->apx3,n,&decoded)!=FE_S2_OK ||
       decoded.frames!=1u ||
       decoded.config.rate_hz!=s->pinned_cfg.input_hz ||
       decoded.config.physical_mics!=s->pinned_cfg.physical_mics ||
       decoded.config.render_channels!=with_render ||
       decoded.config.capture_source_id!=s->pinned_cfg.capture_source_id||
       decoded.config.render_source_id!=(with_render?
         s->pinned_cfg.render_source_id:0u)||
       decoded.config.capture_epoch!=1u ||
       decoded.config.render_epoch!=(with_render?g32(row+40u):0u)||
       decoded.config.clock_authority ||
       decoded.config.capture_timestamp_valid ||
       decoded.config.render_timestamp_valid)
        return FE_T3S1_TAMPER;
    for(i=0u;i<4u;++i)
        if(decoded.config.physical_to_capture_slot[i]!=s->physical_to_slot[i])
            return FE_T3S1_TAMPER;
    memset(&witness,0,sizeof(witness));
    witness.mics=s->pinned_cfg.physical_mics;
    witness.render=with_render;
    witness.capture_hash=g64(row+72u);
    witness.render_hash=g64(row+80u);
    if(fe_s2_replay(slot->apx3,n,replay,&witness,NULL)!=FE_S2_OK ||
       witness.visited!=1u ||
       fe_b1s1_sha256(row,FE_T3S1_ROW_BYTES,next_prior)!=0)
        return FE_T3S1_TAMPER;
    /* This callback is only on a separate outboard consumer, NEVER BF. */
    if(sink(slot->apx3,(size_t)n,row,FE_T3S1_ROW_BYTES,
            context,&accounted)!=0 ||
       accounted!=(size_t)n+FE_T3S1_ROW_BYTES)
        return FE_T3S1_SINK_NOT_ADMITTED;
    memset(&result,0,sizeof(result));
    result.source_sequence=g64(row+48u);
    result.source_capture_id=s->pinned_cfg.capture_source_id;
    result.source_render_id=s->pinned_cfg.render_source_id;
    result.render_event=event;
    result.apx3_bytes=n;
    result.canonical_row_bytes=FE_T3S1_ROW_BYTES;
    result.actually_accounted_bytes=accounted;
    /* No external file fsync / trusted ADC clock / board measurement. */
    memcpy(s->consumer_prior_row_sha256,next_prior,sizeof(next_prior));
    s->drained_global_capture=result.source_sequence;
    *receipt=result;
    atomic_store_explicit(&s->tail,tail+1u,memory_order_release);
    return FE_T3S1_OK;
}
