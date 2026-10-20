#ifndef FE09_B2S3_T1_SOURCE_WITNESS_H
#define FE09_B2S3_T1_SOURCE_WITNESS_H

/* #764: NONINSTALLED source-attested S1 -> T0 -> S2 APX3 test facade.
 * This does NOT make arbitrary direct S1 submissions trustworthy.
 * One capture producer, optional independent render producer, one worker;
 * all callers must use this facade (exclusive S1 submission ownership).
 * No public SDK, clock authority, resynchronization, ABI or device claim.
 */
#include "fe09_b2s3_private_bridge.h"
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>

#define FE_S3_T1_MAX_DEPTH 4u
#define FE_S3_T1_CAP_MAX 1920u
#define FE_S3_T1_REF_MAX 480u

typedef enum {
    FE_T1_OK = 0,
    FE_T1_EINVAL = -1,
    FE_T1_EEMPTY = -2,
    FE_T1_EFULL = -3,
    FE_T1_EFRAME = -4,
    FE_T1_ECORE = -5
} fe_s3_t1_status;

typedef struct {
    uint64_t sequence;
    uint32_t flags, epoch;
    size_t count;
    int16_t staging[FE_S3_T1_CAP_MAX];
    int16_t witness[FE_S3_T1_CAP_MAX];
} fe_s3_t1_capture;

typedef struct {
    uint64_t sequence;
    uint32_t flags, epoch;
    size_t count;
    int16_t staging[FE_S3_T1_REF_MAX];
    int16_t witness[FE_S3_T1_REF_MAX];
} fe_s3_t1_render;

typedef struct {
    fe_s3_bridge *bridge; /* worker owned, S1/S2 frozen */
    uint32_t depth, mics, rate, render;
    uint32_t cap_epoch, ref_epoch; /* owner-specific, initialized to 1 / 0 */
    uint64_t cap_last, ref_last;
    _Atomic uint32_t cap_head, cap_tail, ref_head, ref_tail;
    fe_s3_t1_capture cap[FE_S3_T1_MAX_DEPTH];
    fe_s3_t1_render ref[FE_S3_T1_MAX_DEPTH];
} fe_s3_t1_source_witness;

/* Call once before spawning any producer. Queue+bridge+writer must be
 * fresh, no queued frames; all S1 producer access is exclusive through
 * this facade thereafter. The caller owns the entire aligned witness.
 */
fe_s3_t1_status fe_s3_t1_bind(
    fe_s3_t1_source_witness *witness, fe_s3_bridge *bridge);

/* Producer: stage PCM, actually submit same staged bytes to S1, then
 * separately copy byte-exact immutable witness, finally release-publish.
 * On EFULL, no committed witness/head/source-epoch changes; scratch staging
 * may be overwritten but remains producer-owned and not published.
 */
fe_s3_t1_status fe_s3_t1_capture_submit(
    fe_s3_t1_source_witness *witness, uint64_t seq, uint32_t flags,
    const int16_t *pcm, size_t samples);
fe_s3_t1_status fe_s3_t1_render_submit(
    fe_s3_t1_source_witness *witness, uint64_t seq, uint32_t flags,
    const int16_t *pcm, size_t samples);

/* Worker compares exact caller APX3 candidate sequence, source epochs,
 * flags, counts AND PCM bytes against the independently copied witness
 * of successfully submitted S1 frame(s), BEFORE invoking frozen S3.
 * Failures preserve recorder, S1 queues and external beam outputs.
 * Only on S3 success release store tail to free the witness slot.
 * Quiescent-only get_info; no concurrent 64-bit metrics read.
 */
fe_s3_t1_status fe_s3_t1_step(
    fe_s3_t1_source_witness *witness, const fe_s2_frame *candidate,
    float *beam, size_t beam_count,
    float *render_reference, size_t reference_count,
    void *work, size_t work_bytes);

#endif
