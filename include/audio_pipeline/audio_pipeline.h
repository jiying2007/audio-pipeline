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
#define AP_PIPELINE_CONTROL_API_VERSION 2u

typedef enum ap_profile { AP_PROFILE_CALL = 0, AP_PROFILE_ASSISTANT = 1 } ap_profile_t;
typedef enum ap_resource_class { AP_RESOURCE_TINY = 0, AP_RESOURCE_LOW = 1, AP_RESOURCE_STANDARD = 2 } ap_resource_class_t;
typedef uint32_t ap_stage_mask_t;
enum {
    AP_STAGE_HPF=1u<<0, AP_STAGE_BF=1u<<1, AP_STAGE_SYNC=1u<<2, AP_STAGE_AEC=1u<<3,
    AP_STAGE_RES=1u<<4, AP_STAGE_NS=1u<<5, AP_STAGE_AGC=1u<<6, AP_STAGE_VAD=1u<<7,
    AP_STAGE_ALL=(1u<<8)-1u
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
    uint32_t aec_convergence_frames;
    uint64_t processed_frames;
    uint64_t render_underruns;
    uint64_t aec_resets;
    uint64_t delay_jumps;
    uint64_t reference_sample_slips;
    uint64_t timestamp_observations;
    uint8_t vad_active;
    uint8_t far_end_active;
    uint8_t double_talk_active;
    uint8_t frequency_res_active;
    uint8_t erle_valid;
    uint8_t aec_converged;
    ap_quality_t quality;
    ap_aec_backend_t aec_backend;
} ap_metrics_t;

typedef uint32_t ap_discontinuity_flags_t;
enum {
    AP_DISCONTINUITY_CAPTURE_GAP = 1u << 0,
    AP_DISCONTINUITY_RENDER_GAP = 1u << 1,
    AP_DISCONTINUITY_CLOCK_RESET = 1u << 2,
    AP_DISCONTINUITY_XRUN = 1u << 3,
    AP_DISCONTINUITY_CODEC_REOPEN = 1u << 4,
    AP_DISCONTINUITY_ROUTE_CHANGE = 1u << 5
};

typedef uint32_t ap_tuning_mask_t;
enum {
    AP_TUNING_AEC_MU = 1u << 0,
    AP_TUNING_NS_FLOOR = 1u << 1,
    AP_TUNING_AGC_TARGET = 1u << 2,
    AP_TUNING_LIMITER = 1u << 3
};

typedef struct ap_tuning {
    uint32_t struct_size;
    uint32_t api_version;
    ap_tuning_mask_t mask;
    float aec_mu;
    float ns_floor;
    float agc_target_dbfs;
    float limiter_dbfs;
    uint32_t reserved[8];
} ap_tuning_t;

typedef struct ap_pipeline ap_pipeline_t;

ap_config_t ap_config_default(ap_profile_t profile);
ap_config_t ap_config_for_resource(ap_profile_t profile, ap_resource_class_t resource_class);
ap_stage_mask_t ap_pipeline_compiled_stages(void);
ap_status_t ap_pipeline_validate_config(const ap_config_t *config);
size_t ap_pipeline_state_size(void);
size_t ap_pipeline_state_alignment(void);
size_t ap_pipeline_io_frame_samples(const ap_config_t *config);
size_t ap_pipeline_internal_frame_samples(const ap_config_t *config);
ap_status_t ap_pipeline_init(void *memory,size_t memory_size,const ap_config_t *config,ap_pipeline_t **out_pipeline);
void ap_pipeline_reset(ap_pipeline_t *pipeline);
ap_status_t ap_pipeline_set_quality(ap_pipeline_t *pipeline, ap_quality_t quality);
size_t ap_pipeline_frame_samples(const ap_pipeline_t *pipeline);
uint32_t ap_pipeline_mic_channels(const ap_pipeline_t *pipeline);
uint32_t ap_pipeline_sample_rate_hz(const ap_pipeline_t *pipeline);
ap_stage_mask_t ap_pipeline_stages(const ap_pipeline_t *pipeline);
ap_status_t ap_pipeline_push_render(ap_pipeline_t *pipeline,const int16_t *render,size_t samples);
ap_status_t ap_pipeline_process_capture(ap_pipeline_t *pipeline,const int16_t *mic_interleaved,size_t frames,int16_t *output);
/* Timestamps must refer to corresponding hardware capture/playback positions in
 * the same monotonic clock domain. They seed/narrow sync and are optional. */
ap_status_t ap_pipeline_observe_io_timestamps(ap_pipeline_t *pipeline,
                                              uint64_t capture_timestamp_ns,
                                              uint64_t render_timestamp_ns);
/* Explicit product route/path notification. Clears stale reference/alignment and
 * adaptive AEC state instead of waiting for correlation to rediscover the path. */
ap_status_t ap_pipeline_notify_echo_path_change(ap_pipeline_t *pipeline);
/* Stream discontinuity is distinct from an acoustic echo-path change. It is used
 * for XRUN/capture gaps/render gaps/clock resets and may reset timing/AEC state. */
ap_status_t ap_pipeline_notify_stream_discontinuity(ap_pipeline_t *pipeline,
                                                    ap_discontinuity_flags_t flags,
                                                    uint32_t lost_frames);
/* Frame-boundary tuning control. The caller must serialize this with synchronous
 * processing; the Linux runtime command queue provides that ownership boundary. */
ap_status_t ap_pipeline_apply_tuning(ap_pipeline_t *pipeline,
                                     const ap_tuning_t *tuning);
void ap_pipeline_get_metrics(const ap_pipeline_t *pipeline, ap_metrics_t *metrics);
uint32_t ap_pipeline_algorithmic_latency_ms(const ap_pipeline_t *pipeline);

#ifdef __cplusplus
}
#endif
#endif
