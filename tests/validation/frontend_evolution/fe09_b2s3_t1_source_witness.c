/* Noninstalled #764 S1 queue submission ↔ APX3 exact-bytes witness.
 * Exclusive facade protects source truth in the test harness only.
 */
#include "fe09_b2s3_t1_source_witness.h"
#include <stdint.h>
#include <string.h>

static int disjoint(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 1;
    if (na > UINTPTR_MAX-x || nb > UINTPTR_MAX-y) return 0;
    return x+na <= y || y+nb <= x;
}
static int valid_flags(int render, uint32_t flags) {
    const uint32_t allowed =
        (render ? FE_B1B0_RENDER_GAP : FE_B1B0_CAPTURE_GAP) |
        FE_B1B0_CLOCK_RESET | FE_B2S1_XRUN;
    return (flags & ~allowed) == 0u;
}
static fe_s3_t1_status map_s1(fe_b2s1_status status) {
    if (status == FE_B2S1_OK) return FE_T1_OK;
    if (status == FE_B2S1_EFULL) return FE_T1_EFULL;
    return FE_T1_EINVAL;
}
fe_s3_t1_status fe_s3_t1_bind(fe_s3_t1_source_witness *a,
                             fe_s3_bridge *b) {
    fe_b2s1_info qi;
    fe_b2s1_dump_sketch map;
    if (!a || !b || !b->queue || !b->writer ||
        !disjoint(a, sizeof(*a), b, sizeof(*b)) ||
        !disjoint(a, sizeof(*a), b->queue, b->s1_state_bytes) ||
        !disjoint(a, sizeof(*a), b->writer, sizeof(*b->writer)) ||
        !disjoint(a, sizeof(*a), b->writer->output,
                  b->writer->capacity) ||
        !disjoint(a, sizeof(*a), b->shadow, b->shadow_bytes) ||
        fe_b2s1_get_info(b->queue, &qi) != FE_B2S1_OK ||
        fe_b2s1_private_dump_sketch(b->queue, &map) != FE_B2S1_OK ||
        (qi.depth != 2u && qi.depth != 4u) ||
        qi.input_hz != b->writer->config.rate_hz ||
        qi.physical_mics != b->writer->config.physical_mics ||
        qi.render_channels != b->writer->config.render_channels ||
        qi.processed || qi.capture_submitted || qi.render_submitted ||
        qi.capture_queued || qi.render_queued || b->processed ||
        b->writer->appended || b->writer->last_sequence ||
        b->writer->config.capture_epoch != 1u ||
        b->writer->config.render_epoch != (qi.render_channels ? 1u : 0u) ||
        map.clock_authority != 0u || b->s1_state_bytes != qi.state_bytes)
        return FE_T1_EINVAL;
    memset(a, 0, sizeof(*a));
    a->bridge = b;
    a->depth = qi.depth;
    a->mics = qi.physical_mics;
    a->rate = qi.input_hz;
    a->render = qi.render_channels;
    a->cap_epoch = 1u;
    a->ref_epoch = qi.render_channels ? 1u : 0u;
    atomic_init(&a->cap_head, 0u);
    atomic_init(&a->cap_tail, 0u);
    atomic_init(&a->ref_head, 0u);
    atomic_init(&a->ref_tail, 0u);
    return FE_T1_OK;
}
fe_s3_t1_status fe_s3_t1_capture_submit(
    fe_s3_t1_source_witness *a, uint64_t seq, uint32_t flags,
    const int16_t *pcm, size_t count) {
    fe_s3_t1_capture *slot;
    uint32_t head, tail, next_epoch;
    fe_b2s1_status result;
    size_t bytes;
    if (!a || !a->bridge || !a->bridge->queue || !pcm ||
        a->depth < 2u || a->depth > FE_S3_T1_MAX_DEPTH ||
        a->mics == 0u || a->mics > 4u ||
        (a->rate != 16000u && a->rate != 32000u && a->rate != 48000u))
        return FE_T1_EINVAL;
    if (!seq || seq <= a->cap_last || !valid_flags(0, flags) ||
        count != (size_t)(a->rate/100u) * a->mics ||
        count > FE_S3_T1_CAP_MAX ||
        (flags && a->cap_epoch == UINT32_MAX))
        return FE_T1_EINVAL;
    bytes=count*sizeof(int16_t);
    if (!disjoint(a, sizeof(*a), pcm, bytes))
        return FE_T1_EINVAL;
    head=atomic_load_explicit(&a->cap_head,memory_order_relaxed);
    tail=atomic_load_explicit(&a->cap_tail,memory_order_acquire);
    if (head-tail >= a->depth) return FE_T1_EFULL;
    slot=&a->cap[head%a->depth];
    memcpy(slot->staging,pcm,bytes);
    result=fe_b2s1_submit_capture(a->bridge->queue,seq,flags,
                                  slot->staging,count);
    if (result != FE_B2S1_OK) return map_s1(result);
    next_epoch=a->cap_epoch+(uint32_t)(flags!=0u);
    memcpy(slot->witness,slot->staging,bytes);
    slot->sequence=seq;
    slot->flags=flags;
    slot->epoch=next_epoch;
    slot->count=count;
    a->cap_last=seq;
    a->cap_epoch=next_epoch;
    atomic_store_explicit(&a->cap_head,head+1u,memory_order_release);
    return FE_T1_OK;
}
fe_s3_t1_status fe_s3_t1_render_submit(
    fe_s3_t1_source_witness *a, uint64_t seq, uint32_t flags,
    const int16_t *pcm, size_t count) {
    fe_s3_t1_render *slot;
    uint32_t head,tail,next_epoch;
    fe_b2s1_status result;
    size_t bytes;
    if (!a || !a->bridge || !a->bridge->queue || !a->render || !pcm ||
        a->depth < 2u || a->depth > FE_S3_T1_MAX_DEPTH ||
        (a->rate != 16000u && a->rate != 32000u && a->rate != 48000u))
        return FE_T1_EINVAL;
    if (!seq || seq <= a->ref_last || !valid_flags(1,flags) ||
        count != (size_t)(a->rate/100u) ||
        count > FE_S3_T1_REF_MAX ||
        (flags && a->ref_epoch == UINT32_MAX))
        return FE_T1_EINVAL;
    bytes=count*sizeof(int16_t);
    if (!disjoint(a,sizeof(*a),pcm,bytes)) return FE_T1_EINVAL;
    head=atomic_load_explicit(&a->ref_head,memory_order_relaxed);
    tail=atomic_load_explicit(&a->ref_tail,memory_order_acquire);
    if (head-tail>=a->depth) return FE_T1_EFULL;
    slot=&a->ref[head%a->depth];
    memcpy(slot->staging,pcm,bytes);
    result=fe_b2s1_submit_render(a->bridge->queue,seq,flags,
                                 slot->staging,count);
    if (result != FE_B2S1_OK) return map_s1(result);
    next_epoch=a->ref_epoch+(uint32_t)(flags!=0u);
    memcpy(slot->witness,slot->staging,bytes);
    slot->sequence=seq;
    slot->flags=flags;
    slot->epoch=next_epoch;
    slot->count=count;
    a->ref_last=seq;
    a->ref_epoch=next_epoch;
    atomic_store_explicit(&a->ref_head,head+1u,memory_order_release);
    return FE_T1_OK;
}
fe_s3_t1_status fe_s3_t1_step(
    fe_s3_t1_source_witness *a, const fe_s2_frame *f,
    float *beam, size_t beam_count,
    float *render_ref, size_t ref_count,
    void *work, size_t work_bytes) {
    uint32_t head,tail,rh=0u,rt=0u;
    fe_s3_t1_capture *cap;
    fe_s3_t1_render *ref=NULL;
    fe_s3_status status;
    size_t ncap,nref;
    if (!a || !a->bridge || !f ||
        a->depth < 2u || a->depth > FE_S3_T1_MAX_DEPTH ||
        !disjoint(a,sizeof(*a),f,sizeof(*f)))
        return FE_T1_EINVAL;
    ncap=(size_t)(a->rate/100u)*a->mics;
    nref=(size_t)(a->rate/100u)*a->render;
    if (!f->capture || f->capture_count!=ncap ||
        f->render_count!=nref || (nref&&!f->render) ||
        (!nref&&f->render) || f->capture_timestamp_valid ||
        f->render_timestamp_valid ||
        !disjoint(a,sizeof(*a),f->capture,ncap*sizeof(int16_t)) ||
        !disjoint(a,sizeof(*a),f->render,nref*sizeof(int16_t)) ||
        beam_count != 160u || !beam ||
        (a->render ? (!render_ref || ref_count != 160u) :
                     (render_ref || ref_count)) ||
        !work || work_bytes == 0u || work_bytes > 65536u ||
        !disjoint(a,sizeof(*a),beam,beam_count*sizeof(float)) ||
        !disjoint(a,sizeof(*a),render_ref,ref_count*sizeof(float)) ||
        !disjoint(a,sizeof(*a),work,work_bytes) ||
        !disjoint(f->capture,ncap*sizeof(int16_t),
                  f->render,nref*sizeof(int16_t)) ||
        !disjoint(f->capture,ncap*sizeof(int16_t),
                  beam,beam_count*sizeof(float)) ||
        !disjoint(f->render,nref*sizeof(int16_t),
                  render_ref,ref_count*sizeof(float)) ||
        !disjoint(f->capture,ncap*sizeof(int16_t),work,work_bytes) ||
        !disjoint(f->render,nref*sizeof(int16_t),work,work_bytes))
        return FE_T1_EINVAL;
    head=atomic_load_explicit(&a->cap_head,memory_order_acquire);
    tail=atomic_load_explicit(&a->cap_tail,memory_order_relaxed);
    if(head==tail) return FE_T1_EEMPTY;
    if(head-tail>a->depth) return FE_T1_ECORE;
    cap=&a->cap[tail%a->depth];
    if(a->render) {
        rh=atomic_load_explicit(&a->ref_head,memory_order_acquire);
        rt=atomic_load_explicit(&a->ref_tail,memory_order_relaxed);
        if(rh==rt) return FE_T1_EEMPTY;
        if(rh-rt>a->depth) return FE_T1_ECORE;
        ref=&a->ref[rt%a->depth];
    }
    /* Both producer-owned S1 submissions completed before release-publish.
     * This is an exact second PCM copy, not an unbound metadata hash.
     */
    if(f->sequence!=cap->sequence || f->capture_flags!=cap->flags ||
       f->capture_epoch!=cap->epoch || f->capture_count!=cap->count ||
       memcmp(f->capture,cap->witness,ncap*sizeof(int16_t))!=0)
        return FE_T1_EFRAME;
    if(ref && (f->sequence!=ref->sequence ||
               f->render_flags!=ref->flags ||
               f->render_epoch!=ref->epoch ||
               f->render_count!=ref->count ||
               memcmp(f->render,ref->witness,nref*sizeof(int16_t))!=0))
        return FE_T1_EFRAME;
    if(!ref && (f->render_flags || f->render_epoch))
        return FE_T1_EFRAME;
    status=fe_s3_bridge_step(a->bridge,f,beam,beam_count,
                             render_ref,ref_count,work,work_bytes);
    if(status!=FE_S3_OK)
        return status==FE_S3_EEMPTY ? FE_T1_EEMPTY :
               status==FE_S3_EMISMATCH ? FE_T1_EFRAME : FE_T1_ECORE;
    atomic_store_explicit(&a->cap_tail,tail+1u,memory_order_release);
    if(ref)
        atomic_store_explicit(&a->ref_tail,rt+1u,memory_order_release);
    return FE_T1_OK;
}
