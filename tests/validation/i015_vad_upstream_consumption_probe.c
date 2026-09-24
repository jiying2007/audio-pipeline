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

typedef struct diagnostic_vad_state {
    float noise_rms;
    uint32_t hangover;
} diagnostic_vad_state_t;

typedef struct diagnostic_vad_result {
    float probability;
    float raw_probability;
    float ratio_db;
    float crest_db;
    float noise_rms_before;
    float noise_rms_after;
    uint32_t hangover_before;
    uint32_t hangover_after;
    uint8_t active;
    uint8_t guard_active;
    uint8_t blend_applied;
    uint8_t transient_capped;
    uint8_t noise_update_class;
    uint8_t refresh_class;
} diagnostic_vad_result_t;

static ap_ns_state_t ns_state;
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char public_shipping_mem[AP_MODULE_STATE_MAX_BYTES];
static ap_vad_module_t *public_shipping_module;
static diagnostic_vad_state_t shipping_state;
static diagnostic_vad_state_t no_upstream_state;
static diagnostic_vad_state_t blend_only_state;
static diagnostic_vad_state_t guard_only_state;

static float clampf_local(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static void diagnostic_vad_init(diagnostic_vad_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->noise_rms = 1.0e-3f;
}

static void diagnostic_vad_process(diagnostic_vad_state_t *state,
                                   const float *x,
                                   uint32_t n,
                                   float upstream_probability,
                                   int enable_guard,
                                   int enable_blend,
                                   diagnostic_vad_result_t *result) {
    float e = 1.0e-12f;
    float peak = 0.0f;
    float rms;
    float ratio_db;
    float crest_db;
    float prob;
    uint32_t i;
    int upstream_speech;

    memset(result, 0, sizeof(*result));
    result->noise_rms_before = state->noise_rms;
    result->hangover_before = state->hangover;

    for (i = 0u; i < n; ++i) {
        const float magnitude = fabsf(x[i]);
        e += x[i] * x[i];
        if (magnitude > peak) peak = magnitude;
    }

    rms = sqrtf(e / (float)n);
    if (state->noise_rms <= 0.0f)
        state->noise_rms = rms + 1.0e-6f;

    ratio_db = 20.0f * log10f(
        (rms + 1.0e-7f) / (state->noise_rms + 1.0e-7f));
    crest_db = 20.0f * log10f(
        (peak + 1.0e-7f) / (rms + 1.0e-7f));
    prob = clampf_local((ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);

    result->raw_probability = prob;
    result->ratio_db = ratio_db;
    result->crest_db = crest_db;

    upstream_speech =
        enable_guard &&
        upstream_probability > VAD_UPSTREAM_SPEECH_GUARD &&
        prob > VAD_LOCAL_SPEECH_GUARD;
    result->guard_active = (uint8_t)(upstream_speech != 0);

    if (!upstream_speech &&
        crest_db > VAD_TRANSIENT_CREST_DB &&
        prob > 0.30f) {
        prob = 0.30f;
        result->transient_capped = 1u;
    }

    if (enable_blend && upstream_probability > prob) {
        prob += VAD_UPSTREAM_BLEND * (upstream_probability - prob);
        prob = clampf_local(prob, 0.0f, 1.0f);
        result->blend_applied = 1u;
    }

    if (prob < 0.35f) {
        state->noise_rms = 0.98f * state->noise_rms + 0.02f * rms;
        result->noise_update_class = 1u;
    } else if (!upstream_speech &&
               crest_db >= VAD_NOISE_LIKE_CREST_DB &&
               crest_db <= VAD_TRANSIENT_CREST_DB) {
        state->noise_rms =
            (1.0f - VAD_FAST_NOISE_ALPHA) * state->noise_rms +
            VAD_FAST_NOISE_ALPHA * rms;
        result->noise_update_class = 2u;
    }

    if (prob >= VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = VAD_STRONG_HOLD_FRAMES;
        result->refresh_class = 1u;
    } else if (prob > VAD_NS_DECISION_THRESHOLD) {
        if (state->hangover < VAD_WEAK_HOLD_FRAMES)
            state->hangover = VAD_WEAK_HOLD_FRAMES;
        result->refresh_class = 2u;
    } else if (state->hangover) {
        state->hangover--;
        result->refresh_class = 3u;
    }

    result->probability = prob;
    result->active = (uint8_t)(state->hangover > 0u);
    result->noise_rms_after = state->noise_rms;
    result->hangover_after = state->hangover;
}

static void print_lane(const char *prefix,
                       const diagnostic_vad_result_t *r) {
    printf(
        ",\"%s_probability\":%.9g"
        ",\"%s_active\":%u"
        ",\"%s_raw_probability\":%.9g"
        ",\"%s_ratio_db\":%.9g"
        ",\"%s_crest_db\":%.9g"
        ",\"%s_noise_rms_before\":%.9g"
        ",\"%s_noise_rms_after\":%.9g"
        ",\"%s_hangover_before\":%u"
        ",\"%s_hangover_after\":%u"
        ",\"%s_guard_active\":%u"
        ",\"%s_blend_applied\":%u"
        ",\"%s_transient_capped\":%u"
        ",\"%s_noise_update_class\":%u"
        ",\"%s_refresh_class\":%u",
        prefix, (double)r->probability,
        prefix, (unsigned)r->active,
        prefix, (double)r->raw_probability,
        prefix, (double)r->ratio_db,
        prefix, (double)r->crest_db,
        prefix, (double)r->noise_rms_before,
        prefix, (double)r->noise_rms_after,
        prefix, r->hangover_before,
        prefix, r->hangover_after,
        prefix, (unsigned)r->guard_active,
        prefix, (unsigned)r->blend_applied,
        prefix, (unsigned)r->transient_capped,
        prefix, (unsigned)r->noise_update_class,
        prefix, (unsigned)r->refresh_class);
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
    if (ap_module_vad_init(public_shipping_mem, sizeof(public_shipping_mem),\n                           &public_shipping_module) != AP_OK)\n        return 4;\n    diagnostic_vad_init(&shipping_state);
    diagnostic_vad_init(&no_upstream_state);
    diagnostic_vad_init(&blend_only_state);
    diagnostic_vad_init(&guard_only_state);

    input_file = fopen(argv[1], "rb");
    if (!input_file) {
        perror("fopen");
        return 3;
    }

    for (;;) {
        const size_t got = fread(raw, sizeof(raw[0]), FRAME, input_file);
        ap_ns_result_t ns_result;
        ap_module_vad_result_t public_shipping;
        diagnostic_vad_result_t shipping;
        diagnostic_vad_result_t no_upstream;
        diagnostic_vad_result_t blend_only;
        diagnostic_vad_result_t guard_only;
        uint32_t i;

        if (got == 0u) break;
        if (got != FRAME) {
            fprintf(stderr, "partial input frame: %zu\n", got);
            fclose(input_file);
            return 5;
        }

        for (i = 0u; i < FRAME; ++i)
            input[i] = (float)raw[i] / 32768.0f;

        ap_ns_process(&ns_state, AP_ENHANCE_FULL, NS_FLOOR,
                      input, NULL, ns_output, FRAME, 0, 0, 0, &ns_result);

        if (ap_module_vad_process(
                public_shipping_module,
                ns_output,
                FRAME,
                ns_result.speech_probability,
                1,
                &public_shipping) != AP_OK) {
            fclose(input_file);
            return 6;
        }

        diagnostic_vad_process(
            &shipping_state, ns_output, FRAME,
            ns_result.speech_probability, 1, 1, &shipping);
        diagnostic_vad_process(
            &no_upstream_state, ns_output, FRAME,
            ns_result.speech_probability, 0, 0, &no_upstream);
        diagnostic_vad_process(
            &blend_only_state, ns_output, FRAME,
            ns_result.speech_probability, 0, 1, &blend_only);
        diagnostic_vad_process(
            &guard_only_state, ns_output, FRAME,
            ns_result.speech_probability, 1, 0, &guard_only);

        printf(
            "{\"frame\":%u,"
            "\"upstream_probability\":%.9g,"
            "\"public_shipping_probability\":%.9g,"
            "\"public_shipping_active\":%u",
            frame_index,
            (double)ns_result.speech_probability,
            (double)public_shipping.probability,
            (unsigned)public_shipping.active);
        print_lane("shipping", &shipping);
        print_lane("no_upstream", &no_upstream);
        print_lane("blend_only", &blend_only);
        print_lane("guard_only", &guard_only);
        printf("}\n");

        frame_index++;
    }

    fclose(input_file);
    if (frame_index == 0u) return 7;
    return 0;
}
