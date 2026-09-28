#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define FRAME 160u
#define NS_FLOOR 0.12f
#define VAD_NOISE_LIKE_CREST_DB 8.0f
#define VAD_TRANSIENT_CREST_DB 12.0f
#define VAD_FAST_NOISE_ALPHA 0.08f
#define VAD_UPSTREAM_SPEECH_GUARD 0.55f
#define VAD_LOCAL_SPEECH_GUARD 0.15f
#define VAD_UPSTREAM_BLEND 0.40f
#define VAD_NS_DECISION_THRESHOLD 0.35f
#define VAD_STRONG_REFRESH_THRESHOLD 0.50f
#define VAD_STRONG_HOLD_FRAMES 8u
#define VAD_WEAK_HOLD_FRAMES 6u

enum refresh_kind {
    REFRESH_NONE = 0,
    REFRESH_WEAK = 1,
    REFRESH_STRONG = 2,
};

enum noise_update_kind {
    NOISE_UPDATE_NONE = 0,
    NOISE_UPDATE_SLOW = 1,
    NOISE_UPDATE_FAST = 2,
};

typedef struct vad_state {
    float noise_rms;
    uint32_t hangover;
} vad_state_t;

typedef struct diagnostic_result {
    float probability;
    float raw_probability;
    float pre_blend_probability;
    float rms;
    float noise_rms_before;
    float noise_rms_after;
    float ratio_db;
    float crest_db;
    uint32_t pre_hangover;
    uint32_t post_hangover;
    uint8_t active;
    uint8_t refresh_kind;
    uint8_t noise_update_kind;
    uint8_t guard_active;
    uint8_t upstream_guard_pass;
    uint8_t local_guard_pass;
    uint8_t transient_capped;
    uint8_t blend_applied;
} diagnostic_result_t;

static ap_ns_state_t ns_state;
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char public_shipping_mem[AP_MODULE_STATE_MAX_BYTES];
static ap_vad_module_t *public_shipping_module;
static vad_state_t diagnostic_state;

