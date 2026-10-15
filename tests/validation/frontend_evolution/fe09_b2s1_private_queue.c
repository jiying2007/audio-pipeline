/* FE09-R2B2-S1 first-party research: bounded 10ms capture+render SPSC queues.
 * Only the qualified B1B-S1 first-party SRC/FIR33 implementation processes
 * samples. No heap, I/O, locks, measured clock authority or 2.x SDK changes.
 */
#include "fe09_b2s1_private_queue.h"
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#define B2S1_MAGIC UINT32_C(0x42325331)
#define B2S1_MAX_STATE (64u * 1024u)
#define B2S1_MAX_WORK (64u * 1024u)
#define B2S1_DUMP_ENDIAN_TAG UINT32_C(0x01020304)

typedef struct {
    uint64_t sequence;
    uint32_t flags;
    int16_t samples[FE_B2S1_MAX_CAPTURE_SCALARS];
} capture_slot_t;

typedef struct {
    uint64_t sequence;
    uint32_t flags;
    int16_t samples[FE_B2S1_MAX_SOURCE_SAMPLES];
} render_slot_t;

struct fe_b2s1_queue {
    uint32_t magic, depth, rate, mic_count, has_render, input_samples;
    uint32_t source_slots[4];
    size_t allocated, core_offset, core_bytes, core_work_bytes, total_work_bytes;
    fe_b1b1 *core;
    atomic_uint capture_head, capture_tail, render_head, render_tail;
    atomic_uint capture_high_water, render_high_water;
    /* Single producer of each source owns its last_sequence and submitted. */
    uint64_t capture_submitted, render_submitted, capture_sequence, render_sequence;
    /* Only the worker writes processed. Metrics are queried while quiescent. */
    uint64_t processed;
    capture_slot_t capture[FE_B2S1_MAX_DEPTH];
    render_slot_t render[FE_B2S1_MAX_DEPTH];
};

static int disjoint(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 1;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 0;
    return x + na <= y || y + nb <= x;
}
static size_t align16(size_t value) {
    if (value > SIZE_MAX - 15u) return 0u;
    return (value + 15u) & ~(size_t)15u;
}
static int valid_depth(uint32_t n) {
    return n == 2u || n == 4u;
}
static size_t sizes(const fe_b2s1_config *cfg, size_t *offset,
                    size_t *core_bytes, size_t *work_bytes) {
    size_t start, total;
    uint32_t i, n, rate;
    if (!cfg || !valid_depth(cfg->depth)) return 0u;
    n = cfg->pipeline.ingress.physical_mics;
    rate = cfg->pipeline.ingress.capture_and_render_rate_hz;
    if ((n != 1u && n != 2u && n != 4u) ||
        (rate != 16000u && rate != 32000u && rate != 48000u) ||
        cfg->pipeline.ingress.render_channels > 1u ||
        cfg->pipeline.ingress.capture_clock_authority != 0u ||
        cfg->pipeline.ingress.frame_ms != 10u ||
        !fe_b1b1_state_bytes(&cfg->pipeline) ||
        !fe_b1b1_work_bytes(&cfg->pipeline))
        return 0u;
    *core_bytes = fe_b1b1_state_bytes(&cfg->pipeline);
    *work_bytes = fe_b1b1_work_bytes(&cfg->pipeline);
    start = align16(sizeof(fe_b2s1_queue));
    if (!start || *core_bytes > SIZE_MAX - start) return 0u;
    total = align16(start + *core_bytes);
    if (!total || total > B2S1_MAX_STATE ||
        *core_bytes > B2S1_MAX_STATE ||
        *work_bytes > B2S1_MAX_WORK)
        return 0u;
    for (i = 0u; i < n; ++i) {
        uint32_t j;
        if (cfg->pipeline.ingress.physical_to_capture_slot[i] >= n)
            return 0u;
        for (j = i + 1u; j < n; ++j)
            if (cfg->pipeline.ingress.physical_to_capture_slot[i] ==
                cfg->pipeline.ingress.physical_to_capture_slot[j])
                return 0u;
    }
    *offset = start;
    return total;
}

