#ifndef FE09_B2S1_PRIVATE_QUEUE_H
#define FE09_B2S1_PRIVATE_QUEUE_H

/* FE09-R2B2-S1, preregistration #755. Noninstalled research-only 10ms SPSC
 * paired capture/render ingress driving the SAME first-party B1B-S1 SRC+FIR33.
 * This is NOT an installed 2.x/3.x SDK, real ADC clock or physical HIL.
 * Producer owns each queue's head, worker owns each queue's tail.
 */
#include "fe09_b1b1_single_bf.h"
#include <stddef.h>
#include <stdint.h>

#define FE_B2S1_ALIGNMENT 16u
#define FE_B2S1_MAX_DEPTH 4u
#define FE_B2S1_MAX_SOURCE_SAMPLES 480u
#define FE_B2S1_MAX_CAPTURE_SCALARS (FE_B2S1_MAX_SOURCE_SAMPLES * 4u)
#define FE_B2S1_XRUN 8u
#define FE_B2S1_PRIVATE_DUMP_SCHEMA 2u

typedef enum {
    FE_B2S1_OK = 0,
    FE_B2S1_EINVAL = -1,
    FE_B2S1_ENOMEM = -2,
    FE_B2S1_ESTATE = -3,
    FE_B2S1_EFULL = -4,
    FE_B2S1_EEMPTY = -5
} fe_b2s1_status;

typedef struct fe_b2s1_queue fe_b2s1_queue;

typedef struct {
    fe_b1b1_config pipeline; /* Independent N physical SRC + separate render. */
    uint32_t depth; /* Only 2 or 4. No heap, locks or I/O in frame path. */
} fe_b2s1_config;

typedef struct {
    size_t state_bytes, work_bytes, bf_state_bytes, bf_work_bytes;
    uint32_t depth, physical_mics, render_channels, input_hz;
    uint32_t capture_queued, render_queued;
    uint32_t capture_high_water, render_high_water;
    uint64_t capture_submitted, render_submitted, processed;
    uint64_t capture_sequence, render_sequence;
    fe_b1b1_info pipeline;
} fe_b2s1_info;

typedef struct {
    uint32_t schema_version; /* 2: SKETCH ONLY, no writer or parser exists. */
    uint32_t endian_tag; /* 0x01020304 */
    uint32_t source_hz, source_samples, physical_mics, render_channels;
    uint32_t physical_capture_slots[4];
    uint32_t clock_authority; /* UNKNOWN=0, cannot invent sample-zero. */
    uint32_t record_stride_upper_bound;
    uint32_t new_magic_assigned; /* Always zero. Not APD2 v1. */
} fe_b2s1_dump_sketch;

/* All sizes are configuration-specific; zero means invalid. 16-byte aligned
 * caller-owned state and separate work, inputs/outputs must be disjoint.
 */
size_t fe_b2s1_state_bytes(const fe_b2s1_config *cfg);
size_t fe_b2s1_work_bytes(const fe_b2s1_config *cfg);
fe_b2s1_status fe_b2s1_init(void *state, size_t bytes,
    const fe_b2s1_config *cfg, fe_b2s1_queue **out);

/* One independent SPSC producer per queue; queue element contents are copied.
 * Sequence begins at 1, then increments by one per source; a jump requires
 * explicit capture/render gap or clock-reset flag. Timestamp authority is
 * UNKNOWN in this slice; no timestamp values accepted or synthesized.
 * Valid capture flags: CAPTURE_GAP|CLOCK_RESET|XRUN.
 * Valid render flags: RENDER_GAP|CLOCK_RESET|XRUN.
 * A rejected call changes no queue bytes, heads, sequence or source state.
 */
fe_b2s1_status fe_b2s1_submit_capture(fe_b2s1_queue *state,
    uint64_t frame_sequence, uint32_t flags,
    const int16_t *pcm, size_t count);
fe_b2s1_status fe_b2s1_submit_render(fe_b2s1_queue *state,
    uint64_t frame_sequence, uint32_t flags,
    const int16_t *pcm, size_t count);

/* Worker owns both queue tails. On EEMPTY, mismatched pairs, invalid aliases
 * or a downstream error ALL caller output, heads/tails and state are unchanged.
 * Work buffer holds a full rollback snapshot and private Float32 output.
 * A render gap does not clear mic+BF histories; a capture gap does.
 */
fe_b2s1_status fe_b2s1_process_one(fe_b2s1_queue *state,
    float *beam, size_t beam_count, float *render_ref, size_t ref_count,
    void *work, size_t work_bytes);

fe_b2s1_status fe_b2s1_get_info(const fe_b2s1_queue *state,
    fe_b2s1_info *out);
fe_b2s1_status fe_b2s1_private_dump_sketch(const fe_b2s1_queue *state,
    fe_b2s1_dump_sketch *out);

#endif
