/* #778: Source-exact ORIGINAL private S2 one-frame APX3 + canonical sidecar.
 * Noninstalled hosted research; NO durable I/O, no rolling 128 frame writer,
 * physical source authentication, public SDK or embedded memory claim.
 */
#include "fe09_b2s3_t2b_b1s1_source_chunks.h"
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#define FNV0 UINT64_C(14695981039346656037)
#define FNV1 UINT64_C(1099511628211)

static void p32(uint8_t *p,uint32_t value) {
    unsigned i;
    for(i=0u;i<4u;++i) p[i]=(uint8_t)(value>>(8u*i));
}
static void p64(uint8_t *p,uint64_t value) {
    unsigned i;
    for(i=0u;i<8u;++i) p[i]=(uint8_t)(value>>(8u*i));
}
static uint32_t g32(const uint8_t *p) {
    unsigned i;
    uint32_t x=0u;
    for(i=0u;i<4u;++i)x|=(uint32_t)p[i]<<(8u*i);
    return x;
}
static uint64_t g64(const uint8_t *p) {
    unsigned i;
    uint64_t x=0u;
    for(i=0u;i<8u;++i)x|=(uint64_t)p[i]<<(8u*i);
    return x;
}
static uint64_t witness(const int16_t *pcm,size_t n) {
    size_t i;
    uint64_t h=FNV0;
    for(i=0u;i<n;++i) {
        uint16_t v=(uint16_t)pcm[i];
        h=(h^(uint8_t)v)*FNV1;
        h=(h^(uint8_t)(v>>8u))*FNV1;
    }
    return h;
}
static uint64_t witness_le(const uint8_t *pcm,size_t bytes) {
    size_t i;
    uint64_t h=FNV0;
    for(i=0u;i<bytes;++i)h=(h^pcm[i])*FNV1;
    return h;
}
static int apart(const void *a,size_t na,const void *b,size_t nb) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(!a||!b||!na||!nb)return 1;
    if(na>UINTPTR_MAX-x||nb>UINTPTR_MAX-y)return 0;
    return x+na<=y||y+nb<=x;
}
static int valid_slots(uint32_t mics,const uint32_t *slots) {
    uint32_t seen=0u,i;
    if(!slots||(mics!=1u&&mics!=2u&&mics!=4u))return 0;
    for(i=0u;i<4u;++i) {
        uint32_t n=slots[i];
        if(i>=mics) {
            if(n!=UINT32_MAX)return 0;
        } else {
            if(n>=mics||(seen&(1u<<n)))return 0;
            seen|=(1u<<n);
        }
    }
    return seen==((1u<<mics)-1u);
}
static int prepared(const fe_b1s1_store *s) {
    const fe_b1s0_state *q;
    if(!s||(q=s->source)==NULL||
       (q->cfg.depth!=2u&&q->cfg.depth!=4u)||
       (q->cfg.physical_mics!=1u&&q->cfg.physical_mics!=2u&&
        q->cfg.physical_mics!=4u)||
       (q->cfg.input_hz!=16000u&&q->cfg.input_hz!=32000u&&
        q->cfg.input_hz!=48000u)||
       q->cfg.render_enabled>1u||
       q->cfg.capture_source_id==0u||
       q->cfg.source_generation==0u||
       !valid_slots(q->cfg.physical_mics,s->physical_to_slot)||
       s->committed>FE_B1S1_MAX_CHUNKS||
       !apart(s,sizeof(*s),q,sizeof(*q))||
       !q->core||!q->core->capture_bf||
       !apart(s,sizeof(*s),q->core,sizeof(*q->core))||
       !apart(s,sizeof(*s),q->core->capture_bf,
              q->core->capture_state_bytes))
        return 0;
    return 1;
}
fe_b1s1_status fe_b1s1_init(fe_b1s1_store *s,
                             fe_b1s0_state *q,const uint32_t slots[4]) {
    uint32_t i;
    if(!s||!q||!slots||q->processed||q->cap_last||q->ref_last||
       !q->core||!q->core->capture_bf||
       !apart(s,sizeof(*s),q,sizeof(*q))||
       !apart(s,sizeof(*s),q->core,sizeof(*q->core))||
       !apart(s,sizeof(*s),q->core->capture_bf,
              q->core->capture_state_bytes)||
       !apart(s,sizeof(*s),slots,4u*sizeof(uint32_t))||
       !valid_slots(q->cfg.physical_mics,slots)||
       atomic_load_explicit(&q->cap_head,memory_order_acquire)!=
       atomic_load_explicit(&q->cap_tail,memory_order_acquire)||
       atomic_load_explicit(&q->ref_head,memory_order_acquire)!=
       atomic_load_explicit(&q->ref_tail,memory_order_acquire))
        return FE_B1S1_REJECT;
    memset(s,0,sizeof(*s));
    s->source=q;
    for(i=0u;i<4u;++i)s->physical_to_slot[i]=slots[i];
    return prepared(s)?FE_B1S1_OK:FE_B1S1_REJECT;
}
static int make_row(uint8_t row[FE_B1S1_ROW_BYTES],
     const fe_b1s1_store *s,const fe_b1s0_capture_slot *cap,
     const fe_b1s0_render_slot *ref,uint32_t event,size_t bytes,
     const uint8_t sha[32]) {
    const fe_b1s0_config *cfg=&s->source->cfg;
    unsigned i;
    memset(row,0,FE_B1S1_ROW_BYTES);
    p32(row,FE_B1S1_MANIFEST_MAGIC);
    p32(row+4u,FE_B1S1_MANIFEST_VERSION);
    p32(row+8u,event);
    p32(row+12u,cfg->input_hz);
    p32(row+16u,cfg->physical_mics);
    p64(row+20u,cfg->source_generation);
    p32(row+28u,cfg->capture_source_id);
    p32(row+32u,cfg->render_source_id);
    p32(row+36u,1u); /* No Capture gap in frozen B1-S0. */
    p32(row+40u,ref?ref->epoch:0u);
    p32(row+44u,ref?ref->reason:0u);
    p64(row+48u,cap->sequence); /* GLOBAL positive Capture sequence. */
    p64(row+56u,UINT64_C(1)); /* New ORIGINAL APX3 starts at 1. */
    p32(row+64u,1u); /* Exactly one actual frame per file. */
    p32(row+68u,(uint32_t)bytes);
    p64(row+72u,cap->pcm_hash);
    p64(row+80u,ref&&event==FE_B1S0_RENDER_PRESENT?
        ref->pcm_hash:0u);
    for(i=0u;i<4u;++i)
        p32(row+88u+4u*i,s->physical_to_slot[i]);
    memcpy(row+104u,sha,32u);
    if(s->committed &&
       fe_b1s1_sha256(s->manifest[s->committed-1u],
                       FE_B1S1_ROW_BYTES,row+136u)!=0)
        return -1;
    /* Manifest prev link attests FULL previous canonical 200-byte row;
     * caller digests this row's canonical [0..168) before publication.
     */
    return 0;
}
fe_b1s1_status fe_b1s1_append_one(fe_b1s1_store *s,
    float *beam,size_t bcount,float *render_ref,size_t rcount,
    void *work,size_t wbytes,fe_b1s0_receipt *result) {
    fe_b1s0_state *q;
    const fe_b1s0_capture_slot *cap;
    const fe_b1s0_render_slot *ref=NULL;
    uint32_t h,t,rh,rt,event=FE_B1S0_RENDER_DISABLED;
    size_t nc,nr,expected_total=0u,stride=0u,finished=0u;
    fe_s2_config scfg;
    fe_s2_frame f;
    fe_s2_writer w;
    fe_s2_stream decoded_precommit;
    uint8_t scratch[FE_B1S1_MAX_CHUNK_BYTES],row[FE_B1S1_ROW_BYTES];
    uint8_t chunk_digest[FE_B1S1_SHA256_BYTES];
    if(!prepared(s)||s->committed>=FE_B1S1_MAX_CHUNKS||
       s->last_global_capture==UINT64_MAX||
       (q=s->source)->processed!=s->last_global_capture)
        return FE_B1S1_REJECT;
    if(!beam||bcount!=160u||!work||!result||
       (q->cfg.render_enabled?(!render_ref||rcount!=160u):
       (render_ref||rcount))||
       !apart(s,sizeof(*s),beam,bcount*sizeof(float))||
       !apart(s,sizeof(*s),render_ref,rcount*sizeof(float))||
       !apart(s,sizeof(*s),work,wbytes)||
       !apart(s,sizeof(*s),result,sizeof(*result))||
       !apart(result,sizeof(*result),beam,bcount*sizeof(float))||
       !apart(result,sizeof(*result),render_ref,rcount*sizeof(float))||
       !apart(result,sizeof(*result),work,wbytes))
        return FE_B1S1_REJECT;
    h=atomic_load_explicit(&q->cap_head,memory_order_acquire);
    t=atomic_load_explicit(&q->cap_tail,memory_order_relaxed);
    if(h==t)return FE_B1S1_PENDING;
    if(h-t>q->cfg.depth)return FE_B1S1_SOURCE;
    cap=&q->cap[t%q->cfg.depth];
    nc=(size_t)(q->cfg.input_hz/100u)*q->cfg.physical_mics;
    nr=(size_t)q->cfg.input_hz/100u;
    if(cap->sequence!=s->last_global_capture+UINT64_C(1)||
       witness(cap->pcm,nc)!=cap->pcm_hash)
        return FE_B1S1_SOURCE;
    if(q->cfg.render_enabled) {
        rh=atomic_load_explicit(&q->ref_head,memory_order_acquire);
        rt=atomic_load_explicit(&q->ref_tail,memory_order_relaxed);
        if(rh==rt)return FE_B1S1_PENDING; /* Not assumed absent! */
        if(rh-rt>q->cfg.depth)return FE_B1S1_SOURCE;
        ref=&q->ref[rt%q->cfg.depth];
        event=ref->event_type;
        if(ref->sequence!=cap->sequence||
           (event!=FE_B1S0_RENDER_PRESENT&&
            event!=FE_B1S0_RENDER_ABSENT))
            return FE_B1S1_SOURCE;
        if(event==FE_B1S0_RENDER_PRESENT) {
            if(ref->reason||!ref->epoch||
               (ref->gap_flag!=0u&&
                ref->gap_flag!=FE_B1S0_RENDER_GAP)||
               witness(ref->pcm,nr)!=ref->pcm_hash)
                return FE_B1S1_SOURCE;
        } else if(ref->reason!=FE_B1S0_ABSENT_SOURCE_REPORTED||
                  ref->pcm_hash||ref->gap_flag)
            return FE_B1S1_SOURCE;
    }
    memset(&scfg,0,sizeof(scfg));
    scfg.rate_hz=q->cfg.input_hz;
    scfg.physical_mics=q->cfg.physical_mics;
    scfg.render_channels=(uint32_t)(event==FE_B1S0_RENDER_PRESENT);
    scfg.capture_source_id=q->cfg.capture_source_id;
    scfg.render_source_id=scfg.render_channels?
        q->cfg.render_source_id:0u;
    scfg.capture_epoch=1u;
    scfg.render_epoch=scfg.render_channels?ref->epoch:0u;
    memcpy(scfg.physical_to_capture_slot,
           s->physical_to_slot,sizeof(scfg.physical_to_capture_slot));
    if(fe_s2_layout(&scfg,1u,&expected_total,&stride)!=FE_S2_OK||
       expected_total>FE_B1S1_MAX_CHUNK_BYTES ||
       fe_s2_writer_begin(&w,scratch,sizeof(scratch),&scfg,1u)
           !=FE_S2_OK)
        return FE_B1S1_ORIGINAL_CODEC;
    memset(&f,0,sizeof(f));
    f.sequence=UINT64_C(1);
    f.capture_epoch=scfg.capture_epoch;
    f.render_epoch=scfg.render_epoch;
    f.capture=cap->pcm;
    f.capture_count=nc;
    f.render=scfg.render_channels?ref->pcm:NULL;
    f.render_count=scfg.render_channels?nr:0u;
    /* Entire ORIGINAL first-party APX3 header, record and CRC must
     * validate *before* the real SPSC worker can release source tails/BF.
     * Postcommit verification alone cannot provide atomic rollback.
     */
    if(fe_s2_writer_append(&w,&f)!=FE_S2_OK||
       fe_s2_writer_finish(&w,&finished)!=FE_S2_OK||
       finished!=expected_total||
       fe_s2_decode(scratch,finished,&decoded_precommit)!=FE_S2_OK||
       decoded_precommit.frames!=1u||
       decoded_precommit.total_bytes!=finished||
       decoded_precommit.config.capture_source_id!=
            q->cfg.capture_source_id||
       decoded_precommit.config.render_channels!=scfg.render_channels||
       decoded_precommit.config.render_source_id!=scfg.render_source_id||
       fe_b1s1_sha256(scratch,finished,chunk_digest)!=0)
        return FE_B1S1_ORIGINAL_CODEC;
    if(make_row(row,s,cap,ref,event,finished,chunk_digest)!=0||
       fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,
                      row+FE_B1S1_ROW_DIGEST_OFFSET)!=0)
        return FE_B1S1_ORIGINAL_CODEC;
    /* LAST FALLIBLE operation is the frozen source-authorized B1-S0
     * worker, itself transactional for BF+Render. Since the consumer has
     * NOT advanced its tail, the staged source PCM is still immutable.
     */
    if(fe_b1s0_process_one(q,beam,bcount,render_ref,rcount,
                           work,wbytes,result)!=FE_B1S0_OK)
        return FE_B1S1_CORE;
    /* Only safe memcpy/assignment remain. No new failure after BF commit. */
    memcpy(s->chunks[s->committed],scratch,finished);
    s->chunk_bytes[s->committed]=(uint32_t)finished;
    memcpy(s->manifest[s->committed],row,FE_B1S1_ROW_BYTES);
    ++s->committed;
    /* SPSC source slot is reusable after process_one released its tail;
     * never dereference cap/ref after that point. Worker-only q.processed
     * is the exact committed global sequence. */
    s->last_global_capture=q->processed;
    return FE_B1S1_OK;
}
typedef struct {
    uint64_t capture_hash,render_hash;
    uint32_t expected_mics, expected_render;
    uint32_t visited;
} replay_witness;
static int replay(const fe_s2_stream *stream,uint32_t idx,
                  uint64_t seq,uint32_t capflags,uint32_t refflags,
                  const uint8_t *cap,size_t capbytes,
                  const uint8_t *ref,size_t refbytes,void *opaque) {
    replay_witness *x=(replay_witness *)opaque;
    if(idx||seq!=UINT64_C(1)||capflags||refflags||
       stream->frames!=1u||
       capbytes!=(size_t)stream->config.rate_hz*
                    stream->config.physical_mics/50u||
       refbytes!=(size_t)stream->config.rate_hz*
                    stream->config.render_channels/50u||
       x->expected_mics!=stream->config.physical_mics||
       x->expected_render!=stream->config.render_channels||
       x->capture_hash!=witness_le(cap,capbytes)||
       (refbytes?(!ref||x->render_hash!=witness_le(ref,refbytes)):
        (ref!=NULL||x->render_hash!=0u)))
        return 1;
    x->visited=1u;
    return 0;
}
fe_b1s1_status fe_b1s1_verify(const fe_b1s1_store *s,
                               uint32_t *checked) {
    uint8_t prior[32]={0};
    uint8_t digest[32],row_digest[32];
    uint32_t i,j;
    fe_s2_stream decoded;
    replay_witness ctx;
    if(!prepared(s)||!checked||s->committed==0u||
       s->last_global_capture!=s->committed ||
       /* A truncated manifest must not be accepted by moving BOTH its
        * retained count and last sequence backwards. The worker-owned
        * frozen source commit count is the independent checkpoint.
        */
       s->source->processed!=s->last_global_capture ||
       !apart(s,sizeof(*s),checked,sizeof(*checked)))
        return FE_B1S1_REJECT;
    for(i=0u;i<s->committed;++i) {
        const uint8_t *row=s->manifest[i];
        const uint8_t *chunk=s->chunks[i];
        uint32_t n=s->chunk_bytes[i],event=g32(row+8u);
        uint32_t with_render=(uint32_t)(event==FE_B1S0_RENDER_PRESENT);
        if(n==0u||n>FE_B1S1_MAX_CHUNK_BYTES||
           g32(row)!=FE_B1S1_MANIFEST_MAGIC||
           g32(row+4u)!=FE_B1S1_MANIFEST_VERSION||
           event>FE_B1S0_RENDER_ABSENT||
           (event==FE_B1S0_RENDER_DISABLED &&
            s->source->cfg.render_enabled)||
           (event!=FE_B1S0_RENDER_DISABLED &&
            !s->source->cfg.render_enabled)||
           g32(row+12u)!=s->source->cfg.input_hz||
           g32(row+16u)!=s->source->cfg.physical_mics||
           g64(row+20u)!=s->source->cfg.source_generation||
           g32(row+28u)!=s->source->cfg.capture_source_id||
           g32(row+32u)!=s->source->cfg.render_source_id||
           g32(row+36u)!=1u||
           (event==FE_B1S0_RENDER_DISABLED&&g32(row+40u)!=0u)||
           (event!=FE_B1S0_RENDER_DISABLED&&g32(row+40u)==0u)||
           (event==FE_B1S0_RENDER_ABSENT?
            g32(row+44u)!=FE_B1S0_ABSENT_SOURCE_REPORTED:
            g32(row+44u)!=0u)||
           g64(row+48u)!=(uint64_t)i+UINT64_C(1)||
           g64(row+56u)!=UINT64_C(1)||
           g32(row+64u)!=1u||
           g32(row+68u)!=n||
           memcmp(row+136u,prior,32u)!=0||
           fe_b1s1_sha256(chunk,n,digest)!=0||
           memcmp(row+104u,digest,32u)!=0||
           fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,
                           row_digest)!=0||
           memcmp(row+FE_B1S1_ROW_DIGEST_OFFSET,row_digest,32u)!=0)
            return FE_B1S1_TAMPER;
        for(j=0u;j<4u;++j)
            if(g32(row+88u+4u*j)!=s->physical_to_slot[j])
                return FE_B1S1_TAMPER;
        if(fe_s2_decode(chunk,n,&decoded)!=FE_S2_OK||
           decoded.frames!=1u||
           decoded.config.rate_hz!=s->source->cfg.input_hz||
           decoded.config.physical_mics!=s->source->cfg.physical_mics||
           decoded.config.render_channels!=with_render||
           decoded.config.capture_source_id!=s->source->cfg.capture_source_id||
           decoded.config.render_source_id!=(with_render?
                s->source->cfg.render_source_id:0u)||
           decoded.config.capture_epoch!=1u||
           decoded.config.render_epoch!=(with_render?g32(row+40u):0u)||
           decoded.config.clock_authority||
           decoded.config.capture_timestamp_valid||
           decoded.config.render_timestamp_valid)
            return FE_B1S1_TAMPER;
        for(j=0u;j<4u;++j)
            if(decoded.config.physical_to_capture_slot[j]!=
               s->physical_to_slot[j])
                return FE_B1S1_TAMPER;
        memset(&ctx,0,sizeof(ctx));
        ctx.expected_mics=s->source->cfg.physical_mics;
        ctx.expected_render=with_render;
        ctx.capture_hash=g64(row+72u);
        ctx.render_hash=g64(row+80u);
        if(fe_s2_replay(chunk,n,replay,&ctx,NULL)!=FE_S2_OK||
           ctx.visited!=1u)
            return FE_B1S1_TAMPER;
        if(fe_b1s1_sha256(row,FE_B1S1_ROW_BYTES,prior)!=0)
            return FE_B1S1_TAMPER;
    }
    *checked=s->committed;
    return FE_B1S1_OK;
}