size_t fe_b2s1_state_bytes(const fe_b2s1_config *cfg) {
    size_t offset = 0u, core = 0u, work = 0u;
    return sizes(cfg, &offset, &core, &work);
}
size_t fe_b2s1_work_bytes(const fe_b2s1_config *cfg) {
    size_t offset = 0u, core = 0u, work = 0u, total;
    if (!sizes(cfg, &offset, &core, &work)) return 0u;
    total = align16(core);
    if (!total || work > SIZE_MAX - total ||
        (size_t)320u * sizeof(float) > SIZE_MAX - total - work)
        return 0u;
    total = align16(total + work + (size_t)320u * sizeof(float));
    return total && total <= B2S1_MAX_WORK ? total : 0u;
}

fe_b2s1_status fe_b2s1_init(void *memory, size_t bytes,
    const fe_b2s1_config *cfg, fe_b2s1_queue **out) {
    size_t offset = 0u, core_bytes = 0u, core_work = 0u, need;
    fe_b1b1 *core = NULL;
    fe_b2s1_queue *q;
    uint32_t i;
    if (!out || !disjoint(out, sizeof(*out), memory, bytes) ||
        !disjoint(out, sizeof(*out), cfg, cfg ? sizeof(*cfg) : 0u))
        return FE_B2S1_EINVAL;
    *out = NULL;
    need = sizes(cfg, &offset, &core_bytes, &core_work);
    if (!memory || !need || !fe_b2s1_work_bytes(cfg) ||
        ((uintptr_t)memory % FE_B2S1_ALIGNMENT) ||
        !disjoint(memory, bytes, cfg, sizeof(*cfg)))
        return FE_B2S1_EINVAL;
    if (bytes < need) return FE_B2S1_ENOMEM;
    /* Real first-party B1B-S1 init validates geometry/mask and source pin. */
    if (fe_b1b1_init((unsigned char *)memory + offset, core_bytes,
                     &cfg->pipeline, &core) != FE_B1B1_OK)
        return FE_B2S1_EINVAL;
    q = (fe_b2s1_queue *)memory;
    memset(q, 0, sizeof(*q));
    q->magic = B2S1_MAGIC;
    q->depth = cfg->depth;
    q->rate = cfg->pipeline.ingress.capture_and_render_rate_hz;
    q->mic_count = cfg->pipeline.ingress.physical_mics;
    q->has_render = cfg->pipeline.ingress.render_channels;
    q->input_samples = q->rate / 100u;
    q->allocated = need;
    q->core_offset = offset;
    q->core_bytes = core_bytes;
    q->core_work_bytes = core_work;
    q->total_work_bytes = fe_b2s1_work_bytes(cfg);
    q->core = core;
    for (i = 0u; i < q->mic_count; ++i)
        q->source_slots[i] = cfg->pipeline.ingress.physical_to_capture_slot[i];
    atomic_init(&q->capture_head, 0u);
    atomic_init(&q->capture_tail, 0u);
    atomic_init(&q->render_head, 0u);
    atomic_init(&q->render_tail, 0u);
    atomic_init(&q->capture_high_water, 0u);
    atomic_init(&q->render_high_water, 0u);
    *out = q;
    return FE_B2S1_OK;
}