static float clampf_local(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static void diagnostic_init(vad_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->noise_rms = 1.0e-3f;
}

static void process_shipping_diagnostic(vad_state_t *state,
                                        const float *x,
                                        uint32_t n,
                                        float upstream_probability,
                                        diagnostic_result_t *result) {
    float e = 1.0e-12f;
    float peak = 0.0f;
    float prob;
    uint32_t i;
    int upstream_speech;

    memset(result, 0, sizeof(*result));
    result->pre_hangover = state->hangover;
    result->noise_rms_before = state->noise_rms;

    for (i = 0u; i < n; ++i) {
        const float magnitude = fabsf(x[i]);
        e += x[i] * x[i];
        if (magnitude > peak) peak = magnitude;
    }

    result->rms = sqrtf(e / (float)n);
    if (state->noise_rms <= 0.0f)
        state->noise_rms = result->rms + 1.0e-6f;
    result->noise_rms_before = state->noise_rms;
    result->ratio_db = 20.0f * log10f(
        (result->rms + 1.0e-7f) / (state->noise_rms + 1.0e-7f));
    result->crest_db = 20.0f * log10f(
        (peak + 1.0e-7f) / (result->rms + 1.0e-7f));
    prob = clampf_local((result->ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);
    result->raw_probability = prob;
    result->upstream_guard_pass =
        (uint8_t)(upstream_probability > VAD_UPSTREAM_SPEECH_GUARD);
    result->local_guard_pass =
        (uint8_t)(prob > VAD_LOCAL_SPEECH_GUARD);

    upstream_speech =
        result->upstream_guard_pass && result->local_guard_pass;
    result->guard_active = (uint8_t)(upstream_speech != 0);

    if (!upstream_speech &&
        result->crest_db > VAD_TRANSIENT_CREST_DB &&
        prob > 0.30f) {
        prob = 0.30f;
        result->transient_capped = 1u;
    }
    result->pre_blend_probability = prob;

    if (upstream_probability > prob) {
        prob += VAD_UPSTREAM_BLEND * (upstream_probability - prob);
        prob = clampf_local(prob, 0.0f, 1.0f);
        result->blend_applied = 1u;
    }

    if (prob < VAD_NS_DECISION_THRESHOLD) {
        state->noise_rms = 0.98f * state->noise_rms + 0.02f * result->rms;
        result->noise_update_kind = NOISE_UPDATE_SLOW;
    } else if (!upstream_speech &&
               result->crest_db >= VAD_NOISE_LIKE_CREST_DB &&
               result->crest_db <= VAD_TRANSIENT_CREST_DB) {
        state->noise_rms =
            (1.0f - VAD_FAST_NOISE_ALPHA) * state->noise_rms +
            VAD_FAST_NOISE_ALPHA * result->rms;
        result->noise_update_kind = NOISE_UPDATE_FAST;
    }
    result->noise_rms_after = state->noise_rms;

    if (prob >= VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = VAD_STRONG_HOLD_FRAMES;
        result->refresh_kind = REFRESH_STRONG;
    } else if (prob > VAD_NS_DECISION_THRESHOLD) {
        if (state->hangover < VAD_WEAK_HOLD_FRAMES)
            state->hangover = VAD_WEAK_HOLD_FRAMES;
        result->refresh_kind = REFRESH_WEAK;
    } else if (state->hangover) {
        state->hangover--;
    }

    result->probability = prob;
    result->post_hangover = state->hangover;
    result->active = (uint8_t)(state->hangover > 0u);
}

int main(int argc, char **argv) {
    FILE *input_file;
    int16_t raw[FRAME];
    float input[FRAME];
    float ns_output[FRAME];
    uint32_t frame_index = 0u;

    if (argc != 2) {
        fprintf(stderr, "usage: %s <raw-s16-mono-pcm>\n", argv[0]);
        return 2;
    }

    ap_ns_init(&ns_state, FRAME);
    if (ap_module_vad_init(public_shipping_mem, sizeof(public_shipping_mem),
                           &public_shipping_module) != AP_OK)
        return 4;
    diagnostic_init(&diagnostic_state);

    input_file = fopen(argv[1], "rb");
    if (!input_file) return 3;

    for (;;) {
        const size_t got = fread(raw, sizeof(raw[0]), FRAME, input_file);
        ap_ns_result_t ns_result;
        ap_module_vad_result_t public_shipping;
        diagnostic_result_t diagnostic;
        uint32_t i;

        if (got == 0u) break;
        if (got != FRAME) {
            fclose(input_file);
            return 5;
        }
        for (i = 0u; i < FRAME; ++i)
            input[i] = (float)raw[i] / 32768.0f;

        ap_ns_process(&ns_state, AP_ENHANCE_FULL, NS_FLOOR,
                      input, NULL, ns_output, FRAME, 0, 0, 0, &ns_result);
        if (ap_module_vad_process(public_shipping_module, ns_output, FRAME,
                                  ns_result.speech_probability, 1,
                                  &public_shipping) != AP_OK) {
            fclose(input_file);
            return 6;
        }

        process_shipping_diagnostic(
            &diagnostic_state, ns_output, FRAME,
            ns_result.speech_probability, &diagnostic);

        printf(
            "{\"frame\":%u,"
            "\"upstream_probability\":%.9g,"
            "\"public_shipping_probability\":%.9g,"
            "\"public_shipping_active\":%u,"
            "\"shipping_probability\":%.9g,"
            "\"shipping_active\":%u,"
            "\"rms\":%.9g,"
            "\"noise_rms_before\":%.9g,"
            "\"noise_rms_after\":%.9g,"
            "\"ratio_db\":%.9g,"
            "\"crest_db\":%.9g,"
            "\"raw_probability\":%.9g,"
            "\"pre_blend_probability\":%.9g,"
            "\"pre_hangover\":%u,"
            "\"post_hangover\":%u,"
            "\"refresh_kind\":%u,"
            "\"noise_update_kind\":%u,"
            "\"guard_active\":%u,"
            "\"upstream_guard_pass\":%u,"
            "\"local_guard_pass\":%u,"
            "\"transient_capped\":%u,"
            "\"blend_applied\":%u}\n",
            frame_index,
            (double)ns_result.speech_probability,
            (double)public_shipping.probability,
            (unsigned)public_shipping.active,
            (double)diagnostic.probability,
            (unsigned)diagnostic.active,
            (double)diagnostic.rms,
            (double)diagnostic.noise_rms_before,
            (double)diagnostic.noise_rms_after,
            (double)diagnostic.ratio_db,
            (double)diagnostic.crest_db,
            (double)diagnostic.raw_probability,
            (double)diagnostic.pre_blend_probability,
            diagnostic.pre_hangover,
            diagnostic.post_hangover,
            (unsigned)diagnostic.refresh_kind,
            (unsigned)diagnostic.noise_update_kind,
            (unsigned)diagnostic.guard_active,
            (unsigned)diagnostic.upstream_guard_pass,
            (unsigned)diagnostic.local_guard_pass,
            (unsigned)diagnostic.transient_capped,
            (unsigned)diagnostic.blend_applied);
        frame_index++;
    }

    fclose(input_file);
    return frame_index ? 0 : 7;
}
