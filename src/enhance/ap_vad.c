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
#define AP_VAD_LOCAL_DECISION_THRESHOLD 0.45f
#define AP_VAD_NS_DECISION_THRESHOLD 0.35f

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
    float decision_threshold;
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

    /* Keep standalone/local VAD at the historical 0.45 decision point. The
     * NS-assisted path uses the evidence-derived 0.35 operating point: after
     * replacing the inverted flat NS mean with the sparsity-gap cue, three-seed
     * diagnostics showed roughly +9 pp stable speech-frame coverage on the hard
     * non-stationary seed for only ~+4 pp stable noise-frame admission, while
     * stationary negative admission increased by only ~3.2 pp. Strong recall/FPR
     * gates remain the authority; this is not a user-tunable shipping knob. */
    decision_threshold = use_upstream_probability ?
                         AP_VAD_NS_DECISION_THRESHOLD :
                         AP_VAD_LOCAL_DECISION_THRESHOLD;
    if (prob > decision_threshold) state->hangover = 8u;
    else if (state->hangover) state->hangover--;
    result->probability = prob;
    result->active = (uint8_t)(state->hangover > 0u);
}
