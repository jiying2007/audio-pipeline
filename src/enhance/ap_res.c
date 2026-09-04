#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

#define AP_RES_NEAR_PROTECTION_RELEASE_ALPHA 0.25f
#define AP_RES_NORMAL_RELEASE_ALPHA 0.08f

static float ap_res_clamp(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

void ap_res_init(ap_res_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->gain = 1.0f;
}

float ap_res_process(ap_res_state_t *state,
                     ap_enhance_mode_t mode,
                     float *x,
                     uint32_t frame_samples,
                     float echo_energy,
                     float residual_energy,
                     int far_end_active,
                     int double_talk_active) {
    float target = 1.0f;
    uint32_t i;
    if (far_end_active && !double_talk_active) {
        const float floor_gain = mode == AP_ENHANCE_FULL ? 0.10f :
                                 (mode == AP_ENHANCE_LITE ? 0.16f : 0.24f);
        target = sqrtf(residual_energy /
                       (residual_energy + 0.8f * echo_energy + 1.0e-12f));
        target = ap_res_clamp(target, floor_gain, 1.0f);
    }
    if (target < state->gain) {
        state->gain = 0.45f * state->gain + 0.55f * target;
    } else {
        const float alpha = double_talk_active ?
                            AP_RES_NEAR_PROTECTION_RELEASE_ALPHA :
                            AP_RES_NORMAL_RELEASE_ALPHA;
        state->gain = (1.0f - alpha) * state->gain + alpha * target;
    }
    for (i = 0u; i < frame_samples; ++i) x[i] *= state->gain;
    return state->gain;
}
