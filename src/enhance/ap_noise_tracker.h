#ifndef AUDIO_PIPELINE_AP_NOISE_TRACKER_H
#define AUDIO_PIPELINE_AP_NOISE_TRACKER_H

#include "dsp/ap_dsp.h"
#include <stdint.h>

#define AP_NOISE_TRACKER_BINS_MAX 257u

typedef struct ap_noise_tracker_state {
    float estimate[AP_NOISE_TRACKER_BINS_MAX];
#if defined(AP_BUILD_NS_MCRA)
    float minimum[AP_NOISE_TRACKER_BINS_MAX];
#elif !defined(AP_BUILD_NS_EMA)
#error "Exactly one NS noise estimator must be selected"
#endif
    uint32_t frame;
} ap_noise_tracker_state_t;

typedef struct ap_noise_tracker_result {
    float noise;
    float speech_probability;
} ap_noise_tracker_result_t;

void ap_noise_tracker_init(ap_noise_tracker_state_t *state);
void ap_noise_tracker_update(ap_noise_tracker_state_t *state,
                             uint32_t bin,
                             float power,
                             ap_noise_tracker_result_t *result);
void ap_noise_tracker_next_frame(ap_noise_tracker_state_t *state);

#endif
