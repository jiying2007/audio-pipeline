#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

static float ap_agc_clamp(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

void ap_agc_init(ap_agc_state_t *state,
                 float target_dbfs,
                 float limiter_dbfs) {
    memset(state, 0, sizeof(*state));
    state->gain = 1.0f;
    state->target_linear = powf(10.0f, target_dbfs / 20.0f);
    state->limiter_linear = powf(10.0f, limiter_dbfs / 20.0f);
}

void ap_agc_process(ap_agc_state_t *state,
                    float *x,
                    uint32_t n) {
    uint32_t i;
    float e = 1.0e-12f;
    float peak = 0.0f, target_gain, alpha;
    for (i = 0u; i < n; ++i) {
        const float a = fabsf(x[i]);
        e += x[i] * x[i];
        if (a > peak) peak = a;
    }
    {
        const float rms = sqrtf(e / (float)n);
        target_gain = ap_agc_clamp(state->target_linear / (rms + 1.0e-6f), 0.25f, 8.0f);
    }
    alpha = target_gain < state->gain ? 0.25f : 0.015f;
    state->gain += alpha * (target_gain - state->gain);
    {
        const float limit = state->limiter_linear;
        float gain = state->gain;
        if (peak * gain > limit && peak > 1.0e-6f) gain = limit / peak;
        for (i = 0u; i < n; ++i) x[i] = ap_agc_clamp(x[i] * gain, -limit, limit);
    }
}
