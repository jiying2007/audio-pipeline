#ifndef AUDIO_PIPELINE_AP_ENHANCE_H
#define AUDIO_PIPELINE_AP_ENHANCE_H

#include "ap_limits.h"
#include "dsp/ap_dsp.h"
#include "enhance/ap_noise_tracker.h"
#include <stdint.h>

#define AP_NS_FFT_MAX 512u
#define AP_NS_BINS_MAX AP_NOISE_TRACKER_BINS_MAX

typedef enum ap_enhance_mode {
    AP_ENHANCE_SAFE = 0,
    AP_ENHANCE_LITE = 1,
    AP_ENHANCE_FULL = 2
} ap_enhance_mode_t;

typedef struct ap_ns_state {
    uint32_t nfft;
    float previous[AP_INTERNAL_FRAME_MAX];
    float previous_echo[AP_INTERNAL_FRAME_MAX];
    float overlap[AP_INTERNAL_FRAME_MAX];
    ap_noise_tracker_state_t noise_tracker;
    float residual_gain_bins[AP_NS_BINS_MAX];
    ap_complex_t spectrum[AP_NS_FFT_MAX];
    float echo_power[AP_NS_BINS_MAX];
    float speech_probability;
    float noise_rms_dbfs;
} ap_ns_state_t;

typedef struct ap_enhance_state {
    ap_ns_state_t ns;
    float agc_gain;
    float agc_target_linear;
    float limiter_linear;
    float residual_gain;
    float vad_noise_rms;
    uint32_t vad_hangover;
} ap_enhance_state_t;

typedef struct ap_enhance_params {
    float ns_floor;
    uint8_t enable_residual_echo_suppression;
    uint8_t enable_noise_suppression;
    uint8_t enable_agc;
    uint8_t enable_vad;
} ap_enhance_params_t;

typedef struct ap_enhance_result {
    float residual_echo_gain;
    float noise_rms_dbfs;
    float vad_probability;
    uint8_t vad_active;
    uint8_t frequency_res_active;
} ap_enhance_result_t;

void ap_enhance_init(ap_enhance_state_t *state,
                     uint32_t frame_samples,
                     float agc_target_dbfs,
                     float limiter_dbfs);
void ap_enhance_process(ap_enhance_state_t *state,
                        ap_enhance_mode_t mode,
                        const ap_enhance_params_t *params,
                        float *aec_residual,
                        const float *echo,
                        float *out,
                        uint32_t frame_samples,
                        float echo_energy,
                        float residual_energy,
                        int far_end_active,
                        int double_talk_active,
                        ap_enhance_result_t *result);

#endif
