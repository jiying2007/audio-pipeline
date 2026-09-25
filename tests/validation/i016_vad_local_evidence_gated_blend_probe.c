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

typedef struct vad_state {
    float noise_rms;
    uint32_t hangover;
} vad_state_t;

typedef struct vad_result {
    float probability;
    float raw_probability;
    uint8_t active;
    uint8_t guard_active;
    uint8_t blend_applied;
    uint8_t blend_blocked_by_local_gate;
} vad_result_t;

static ap_ns_state_t ns_state;
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char public_shipping_mem[AP_MODULE_STATE_MAX_BYTES];
static ap_vad_module_t *public_shipping_module;
static vad_state_t shipping_state;
static vad_state_t candidate_state;

static float clampf_local(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static void state_init(vad_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->noise_rms = 1.0e-3f;
}

static void process_lane(vad_state_t *state,
                         const float *x,
                         uint32_t n,
                         float upstream_probability,
                         int gate_blend_with_local_evidence,
                         vad_result_t *result) {
    float e = 1.0e-12f;
    float peak = 0.0f;
    float rms;
    float ratio_db;
    float crest_db;
    float prob;
    float raw_prob;
    uint32_t i;
    int upstream_speech;

    memset(result, 0, sizeof(*result));
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
    raw_prob = prob;
    result->raw_probability = raw_prob;

    upstream_speech =
        upstream_probability > VAD_UPSTREAM_SPEECH_GUARD &&
        raw_prob > VAD_LOCAL_SPEECH_GUARD;
    result->guard_active = (uint8_t)(upstream_speech != 0);

    if (!upstream_speech &&
        crest_db > VAD_TRANSIENT_CREST_DB &&
        prob > 0.30f) {
        prob = 0.30f;
    }

    if (upstream_probability > prob) {
        const int local_gate_pass =
            !gate_blend_with_local_evidence ||
            raw_prob > VAD_LOCAL_SPEECH_GUARD;
        if (local_gate_pass) {
            prob += VAD_UPSTREAM_BLEND * (upstream_probability - prob);
            prob = clampf_local(prob, 0.0f, 1.0f);
            result->blend_applied = 1u;
        } else {
            result->blend_blocked_by_local_gate = 1u;
        }
    }

    if (prob < 0.35f) {
        state->noise_rms = 0.98f * state->noise_rms + 0.02f * rms;
    } else if (!upstream_speech &&
               crest_db >= VAD_NOISE_LIKE_CREST_DB &&
               crest_db <= VAD_TRANSIENT_CREST_DB) {
        state->noise_rms =
            (1.0f - VAD_FAST_NOISE_ALPHA) * state->noise_rms +
            VAD_FAST_NOISE_ALPHA * rms;
    }

    if (prob >= VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = VAD_STRONG_HOLD_FRAMES;
    } else if (prob > VAD_NS_DECISION_THRESHOLD) {
        if (state->hangover < VAD_WEAK_HOLD_FRAMES)
            state->hangover = VAD_WEAK_HOLD_FRAMES;
    } else if (state->hangover) {
        state->hangover--;
    }

    result->probability = prob;
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
    state_init(&shipping_state);
    state_init(&candidate_state);

    input_file = fopen(argv[1], "rb");
    if (!input_file) {
        perror("fopen");
        return 3;
    }

    for (;;) {
        const size_t got = fread(raw, sizeof(raw[0]), FRAME, input_file);
        ap_ns_result_t ns_result;
        ap_module_vad_result_t public_shipping;
        vad_result_t shipping;
        vad_result_t candidate;
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

        process_lane(&shipping_state, ns_output, FRAME,
                     ns_result.speech_probability, 0, &shipping);
        process_lane(&candidate_state, ns_output, FRAME,
                     ns_result.speech_probability, 1, &candidate);

        printf(
            "{\"frame\":%u,\"upstream_probability\":%.9g,"
            "\"public_shipping_probability\":%.9g,"
            "\"public_shipping_active\":%u,"
            "\"shipping_probability\":%.9g,\"shipping_active\":%u,"
            "\"candidate_probability\":%.9g,\"candidate_active\":%u,"
            "\"candidate_raw_probability\":%.9g,"
            "\"candidate_guard_active\":%u,"
            "\"candidate_blend_applied\":%u,"
            "\"candidate_blend_blocked_by_local_gate\":%u}\n",
            frame_index,
            (double)ns_result.speech_probability,
            (double)public_shipping.probability,
            (unsigned)public_shipping.active,
            (double)shipping.probability,
            (unsigned)shipping.active,
            (double)candidate.probability,
            (unsigned)candidate.active,
            (double)candidate.raw_probability,
            (unsigned)candidate.guard_active,
            (unsigned)candidate.blend_applied,
            (unsigned)candidate.blend_blocked_by_local_gate);
        frame_index++;
    }

    fclose(input_file);
    return frame_index ? 0 : 7;
}
