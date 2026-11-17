#ifndef AUDIO_PIPELINE_AP_ENHANCE_H
#define AUDIO_PIPELINE_AP_ENHANCE_H

#include <stdint.h>

#ifndef AP_BUILD_STAGE_RES
#define AP_BUILD_STAGE_RES 0
#endif
#ifndef AP_BUILD_STAGE_NS
#define AP_BUILD_STAGE_NS 0
#endif
#ifndef AP_BUILD_STAGE_AGC
#define AP_BUILD_STAGE_AGC 0
#endif
#ifndef AP_BUILD_STAGE_VAD
#define AP_BUILD_STAGE_VAD 0
#endif

typedef enum ap_enhance_mode {
    AP_ENHANCE_SAFE = 0,
    AP_ENHANCE_LITE = 1,
    AP_ENHANCE_FULL = 2
} ap_enhance_mode_t;

#if AP_BUILD_STAGE_RES
typedef struct ap_res_state {
    float gain;
} ap_res_state_t;
void ap_res_init(ap_res_state_t *state);
float ap_res_process(ap_res_state_t *state,
                     ap_enhance_mode_t mode,
                     float *samples,
                     uint32_t frame_samples,
                     float echo_energy,
                     float residual_energy,
                     int far_end_active,
                     int double_talk_active);
#endif

#if AP_BUILD_STAGE_NS
#include "ap_limits.h"
#include "dsp/ap_dsp.h"
#include "enhance/ap_noise_tracker.h"
#define AP_NS_FFT_MAX 512u
#define AP_NS_BINS_MAX AP_NOISE_TRACKER_BINS_MAX

typedef struct ap_ns_state {
    uint32_t nfft;
    float previous[AP_INTERNAL_FRAME_MAX];
    float overlap[AP_INTERNAL_FRAME_MAX];
    ap_noise_tracker_state_t noise_tracker;
    ap_complex_t spectrum[AP_NS_FFT_MAX];
    float speech_probability;
    float noise_rms_dbfs;
#if AP_BUILD_STAGE_RES
    float previous_echo[AP_INTERNAL_FRAME_MAX];
    float residual_gain_bins[AP_NS_BINS_MAX];
    float echo_power[AP_NS_BINS_MAX];
#endif
} ap_ns_state_t;

typedef struct ap_ns_result {
    float residual_echo_gain;
    float noise_rms_dbfs;
    float speech_probability;
    uint8_t frequency_res_active;
} ap_ns_result_t;

void ap_ns_init(ap_ns_state_t *state, uint32_t frame_samples);
void ap_ns_process(ap_ns_state_t *state,
                   ap_enhance_mode_t mode,
                   float floor_gain,
                   const float *input,
                   const float *echo,
                   float *output,
                   uint32_t frame_samples,
                   int enable_frequency_res,
                   int far_end_active,
                   int double_talk_active,
                   ap_ns_result_t *result);
#endif

#if AP_BUILD_STAGE_AGC
typedef struct ap_agc_state {
    float gain;
    float target_linear;
    float limiter_linear;
} ap_agc_state_t;
void ap_agc_init(ap_agc_state_t *state,
                 float target_dbfs,
                 float limiter_dbfs);
void ap_agc_process(ap_agc_state_t *state,
                    float *samples,
                    uint32_t frame_samples);
void ap_agc_process_controlled(ap_agc_state_t *state,
                               float *samples,
                               uint32_t frame_samples,
                               int allow_gain_increase);
#endif

#if AP_BUILD_STAGE_VAD
typedef struct ap_vad_state {
    float noise_rms;
    uint32_t hangover;
} ap_vad_state_t;
typedef struct ap_vad_result {
    float probability;
    uint8_t active;
} ap_vad_result_t;
void ap_vad_init(ap_vad_state_t *state);
void ap_vad_process(ap_vad_state_t *state,
                    const float *samples,
                    uint32_t frame_samples,
                    float upstream_speech_probability,
                    int use_upstream_probability,
                    ap_vad_result_t *result);
#endif

#endif
