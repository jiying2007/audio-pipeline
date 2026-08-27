#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_H
#define AUDIO_PIPELINE_AUDIO_PIPELINE_H

#include "audio_pipeline/audio_types.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AP_PIPELINE_STATE_MAX_BYTES 80000u
#define AP_PIPELINE_STATE_ALIGNMENT 16u

typedef enum ap_profile {
    AP_PROFILE_CALL = 0,
    AP_PROFILE_ASSISTANT = 1
} ap_profile_t;

typedef enum ap_resource_class {
    AP_RESOURCE_TINY = 0,
    AP_RESOURCE_LOW = 1,
    AP_RESOURCE_STANDARD = 2
} ap_resource_class_t;

typedef uint32_t ap_stage_mask_t;
enum {
    AP_STAGE_HPF  = 1u << 0,
    AP_STAGE_BF   = 1u << 1,
    AP_STAGE_SYNC = 1u << 2,
    AP_STAGE_AEC  = 1u << 3,
    AP_STAGE_RES  = 1u << 4,
    AP_STAGE_NS   = 1u << 5,
    AP_STAGE_AGC  = 1u << 6,
    AP_STAGE_VAD  = 1u << 7,
    AP_STAGE_ALL  = (1u << 8) - 1u
};

typedef struct ap_config {
    uint32_t io_sample_rate_hz;
    uint32_t internal_sample_rate_hz;
    uint32_t mic_channels;
    float mic_spacing_mm;

    uint32_t aec_filter_ms;
    uint32_t max_delay_ms;
    uint32_t initial_delay_ms;
    float aec_mu;
    uint32_t aec_adapt_stride;

    float ns_floor;
    float agc_target_dbfs;
    float limiter_dbfs;

    ap_resource_class_t resource_class;
    ap_stage_mask_t stages;
    /* SYNC sub-policies; both must be zero when AP_STAGE_SYNC is absent. */
    uint8_t enable_delay_tracking;
    uint8_t enable_clock_drift_compensation;
} ap_config_t;

typedef struct ap_metrics {
    float input_rms_dbfs;
    float output_rms_dbfs;
    float noise_rms_dbfs;
    float erle_db;
    float residual_echo_gain;
    float vad_probability;
    float estimated_drift_ppm;
    int32_t delay_error_samples;
    uint32_t estimated_delay_ms;
    uint32_t active_aec_taps;
    uint32_t active_aec_adapt_stride;
    uint32_t active_aec_partitions;
    uint32_t aec_block_samples;
    uint64_t processed_frames;
    uint64_t render_underruns;
    uint64_t aec_resets;
    uint64_t delay_jumps;
    uint64_t reference_sample_slips;
    uint8_t vad_active;
    uint8_t far_end_active;
    uint8_t double_talk_active;
    uint8_t frequency_res_active;
    ap_quality_t quality;
    ap_aec_backend_t aec_backend;
} ap_metrics_t;

typedef struct ap_pipeline ap_pipeline_t;

ap_config_t ap_config_default(ap_profile_t profile);
ap_config_t ap_config_for_resource(ap_profile_t profile,
                                   ap_resource_class_t resource_class);

/* Stages physically present in this build. Runtime configs must be a subset. */
ap_stage_mask_t ap_pipeline_compiled_stages(void);
ap_status_t ap_pipeline_validate_config(const ap_config_t *config);

size_t ap_pipeline_state_size(void);
size_t ap_pipeline_state_alignment(void);
size_t ap_pipeline_io_frame_samples(const ap_config_t *config);
size_t ap_pipeline_internal_frame_samples(const ap_config_t *config);

ap_status_t ap_pipeline_init(void *memory,
                             size_t memory_size,
                             const ap_config_t *config,
                             ap_pipeline_t **out_pipeline);
void ap_pipeline_reset(ap_pipeline_t *pipeline);
ap_status_t ap_pipeline_set_quality(ap_pipeline_t *pipeline, ap_quality_t quality);

size_t ap_pipeline_frame_samples(const ap_pipeline_t *pipeline);
uint32_t ap_pipeline_mic_channels(const ap_pipeline_t *pipeline);
uint32_t ap_pipeline_sample_rate_hz(const ap_pipeline_t *pipeline);
ap_stage_mask_t ap_pipeline_stages(const ap_pipeline_t *pipeline);

/* Render is meaningful only when AP_STAGE_SYNC is selected. */
ap_status_t ap_pipeline_push_render(ap_pipeline_t *pipeline,
                                    const int16_t *render,
                                    size_t samples);
ap_status_t ap_pipeline_process_capture(ap_pipeline_t *pipeline,
                                        const int16_t *mic_interleaved,
                                        size_t frames,
                                        int16_t *output);

void ap_pipeline_get_metrics(const ap_pipeline_t *pipeline, ap_metrics_t *metrics);
uint32_t ap_pipeline_algorithmic_latency_ms(const ap_pipeline_t *pipeline);

#ifdef __cplusplus
}
#endif

#endif
