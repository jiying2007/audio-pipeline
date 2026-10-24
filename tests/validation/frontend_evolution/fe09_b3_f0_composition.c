/* FE09-B3-F0 #837: routing/ownership only; original DSP remains unchanged. */
#include "fe09_b3_f0_composition.h"
#include "core/ap_pipeline_internal.h"
/* Compile unchanged original B1B1 exactly once. Its real layout is needed
 * for complete original-initializer admission, not a guessed ABI mirror. */
#include "fe09_b1b1_single_bf.c"
#include <fenv.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#define B3_MAGIC UINT32_C(0x42334630)
#define FNV0 UINT64_C(14695981039346656037)
#define FNV1 UINT64_C(1099511628211)

static uint64_t byte_hash(uint64_t h, uint8_t b) { return (h ^ b) * FNV1; }
uint64_t fe_b3_f0_hash_bytes(const void *p, size_t n) {
    const uint8_t *b = (const uint8_t *)p;
    uint64_t h = FNV0;
    for (size_t i = 0; i < n; ++i) h = byte_hash(h, b[i]);
    return h;
}
uint64_t fe_b3_f0_hash_s16(const int16_t *p, size_t n) {
    uint64_t h = FNV0;
    for (size_t i = 0; i < n; ++i) {
        uint16_t v = (uint16_t)p[i];
        h = byte_hash(h, (uint8_t)v);
        h = byte_hash(h, (uint8_t)(v >> 8u));
    }
    return h;
}
uint64_t fe_b3_f0_hash_f32(const float *p, size_t n) {
    uint64_t h = FNV0;
    _Static_assert(sizeof(float) == sizeof(uint32_t), "FP32 evidence boundary");
    for (size_t i = 0; i < n; ++i) {
        uint32_t v;
        memcpy(&v, &p[i], sizeof(v));
        for (unsigned k = 0; k < 4u; ++k)
            h = byte_hash(h, (uint8_t)(v >> (8u*k)));
    }
    return h;
}
uint64_t fe_b3_f0_capture_fingerprint(const fe_b1b1 *s,size_t n,
                                      void *scratch,size_t bytes) {
    uint8_t *copy=(uint8_t *)scratch;
    if (!s || !scratch || n<sizeof(*s) || n>bytes || n!=s->allocated)
        return 0u;
    memcpy(copy,s,n);
    memset(copy+offsetof(struct fe_b1b1,source),0,sizeof(s->source));
    memset(copy+offsetof(struct fe_b1b1,array),0,sizeof(s->array));
    return fe_b3_f0_hash_bytes(copy,n);
}
static fe_b1b1_config frozen_capture_config(void) {
    fe_b1b1_config c;
    static const double x[4]={0.0,0.035,0.07,0.105};
    memset(&c,0,sizeof(c));
    c.ingress.struct_size=(uint32_t)sizeof(c.ingress);
    c.ingress.api_version=FE_B1B0_VERSION;
    c.ingress.capture_and_render_rate_hz=16000u;c.ingress.frame_ms=10u;
    c.ingress.physical_mics=4u;c.ingress.active_mic_mask=15u;
    c.array.sample_rate_hz=16000u;c.array.mic_count=4u;c.array.active_mask=15u;
    c.array.reference_mic=0u;c.array.interpolation=FE_ARRAY_FIR33_HANN;
    c.array.direction[1]=1.0;
    for (uint32_t j=0;j<4u;++j) {
        c.ingress.physical_to_capture_slot[j]=j;
        c.array.microphones[j].input_channel=j;
        c.array.microphones[j].gain=1.0;
        c.array.microphones[j].position_m[0]=x[j];
    }
    return c;
}
static int same_fresh_capture(const fe_b1b1 *s,const fe_b1b1 *reference,size_t n) {
    fe_b1b1 actual,expected;
    if (!s || !reference || n<sizeof(*s) || s->allocated!=n || reference->allocated!=n ||
        s->source_offset>=n || s->array_offset>=n ||
        s->source!=(const void *)((const uint8_t *)s+s->source_offset) ||
        s->array!=(const void *)((const uint8_t *)s+s->array_offset)) return 0;
    memcpy(&actual,s,sizeof(actual));memcpy(&expected,reference,sizeof(expected));
    actual.source=NULL;actual.array=NULL;expected.source=NULL;expected.array=NULL;
    /* Outer align16 tail/gaps are not initialized by original B1B1. Compare
     * only the actual original initialized header and both complete child
     * states; unused padding is not a freshness condition. */
    return memcmp(&actual,&expected,sizeof(actual))==0 &&
        s->source_bytes<=n-s->source_offset && s->array_bytes<=n-s->array_offset &&
        memcmp(s->source,reference->source,s->source_bytes)==0 &&
        memcmp(s->array,reference->array,s->array_bytes)==0;
}
static int apart(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 1;
    if (na > UINTPTR_MAX-x || nb > UINTPTR_MAX-y) return 0;
    return x+na <= y || y+nb <= x;
}
static int owner_fixed(const fe_b1s0_config *c) {
    return c->depth == 2u && c->physical_mics == 4u &&
        c->input_hz == 16000u && c->render_enabled == 1u &&
        c->capture_source_id == FE_B3_F0_CAPTURE_ID &&
        c->render_source_id == FE_B3_F0_RENDER_ID &&
        c->source_generation == FE_B3_F0_GENERATION;
}
static int mono_fixed(const ap_config_t *c) {
    return c->io_sample_rate_hz == 16000u &&
        c->internal_sample_rate_hz == 16000u && c->mic_channels == 1u &&
        c->mic_spacing_mm == 35.0f && c->aec_filter_ms == 96u &&
        c->max_delay_ms == 180u && c->initial_delay_ms == 40u &&
        c->aec_mu == 0.22f && c->aec_adapt_stride == 2u &&
        c->ns_floor == 0.12f && c->agc_target_dbfs == -20.0f &&
        c->limiter_dbfs == -2.0f &&
        c->resource_class == AP_RESOURCE_STANDARD &&
        c->stages == FE_B3_F0_STAGE_MASK &&
        c->enable_delay_tracking == 1u &&
        c->enable_clock_drift_compensation == 1u;
}
static int front_fixed(const fe_b1b1_info *i) {
    return i->physical_mics == 4u && i->render_channels == 0u &&
        i->input_rate_hz == 16000u && i->source.physical_mics == 4u &&
        i->source.render_channels == 0u &&
        i->source.capture_clock_authority == 0u &&
        i->source.active_mic_mask == 15u &&
        i->source.existing_first_party_filter_delay_samples == 0u &&
        i->array.mic_count == 4u && i->array.active_mask == 15u &&
        i->array.sample_rate_hz == 16000u &&
        i->array.common_delay_samples == 22u &&
        i->array.interpolation == FE_ARRAY_FIR33_HANN &&
        i->array.direction[0] == 0.0 && i->array.direction[1] == 1.0 &&
        i->array.direction[2] == 0.0 &&
        i->array.transition_total_samples == 0u &&
        i->array.steering_accepted == 0u;
}
static int state_ranges(const fe_b3_f0 *b) {
    const void *p[] = {b, b->owner, b->front, b->capture, b->mono};
    const size_t n[] = {sizeof(*b), sizeof(*b->owner), sizeof(*b->front),
                       b->capture_bytes, b->mono_bytes};
    for (unsigned i = 0; i < 5u; ++i)
        for (unsigned j = i+1u; j < 5u; ++j)
            if (!apart(p[i], n[i], p[j], n[j])) return 0;
    return 1;
}
static int fresh_owner(const fe_b1s0_state *q, const fe_b1b1_info *i) {
    return q->cap_last == 0u && q->ref_last == 0u && q->processed == 0u &&
        q->actual_render_frames == 0u &&
        atomic_load_explicit(&q->cap_head, memory_order_relaxed) == 0u &&
        atomic_load_explicit(&q->cap_tail, memory_order_relaxed) == 0u &&
        atomic_load_explicit(&q->ref_head, memory_order_relaxed) == 0u &&
        atomic_load_explicit(&q->ref_tail, memory_order_relaxed) == 0u &&
        q->core->accepted_capture == 0u && q->core->accepted_render == 0u &&
        q->core->capture_sequence == 0u && q->core->render_sequence == 0u &&
        i->accepted_frames == 0u && i->source.accepted_frames == 0u &&
        i->array.samples_processed == 0u;
}
fe_b3_f0_status fe_b3_f0_bind(fe_b3_f0 *b, fe_b1s0_state *q,
                             ap_pipeline_t *p, size_t mono_bytes) {
    fe_b3_f0 next;
    fe_b1b1_info info;
    ap_config_t config;
    ap_metrics_t metrics;
    _Alignas(16) uint8_t reference_capture_memory[16384u];
    _Alignas(16) uint8_t reference_mono_memory[AP_PIPELINE_STATE_MAX_BYTES];
    fe_b1b1 *reference_capture=NULL;
    ap_pipeline_t *reference_mono=NULL;
    fe_b1b1_config frozen=frozen_capture_config();
    if (!b || !q || !p || !q->core || !q->core->capture_bf ||
        mono_bytes != ap_pipeline_state_size() ||
        mono_bytes > AP_PIPELINE_STATE_MAX_BYTES ||
        (uintptr_t)p % AP_PIPELINE_STATE_ALIGNMENT ||
        !owner_fixed(&q->cfg) || q->core->input_hz != 16000u ||
        q->core->physical_mics != 4u ||
        fe_b1b1_get_info(q->core->capture_bf, &info) != FE_B1B1_OK ||
        !front_fixed(&info) || !fresh_owner(q, &info) ||
        ap_pipeline_compiled_stages() != AP_STAGE_ALL ||
        ap_pipeline_get_config(p, &config) != AP_OK || !mono_fixed(&config))
        return FE_B3_F0_REJECT;
    memset(&metrics, 0, sizeof(metrics));
    ap_pipeline_get_metrics(p, &metrics);
    if (metrics.processed_frames != 0u || metrics.quality != AP_QUALITY_FULL ||
        metrics.aec_backend != AP_AEC_BACKEND_MDF) return FE_B3_F0_REJECT;
    /* Complete original references prove slot/geometry and hidden freshness.
     * processed_frames==0 alone does not exclude preloaded Render history.
     * Bounded constructor scratch exists only at bind, never per frame. */
    memset(reference_capture_memory,0,sizeof(reference_capture_memory));
    memset(reference_mono_memory,0,sizeof(reference_mono_memory));
    if (info.state_bytes>sizeof(reference_capture_memory) ||
        fe_b1b1_init(reference_capture_memory,info.state_bytes,&frozen,&reference_capture)
            !=FE_B1B1_OK ||
        !same_fresh_capture(q->core->capture_bf,reference_capture,info.state_bytes) ||
        ap_pipeline_init(reference_mono_memory,mono_bytes,&config,&reference_mono)!=AP_OK ||
        memcmp(p,reference_mono,mono_bytes)!=0)
        return FE_B3_F0_REJECT;
    memset(&next, 0, sizeof(next));
    next.magic = B3_MAGIC;
    next.owner = q; next.front = q->core; next.capture = q->core->capture_bf;
    next.mono = p; next.mono_bytes = mono_bytes;
    next.capture_bytes = info.state_bytes; next.work_bytes = info.work_bytes;
    next.owner_config = q->cfg; next.mono_config = config;
    /* Check actual output bridge address, not the temporary stack descriptor. */
    {
        const void *ptr[] = {b,q,q->core,q->core->capture_bf,p};
        const size_t len[] = {sizeof(*b),sizeof(*q),sizeof(*q->core),
                              info.state_bytes,mono_bytes};
        for (unsigned i = 0; i < 5u; ++i)
            for (unsigned j = i+1u; j < 5u; ++j)
                if (!apart(ptr[i],len[i],ptr[j],len[j]))
                    return FE_B3_F0_REJECT;
    }
    *b = next;
    return FE_B3_F0_OK;
}
static int preflight(fe_b3_f0 *b, int16_t *out, size_t n,
                     void *work, size_t wn, fe_b3_f0_receipt *r) {
    ap_config_t cfg;
    ap_metrics_t met;
    fe_b1b1_info info;
    const void *ptr[3];
    size_t len[3];
    if (!b || b->magic != B3_MAGIC || b->failed || !b->owner || !b->mono ||
        !b->front || !b->capture || b->accepted >= FE_B3_F0_FRAMES ||
        b->owner->core != b->front || b->front->capture_bf != b->capture ||
        !owner_fixed(&b->owner->cfg) ||
        b->mono_bytes != ap_pipeline_state_size() ||
        !state_ranges(b) || !out || n != FE_B3_F0_HOP || !r || !work ||
        wn < b->work_bytes || wn > 32768u ||
        (uintptr_t)work % FE_B1B1_ALIGNMENT ||
        fegetround() != FE_TONEAREST ||
        ap_pipeline_get_config(b->mono, &cfg) != AP_OK || !mono_fixed(&cfg) ||
        fe_b1b1_get_info(b->capture, &info) != FE_B1B1_OK ||
        !front_fixed(&info) || info.state_bytes != b->capture_bytes ||
        info.work_bytes != b->work_bytes ||
        b->front->capture_state_bytes != b->capture_bytes ||
        b->front->capture_work_bytes != b->work_bytes ||
        b->front->input_hz != 16000u || b->front->physical_mics != 4u ||
        b->owner->processed != b->accepted ||
        b->owner->actual_render_frames != b->present ||
        b->front->accepted_capture != b->accepted ||
        b->front->accepted_render != b->present)
        return 0;
    memset(&met, 0, sizeof(met));
    ap_pipeline_get_metrics(b->mono, &met);
    if (met.processed_frames != b->accepted || met.quality != AP_QUALITY_FULL ||
        met.aec_backend != AP_AEC_BACKEND_MDF) return 0;
    ptr[0] = out; ptr[1] = work; ptr[2] = r;
    len[0] = n*sizeof(*out); len[1] = wn; len[2] = sizeof(*r);
    for (unsigned i = 0; i < 3u; ++i) {
        if (!apart(ptr[i],len[i],b,sizeof(*b)) ||
            !apart(ptr[i],len[i],b->owner,sizeof(*b->owner)) ||
            !apart(ptr[i],len[i],b->front,sizeof(*b->front)) ||
            !apart(ptr[i],len[i],b->capture,b->capture_bytes) ||
            !apart(ptr[i],len[i],b->mono,b->mono_bytes)) return 0;
        for (unsigned j = i+1u; j < 3u; ++j)
            if (!apart(ptr[i],len[i],ptr[j],len[j])) return 0;
    }
    return 1;
}
static int16_t to_s16(float x, uint64_t *clips) {
    long n;
    if (x >= 1.0f) { ++*clips; return INT16_MAX; }
    if (x <= -1.0f) { if (x < -1.0f) ++*clips; return INT16_MIN; }
    n = lrintf(x*32768.0f);
    if (n > INT16_MAX) { ++*clips; return INT16_MAX; }
    if (n < INT16_MIN) { ++*clips; return INT16_MIN; }
    return (int16_t)n;
}
static fe_b3_f0_status fatal(fe_b3_f0 *b) {
    b->failed = 1u;
    return FE_B3_F0_FATAL;
}
fe_b3_f0_status fe_b3_f0_process_one(fe_b3_f0 *b,
    int16_t *output, size_t count, void *work, size_t work_bytes,
    fe_b3_f0_receipt *receipt) {
    fe_b3_f0_receipt next;
    float ref[FE_B3_F0_HOP];
    int16_t mono[FE_B3_F0_HOP], reference[FE_B3_F0_HOP], out[FE_B3_F0_HOP];
    fe_b1s0_status status;
    uint32_t kind;
    const uint32_t poison = UINT32_C(0x7fc12345);
    uint64_t cbefore;
    if (b && b->magic == B3_MAGIC && b->failed) return FE_B3_F0_FATAL;
    if (!preflight(b,output,count,work,work_bytes,receipt))
        return FE_B3_F0_REJECT;
    memset(&next,0,sizeof(next));
    for (unsigned k = 0; k < FE_B3_F0_HOP; ++k)
        memcpy(&ref[k],&poison,sizeof(poison));
    status = fe_b1s0_process_one(b->owner,next.beam,FE_B3_F0_HOP,
        ref,FE_B3_F0_HOP,work,work_bytes,&next.source);
    if (status == FE_B1S0_EMPTY) return FE_B3_F0_PENDING;
    if (status != FE_B1S0_OK) return FE_B3_F0_REJECT;
    /* Source committed. Frozen subsequent guards are proven satisfied.
     * Any violation from here is fatal evidence, never ordinary REJECT. */
    kind = next.source.render_event;
    if (next.source.capture_sequence != b->accepted+1u ||
        next.source.source_generation != FE_B3_F0_GENERATION ||
        (kind != FE_B1S0_RENDER_PRESENT && kind != FE_B1S0_RENDER_ABSENT))
        return fatal(b);
    if (kind == FE_B1S0_RENDER_ABSENT) {
        next.absent_reference_untouched = 1u;
        for (unsigned k=0;k<FE_B3_F0_HOP;++k) {
            uint32_t bits;
            memcpy(&bits,&ref[k],sizeof(bits));
            if (bits != poison) return fatal(b);
        }
    }
    for (unsigned k=0;k<FE_B3_F0_HOP;++k) {
        if (!isfinite(next.beam[k])) return fatal(b);
        mono[k] = to_s16(next.beam[k],&next.beam_clips);
        if (kind == FE_B1S0_RENDER_PRESENT) {
            if (!isfinite(ref[k])) return fatal(b);
            reference[k] = to_s16(ref[k],&next.reference_clips);
        }
    }
    if (b->prior_event != 0u && b->prior_event != kind) {
        cbefore = fe_b3_f0_hash_bytes(b->capture,b->capture_bytes);
        if (ap_pipeline_notify_stream_discontinuity(b->mono,
                AP_DISCONTINUITY_RENDER_GAP,1u) != AP_OK)
            return fatal(b);
        next.notify_capture_preserved =
            (uint32_t)(cbefore == fe_b3_f0_hash_bytes(b->capture,b->capture_bytes));
        if (!next.notify_capture_preserved) return fatal(b);
        next.explicit_notify = 1u;
    }
    if (kind == FE_B1S0_RENDER_PRESENT &&
        ap_pipeline_push_render(b->mono,reference,FE_B3_F0_HOP) != AP_OK)
        return fatal(b);
    if (ap_pipeline_process_capture(b->mono,mono,FE_B3_F0_HOP,out) != AP_OK)
        return fatal(b);
    ++b->accepted;
    b->present += (uint64_t)(kind == FE_B1S0_RENDER_PRESENT);
    b->absent += (uint64_t)(kind == FE_B1S0_RENDER_ABSENT);
    b->notifications += next.explicit_notify;
    b->beam_clips += next.beam_clips;
    b->reference_clips += next.reference_clips;
    b->prior_event = kind;
    memcpy(output,out,sizeof(out));
    *receipt = next;
    return FE_B3_F0_OK;
}
