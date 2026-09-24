#include "audio_pipeline/audio_modules.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !AP_HAVE_MODULE_NS || !AP_HAVE_MODULE_VAD
#error "Calibrated local-SNR probe requires standalone NS and VAD modules"
#endif

#define FRAME 160u
#define BASE_FLOOR 0.12f
#define STRESS_FLOOR 0.05f
#define PROB_EPS 1.0e-6f
#define FLOOR_EPS_DB 1.0e-6f

#define VAD_NOISE_LIKE_CREST_DB 8.0f
#define VAD_TRANSIENT_CREST_DB 12.0f
#define VAD_UPSTREAM_SPEECH_GUARD 0.55f
#define VAD_LOCAL_SPEECH_GUARD 0.15f
#define VAD_UPSTREAM_BLEND 0.40f
#define VAD_NS_DECISION_THRESHOLD 0.35f
#define VAD_STRONG_REFRESH_THRESHOLD 0.50f
#define VAD_STRONG_HOLD_FRAMES 8u
#define VAD_WEAK_HOLD_FRAMES 6u

typedef struct shipping_mirror_state {
    float noise_rms;
    uint32_t hangover;
} shipping_mirror_state_t;

typedef struct counter_state {
    uint32_t hangover;
} counter_state_t;

typedef struct counter_result {
    float input_rms_dbfs;
    float calibrated_noise_dbfs;
    float ratio_db;
    float crest_db;
    float raw_probability;
    float probability;
    uint32_t hangover_before;
    uint32_t hangover_after;
    uint8_t upstream_speech;
    uint8_t transient_capped;
    uint8_t blend_applied;
    uint8_t refresh;
    uint8_t active;
} counter_result_t;

typedef struct counters {
    uint64_t frames;
    uint64_t speech_frames;
    uint64_t noise_frames;
    uint64_t mirror_probability_mismatch_frames;
    uint64_t mirror_active_mismatch_frames;
    uint64_t floor_probability_mismatch_frames;
    uint64_t floor_active_mismatch_frames;
    uint64_t behavior_probability_diff_frames;
    uint64_t behavior_active_diff_frames;
    uint64_t speech_shipping_active;
    uint64_t speech_counter_active;
    uint64_t noise_shipping_active;
    uint64_t noise_counter_active;
    uint64_t lost_speech_frames;
    uint64_t gained_speech_frames;
    float max_mirror_probability_delta;
    float max_floor_probability_delta;
    float max_floor_noise_reference_delta_db;
    float max_floor_upstream_probability_delta;
    float max_shipping_counter_probability_delta;
    float max_counter_ratio_db;
    float min_counter_ratio_db;
} counters_t;

_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char ns_base_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char ns_stress_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char vad_shipping_mem[AP_MODULE_STATE_MAX_BYTES];

