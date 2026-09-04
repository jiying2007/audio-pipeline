#ifndef AUDIO_PIPELINE_AP_FRONTEND_H
#define AUDIO_PIPELINE_AP_FRONTEND_H

#include <stdint.h>

#define AP_FRONTEND_MAX_MIC_CHANNELS 2u
#define AP_BF_HISTORY 8u

typedef struct ap_hpf_state {
    float r;
    float x[AP_FRONTEND_MAX_MIC_CHANNELS];
    float y[AP_FRONTEND_MAX_MIC_CHANNELS];
    uint32_t channels;
} ap_hpf_state_t;

typedef struct ap_beamformer_state {
    float history[AP_FRONTEND_MAX_MIC_CHANNELS][AP_BF_HISTORY];
    float weight_a;
    int lag;
    int max_lag;
    uint32_t counter;
} ap_beamformer_state_t;

void ap_hpf_init(ap_hpf_state_t *state,
                 uint32_t sample_rate_hz,
                 uint32_t channels);
void ap_hpf_process(ap_hpf_state_t *state,
                    float *x,
                    uint32_t n,
                    uint32_t channel);

void ap_beamformer_init(ap_beamformer_state_t *state,
                        uint32_t sample_rate_hz,
                        float mic_spacing_mm);
void ap_beamformer_process(ap_beamformer_state_t *state,
                           int track_direction,
                           float *mic0,
                           float *mic1,
                           float *out,
                           uint32_t n);

#endif
