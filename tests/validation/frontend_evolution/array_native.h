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
    FE_ARRAY_ESTATE = -3,
    FE_ARRAY_EBUSY = -4
} fe_array_status;

typedef enum {
    FE_ARRAY_LINEAR = 0,
    FE_ARRAY_LAGRANGE3 = 1,
    FE_ARRAY_FIR17_HANN = 2,
    FE_ARRAY_FIR33_HANN = 3,
    FE_ARRAY_SPATIAL33 = 4
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
    double compensation_samples[FE_ARRAY_MAX_MICS]; /* Last committed bank. */
    double direction[3], target_direction[3];
    uint32_t transition_total_samples, transition_done_samples;
    uint64_t steering_accepted, steering_completed, steering_cancelled;
} fe_array_info;

/* Returns zero for unsupported channel capacity. State physically scales by N. */
size_t fe_array_state_bytes(uint32_t mic_count);
/* Mode-aware research allocation. Legacy query above covers only linear/cubic.
 * FIR modes append two N*taps coefficient banks after the unchanged histories.
 * All coefficients are generated in init/control, never per audio sample.
 */
size_t fe_array_state_bytes_for_mode(uint32_t mic_count, fe_array_interpolation mode);
/* Every failed init leaves storage unchanged and sets a non-overlapping *out=NULL.
 * memory must be aligned to FE_ARRAY_ALIGNMENT; cfg/out must not alias memory.
 * The fixed common delay is ceil(max_i ||r_i-r_ref|| fs/343 + max_i |latency_i|)+1.
 * Per-channel delay is common + dot(ri-r_ref,u) fs/343 - latency_i.
 * Linear/cubic retain that common latency. FIR17/FIR33 add 8/16 samples
 * respectively, to make every tap causal. The complete tap range must fit the
 * 128-sample history; unsupported geometry is rejected, not clamped.
 * FIR coefficients: sinc(k-f)*Hann(k/R), k=-R..R, divided by their sum
 * (unit DC coefficient normalization, not signal-level normalization).
 * No lookahead/steering estimator. FIRs are research modes, not a shipping API.
 */
fe_array_status fe_array_init(void *memory, size_t bytes,
                              const fe_array_config *cfg, fe_array **out);
/* Explicit fixed spatial FIRs: flattened [physical_mic][33], direct SUM of
 * calibrated filtered channels (weights already include spatial scaling).
 * Common delay is the geometry FIR33 delay; tap zero starts common-16.
 * All physical microphones must be active. Direction-only steering and actual
 * mask changes are rejected: they cannot regenerate a joint spatial design.
 * Coefficients: finite, |tap|<=16, total L1<=64, aggregate DC within1e-3 of1.
 * These are safety/identity bounds, NOT a WNG or speech-quality certificate.
 * Caller must bind bank to geometry/rate/direction/calibration; no hidden design.
 * Inputs/coefficients/cfg/out/state must not alias as documented by legacy init.
 */
fe_array_status fe_array_init_spatial33(void *memory, size_t bytes,
    const fe_array_config *cfg, const float *coefficients, size_t coefficient_count,
    fe_array **out);
/* Same-history transition to an EXPLICIT replacement bank; T obeys legacy limits.
 * Atomic rejection; busy has no queue. Same direction with different coefficients
 * is a real transition. A fully identical bank+direction is an idle no-op.
 */
fe_array_status fe_array_request_spatial33(fe_array *state, const double direction[3],
    const float *coefficients, size_t coefficient_count, uint32_t transition_samples);
fe_array_status fe_array_get_info(const fe_array *state, fe_array_info *out);
/* Reset cancels an in-flight transition, retaining the last committed direction,
 * and clears histories, sample/steering counters. Reset an associated controller too.
 */
fe_array_status fe_array_reset(fe_array *state);
/* Caller-serialized, before a process call. Unit direction must not alias state.
 * T is 2..sample_rate/10 samples. Sample k uses alpha=k/(T-1); first/last
 * outputs are exactly old/new bank. Both banks use the same channel histories.
 * Common delay, sample counter, gains/mapping/mask are unchanged. Rejected calls
 * are atomic; overlapping requests return EBUSY (no queue). Same direction is a
 * no-op when idle. This is not a DOA estimator, angle slew or click-free guarantee.
 */
fe_array_status fe_array_request_steer(fe_array *state, const double direction[3],
                                      uint32_t transition_samples);
/* At a process-call boundary only. Re-enabled channels start with zero history;
 * continuing channels keep history. This is explicit fault control, not detection
 * or a click-free transition. An actual mask change cancels pending steering,
 * retaining its last committed bank; a same-mask call is a no-op.
 * The common delay never changes with active mask.
 */
fe_array_status fe_array_set_active_mask(fe_array *state, uint32_t mask);
/* Interleaved normalized float input; 1 sample frame through 10ms per call.
 * input_count counts float values; output_count=input_count/mic_count exactly.
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
