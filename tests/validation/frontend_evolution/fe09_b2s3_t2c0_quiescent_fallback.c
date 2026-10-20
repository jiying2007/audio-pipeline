/* #784: control-thread only NONSEAMLESS fallback; frozen S1/B1/S2 untouched. */
#include "fe09_b2s3_t2c0_quiescent_fallback.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    const void *pointer;
    size_t bytes;
} fe_t2c0_span;

static int apart(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 0;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 0;
    return x + na <= y || y + nb <= x;
}
static int slots_valid(const fe_t2c0_session *s) {
    uint32_t mic = s->source->cfg.physical_mics, seen = 0u, i;
    if (mic != 1u && mic != 2u && mic != 4u) return 0;
    for (i = 0u; i < 4u; ++i) {
        uint32_t slot = s->archive->physical_to_slot[i];
        if (i >= mic) {
            if (slot != UINT32_MAX) return 0;
        } else {
            if (slot >= mic || (seen & (1u << slot))) return 0;
            seen |= 1u << slot;
        }
    }
    return seen == (1u << mic) - 1u;
}
static int view(fe_t2c0_session *s, uint32_t *capture_wait,
                uint32_t *render_wait) {
    fe_b1s0_state *q;
    fe_b1s1_store *a;
    uint32_t ch, ct, rh, rt, cp, rp;
    if (!s || !(q = s->source) || !(a = s->archive) ||
        a->source != q || !q->core || !q->core->capture_bf ||
        !apart(s, sizeof(*s), q, sizeof(*q)) ||
        !apart(s, sizeof(*s), a, sizeof(*a)) ||
        !apart(q, sizeof(*q), a, sizeof(*a)) ||
        !apart(a, sizeof(*a), q->core, sizeof(*q->core)) ||
        !apart(q, sizeof(*q), q->core, sizeof(*q->core)) ||
        !apart(a, sizeof(*a), q->core->capture_bf,
               q->core->capture_state_bytes) ||
        !apart(q, sizeof(*q), q->core->capture_bf,
               q->core->capture_state_bytes) ||
        !slots_valid(s) ||
        (q->cfg.depth != 2u && q->cfg.depth != 4u) ||
        (q->cfg.input_hz != 16000u && q->cfg.input_hz != 32000u &&
         q->cfg.input_hz != 48000u) ||
        q->cfg.render_enabled > 1u ||
        q->cfg.capture_source_id == 0u ||
        q->cfg.source_generation == 0u ||
        q->cfg.source_generation == UINT64_MAX ||
        ((q->cfg.render_source_id == 0u) !=
         (q->cfg.render_enabled == 0u)) ||
        (q->cfg.render_enabled &&
         q->cfg.capture_source_id == q->cfg.render_source_id) ||
        a->committed > FE_B1S1_MAX_CHUNKS ||
        a->last_global_capture != q->processed ||
        q->processed != a->committed ||
        q->cap_last < q->processed ||
        (q->cfg.render_enabled && q->ref_last < q->processed) ||
        q->core->input_hz != q->cfg.input_hz ||
        q->core->physical_mics != q->cfg.physical_mics ||
        q->core->accepted_capture != q->processed ||
        q->core->capture_sequence != q->processed)
        return 0;
    ch = atomic_load_explicit(&q->cap_head, memory_order_acquire);
    ct = atomic_load_explicit(&q->cap_tail, memory_order_acquire);
    rh = atomic_load_explicit(&q->ref_head, memory_order_acquire);
    rt = atomic_load_explicit(&q->ref_tail, memory_order_acquire);
    cp = ch - ct;
    rp = rh - rt;
    if (cp > q->cfg.depth || rp > q->cfg.depth ||
        q->cap_last - q->processed != (uint64_t)cp ||
        (q->cfg.render_enabled ?
         q->ref_last - q->processed != (uint64_t)rp :
         (q->ref_last != 0u || rp != 0u)) ||
        q->core->accepted_render != q->actual_render_frames)
        return 0;
    *capture_wait = cp;
    *render_wait = rp;
    return 1;
}
static int disjoint_sessions(fe_t2c0_gate *gate,
                             fe_t2c0_session *old,
                             fe_t2c0_session *fresh,
                             fe_t2c0_receipt *receipt) {
    const fe_t2c0_span a[] = {
        {old, sizeof(*old)},
        {old->source, sizeof(*old->source)},
        {old->archive, sizeof(*old->archive)},
        {old->source->core, sizeof(*old->source->core)},
        {old->source->core->capture_bf,
         old->source->core->capture_state_bytes}
    };
    const fe_t2c0_span b[] = {
        {fresh, sizeof(*fresh)},
        {fresh->source, sizeof(*fresh->source)},
        {fresh->archive, sizeof(*fresh->archive)},
        {fresh->source->core, sizeof(*fresh->source->core)},
        {fresh->source->core->capture_bf,
         fresh->source->core->capture_state_bytes}
    };
    size_t i, j;
    if (!apart(gate, sizeof(*gate), receipt, sizeof(*receipt)))
        return 0;
    for (i = 0u; i < sizeof(a) / sizeof(a[0]); ++i) {
        if (!apart(a[i].pointer, a[i].bytes, gate, sizeof(*gate)) ||
            !apart(a[i].pointer, a[i].bytes, receipt, sizeof(*receipt)))
            return 0;
        for (j = 0u; j < sizeof(b) / sizeof(b[0]); ++j)
            if (!apart(a[i].pointer, a[i].bytes,
                       b[j].pointer, b[j].bytes))
                return 0;
    }
    for (j = 0u; j < sizeof(b) / sizeof(b[0]); ++j)
        if (!apart(b[j].pointer, b[j].bytes, gate, sizeof(*gate)) ||
            !apart(b[j].pointer, b[j].bytes, receipt, sizeof(*receipt)))
            return 0;
    return 1;
}
fe_t2c0_status fe_t2c0_init(fe_t2c0_gate *g,
                             fe_t2c0_session *initial) {
    uint32_t cap = 0u, ref = 0u;
    if (!g || !view(initial, &cap, &ref) ||
        !apart(g, sizeof(*g), initial, sizeof(*initial)) ||
        !apart(g, sizeof(*g), initial->source,
               sizeof(*initial->source)) ||
        !apart(g, sizeof(*g), initial->archive,
               sizeof(*initial->archive)) ||
        !apart(g, sizeof(*g), initial->source->core,
               sizeof(*initial->source->core)) ||
        !apart(g, sizeof(*g), initial->source->core->capture_bf,
               initial->source->core->capture_state_bytes))
        return FE_T2C0_DENIED;
    memset(g, 0, sizeof(*g));
    g->required_owners = FE_T2C0_CAPTURE_OWNER | FE_T2C0_WORKER_OWNER |
        (initial->source->cfg.render_enabled ? FE_T2C0_RENDER_OWNER : 0u);
    atomic_init(&g->current, initial);
    atomic_init(&g->generation, initial->source->cfg.source_generation);
    atomic_init(&g->acks, 0u);
    atomic_init(&g->phase, FE_T2C0_RUNNING);
    return FE_T2C0_OK;
}
fe_t2c0_session *fe_t2c0_current(fe_t2c0_gate *g,
                                  uint64_t generation) {
    fe_t2c0_session *s;
    if (!g || !generation ||
        atomic_load_explicit(&g->phase, memory_order_acquire) !=
        FE_T2C0_RUNNING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        generation)
        return NULL;
    s = atomic_load_explicit(&g->current, memory_order_acquire);
    if (!s ||
        atomic_load_explicit(&g->phase, memory_order_acquire) !=
        FE_T2C0_RUNNING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        generation)
        return NULL;
    return s;
}
fe_t2c0_status fe_t2c0_request_stop(fe_t2c0_gate *g,
    uint64_t generation, fe_t2c0_reason reason) {
    if (!g || !generation || generation == UINT64_MAX ||
        reason < FE_T2C0_REASON_RENDER_OWNER_UNAVAILABLE ||
        reason > FE_T2C0_REASON_OPERATOR_RESTART ||
        atomic_load_explicit(&g->phase, memory_order_acquire) !=
        FE_T2C0_RUNNING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        generation)
        return FE_T2C0_DENIED;
    if (reason == FE_T2C0_REASON_RENDER_OWNER_UNAVAILABLE &&
        !(g->required_owners & FE_T2C0_RENDER_OWNER))
        return FE_T2C0_DENIED;
    /* Only one supervisor is authorized to write reason and phase. */
    g->requested_reason = (uint32_t)reason;
    atomic_store_explicit(&g->acks, 0u, memory_order_relaxed);
    atomic_store_explicit(&g->phase, FE_T2C0_STOPPING,
                          memory_order_release);
    return FE_T2C0_OK;
}
fe_t2c0_status fe_t2c0_ack(fe_t2c0_gate *g, uint64_t generation,
                            uint32_t owner) {
    uint32_t prior, next;
    if (!g || !generation || !owner || (owner & (owner - 1u)) ||
        !(g->required_owners & owner) ||
        atomic_load_explicit(&g->phase, memory_order_acquire) !=
        FE_T2C0_STOPPING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        generation)
        return FE_T2C0_DENIED;
    prior = atomic_load_explicit(&g->acks, memory_order_acquire);
    do {
        if (prior & owner) return FE_T2C0_DENIED;
        next = prior | owner;
    } while (!atomic_compare_exchange_weak_explicit(
        &g->acks, &prior, next,
        memory_order_acq_rel, memory_order_acquire));
    return FE_T2C0_OK;
}
fe_t2c0_status fe_t2c0_restart(fe_t2c0_gate *g,
    uint64_t generation, fe_t2c0_session *fresh,
    fe_t2c0_receipt *receipt) {
    fe_t2c0_session *old;
    fe_t2c0_receipt next;
    fe_b1s0_state *oq, *nq;
    uint32_t old_cp, old_rp, new_cp, new_rp, count = 0u, i, max_source;
    if (!g || !receipt || !generation || generation == UINT64_MAX ||
        atomic_load_explicit(&g->phase, memory_order_acquire) !=
        FE_T2C0_STOPPING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        generation ||
        atomic_load_explicit(&g->acks, memory_order_acquire) !=
        g->required_owners ||
        !(old = atomic_load_explicit(&g->current, memory_order_acquire)) ||
        old == fresh ||
        !view(old, &old_cp, &old_rp) ||
        !view(fresh, &new_cp, &new_rp))
        return FE_T2C0_DENIED;
    oq = old->source;
    nq = fresh->source;
    max_source = oq->cfg.capture_source_id >
                 oq->cfg.render_source_id ?
                 oq->cfg.capture_source_id : oq->cfg.render_source_id;
    if (!disjoint_sessions(g, old, fresh, receipt) ||
        oq->cfg.source_generation != generation ||
        nq->cfg.source_generation != generation + UINT64_C(1) ||
        oq->cfg.depth != nq->cfg.depth ||
        oq->cfg.input_hz != nq->cfg.input_hz ||
        oq->cfg.physical_mics != nq->cfg.physical_mics ||
        nq->cfg.capture_source_id <= max_source ||
        (nq->cfg.render_enabled &&
         (nq->cfg.render_source_id <= max_source ||
          nq->cfg.render_source_id == nq->cfg.capture_source_id)) ||
        nq->processed || nq->cap_last || nq->ref_last ||
        nq->actual_render_frames || new_cp || new_rp ||
        nq->core->accepted_capture || nq->core->accepted_render ||
        nq->core->capture_sequence || nq->core->render_sequence ||
        nq->core->render_epoch != 1u ||
        nq->producer_ref_epoch != (nq->cfg.render_enabled ? 1u : 0u) ||
        fresh->archive->committed || fresh->archive->last_global_capture)
        return FE_T2C0_DENIED;
    for (i = 0u; i < 4u; ++i)
        if (old->archive->physical_to_slot[i] !=
            fresh->archive->physical_to_slot[i])
            return FE_T2C0_DENIED;
    if (old->archive->committed &&
        (fe_b1s1_verify(old->archive, &count) != FE_B1S1_OK ||
         count != old->archive->committed))
        return FE_T2C0_SOURCE;
    memset(&next, 0, sizeof(next));
    next.schema_version = 1u;
    next.reason = g->requested_reason;
    next.owners_acknowledged = g->required_owners;
    next.old_capture_source_id = oq->cfg.capture_source_id;
    next.old_render_source_id = oq->cfg.render_source_id;
    next.new_capture_source_id = nq->cfg.capture_source_id;
    next.new_render_source_id = nq->cfg.render_source_id;
    next.old_render_enabled = oq->cfg.render_enabled;
    next.new_render_enabled = nq->cfg.render_enabled;
    next.old_completed_apx3_chunks = old->archive->committed;
    next.quarantined_capture_frames = old_cp;
    next.quarantined_render_events = old_rp;
    next.old_generation = generation;
    next.new_generation = generation + UINT64_C(1);
    next.old_processed_capture = oq->processed;
    next.old_source_capture_submitted = oq->cap_last;
    next.old_render_source_submitted = oq->ref_last;
    if (old_cp) {
        next.lost_capture_start = oq->processed + UINT64_C(1);
        next.lost_capture_end = oq->cap_last;
    }
    if (old->archive->committed)
        memcpy(next.previous_committed_row_sha256,
               old->archive->manifest[old->archive->committed - 1u] +
                   FE_B1S1_ROW_DIGEST_OFFSET, 32u);
    /* all zero authority flags are intentional: no durable IO, physical
     * absence certification, preserved BF history or public SDK here.
     * All checks complete BEFORE the only pointer/generation publication.
     */
    *receipt = next;
    atomic_store_explicit(&g->current, fresh, memory_order_release);
    atomic_store_explicit(&g->generation, next.new_generation,
                          memory_order_release);
    atomic_store_explicit(&g->acks, 0u, memory_order_release);
    g->required_owners =
        FE_T2C0_CAPTURE_OWNER | FE_T2C0_WORKER_OWNER |
        (nq->cfg.render_enabled ? FE_T2C0_RENDER_OWNER : 0u);
    atomic_store_explicit(&g->phase, FE_T2C0_RUNNING,
                          memory_order_release);
    return FE_T2C0_OK;
}
