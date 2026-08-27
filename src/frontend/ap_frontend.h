#ifndef AUDIO_PIPELINE_AP_FRONTEND_H
#define AUDIO_PIPELINE_AP_FRONTEND_H

#include <stdint.h>

#define AP_FRONTEND_MAX_MIC_CHANNELS 2u
#define AP_BF_HISTORY 8u

typedef struct ap_frontend_state {
    float hpf_r;
    float hpf_x[AP_FRONTEND_MAX_MIC_CHANNELS];
    float hpf_y[AP_FRONTEND_MAX_MIC_CHANNELS];
    float bf_history[AP_FRONTEND_MAX_MIC_CHANNELS][AP_BF_HISTORY];
    int bf_lag;
    int bf_max_lag;
    uint32_t bf_counter;
} ap_frontend_state_t;

void ap_frontend_init(ap_frontend_state_t *state,
                      uint32_t sample_rate_hz,
                      float mic_spacing_mm);
void ap_hpf_process(ap_frontend_state_t *state,
                    float *x,
                    uint32_t n,
                    uint32_t channel);
void ap_beamform(ap_frontend_state_t *state,
                 int track_direction,
                 float *a,
                 float *b,
                 float *out,
                 uint32_t n);

#endif
