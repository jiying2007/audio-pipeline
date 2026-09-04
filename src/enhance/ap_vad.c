#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

#define AP_VAD_NOISE_LIKE_CREST_DB 8.0f
#define AP_VAD_TRANSIENT_CREST_DB 12.0f
#define AP_VAD_FAST_NOISE_ALPHA 0.08f
#define AP_VAD_UPSTREAM_SPEECH_GUARD 0.55f

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
    float peak = 0.0f;
    uint32_t i;
    float rms, ratio_db, crest_db, prob;
    const int upstream_speech =
        use_upstream_probability && upstream_speech_probability > AP_VAD_UPSTREAM_SPEECH_GUARD;

    for (i = 0u; i < n; ++i) {
        const float magnitude = fabsf(x[i]);
        e += x[i] * x[i];
        if (magnitude > peak) peak = magnitude;
    }
    rms = sqrtf(e / (float)n);
    if (state->noise_rms <= 0.0f) state->noise_rms = rms + 1.0e-6f;
    ratio_db = 20.0f * log10f((rms + 1.0e-7f) /
                              (state->noise_rms + 1.0e-7f));
    crest_db = 20.0f * log10f((peak + 1.0e-7f) / (rms + 1.0e-7f));
    prob = ap_vad_clamp((ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);

    /* A short high-crest transient is much more likely to be a click/impact than
     * sustained speech. Keep an explicit upstream speech estimate authoritative
     * so fricatives/plosives are not suppressed when NS has positive evidence. */
    if (!upstream_speech && crest_db > AP_VAD_TRANSIENT_CREST_DB && prob > 0.30f)
        prob = 0.30f;

    if (use_upstream_probability && upstream_speech_probability > prob)
        prob = upstream_speech_probability;

    if (prob < 0.35f) {
        state->noise_rms = 0.98f * state->noise_rms + 0.02f * rms;
    } else if (!upstream_speech &&
               crest_db >= AP_VAD_NOISE_LIKE_CREST_DB &&
               crest_db <= AP_VAD_TRANSIENT_CREST_DB) {
        /* The old one-way gate could permanently classify a stationary noise
         * floor as speech: once prob exceeded 0.35 the floor stopped adapting.
         * Noise-like crest factors provide a bounded escape path without a
         * fixed startup calibration window or public tuning/ABI change. */
        state->noise_rms = (1.0f - AP_VAD_FAST_NOISE_ALPHA) * state->noise_rms +
                           AP_VAD_FAST_NOISE_ALPHA * rms;
    }

    if (prob > 0.45f) state->hangover = 8u;
    else if (state->hangover) state->hangover--;
    result->probability = prob;
    result->active = (uint8_t)(state->hangover > 0u);
}
