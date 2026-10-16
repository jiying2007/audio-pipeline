#ifndef FE09_B2S3_T2B_B1S0_OWNER_SPSC_H
#define FE09_B2S3_T2B_B1S0_OWNER_SPSC_H

/* FE09 #776: NONINSTALLED owner-witness, two SPSC source domains, worker.
 * Source IDs/generations are logical credentials, NOT cryptographic identity
 * or proof of DAC/ADC physical clocks. No APX3 recorder, ABI or device claim.
 * Only one exclusive producer for each enabled domain, one exclusive worker.
 */
#include "fe09_b2s3_t2b_b0_capture_only.h"
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>

#define FE_B1S0_MAX_DEPTH 4u
#define FE_B1S0_CAPTURE_MAX 1920u
#define FE_B1S0_RENDER_MAX 480u
#define FE_B1S0_ABSENT_SOURCE_REPORTED 1u
#define FE_B1S0_RENDER_GAP FE_B1B0_RENDER_GAP

typedef enum {
    FE_B1S0_OK=0, FE_B1S0_REJECT=-1, FE_B1S0_FULL=-2,
    FE_B1S0_EMPTY=-3, FE_B1S0_MISMATCH=-4, FE_B1S0_CORE=-5
} fe_b1s0_status;

typedef enum {
    FE_B1S0_RENDER_DISABLED=0,
    FE_B1S0_RENDER_PRESENT=1,
    FE_B1S0_RENDER_ABSENT=2
} fe_b1s0_event;

typedef struct {
    uint32_t depth, physical_mics, input_hz, render_enabled;
    uint32_t capture_source_id, render_source_id;
    uint64_t source_generation;
} fe_b1s0_config;

typedef struct {
    uint64_t sequence;
    uint64_t pcm_hash;
    int16_t pcm[FE_B1S0_CAPTURE_MAX];
} fe_b1s0_capture_slot;

typedef struct {
    uint64_t sequence, pcm_hash;
    uint32_t event_type, reason, epoch, gap_flag;
    int16_t pcm[FE_B1S0_RENDER_MAX]; /* ONLY meaningful for actual PRESENT. */
} fe_b1s0_render_slot;

typedef struct {
    uint64_t source_generation, capture_sequence;
    uint64_t capture_pcm_hash, render_pcm_hash;
    uint32_t capture_source_id, render_source_id;
    uint32_t render_event, render_reason, render_epoch;
    uint32_t mic_bf_progressed, reference_actual_pcm, source_clock_known;
    uint32_t recorder_qualified, public_sdk_qualified, device_qualified;
} fe_b1s0_receipt;

/* Research state is caller-owned and can be statically allocated.
 * These non-atomic metrics are owner-only and inspected only after pthread
 * joins. No container-byte snapshots while other owner threads are active.
 */
typedef struct {
    fe_b1s0_config cfg;
    fe_t2b_b0 *core; /* pre-bound to separately allocated mic-only B1B1. */
    atomic_uint cap_head, cap_tail, ref_head, ref_tail;
    uint64_t cap_last, ref_last, processed, actual_render_frames;
    uint32_t producer_ref_epoch, producer_prior_absent;
    uint32_t worker_prior_absent;
    fe_b1s0_capture_slot cap[FE_B1S0_MAX_DEPTH];
    fe_b1s0_render_slot ref[FE_B1S0_MAX_DEPTH];
} fe_b1s0_state;

/* Fresh, disjoint, bound first-party B0 core, no source published.
 * Caller guarantees owner lifetime and never rebinds after thread start.
 */
fe_b1s0_status fe_b1s0_init(fe_b1s0_state *q, const fe_b1s0_config *cfg,
                             fe_t2b_b0 *core);

/* True independent producer APIs. Sequence begins 1 and continues by 1.
 * External source-owner ID+generation must match the immutable binding.
 * Full/rejected returns do not publish head/last/epoch or PCM bytes.
 */
fe_b1s0_status fe_b1s0_capture_submit(fe_b1s0_state *q,
    uint32_t source_id, uint64_t generation, uint64_t sequence,
    const int16_t *pcm, size_t sample_count);
fe_b1s0_status fe_b1s0_render_present(fe_b1s0_state *q,
    uint32_t source_id, uint64_t generation, uint64_t association_sequence,
    uint32_t render_epoch, uint32_t gap_flag,
    const int16_t *pcm, size_t sample_count);
fe_b1s0_status fe_b1s0_render_absent(fe_b1s0_state *q,
    uint32_t source_id, uint64_t generation, uint64_t association_sequence,
    uint32_t render_epoch, uint32_t owner_reason);

/* A queued Capture alone with render_enabled=1 is PENDING (EMPTY), not a
 * valid missing Render event. Only actual source-owner ABSENT token allows
 * progression without reference. Failed calls preserve external outputs,
 * receipt, all queue tails, B0 mic BF and reference histories exactly.
 * Present reference output is written ONLY for actual PCM events.
 */
fe_b1s0_status fe_b1s0_process_one(fe_b1s0_state *q,
    float *beam, size_t beam_count, float *reference, size_t reference_count,
    void *work, size_t work_bytes, fe_b1s0_receipt *receipt);

/* Test-only: before either producer starts, seed both EMPTY ring counters
 * near UINT32_MAX. Cannot mutate any populated/running queue. */
fe_b1s0_status fe_b1s0_seed_wrap_before_start(fe_b1s0_state *q,
                                               uint32_t counter);

#endif