static int state_ok(const fe_b2s1_queue *q) {
    if (!q || q->magic != B2S1_MAGIC || !valid_depth(q->depth) ||
        (q->mic_count != 1u && q->mic_count != 2u && q->mic_count != 4u) ||
        q->has_render > 1u || q->input_samples != q->rate / 100u ||
        (q->rate != 16000u && q->rate != 32000u && q->rate != 48000u) ||
        q->core_offset != align16(sizeof(*q)) ||
        q->allocated > B2S1_MAX_STATE ||
        q->core_offset > q->allocated ||
        q->core_bytes > q->allocated - q->core_offset ||
        q->allocated != align16(q->core_offset + q->core_bytes) ||
        q->core_bytes == 0u || q->core_work_bytes == 0u ||
        q->total_work_bytes > B2S1_MAX_WORK ||
        q->total_work_bytes != align16(align16(q->core_bytes) +
             q->core_work_bytes + (size_t)320u * sizeof(float)) ||
        q->core != (const void *)((const unsigned char *)q + q->core_offset))
        return 0;
    return 1;
}
static int sequence_ok(uint64_t latest, uint64_t incoming, uint32_t flags,
                       uint32_t jump_mask) {
    return incoming && incoming > latest &&
           (incoming == latest + 1u || (flags & jump_mask));
}
static fe_b2s1_status submit(fe_b2s1_queue *q, int render,
    uint64_t seq, uint32_t flags, const int16_t *pcm, size_t count) {
    atomic_uint *head, *tail, *hwm;
    uint32_t h, t, index, available, allowed, gap;
    uint64_t *last, *submitted;
    size_t samples;
    if (!state_ok(q)) return FE_B2S1_ESTATE;
    if (render && !q->has_render) return FE_B2S1_EINVAL;
    allowed = (render ? FE_B1B0_RENDER_GAP : FE_B1B0_CAPTURE_GAP) |
              FE_B1B0_CLOCK_RESET | FE_B2S1_XRUN;
    gap = allowed;
    samples = (size_t)q->input_samples * (render ? 1u : q->mic_count);
    if (!pcm || count != samples || (flags & ~allowed) ||
        !disjoint(q, q->allocated, pcm, count * sizeof(int16_t)))
        return FE_B2S1_EINVAL;
    head = render ? &q->render_head : &q->capture_head;
    tail = render ? &q->render_tail : &q->capture_tail;
    hwm = render ? &q->render_high_water : &q->capture_high_water;
    last = render ? &q->render_sequence : &q->capture_sequence;
    submitted = render ? &q->render_submitted : &q->capture_submitted;
    if (*submitted == UINT64_MAX || !sequence_ok(*last, seq, flags, gap))
        return FE_B2S1_EINVAL;
    h = atomic_load_explicit(head, memory_order_relaxed);
    t = atomic_load_explicit(tail, memory_order_acquire);
    available = h - t;
    if (available >= q->depth) return FE_B2S1_EFULL;
    index = h % q->depth;
    if (render) {
        render_slot_t *slot = &q->render[index];
        memcpy(slot->samples, pcm, count * sizeof(int16_t));
        slot->sequence = seq;
        slot->flags = flags;
    } else {
        capture_slot_t *slot = &q->capture[index];
        memcpy(slot->samples, pcm, count * sizeof(int16_t));
        slot->sequence = seq;
        slot->flags = flags;
    }
    *last = seq;
    ++*submitted;
    if (available + 1u > atomic_load_explicit(hwm, memory_order_relaxed))
        atomic_store_explicit(hwm, available + 1u, memory_order_relaxed);
    atomic_store_explicit(head, h + 1u, memory_order_release);
    return FE_B2S1_OK;
}

fe_b2s1_status fe_b2s1_submit_capture(fe_b2s1_queue *q,
    uint64_t seq, uint32_t flags, const int16_t *pcm, size_t count) {
    return submit(q, 0, seq, flags, pcm, count);
}
fe_b2s1_status fe_b2s1_submit_render(fe_b2s1_queue *q,
    uint64_t seq, uint32_t flags, const int16_t *pcm, size_t count) {
    return submit(q, 1, seq, flags, pcm, count);
}

