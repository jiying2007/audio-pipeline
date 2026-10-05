#ifndef FE_ARRAY_NATIVE_H
#define FE_ARRAY_NATIVE_H

/* First-party FE02/03 research API. Not installed, not a 2.x SDK extension.
 * Caller-serialized control and processing; no allocation, I/O or locks in core.
 * A microphone is not a render-reference channel. No render input is accepted.
 */
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FE_ARRAY_MAX_MICS 4u
#define FE_ARRAY_HISTORY 128u
#define FE_ARRAY_ALIGNMENT 16u

typedef enum {
    FE_ARRAY_OK = 0,
    FE_ARRAY_EINVAL = -1,
    FE_ARRAY_ENOMEM = -2,
    FE_ARRAY_ESTATE = -3
} fe_array_status;

typedef enum {
    FE_ARRAY_LINEAR = 0,
    FE_ARRAY_LAGRANGE3 = 1
} fe_array_interpolation;

typedef struct {
    double position_m[3];
    double gain; /* Signed correction; |gain| in [0.25, 4]. Includes polarity. */
    double latency_samples; /* Positive means this physical channel arrives late. */
    uint32_t input_channel;
} fe_array_microphone;

typedef struct {
    uint32_t sample_rate_hz; /* 8/16/24/32/48 kHz; no implicit resampling. */
    uint32_t mic_count; /* Exactly 1, 2 or 4; three-active-of-four uses mask. */
    uint32_t reference_mic; /* Geometric reference; need not remain active. */
    uint32_t active_mask; /* Physical mic indices, not PCM slot indices. */
    fe_array_interpolation interpolation;
    double direction[3]; /* Unit vector from array toward far-field source. */
    fe_array_microphone microphones[FE_ARRAY_MAX_MICS];
} fe_array_config;

typedef struct fe_array fe_array;
typedef struct {
    uint32_t sample_rate_hz;
    uint32_t mic_count;
    uint32_t active_mask;
    uint32_t common_delay_samples;
    fe_array_interpolation interpolation;
    size_t state_bytes; /* Header and per-channel delay histories, no heap. */
    uint64_t samples_processed; /* Per-channel sample frames, not interleaved values. */
    double compensation_samples[FE_ARRAY_MAX_MICS];
} fe_array_info;

/* Returns zero for unsupported channel capacity. State physically scales by N. */
size_t fe_array_state_bytes(uint32_t mic_count);
/* Every failed init leaves storage unchanged and sets a non-overlapping *out=NULL.
 * memory must be aligned to FE_ARRAY_ALIGNMENT; cfg/out must not alias memory.
 * The fixed common delay is ceil(max_i ||r_i-r_ref|| fs/343 + max_i |latency_i|)+1.
 * Per-channel delay is common + dot(r_i-r_ref,u) fs/343 - latency_i.
 * Both interpolators use the same common latency. No lookahead/steering estimator.
 */
fe_array_status fe_array_init(void *memory, size_t bytes,
                              const fe_array_config *cfg, fe_array **out);
fe_array_status fe_array_get_info(const fe_array *state, fe_array_info *out);
fe_array_status fe_array_reset(fe_array *state);
/* At a process-call boundary only. Re-enabled channels start with zero history;
 * continuing channels keep history. This is explicit fault control, not detection
 * or a click-free transition. The common delay never changes with active mask.
 */
fe_array_status fe_array_set_active_mask(fe_array *state, uint32_t mask);
/* Interleaved normalized float input; 1..10ms per call. input_count is the number
 * of float values; output_count must equal input_count/mic_count exactly.
 * Active samples must be finite and |x|<=1. Inactive slots are ignored/zero-stored.
 * Output is unclipped float: gain correction and interpolation may exceed unity.
 * Input, output and state must be disjoint. Validate all input before mutation.
 * No tail padding/flush: one output per input frame, zero prehistory at reset.
 */
fe_array_status fe_array_process(fe_array *state, const float *input,
                                 size_t input_count, float *output,
                                 size_t output_count);

#ifdef __cplusplus
}
#endif
#endif
