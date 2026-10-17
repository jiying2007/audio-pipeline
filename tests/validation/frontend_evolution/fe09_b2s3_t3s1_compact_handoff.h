#ifndef FE09_B2S3_T3S1_COMPACT_HANDOFF_H
#define FE09_B2S3_T3S1_COMPACT_HANDOFF_H

/* FE09 S3-T3-S1 (#789): NONINSTALLED original-S2 two-slot APX3 handoff.
 * One exclusive B1S0 Capture worker produces; a distinct consumer drains.
 * The pinned source owner, generation, geometry, and slot map never change.
 * NOT an archive, power-failure transaction, 192KiB firmware qualification,
 * device-clock claim, 3.x public ABI or shipping audio SDK.
 */
#include "fe09_b2s3_t2b_b1s1_source_chunks.h"
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>

#define FE_T3S1_MAX_SLOTS 2u
#define FE_T3S1_CHUNK_BYTES FE_B1S1_MAX_CHUNK_BYTES
#define FE_T3S1_ROW_BYTES FE_B1S1_ROW_BYTES

typedef enum {
    FE_T3S1_OK = 0, FE_T3S1_REJECT = -1,
    FE_T3S1_PENDING = -2, FE_T3S1_FULL = -3,
    FE_T3S1_SOURCE = -4, FE_T3S1_CODEC = -5,
    FE_T3S1_CORE = -6, FE_T3S1_TAMPER = -7,
    FE_T3S1_SINK_NOT_ADMITTED = -8
} fe_t3s1_status;

typedef struct {
    uint8_t apx3[FE_T3S1_CHUNK_BYTES];
    uint8_t canonical_row[FE_T3S1_ROW_BYTES];
    uint32_t apx3_bytes;
} fe_t3s1_slot;

typedef int (*fe_t3s1_outboard_sink)(
    const uint8_t *apx3, size_t apx3_bytes,
    const uint8_t *canonical_row, size_t canonical_row_bytes,
    void *context, size_t *actually_accounted_bytes);

typedef struct {
    fe_b1s0_state *source;       /* immutable binding, worker-owned access */
    fe_b1s0_config pinned_cfg;  /* immutable, readable by both owners */
    fe_t3s1_outboard_sink pinned_sink; /* exact bound callback identity */
    void *pinned_sink_context;    /* immutable owner context binding */
    uint32_t physical_to_slot[4];
    uint32_t slot_count;        /* physical slots=1 or 2, not logical depth */
    atomic_uint head, tail;     /* uint32 wrap; one producer, one consumer */
    uint64_t last_global_capture; /* worker only, never read concurrently */
    uint64_t drained_global_capture; /* consumer only */
    uint8_t producer_prior_row_sha256[32]; /* worker only */
    uint8_t consumer_prior_row_sha256[32]; /* consumer only */
    fe_t3s1_slot *slot;      /* exact externally allocated 1 or 2 slots */
    size_t slot_allocation_bytes; /* == slot_count * sizeof(fe_t3s1_slot) */
} fe_t3s1_ring;

typedef struct {
    uint64_t source_sequence;
    uint32_t source_capture_id, source_render_id, render_event;
    uint32_t apx3_bytes, canonical_row_bytes;
    size_t actually_accounted_bytes; /* test-only external sink acknowledgement */
    uint32_t hardware_qualified, durable_qualified, product_qualified;
} fe_t3s1_drain_receipt;

/* Out-of-audio-path, test-only sink. 0 means a complete transfer was
 * accounted for by that sink, not that a file was synced or power-safe.
 * Returning error / short ack withholds ring tail. Callbacks must not
 * mutate ring/source buffers; retries need sink-side idempotent identity.
 */
/* Must initialize BEFORE spawning any source, worker or sink threads.
 * Source is a fresh, bound original B1S0; producer/consumer never rebind.
 */
fe_t3s1_status fe_t3s1_init(fe_t3s1_ring *ring,
    fe_b1s0_state *source, const uint32_t slots[4],
    fe_t3s1_slot *storage, size_t storage_bytes, uint32_t physical_slots,
    fe_t3s1_outboard_sink outboard_sink, void *outboard_context);

/* Worker: reserve a free physical slot FIRST. Preflight exact original S2
 * writer+decode+SHA and canonical FBS1 prev-row chain using stack scratch.
 * Only AFTER successful preflight may first-party B1S0 consume BF/source.
 * Postcommit copies and release-store are infallible; no callback or I/O.
 * PENDING/FULL/rejections preserve source tails, BF, output and ring.
 */
fe_t3s1_status fe_t3s1_step(fe_t3s1_ring *ring,
    float *beam, size_t beam_count, float *render_ref, size_t ref_count,
    void *work, size_t work_bytes, fe_b1s0_receipt *receipt);

/* Separate consumer thread: verify original S2 replay, file SHA and FBS1
 * row chain before invoking the outboard sink. ACK/tail advance only on a
 * complete, explicitly accounted actual-byte transfer; no durability claim.
 */
fe_t3s1_status fe_t3s1_drain_one(fe_t3s1_ring *ring,
    fe_t3s1_outboard_sink sink, void *context,
    fe_t3s1_drain_receipt *receipt);

/* Test-only: seed an EMPTY compact ring near UINT32_MAX before producers.
 * Not a live ring counter/epoch repair API.
 */
fe_t3s1_status fe_t3s1_seed_wrap_before_start(
    fe_t3s1_ring *ring, uint32_t value);

#endif
