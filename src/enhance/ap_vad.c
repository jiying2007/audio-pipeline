#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

static float ap_vad_clamp(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

void ap_vad_init(ap_vad_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->noise_rms = 1.0e-3f;
}

void ap_vad_process(ap_vad_state_t *state,
                    const float *x,
                    uint32_t n,
                    float upstream_speech_probability,
                    int use_upstream_probability,
                    ap_vad_result_t *result) {
    float e = 1.0e-12f;
    uint32_t i;
    float rms, ratio_db, prob;
    for (i = 0u; i < n; ++i) e += x[i] * x[i];
    rms = sqrtf(e / (float)n);
    if (state->noise_rms <= 0.0f) state->noise_rms = rms + 1.0e-6f;
    ratio_db = 20.0f * log10f((rms + 1.0e-7f) /
                              (state->noise_rms + 1.0e-7f));
    prob = ap_vad_clamp((ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);
    if (use_upstream_probability && upstream_speech_probability > prob)
        prob = upstream_speech_probability;
    if (prob < 0.35f)
        state->noise_rms = 0.98f * state->noise_rms + 0.02f * rms;
    if (prob > 0.45f) state->hangover = 8u;
    else if (state->hangover) state->hangover--;
    result->probability = prob;
    result->active = (uint8_t)(state->hangover > 0u);
}