fe_b2s1_status fe_b2s1_process_one(fe_b2s1_queue *q,
    float *beam, size_t beam_count, float *reference, size_t reference_count,
    void *work, size_t work_bytes) {
    uint32_t h, t, rh = 0u, rt = 0u, flags = 0u;
    const capture_slot_t *cap;
    const render_slot_t *ref = NULL;
    size_t core_aligned;
    unsigned char *backup, *bf_work;
    float *beam_tmp, *ref_tmp;
    if (!state_ok(q)) return FE_B2S1_ESTATE;
    if (!beam || beam_count != 160u ||
        (q->has_render ? (!reference || reference_count != 160u) :
                         (reference || reference_count)) ||
        !work || ((uintptr_t)work % FE_B2S1_ALIGNMENT) ||
        work_bytes < q->total_work_bytes || work_bytes > B2S1_MAX_WORK ||
        !disjoint(q, q->allocated, work, work_bytes) ||
        !disjoint(q, q->allocated, beam, beam_count * sizeof(float)) ||
        !disjoint(work, work_bytes, beam, beam_count * sizeof(float)) ||
        !disjoint(q, q->allocated, reference,
                  reference_count * sizeof(float)) ||
        !disjoint(work, work_bytes, reference,
                  reference_count * sizeof(float)) ||
        !disjoint(beam, beam_count * sizeof(float), reference,
                  reference_count * sizeof(float)) ||
        q->processed == UINT64_MAX)
        return FE_B2S1_EINVAL;
    h = atomic_load_explicit(&q->capture_head, memory_order_acquire);
    t = atomic_load_explicit(&q->capture_tail, memory_order_relaxed);
    if (h == t) return FE_B2S1_EEMPTY;
    if (h - t > q->depth) return FE_B2S1_ESTATE;
    cap = &q->capture[t % q->depth];
    if (q->has_render) {
        rh = atomic_load_explicit(&q->render_head, memory_order_acquire);
        rt = atomic_load_explicit(&q->render_tail, memory_order_relaxed);
        if (rh == rt) return FE_B2S1_EEMPTY;
        if (rh - rt > q->depth) return FE_B2S1_ESTATE;
        ref = &q->render[rt % q->depth];
        if (ref->sequence != cap->sequence ||
            !!(ref->flags & FE_B1B0_CLOCK_RESET) !=
            !!(cap->flags & FE_B1B0_CLOCK_RESET))
            return FE_B2S1_EINVAL;
        if (ref->flags & (FE_B1B0_RENDER_GAP | FE_B2S1_XRUN))
            flags |= FE_B1B0_RENDER_GAP;
    }
    if (cap->flags & (FE_B1B0_CAPTURE_GAP | FE_B2S1_XRUN))
        flags |= FE_B1B0_CAPTURE_GAP;
    if (cap->flags & FE_B1B0_CLOCK_RESET)
        flags = FE_B1B0_CLOCK_RESET;
    /* Trust-bound the exact snapshot bytes at this call site as well as in
     * state_ok(); strict GCC fortify must see a finite memcpy object bound. */
    if (q->core_bytes == 0u || q->core_bytes > B2S1_MAX_STATE ||
        q->core_bytes > work_bytes ||
        q->total_work_bytes < q->core_bytes)
        return FE_B2S1_ESTATE;
    core_aligned = align16(q->core_bytes);
    if (!core_aligned || core_aligned > work_bytes ||
        q->core_work_bytes > work_bytes - core_aligned)
        return FE_B2S1_ESTATE;
    backup = (unsigned char *)work;
    bf_work = backup + core_aligned;
    beam_tmp = (float *)(void *)(bf_work + q->core_work_bytes);
    ref_tmp = beam_tmp + 160u;
    /* Include all first-party SRC+FIR33 state in the transactional snapshot.
     * Work, outputs and q state have already been checked for any alias.
     */
    memcpy(backup, q->core, q->core_bytes);
    if ((flags && fe_b1b1_notify_gap(q->core, flags) != FE_B1B1_OK) ||
        fe_b1b1_process(q->core, cap->samples,
                        (size_t)q->input_samples * q->mic_count,
                        ref ? ref->samples : NULL,
                        (size_t)q->input_samples * q->has_render,
                        beam_tmp, 160u, q->has_render ? ref_tmp : NULL,
                        (size_t)160u * q->has_render, bf_work,
                        q->core_work_bytes) != FE_B1B1_OK) {
        memcpy(q->core, backup, q->core_bytes);
        return FE_B2S1_ESTATE;
    }
    memcpy(beam, beam_tmp, 160u * sizeof(float));
    if (q->has_render) memcpy(reference, ref_tmp, 160u * sizeof(float));
    ++q->processed;
    atomic_store_explicit(&q->capture_tail, t + 1u, memory_order_release);
    if (q->has_render)
        atomic_store_explicit(&q->render_tail, rt + 1u, memory_order_release);
    return FE_B2S1_OK;
}

