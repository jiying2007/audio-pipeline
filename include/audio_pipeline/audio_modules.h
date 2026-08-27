#ifndef AUDIO_PIPELINE_AUDIO_MODULES_H
#define AUDIO_PIPELINE_AUDIO_MODULES_H

#include "audio_pipeline/audio_types.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AP_MODULE_STATE_ALIGNMENT 16u
#define AP_MODULE_STATE_MAX_BYTES 40000u

#if AP_HAVE_MODULE_RESAMPLER
ap_status_t ap_module_resampler_input_s16(const int16_t *input,
                                          size_t input_frames,
                                          uint32_t channels,
                                          uint32_t channel,
                                          float *output,
                                          size_t output_frames);
ap_status_t ap_module_resampler_output_s16(const float *input,
                                           size_t input_frames,
                                           int16_t *output,
                                           size_t output_frames);
#endif

#if AP_HAVE_MODULE_HPF
typedef struct ap_hpf_module ap_hpf_module_t;
size_t ap_module_hpf_state_size(void);
ap_status_t ap_module_hpf_init(void *memory, size_t memory_size,
                               uint32_t sample_rate_hz, uint32_t channels,
                               ap_hpf_module_t **out);
ap_status_t ap_module_hpf_process(ap_hpf_module_t *module,
                                  float *samples, size_t frame_samples,
                                  uint32_t channel);
#endif

#if AP_HAVE_MODULE_BF
typedef struct ap_beamformer_module ap_beamformer_module_t;
size_t ap_module_beamformer_state_size(void);
ap_status_t ap_module_beamformer_init(void *memory, size_t memory_size,
                                      uint32_t sample_rate_hz,
                                      float mic_spacing_mm,
                                      ap_beamformer_module_t **out);
ap_status_t ap_module_beamformer_process(ap_beamformer_module_t *module,
                                         int track_direction,
                                         float *mic0, float *mic1,
                                         float *output,
                                         size_t frame_samples);
#endif

#if AP_HAVE_MODULE_SYNC
typedef struct ap_sync_module ap_sync_module_t;
typedef struct ap_module_sync_event {
    int32_t delay_error_samples;
    uint32_t reference_sample_slips;
    uint8_t delay_observed;
    uint8_t route_jump;
} ap_module_sync_event_t;
typedef struct ap_module_sync_status {
    float estimated_drift_ppm;
    uint32_t delay_samples;
} ap_module_sync_status_t;
size_t ap_module_sync_state_size(void);
ap_status_t ap_module_sync_init(void *memory, size_t memory_size,
                                uint32_t initial_delay_samples,
                                ap_sync_module_t **out);
ap_status_t ap_module_sync_push_render(ap_sync_module_t *module,
                                       const float *render, size_t samples,
                                       uint64_t processed_frames);
ap_status_t ap_module_sync_track(ap_sync_module_t *module,
                                 const float *mic, size_t frame_samples,
                                 uint32_t sample_rate_hz,
                                 uint32_t max_delay_ms,
                                 int enable_delay_tracking,
                                 int enable_clock_drift_compensation,
                                 ap_module_sync_event_t *event);
ap_status_t ap_module_sync_get_reference(ap_sync_module_t *module,
                                         size_t frame_samples,
                                         float *output,
                                         int *underrun);
void ap_module_sync_get_status(const ap_sync_module_t *module,
                               ap_module_sync_status_t *status);
#endif

#if AP_HAVE_MODULE_AEC
typedef struct ap_aec_module ap_aec_module_t;
typedef struct ap_module_aec_config {
    uint32_t sample_rate_hz;
    uint32_t filter_ms;
    uint32_t adapt_stride;
    float mu;
} ap_module_aec_config_t;
typedef struct ap_module_aec_result {
    float echo_energy;
    uint32_t active_taps;
    uint32_t active_partitions;
    uint32_t block_samples;
    ap_aec_backend_t backend;
} ap_module_aec_result_t;
size_t ap_module_aec_state_size(void);
ap_status_t ap_module_aec_init(void *memory, size_t memory_size,
                               const ap_module_aec_config_t *config,
                               ap_aec_module_t **out);
void ap_module_aec_reset(ap_aec_module_t *module);
ap_status_t ap_module_aec_process(ap_aec_module_t *module,
                                  const float *mic,
                                  const float *reference,
                                  float *output,
                                  float *predicted_echo,
                                  size_t frame_samples,
                                  int far_end_active,
                                  int double_talk_active,
                                  ap_module_aec_result_t *result);
#endif

#if AP_HAVE_MODULE_RES
typedef struct ap_res_module ap_res_module_t;
size_t ap_module_res_state_size(void);
ap_status_t ap_module_res_init(void *memory, size_t memory_size,
                               ap_res_module_t **out);
ap_status_t ap_module_res_process(ap_res_module_t *module,
                                  ap_quality_t quality,
                                  float *samples, size_t frame_samples,
                                  float echo_energy,
                                  float residual_energy,
                                  int far_end_active,
                                  int double_talk_active,
                                  float *applied_gain);
#endif

#if AP_HAVE_MODULE_NS
typedef struct ap_ns_module ap_ns_module_t;
typedef struct ap_module_ns_config {
    uint32_t sample_rate_hz;
    float floor_gain;
} ap_module_ns_config_t;
typedef struct ap_module_ns_result {
    float noise_rms_dbfs;
    float speech_probability;
    float residual_echo_gain;
    uint8_t frequency_res_active;
} ap_module_ns_result_t;
size_t ap_module_ns_state_size(void);
ap_status_t ap_module_ns_init(void *memory, size_t memory_size,
                              const ap_module_ns_config_t *config,
                              ap_ns_module_t **out);
ap_status_t ap_module_ns_process(ap_ns_module_t *module,
                                 ap_quality_t quality,
                                 const float *input,
                                 const float *predicted_echo,
                                 float *output,
                                 size_t frame_samples,
                                 int enable_frequency_res,
                                 int far_end_active,
                                 int double_talk_active,
                                 ap_module_ns_result_t *result);
#endif

#if AP_HAVE_MODULE_AGC
typedef struct ap_agc_module ap_agc_module_t;
typedef struct ap_module_agc_config {
    float target_dbfs;
    float limiter_dbfs;
} ap_module_agc_config_t;
size_t ap_module_agc_state_size(void);
ap_status_t ap_module_agc_init(void *memory, size_t memory_size,
                               const ap_module_agc_config_t *config,
                               ap_agc_module_t **out);
ap_status_t ap_module_agc_process(ap_agc_module_t *module,
                                  float *samples, size_t frame_samples);
#endif

#if AP_HAVE_MODULE_VAD
typedef struct ap_vad_module ap_vad_module_t;
typedef struct ap_module_vad_result {
    float probability;
    uint8_t active;
} ap_module_vad_result_t;
size_t ap_module_vad_state_size(void);
ap_status_t ap_module_vad_init(void *memory, size_t memory_size,
                               ap_vad_module_t **out);
ap_status_t ap_module_vad_process(ap_vad_module_t *module,
                                  const float *samples, size_t frame_samples,
                                  float upstream_speech_probability,
                                  int use_upstream_probability,
                                  ap_module_vad_result_t *result);
#endif

#ifdef __cplusplus
}
#endif

#endif
