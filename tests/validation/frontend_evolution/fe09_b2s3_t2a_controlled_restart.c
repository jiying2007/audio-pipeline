/* FE09 S3-T2-A (#769) CONTROL ONLY: no audio-thread or shipping changes. */
#include "fe09_b2s3_t2a_controlled_restart.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

static int separate(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 0;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 0;
    return x + na <= y || y + nb <= x;
}
typedef struct {
    const void *ptr;
    size_t len;
} span_t;
static int source_view(fe_s3_t1_source_witness *w,
                       fe_b2s1_info *q) {
    fe_s3_bridge *b;
    fe_s2_writer *writer;
    size_t total = 0u, stride = 0u;
    if (!w || !q || !(b = w->bridge) || !b->queue ||
        !(writer = b->writer) || !writer->output || !b->shadow ||
        w->mics == 0u || w->mics > 4u || w->render > 1u ||
        (w->depth != 2u && w->depth != 4u) ||
        (w->rate != 16000u && w->rate != 32000u && w->rate != 48000u))
        return 0;
    if (fe_b2s1_get_info(b->queue, q) != FE_B2S1_OK ||
        q->state_bytes == 0u || q->state_bytes > 65536u ||
        q->physical_mics != w->mics || q->depth != w->depth ||
        q->render_channels != w->render || q->input_hz != w->rate ||
        b->s1_state_bytes != q->state_bytes ||
        writer->config.physical_mics != w->mics ||
        writer->config.render_channels != w->render ||
        writer->config.rate_hz != w->rate ||
        b->capture_source_id != writer->config.capture_source_id ||
        b->render_source_id != writer->config.render_source_id ||
        writer->config.capture_source_id == 0u ||
        ((writer->config.render_source_id == 0u) != (w->render == 0u)) ||
        (w->render && writer->config.render_source_id ==
                       writer->config.capture_source_id) ||
        writer->config.clock_authority != 0u ||
        writer->config.capture_timestamp_valid != 0u ||
        writer->config.render_timestamp_valid != 0u ||
        writer->config.capture_epoch == 0u ||
        writer->config.render_epoch != (w->render ? 1u : 0u) ||
        b->processed != writer->appended ||
        writer->target_frames == 0u ||
        writer->target_frames > FE_S2_MAX_FRAMES ||
        fe_s2_layout(&writer->config, writer->target_frames,
                     &total, &stride) != FE_S2_OK ||
        writer->total_bytes != total || writer->record_stride != stride ||
        writer->appended > writer->target_frames ||
        writer->capacity == 0u || writer->capacity > FE_S2_MAX_BYTES ||
        b->shadow_bytes == 0u || b->shadow_bytes > FE_S2_MAX_BYTES ||
        b->record_bytes != writer->total_bytes ||
        b->record_stride != writer->record_stride ||
        b->record_bytes > writer->capacity ||
        b->record_bytes > b->shadow_bytes)
        return 0;
    return 1;
}
static int memory_separate(fe_s3_t1_source_witness *old,
                           const fe_b2s1_info *old_q,
                           fe_s3_t1_source_witness *next,
                           const fe_b2s1_info *new_q,
                           const fe_t2a_gate *gate,
                           const fe_t2a_receipt *receipt) {
    size_t i, j;
    fe_s3_bridge *a = old->bridge, *b = next->bridge;
    const span_t oa[] = {
        {old, sizeof(*old)}, {a, sizeof(*a)},
        {a->queue, old_q->state_bytes},
        {a->writer, sizeof(*a->writer)},
        {a->writer->output, a->writer->capacity},
        {a->shadow, a->shadow_bytes}
    };
    const span_t nb[] = {
        {next, sizeof(*next)}, {b, sizeof(*b)},
        {b->queue, new_q->state_bytes},
        {b->writer, sizeof(*b->writer)},
        {b->writer->output, b->writer->capacity},
        {b->shadow, b->shadow_bytes}
    };
    for (i = 0u; i < sizeof(oa)/sizeof(oa[0]); ++i) {
        if (!separate(oa[i].ptr, oa[i].len, gate, sizeof(*gate)) ||
            !separate(oa[i].ptr, oa[i].len, receipt, sizeof(*receipt)))
            return 0;
        for (j = 0u; j < sizeof(nb)/sizeof(nb[0]); ++j)
            if (!separate(oa[i].ptr, oa[i].len,
                          nb[j].ptr, nb[j].len))
                return 0;
    }
    for (i = 0u; i < sizeof(nb)/sizeof(nb[0]); ++i)
        if (!separate(nb[i].ptr, nb[i].len, gate, sizeof(*gate)) ||
            !separate(nb[i].ptr, nb[i].len, receipt, sizeof(*receipt)))
            return 0;
    return separate(gate, sizeof(*gate), receipt, sizeof(*receipt));
}
fe_t2a_status fe_t2a_init(fe_t2a_gate *g,
    fe_s3_t1_source_witness *first, uint64_t generation) {
    fe_b2s1_info qi;
    if (!g || !generation || generation == UINT64_MAX ||
        !source_view(first, &qi) ||
        !separate(g, sizeof(*g), first, sizeof(*first)) ||
        !separate(g, sizeof(*g), first->bridge, sizeof(*first->bridge)) ||
        !separate(g, sizeof(*g), first->bridge->queue, qi.state_bytes) ||
        !separate(g, sizeof(*g), first->bridge->writer,
                  sizeof(*first->bridge->writer)) ||
        !separate(g, sizeof(*g), first->bridge->writer->output,
                  first->bridge->writer->capacity) ||
        !separate(g, sizeof(*g), first->bridge->shadow,
                  first->bridge->shadow_bytes))
        return FE_T2A_DENIED;
    memset(g, 0, sizeof(*g));
    g->required_owners = FE_T2A_CAPTURE_OWNER | FE_T2A_WORKER_OWNER |
        (first->render ? FE_T2A_RENDER_OWNER : 0u);
    atomic_init(&g->acknowledgments, 0u);
    atomic_init(&g->generation, generation);
    atomic_init(&g->current, first);
    atomic_init(&g->phase, FE_T2A_RUNNING);
    return FE_T2A_OK;
}
fe_s3_t1_source_witness *fe_t2a_session(fe_t2a_gate *g,
                                        uint64_t expected_generation) {
    fe_s3_t1_source_witness *current;
    if (!g || !expected_generation ||
        atomic_load_explicit(&g->phase, memory_order_acquire) != FE_T2A_RUNNING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        expected_generation)
        return NULL;
    current = atomic_load_explicit(&g->current, memory_order_acquire);
    if (atomic_load_explicit(&g->phase, memory_order_acquire) != FE_T2A_RUNNING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        expected_generation)
        return NULL;
    return current;
}
fe_t2a_status fe_t2a_request_stop(fe_t2a_gate *g,
    uint64_t expected_generation, fe_t2a_reason reason) {
    if (!g || expected_generation == UINT64_MAX ||
        !expected_generation || reason < FE_T2A_REASON_RENDER_ABSENT ||
        reason > FE_T2A_REASON_XRUN ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        expected_generation ||
        atomic_load_explicit(&g->phase, memory_order_acquire) != FE_T2A_RUNNING)
        return FE_T2A_DENIED;
    /* Exactly one independent supervisor controls requests/restarts.
     * Atomic phase publication prevents owners from starting new work.
     */
    g->requested_reason = (uint32_t)reason;
    atomic_store_explicit(&g->acknowledgments, 0u, memory_order_relaxed);
    atomic_store_explicit(&g->phase, FE_T2A_STOPPING, memory_order_release);
    return FE_T2A_OK;
}
fe_t2a_status fe_t2a_ack_stopped(fe_t2a_gate *g,
    uint64_t expected_generation, uint32_t owner) {
    uint32_t prior, desired;
    if (!g || !expected_generation || !owner ||
        (owner & (owner - 1u)) != 0u ||
        (owner & g->required_owners) != owner ||
        atomic_load_explicit(&g->phase, memory_order_acquire) !=
        FE_T2A_STOPPING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        expected_generation)
        return FE_T2A_DENIED;
    prior = atomic_load_explicit(&g->acknowledgments, memory_order_acquire);
    do {
        if ((prior & owner) != 0u) return FE_T2A_DENIED;
        desired = prior | owner;
    } while (!atomic_compare_exchange_weak_explicit(
        &g->acknowledgments, &prior, desired,
        memory_order_acq_rel, memory_order_acquire));
    return FE_T2A_OK;
}
fe_t2a_status fe_t2a_restart(fe_t2a_gate *g,
    uint64_t expected_generation, fe_s3_t1_source_witness *next,
    fe_t2a_receipt *receipt) {
    fe_s3_t1_source_witness *old;
    fe_s3_bridge *a, *b;
    fe_s2_writer *ow, *nw;
    fe_b2s1_info qi, ni;
    fe_t2a_receipt entry;
    uint32_t old_cap, old_ref, new_cap, new_ref, max_old_source, i;
    if (!g || !receipt || !expected_generation ||
        expected_generation == UINT64_MAX ||
        atomic_load_explicit(&g->phase, memory_order_acquire) !=
        FE_T2A_STOPPING ||
        atomic_load_explicit(&g->generation, memory_order_acquire) !=
        expected_generation ||
        atomic_load_explicit(&g->acknowledgments, memory_order_acquire) !=
        g->required_owners ||
        g->requested_reason < (uint32_t)FE_T2A_REASON_RENDER_ABSENT ||
        g->requested_reason > (uint32_t)FE_T2A_REASON_XRUN ||
        !(old = atomic_load_explicit(&g->current, memory_order_acquire)) ||
        !source_view(old, &qi) || !source_view(next, &ni))
        return FE_T2A_DENIED;
    a = old->bridge; b = next->bridge;
    ow = a->writer; nw = b->writer;
    old_cap = ow->config.capture_source_id;
    old_ref = ow->config.render_source_id;
    new_cap = nw->config.capture_source_id;
    new_ref = nw->config.render_source_id;
    max_old_source = old_cap > old_ref ? old_cap : old_ref;
    if (qi.depth != ni.depth || qi.physical_mics != ni.physical_mics ||
        qi.render_channels != ni.render_channels || qi.input_hz != ni.input_hz ||
        !memory_separate(old, &qi, next, &ni, g, receipt) ||
        new_cap <= max_old_source ||
        (next->render && (new_ref <= max_old_source ||
                          new_ref == new_cap)) ||
        (next->render == 0u && new_ref != 0u) ||
        ni.processed != 0u || ni.capture_submitted != 0u ||
        ni.render_submitted != 0u || ni.capture_queued != 0u ||
        ni.render_queued != 0u ||
        nw->appended != 0u || nw->last_sequence != 0u ||
        b->processed != 0u || nw->config.capture_epoch != 1u ||
        nw->config.render_epoch != (next->render ? 1u : 0u) ||
        nw->current_capture_epoch != 1u ||
        nw->current_render_epoch != (next->render ? 1u : 0u) ||
        next->cap_epoch != 1u ||
        next->ref_epoch != (next->render ? 1u : 0u) ||
        next->cap_last != 0u || next->ref_last != 0u ||
        atomic_load_explicit(&next->cap_head, memory_order_acquire) != 0u ||
        atomic_load_explicit(&next->cap_tail, memory_order_acquire) != 0u ||
        atomic_load_explicit(&next->ref_head, memory_order_acquire) != 0u ||
        atomic_load_explicit(&next->ref_tail, memory_order_acquire) != 0u)
        return FE_T2A_DENIED;
    for (i = 0u; i < 4u; ++i)
        if (ow->config.physical_to_capture_slot[i] !=
            nw->config.physical_to_capture_slot[i])
            return FE_T2A_DENIED;
    memset(&entry, 0, sizeof(entry));
    entry.schema_version = 1u;
    entry.reason = g->requested_reason;
    entry.owner_acks = g->required_owners;
    entry.old_capture_source_id = old_cap;
    entry.old_render_source_id = old_ref;
    entry.new_capture_source_id = new_cap;
    entry.new_render_source_id = new_ref;
    entry.old_capture_epoch = old->cap_epoch;
    entry.old_render_epoch = old->ref_epoch;
    entry.fresh_capture_epoch = next->cap_epoch;
    entry.fresh_render_epoch = next->ref_epoch;
    entry.old_capture_queued = qi.capture_queued;
    entry.old_render_queued = qi.render_queued;
    entry.old_recorder_committed = ow->appended;
    entry.old_recorder_target = ow->target_frames;
    entry.old_recorder_quarantined = 1u;
    entry.mic_bf_history_preserved = 0u;
    entry.public_sdk_admitted = 0u;
    entry.old_generation = expected_generation;
    entry.new_generation = expected_generation + 1u;
    entry.old_processed = qi.processed;
    entry.old_capture_sequence = qi.capture_sequence;
    entry.old_render_sequence = qi.render_sequence;
    /* Exactly one control thread owns publication. All prior owners ACKed,
     * next owners do not exist yet. Publish new pointer and generation first;
     * publish RUNNING last with release order.
     */
    g->last_receipt = entry;
    *receipt = entry;
    atomic_store_explicit(&g->current, next, memory_order_release);
    atomic_store_explicit(&g->generation, entry.new_generation,
                          memory_order_release);
    atomic_store_explicit(&g->acknowledgments, 0u, memory_order_release);
    atomic_store_explicit(&g->phase, FE_T2A_RUNNING, memory_order_release);
    return FE_T2A_OK;
}
