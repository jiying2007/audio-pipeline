#ifndef FE09_B1B1_SINGLE_BF_H
#define FE09_B1B1_SINGLE_BF_H

/* FE09-R2B1B-S1, issue #743. Noninstalled research-only SRC -> one array BF.
 * No 3.x public ABI, AEC, physical ADC clock, SSC305 or product qualification.
 * A separate mono render never enters the array beamformer.
 */
#include <stddef.h>
#include <stdint.h>
#include "fe09_b1b0_src.h"
#include "array_native.h"

#define FE_B1B1_ALIGNMENT 16u
#define FE_B1B1_INTERNAL_FRAMES 160u
#define FE_B1B1_VERSION UINT32_C(0x00030003)

typedef enum {
    FE_B1B1_OK = 0,
    FE_B1B1_EINVAL = -1,
    FE_B1B1_ENOMEM = -2,
    FE_B1B1_ESTATE = -3
} fe_b1b1_status;

typedef struct {
    fe_b1b0_config ingress; /* Actual unchanged N+render first-party SRC. */
    fe_array_config array; /* Actual unchanged one FIR33_HANN BF, 16kHz. */
} fe_b1b1_config;

typedef struct fe_b1b1 fe_b1b1;

typedef struct {
    size_t state_bytes, work_bytes, source_state_bytes, array_state_bytes;
    uint32_t physical_mics, render_channels, input_rate_hz;
    uint64_t accepted_frames, clipped_samples;
    fe_b1b0_info source; /* Separately auditable capture vs render epochs. */
    fe_array_info array; /* Source-only BF, not a measured gain verdict. */
} fe_b1b1_info;

/* Exact caller-owned aligned arena. Zero means invalid descriptor.
 * Processing needs a separate caller-owned work area including a complete
 * private state snapshot; not an optimized embedded memory footprint.
 */
size_t fe_b1b1_state_bytes(const fe_b1b1_config *cfg);
size_t fe_b1b1_work_bytes(const fe_b1b1_config *cfg);
fe_b1b1_status fe_b1b1_init(void *memory, size_t bytes,
                            const fe_b1b1_config *cfg, fe_b1b1 **out);

/* Pure physical-major -> interleaved transfer with saturation, never wrap.
 * All input values must be finite; rejected operations write nothing.
 * For an actual frame count = 160; output contains N*160 floats.
 */
fe_b1b1_status fe_b1b1_transpose_clamp(const float *physical_major,
                                      size_t input_count, uint32_t mics,
                                      float *interleaved, size_t output_count,
                                      uint64_t *clipped);

/* On any rejected frame call, state and external output are unchanged.
 * Caller serializes all controls/callbacks, supplies 16-byte-aligned
 * work buffer, and keeps all input/output/state/work memory disjoint.
 * Beamformed output remains UNCLIPPED Float32; independent render remains
 * 160 Float32 reference values (NOT AEC or a fifth microphone).
 */
fe_b1b1_status fe_b1b1_process(fe_b1b1 *s, const int16_t *capture,
    size_t capture_count, const int16_t *render, size_t render_count,
    float *beamformed, size_t beamformed_count,
    float *render_reference, size_t reference_count,
    void *work, size_t work_bytes);

/* Explicit commands, never automatic microphone health/DOA decisions.
 * CAPTURE_GAP resets N mic SRC histories AND array BF histories.
 * RENDER_GAP resets only the mono reference history, not array BF.
 * CLOCK_RESET resets both domains, no invented clocks or timestamps.
 */
fe_b1b1_status fe_b1b1_set_active_mask(fe_b1b1 *s, uint32_t mask);
fe_b1b1_status fe_b1b1_notify_gap(fe_b1b1 *s, uint32_t flags);
fe_b1b1_status fe_b1b1_request_steer(fe_b1b1 *s, const double direction[3],
                                     uint32_t transition_samples);
fe_b1b1_status fe_b1b1_reset(fe_b1b1 *s);
fe_b1b1_status fe_b1b1_get_info(const fe_b1b1 *s, fe_b1b1_info *out);

#endif
