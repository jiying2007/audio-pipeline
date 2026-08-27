#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_H
#define AUDIO_PIPELINE_AUDIO_PIPELINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AP_FRAME_MS 10u
#define AP_MAX_MIC_CHANNELS 2u
#define AP_MAX_IO_RATE_HZ 48000u
#define AP_MAX_IO_FRAME_SAMPLES (AP_MAX_IO_RATE_HZ / 100u)

/* Caller-owned storage contract. The exact build-specific requirement is
 * returned by ap_pipeline_state_size(); static callers may reserve this hard
 * ceiling. Storage must satisfy AP_PIPELINE_STATE_ALIGNMENT. */
#define AP_PIPELINE_STATE_MAX_BYTES 80000u
#define AP_PIPELINE_STATE_ALIGNMENT 16u

typedef enum ap_status {
    AP_OK = 0,
    AP_EINVAL = -1,
    AP_ENOMEM = -2,
    AP_ESTATE = -3,
    AP_EFULL = -4,
    AP_EEMPTY = -5
} ap_status_t;

typedef enum ap_profile {
    AP_PROFILE_CALL = 0,
    AP_PROFILE_ASSISTANT = 1
} ap_profile_t;

/* Product-time resource envelope. This is independent from FULL/LITE/SAFE,
 * which is the runtime overload state machine. */
typedef enum ap_resource_class {
    AP_RESOURCE_TINY = 0,
    AP_RESOURCE_LOW = 1,
    AP_RESOURCE_STANDARD = 2
} ap_resource_class_t;

typedef enum ap_quality {
    AP_QUALITY_SAFE = 0,
    AP_QUALITY_LITE = 1,
    AP_QUALITY_FULL = 2
} ap_quality_t;

typedef enum ap_aec_backend {
    AP_AEC_BACKEND_MDF = 0,
    AP_AEC_BACKEND_NLMS = 1
} ap_aec_backend_t;

typedef struct ap_config {
    uint32_t io_sample_rate_hz;
    uint32_t internal_sample_rate_hz;
    uint32_t mic_channels;
    float mic_spacing_mm;

    uint32_t aec_filter_ms;
    uint32_t max_delay_ms;
    uint32_t initial_delay_ms;
    float aec_mu;
    /* MDF: number of 2 ms sub-blocks between adaptation updates.
     * NLMS: number of samples between coefficient updates. */
    uint32_t aec_adapt_stride;

    float ns_floor;
    float agc_target_dbfs;
    float limiter_dbfs;

    ap_resource_class_t resource_class;
    uint8_t enable_hpf;
    uint8_t enable_beamformer;
    uint8_t enable_delay_tracking;
    uint8_t enable_clock_drift_compensation;
    uint8_t enable_aec;
    uint8_t enable_residual_echo_suppression;
    uint8_t enable_noise_suppression;
    uint8_t enable_agc;
    uint8_t enable_vad;
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

/* Standard resource envelope convenience constructor. */
ap_config_t ap_config_default(ap_profile_t profile);
/* Explicit product resource envelope; callers may override fields afterwards. */
ap_config_t ap_config_for_resource(ap_profile_t profile,
                                   ap_resource_class_t resource_class);

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

/* Runtime geometry getters avoid duplicating configuration in adapters. */
size_t ap_pipeline_frame_samples(const ap_pipeline_t *pipeline);
uint32_t ap_pipeline_mic_channels(const ap_pipeline_t *pipeline);
uint32_t ap_pipeline_sample_rate_hz(const ap_pipeline_t *pipeline);

/* Push exactly one 10 ms mono post-mix/post-gain DAC reference frame. */
ap_status_t ap_pipeline_push_render(ap_pipeline_t *pipeline,
                                    const int16_t *render,
                                    size_t samples);

/* Process exactly one 10 ms interleaved microphone frame and produce mono S16. */
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