fe_b2s1_status fe_b2s1_get_info(const fe_b2s1_queue *q,
                                fe_b2s1_info *out) {
    fe_b1b1_info kernel;
    uint32_t ch, ct, rh, rt;
    if (!state_ok(q)) return FE_B2S1_ESTATE;
    if (!out || !disjoint(q, q->allocated, out, sizeof(*out)) ||
        fe_b1b1_get_info(q->core, &kernel) != FE_B1B1_OK)
        return FE_B2S1_EINVAL;
    ch = atomic_load_explicit(&q->capture_head, memory_order_acquire);
    ct = atomic_load_explicit(&q->capture_tail, memory_order_acquire);
    rh = atomic_load_explicit(&q->render_head, memory_order_acquire);
    rt = atomic_load_explicit(&q->render_tail, memory_order_acquire);
    if (ch - ct > q->depth || rh - rt > q->depth)
        return FE_B2S1_ESTATE;
    memset(out, 0, sizeof(*out));
    out->state_bytes = q->allocated;
    out->bf_state_bytes = q->core_bytes;
    out->bf_work_bytes = q->core_work_bytes;
    out->work_bytes = q->total_work_bytes;
    out->depth = q->depth;
    out->physical_mics = q->mic_count;
    out->render_channels = q->has_render;
    out->input_hz = q->rate;
    out->capture_queued = ch - ct;
    out->render_queued = rh - rt;
    out->capture_high_water = atomic_load_explicit(
        &q->capture_high_water, memory_order_acquire);
    out->render_high_water = atomic_load_explicit(
        &q->render_high_water, memory_order_acquire);
    out->capture_submitted = q->capture_submitted;
    out->render_submitted = q->render_submitted;
    out->capture_sequence = q->capture_sequence;
    out->render_sequence = q->render_sequence;
    out->processed = q->processed;
    out->pipeline = kernel;
    return FE_B2S1_OK;
}

fe_b2s1_status fe_b2s1_private_dump_sketch(const fe_b2s1_queue *q,
                                           fe_b2s1_dump_sketch *out) {
    uint32_t i;
    if (!state_ok(q)) return FE_B2S1_ESTATE;
    if (!out || !disjoint(q, q->allocated, out, sizeof(*out)))
        return FE_B2S1_EINVAL;
    memset(out, 0, sizeof(*out));
    out->schema_version = FE_B2S1_PRIVATE_DUMP_SCHEMA;
    out->endian_tag = B2S1_DUMP_ENDIAN_TAG;
    out->source_hz = q->rate;
    out->source_samples = q->input_samples;
    out->physical_mics = q->mic_count;
    out->render_channels = q->has_render;
    for (i = 0u; i < q->mic_count; ++i)
        out->physical_capture_slots[i] = q->source_slots[i];
    out->record_stride_upper_bound =
        40u + (q->mic_count + q->has_render) * q->input_samples * 2u;
    out->clock_authority = 0u;
    out->new_magic_assigned = 0u; /* explicitly not APD2 and no new magic. */
    return FE_B2S1_OK;
}
