#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

#define AP_VAD_NOISE_LIKE_CREST_DB 8.0f
#define AP_VAD_TRANSIENT_CREST_DB 12.0f
#define AP_VAD_FAST_NOISE_ALPHA 0.08f
#define AP_VAD_UPSTREAM_SPEECH_GUARD 0.55f
#define AP_VAD_LOCAL_SPEECH_GUARD 0.15f
#define AP_VAD_UPSTREAM_BLEND 0.40f
#define AP_VAD_DECISION_THRESHOLD 0.45f
#define AP_VAD_SOFT_ATTACK_THRESHOLD 0.30f
#define AP_VAD_SOFT_UPSTREAM_THRESHOLD 0.45f
#define AP_VAD_SOFT_ATTACK_FRAMES 3u
#define AP_VAD_ACTIVE_STATE_BASE (AP_VAD_SOFT_ATTACK_FRAMES + 1u)
#define AP_VAD_HANGOVER_FRAMES 8u
#define AP_VAD_ACTIVE_STATE_MAX (AP_VAD_ACTIVE_STATE_BASE + AP_VAD_HANGOVER_FRAMES - 1u)

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
    int upstream_speech;

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

    /* Upstream NS probability is useful corroborating evidence, but it is not an
     * independent speech oracle: rapidly changing noise can produce high
     * spectral speech likelihood. Require some local level evidence before it
     * can freeze noise adaptation or bypass transient suppression. */
    upstream_speech = use_upstream_probability &&
                      upstream_speech_probability > AP_VAD_UPSTREAM_SPEECH_GUARD &&
                      prob > AP_VAD_LOCAL_SPEECH_GUARD;

    if (!upstream_speech && crest_db > AP_VAD_TRANSIENT_CREST_DB && prob > 0.30f)
        prob = 0.30f;

    if (use_upstream_probability && upstream_speech_probability > prob) {
        prob += AP_VAD_UPSTREAM_BLEND * (upstream_speech_probability - prob);
        prob = ap_vad_clamp(prob, 0.0f, 1.0f);
    }

    if (prob < 0.35f) {
        state->noise_rms = 0.98f * state->noise_rms + 0.02f * rms;
    } else if (!upstream_speech &&
               crest_db >= AP_VAD_NOISE_LIKE_CREST_DB &&
               crest_db <= AP_VAD_TRANSIENT_CREST_DB) {
        /* Escape the one-way speech latch for noise-like frames. Upstream NS
         * evidence alone is deliberately insufficient to block this path. */
        state->noise_rms = (1.0f - AP_VAD_FAST_NOISE_ALPHA) * state->noise_rms +
                           AP_VAD_FAST_NOISE_ALPHA * rms;
    }

    /* Reuse the existing 32-bit hangover field as a compact decision state so
     * the temporal discriminator adds no pipeline-state bytes. Values below
     * AP_VAD_ACTIVE_STATE_BASE are an inactive soft-attack count; values at or
     * above it are an active hangover countdown. A single high-confidence frame
     * still activates immediately. Moderate NS-correlated evidence must persist
     * for three consecutive frames, which recovers sustained speech near the
     * threshold without making isolated non-stationary noise peaks authoritative. */
    if (prob > AP_VAD_DECISION_THRESHOLD) {
        state->hangover = AP_VAD_ACTIVE_STATE_MAX;
    } else if (state->hangover >= AP_VAD_ACTIVE_STATE_BASE) {
        state->hangover--;
    } else if (use_upstream_probability &&
               upstream_speech_probability > AP_VAD_SOFT_UPSTREAM_THRESHOLD &&
               prob > AP_VAD_SOFT_ATTACK_THRESHOLD) {
        if (state->hangover < AP_VAD_SOFT_ATTACK_FRAMES) state->hangover++;
        if (state->hangover >= AP_VAD_SOFT_ATTACK_FRAMES)
            state->hangover = AP_VAD_ACTIVE_STATE_MAX;
    } else {
        state->hangover = 0u;
    }
    result->probability = prob;
    result->active = (uint8_t)(state->hangover >= AP_VAD_ACTIVE_STATE_BASE);
}
