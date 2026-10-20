#ifndef FE09_B2S3_T2B_B0_CAPTURE_ONLY_H
#define FE09_B2S3_T2B_B0_CAPTURE_ONLY_H

/* FE09 T2-B/B0 (#771): NONINSTALLED research-only Capture SRC/FIR33 state
 * isolated from optional real Render SRC. No public ABI, SPSC liveness,
 * APX3 recorder, physical ADC/DAC clock or product admission.
 *
 * Source PCM in the accompanying tests is first-party synthetic. This B0
 * adapter neither attests hardware capture nor aligns independent clocks.
 * The caller serializes its separate Capture/Render calls: no thread-safe
 * producer/worker contract is supplied until the separate B1 stage.
 */
#include "fe09_b1b1_single_bf.h"
#include "frontend/ap_resampler.h"
#include <stddef.h>
#include <stdint.h>

#define FE_T2B_B0_FRAMES 160u
#define FE_T2B_B0_RENDER_GAP FE_B1B0_RENDER_GAP
#define FE_T2B_B0_VERSION 1u

typedef enum {
    FE_T2B_B0_OK = 0,
    FE_T2B_B0_REJECT = -1,
    FE_T2B_B0_CORE = -2
} fe_t2b_b0_status;

typedef struct {
    fe_b1b1 *capture_bf; /* Must be independently initialized render=0. */
    size_t capture_state_bytes, capture_work_bytes;
    uint32_t input_hz, physical_mics, render_epoch;
    uint64_t capture_sequence, render_sequence;
    uint64_t accepted_capture, accepted_render;
    ap_resampler_state_t render_src; /* Distinct source-owned reference SRC. */
} fe_t2b_b0;

/* Caller owns and separately initializes first-party capture-only B1B1.
 * No in-place reinterpretation of paired B1B1/S1 state and no source clocks.
 * Must bind before any frames are processed, with disjoint aligned memory.
 */
fe_t2b_b0_status fe_t2b_b0_bind(fe_t2b_b0 *a,
    fe_b1b1 *capture_only, uint32_t input_hz, uint32_t physical_mics);

/* One real continuous Capture frame, independent of Render availability.
 * First sequence=1, subsequent sequence=previous+1; no hidden gap recovery.
 * On rejection no Capture state/output/counter is committed.
 */
fe_t2b_b0_status fe_t2b_b0_capture(fe_t2b_b0 *a,
    uint64_t seq, const int16_t *pcm, size_t samples,
    float *beam, size_t beam_count, void *work, size_t work_bytes);

/* Optional actual Render sample only. Missing Render means NO invocation.
 * Render sequence may jump only with explicit RENDER_GAP. A render gap resets
 * the independent render resampler, never mic SRC or FIR33 state. No silent
 * zero reference frames and no shared clock/sample-zero assertions.
 */
fe_t2b_b0_status fe_t2b_b0_render(fe_t2b_b0 *a,
    uint64_t seq, uint32_t flags, const int16_t *pcm, size_t samples,
    float *reference, size_t reference_count);

#endif