static float clampf_local(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static uint32_t next_pow2(uint32_t x) {
    uint32_t p = 1u;
    while (p < x) p <<= 1u;
    return p;
}

static float frame_rms(const float *x) {
    double e = 1.0e-18;
    uint32_t i;
    for (i = 0u; i < FRAME; ++i) e += (double)x[i] * (double)x[i];
    return (float)sqrt(e / (double)FRAME);
}

static float frame_rms_dbfs(const float *x) {
    const float rms = frame_rms(x);
    return 20.0f * log10f(rms + 1.0e-18f);
}

static float frame_crest_db(const float *x) {
    float peak = 0.0f;
    float rms = frame_rms(x);
    uint32_t i;
    for (i = 0u; i < FRAME; ++i) {
        const float magnitude = fabsf(x[i]);
        if (magnitude > peak) peak = magnitude;
    }
    return 20.0f * log10f((peak + 1.0e-7f) / (rms + 1.0e-7f));
}

static void shipping_mirror_reset(shipping_mirror_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->noise_rms = 1.0e-3f;
}

static void shipping_mirror_process(shipping_mirror_state_t *state,
                                    const float *x,
                                    float upstream_probability,
                                    float *probability,
                                    uint8_t *active) {
    float e = 1.0e-12f;
    float peak = 0.0f;
    float rms, ratio_db, crest_db, prob;
    int upstream_speech;
    uint32_t i;

    for (i = 0u; i < FRAME; ++i) {
        const float magnitude = fabsf(x[i]);
        e += x[i] * x[i];
        if (magnitude > peak) peak = magnitude;
    }
    rms = sqrtf(e / (float)FRAME);
    if (state->noise_rms <= 0.0f) state->noise_rms = rms + 1.0e-6f;
    ratio_db = 20.0f * log10f((rms + 1.0e-7f) /
                              (state->noise_rms + 1.0e-7f));
    crest_db = 20.0f * log10f((peak + 1.0e-7f) / (rms + 1.0e-7f));
    prob = clampf_local((ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);

    upstream_speech =
        upstream_probability > VAD_UPSTREAM_SPEECH_GUARD &&
        prob > VAD_LOCAL_SPEECH_GUARD;

    if (!upstream_speech && crest_db > VAD_TRANSIENT_CREST_DB && prob > 0.30f)
        prob = 0.30f;

    if (upstream_probability > prob) {
        prob += VAD_UPSTREAM_BLEND * (upstream_probability - prob);
        prob = clampf_local(prob, 0.0f, 1.0f);
    }

    if (prob < 0.35f) {
        state->noise_rms = 0.98f * state->noise_rms + 0.02f * rms;
    } else if (!upstream_speech &&
               crest_db >= VAD_NOISE_LIKE_CREST_DB &&
               crest_db <= VAD_TRANSIENT_CREST_DB) {
        state->noise_rms = 0.92f * state->noise_rms + 0.08f * rms;
    }

    if (prob >= VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = VAD_STRONG_HOLD_FRAMES;
    } else if (prob > VAD_NS_DECISION_THRESHOLD) {
        if (state->hangover < VAD_WEAK_HOLD_FRAMES)
            state->hangover = VAD_WEAK_HOLD_FRAMES;
    } else if (state->hangover) {
        state->hangover--;
    }

    *probability = prob;
    *active = (uint8_t)(state->hangover > 0u);
}

static void counter_reset(counter_state_t *state) {
    memset(state, 0, sizeof(*state));
}

static void counter_process(counter_state_t *state,
                            const float *pre_ns,
                            float legacy_noise_dbfs,
                            float upstream_probability,
                            float scale_offset_db,
                            counter_result_t *out) {
    float prob;

    memset(out, 0, sizeof(*out));
    out->hangover_before = state->hangover;
    out->input_rms_dbfs = frame_rms_dbfs(pre_ns);
    out->calibrated_noise_dbfs = legacy_noise_dbfs + scale_offset_db;
    out->ratio_db = out->input_rms_dbfs - out->calibrated_noise_dbfs;
    out->crest_db = frame_crest_db(pre_ns);
    prob = clampf_local((out->ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);
    out->raw_probability = prob;

    out->upstream_speech =
        (uint8_t)(upstream_probability > VAD_UPSTREAM_SPEECH_GUARD &&
                  prob > VAD_LOCAL_SPEECH_GUARD);

    if (!out->upstream_speech &&
        out->crest_db > VAD_TRANSIENT_CREST_DB &&
        prob > 0.30f) {
        prob = 0.30f;
        out->transient_capped = 1u;
    }

    if (upstream_probability > prob) {
        prob += VAD_UPSTREAM_BLEND * (upstream_probability - prob);
        prob = clampf_local(prob, 0.0f, 1.0f);
        out->blend_applied = 1u;
    }
    out->probability = prob;

    if (prob >= VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = VAD_STRONG_HOLD_FRAMES;
        out->refresh = 1u;
    } else if (prob > VAD_NS_DECISION_THRESHOLD) {
        if (state->hangover < VAD_WEAK_HOLD_FRAMES)
            state->hangover = VAD_WEAK_HOLD_FRAMES;
        out->refresh = 2u;
    } else if (state->hangover) {
        state->hangover--;
        out->refresh = 3u;
    }

    out->hangover_after = state->hangover;
    out->active = (uint8_t)(state->hangover > 0u);
}

static void update_max(float value, float *maximum) {
    if (value > *maximum) *maximum = value;
}

static void update_min(float value, float *minimum) {
    if (value < *minimum) *minimum = value;
}

static int read_label(FILE *labels, unsigned *label) {
    const int rc = fscanf(labels, "%u", label);
    if (rc == EOF) return 0;
    if (rc != 1 || (*label != 0u && *label != 1u)) return -1;
    return 1;
}

int main(int argc, char **argv) {
    ap_ns_module_t *ns_base = NULL;
    ap_ns_module_t *ns_stress = NULL;
    ap_vad_module_t *vad_shipping = NULL;
    const ap_module_ns_config_t base_cfg = {16000u, BASE_FLOOR};
    const ap_module_ns_config_t stress_cfg = {16000u, STRESS_FLOOR};
    shipping_mirror_state_t shipping_mirror;
    counter_state_t counter_base;
    counter_state_t counter_stress;
    counters_t count;
    FILE *audio = NULL;
    FILE *labels = NULL;
    FILE *output = NULL;
    int16_t raw[FRAME];
    float input[FRAME];
    float out_base[FRAME];
    float out_stress[FRAME];
    const uint32_t nfft = next_pow2(FRAME * 2u);
    const uint32_t bins = nfft / 2u + 1u;
    const float scale_offset_db =
        10.0f * log10f(2.0f * (float)bins * (float)nfft / (float)FRAME);

    if (argc != 4) {
        fprintf(stderr, "usage: %s <input-s16le.pcm> <labels.txt> <output.json>\n", argv[0]);
        return 2;
    }
    if (nfft != 512u || bins != 257u) return 3;

    audio = fopen(argv[1], "rb");
    labels = fopen(argv[2], "rb");
    output = fopen(argv[3], "wb");
    if (!audio || !labels || !output) {
        perror("fopen");
        return 2;
    }

    if (ap_module_ns_init(ns_base_mem, sizeof(ns_base_mem), &base_cfg, &ns_base) != AP_OK)
        return 4;
    if (ap_module_ns_init(ns_stress_mem, sizeof(ns_stress_mem), &stress_cfg, &ns_stress) != AP_OK)
        return 5;
    if (ap_module_vad_init(vad_shipping_mem, sizeof(vad_shipping_mem), &vad_shipping) != AP_OK)
        return 6;

    shipping_mirror_reset(&shipping_mirror);
    counter_reset(&counter_base);
    counter_reset(&counter_stress);
    memset(&count, 0, sizeof(count));
    count.min_counter_ratio_db = 1.0e9f;
    count.max_counter_ratio_db = -1.0e9f;

    while (fread(raw, sizeof(raw[0]), FRAME, audio) == FRAME) {
        ap_module_ns_result_t rb;
        ap_module_ns_result_t rs;
        ap_module_vad_result_t shipping;
        counter_result_t cb;
        counter_result_t cs;
        float mirror_probability;
        uint8_t mirror_active;
        float delta;
        unsigned label;
        int label_rc;
        uint32_t i;

        label_rc = read_label(labels, &label);
        if (label_rc <= 0) return 7;
        for (i = 0u; i < FRAME; ++i)
            input[i] = (float)raw[i] / 32768.0f;

        if (ap_module_ns_process(ns_base, AP_QUALITY_FULL, input, NULL,
                                 out_base, FRAME, 0, 0, 0, &rb) != AP_OK)
            return 8;
        if (ap_module_ns_process(ns_stress, AP_QUALITY_FULL, input, NULL,
                                 out_stress, FRAME, 0, 0, 0, &rs) != AP_OK)
            return 9;
        if (ap_module_vad_process(vad_shipping, out_base, FRAME,
                                  rb.speech_probability, 1, &shipping) != AP_OK)
            return 10;

        shipping_mirror_process(&shipping_mirror, out_base, rb.speech_probability,
                                &mirror_probability, &mirror_active);
        counter_process(&counter_base, input, rb.noise_rms_dbfs,
                        rb.speech_probability, scale_offset_db, &cb);
        counter_process(&counter_stress, input, rs.noise_rms_dbfs,
                        rs.speech_probability, scale_offset_db, &cs);

        delta = fabsf(shipping.probability - mirror_probability);
        update_max(delta, &count.max_mirror_probability_delta);
        if (delta > PROB_EPS) count.mirror_probability_mismatch_frames++;
        if (shipping.active != mirror_active) count.mirror_active_mismatch_frames++;

        delta = fabsf(cb.probability - cs.probability);
        update_max(delta, &count.max_floor_probability_delta);
        if (delta > PROB_EPS) count.floor_probability_mismatch_frames++;
        if (cb.active != cs.active) count.floor_active_mismatch_frames++;

        delta = fabsf(rb.noise_rms_dbfs - rs.noise_rms_dbfs);
        update_max(delta, &count.max_floor_noise_reference_delta_db);
        delta = fabsf(rb.speech_probability - rs.speech_probability);
        update_max(delta, &count.max_floor_upstream_probability_delta);

        delta = fabsf(shipping.probability - cb.probability);
        update_max(delta, &count.max_shipping_counter_probability_delta);
        if (delta > PROB_EPS) count.behavior_probability_diff_frames++;
        if (shipping.active != cb.active) count.behavior_active_diff_frames++;

        update_max(cb.ratio_db, &count.max_counter_ratio_db);
        update_min(cb.ratio_db, &count.min_counter_ratio_db);

        if (label) {
            count.speech_frames++;
            if (shipping.active) count.speech_shipping_active++;
            if (cb.active) count.speech_counter_active++;
            if (shipping.active && !cb.active) count.lost_speech_frames++;
            if (!shipping.active && cb.active) count.gained_speech_frames++;
        } else {
            count.noise_frames++;
            if (shipping.active) count.noise_shipping_active++;
            if (cb.active) count.noise_counter_active++;
        }
        count.frames++;
    }

    {
        unsigned extra;
        if (read_label(labels, &extra) > 0) return 11;
    }
    if (count.frames == 0u || count.speech_frames == 0u || count.noise_frames == 0u)
        return 12;

    fprintf(output,
        "{\n"
        "  \"schema_version\": 1,\n"
        "  \"frames\": %llu,\n"
        "  \"speech_frames\": %llu,\n"
        "  \"noise_frames\": %llu,\n"
        "  \"mirror_probability_mismatch_frames\": %llu,\n"
        "  \"mirror_active_mismatch_frames\": %llu,\n"
        "  \"max_mirror_probability_delta\": %.9g,\n"
        "  \"floor_probability_mismatch_frames\": %llu,\n"
        "  \"floor_active_mismatch_frames\": %llu,\n"
        "  \"max_floor_probability_delta\": %.9g,\n"
        "  \"max_floor_noise_reference_delta_db\": %.9g,\n"
        "  \"max_floor_upstream_probability_delta\": %.9g,\n"
        "  \"behavior_probability_diff_frames\": %llu,\n"
        "  \"behavior_active_diff_frames\": %llu,\n"
        "  \"max_shipping_counter_probability_delta\": %.9g,\n"
        "  \"speech_shipping_active\": %llu,\n"
        "  \"speech_counter_active\": %llu,\n"
        "  \"noise_shipping_active\": %llu,\n"
        "  \"noise_counter_active\": %llu,\n"
        "  \"lost_speech_frames\": %llu,\n"
        "  \"gained_speech_frames\": %llu,\n"
        "  \"scale_offset_db\": %.12g,\n"
        "  \"min_counter_ratio_db\": %.9g,\n"
        "  \"max_counter_ratio_db\": %.9g\n"
        "}\n",
        (unsigned long long)count.frames,
        (unsigned long long)count.speech_frames,
        (unsigned long long)count.noise_frames,
        (unsigned long long)count.mirror_probability_mismatch_frames,
        (unsigned long long)count.mirror_active_mismatch_frames,
        (double)count.max_mirror_probability_delta,
        (unsigned long long)count.floor_probability_mismatch_frames,
        (unsigned long long)count.floor_active_mismatch_frames,
        (double)count.max_floor_probability_delta,
        (double)count.max_floor_noise_reference_delta_db,
        (double)count.max_floor_upstream_probability_delta,
        (unsigned long long)count.behavior_probability_diff_frames,
        (unsigned long long)count.behavior_active_diff_frames,
        (double)count.max_shipping_counter_probability_delta,
        (unsigned long long)count.speech_shipping_active,
        (unsigned long long)count.speech_counter_active,
        (unsigned long long)count.noise_shipping_active,
        (unsigned long long)count.noise_counter_active,
        (unsigned long long)count.lost_speech_frames,
        (unsigned long long)count.gained_speech_frames,
        (double)scale_offset_db,
        (double)count.min_counter_ratio_db,
        (double)count.max_counter_ratio_db);

    fclose(audio);
    fclose(labels);
    fclose(output);
    return 0;
}
