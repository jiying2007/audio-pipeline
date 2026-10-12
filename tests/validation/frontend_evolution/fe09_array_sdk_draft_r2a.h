#ifndef FE09_R2A_ARRAY_SDK_DRAFT_H
#define FE09_R2A_ARRAY_SDK_DRAFT_H

/* FE09-R2A noninstalled research-only ABI prototype (issue #730).
 * This is NOT include/audio_pipeline, NOT a public 3.x SDK or product API.
 * The FIR33 DSP implementation is exclusively array_native.c.
 */
#include "array_native.h"
#include <stddef.h>
#include <stdint.h>

#define FE_R2A_DRAFT_VERSION UINT32_C(0x00030000)
#define FE_R2A_ALIGNMENT 16u
#define FE_R2A_FRAME_MS 10u
#define FE_R2A_RATE_HZ 16000u
#define FE_R2A_FRAME_SAMPLES 160u
#define FE_R2A_CAPTURE_GAP 1u
#define FE_R2A_RENDER_GAP 2u

typedef enum {
    FE_R2A_OK = 0,
    FE_R2A_EINVAL = -1,
    FE_R2A_ENOMEM = -2,
    FE_R2A_ESTATE = -3,
    FE_R2A_EBUSY = -4
} fe_r2a_status;

/* Fields are intentionally unfrozen; reject unknown size/version.
 * Physical source slot map differs from a separate, optional render input.
 * capture_clock_authority MUST remain zero: no ADC clock was qualified.
 */
typedef struct {
    uint32_t struct_size;
    uint32_t api_version;
    uint32_t sample_rate_hz;
    uint32_t frame_ms;
    uint32_t physical_mics;
    uint32_t render_channels;
    uint32_t reference_mic;
    uint32_t active_mic_mask;
    uint32_t capture_clock_authority;
    double source_direction[3];
    fe_array_microphone microphones[FE_ARRAY_MAX_MICS];
} fe_r2a_config;

typedef struct fe_r2a_adapter fe_r2a_adapter;
typedef struct {
    size_t requested_state_bytes;
    size_t native_fir33_state_bytes;
    uint32_t physical_mics;
    uint32_t render_channels;
    uint32_t active_mic_mask;
    uint32_t common_delay_samples;
    uint64_t total_frames;       /* Accepted 10ms frames, across capture gaps. */
    uint64_t capture_epoch;      /* Increment on an accepted capture gap. */
    uint64_t render_epoch;       /* Increment on an accepted render gap. */
    uint64_t observed_render_frames;
    uint64_t clipped_samples;
    uint64_t render_fnv64;
} fe_r2a_info;

/* First-party single-core adapter; a new major ABI is NOT implemented. */
size_t fe_r2a_state_bytes(const fe_r2a_config *cfg);
fe_r2a_status fe_r2a_init(void *memory, size_t bytes,
                           const fe_r2a_config *cfg, fe_r2a_adapter **out);
fe_r2a_status fe_r2a_process(fe_r2a_adapter *state,
                              const int16_t *capture_interleaved,
                              size_t capture_scalar_samples,
                              const int16_t *separate_render,
                              size_t render_scalar_samples,
                              int16_t *mono_output,
                              size_t mono_scalar_samples);
fe_r2a_status fe_r2a_set_active_mask(fe_r2a_adapter *state, uint32_t mask);
fe_r2a_status fe_r2a_request_steer(fe_r2a_adapter *state,
                                    const double direction[3],
                                    uint32_t duration_samples);
fe_r2a_status fe_r2a_notify_gap(fe_r2a_adapter *state, uint32_t flags);
fe_r2a_status fe_r2a_reset(fe_r2a_adapter *state);
fe_r2a_status fe_r2a_get_info(const fe_r2a_adapter *state, fe_r2a_info *out);

#endif
