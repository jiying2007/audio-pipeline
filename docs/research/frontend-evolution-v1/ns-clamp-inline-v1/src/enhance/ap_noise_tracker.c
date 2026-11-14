#include "enhance/ap_noise_tracker.h"
#include <string.h>

#define AP_MCRA_MINIMUM_RISE_PERIOD 8u
#define AP_MCRA_MINIMUM_RISE_FACTOR 1.126493f

void ap_noise_tracker_init(ap_noise_tracker_state_t *state) {
    memset(state, 0, sizeof(*state));
}

void ap_noise_tracker_update(ap_noise_tracker_state_t *state,
                             uint32_t bin,
                             float power,
                             ap_noise_tracker_result_t *result) {
    float noise = state->estimate[bin];
    float speech = 0.0f;

    if (state->frame < 20u || noise <= 0.0f) {
        noise = power;
#if defined(AP_BUILD_NS_MCRA)
        state->minimum[bin] = power;
#endif
    } else {
#if defined(AP_BUILD_NS_MCRA)
        float minimum = state->minimum[bin];
        float ratio;
        float alpha;
        if (minimum <= 0.0f) minimum = noise;
        if (power < minimum) minimum = power;
        if (minimum < 1.0e-12f) minimum = 1.0e-12f;
        state->minimum[bin] = minimum;
        ratio = power / minimum;
        speech = ap_clampf((ratio - 1.6f) * 0.30f, 0.0f, 1.0f);
        alpha = 0.90f + 0.098f * speech;
        noise = alpha * noise + (1.0f - alpha) * power;
#else
        const float post = power / (noise + 1.0e-12f);
        float alpha;
        speech = ap_clampf((post - 1.4f) * 0.35f, 0.0f, 1.0f);
        alpha = speech > 0.35f ? 0.995f : 0.92f;
        noise = alpha * noise + (1.0f - alpha) * power;
#endif
    }

    state->estimate[bin] = noise;
    result->noise = noise;
    result->speech_probability = speech;
}

void ap_noise_tracker_next_frame(ap_noise_tracker_state_t *state) {
    state->frame++;
#if defined(AP_BUILD_NS_MCRA)
    if (state->frame >= 20u &&
        (state->frame & (AP_MCRA_MINIMUM_RISE_PERIOD - 1u)) == 0u) {
        uint32_t k;
        for (k = 0u; k < AP_NOISE_TRACKER_BINS_MAX; ++k) {
            if (state->minimum[k] > 0.0f)
                state->minimum[k] *= AP_MCRA_MINIMUM_RISE_FACTOR;
        }
    }
#endif
}
