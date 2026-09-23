#include "audio_pipeline/audio_modules.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !AP_HAVE_MODULE_RESAMPLER || !AP_HAVE_MODULE_NS || !AP_HAVE_MODULE_VAD
#error "VAD state-divergence probe requires resampler, NS and VAD public modules"
#endif

#define FRAME 160u
#define PROB_EPS 1.0e-6f

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

enum noise_update_class {
    NOISE_UPDATE_NONE = 0,
    NOISE_UPDATE_SLOW = 1,
    NOISE_UPDATE_FAST = 2
};

enum refresh_class {
    REFRESH_NONE = 0,
    REFRESH_STRONG = 1,
    REFRESH_WEAK = 2,
    REFRESH_DECAY = 3
};

typedef struct mirror_state {
    float noise_rms;
    uint32_t hangover;
} mirror_state_t;

typedef struct mirror_result {
    float rms;
    float noise_rms_before;
    float noise_rms_after;
    float ratio_db;
    float crest_db;
    float raw_probability;
    float post_transient_probability;
    float probability;
    uint32_t hangover_before;
    uint32_t hangover_after;
    uint8_t upstream_speech;
    uint8_t transient_capped;
    uint8_t blend_applied;
    uint8_t noise_update;
    uint8_t refresh;
    uint8_t active;
} mirror_result_t;

typedef struct counters {
    uint64_t frames;
    uint64_t speech_frames;
    uint64_t noise_frames;
    uint64_t mirror_probability_mismatch_frames;
    uint64_t mirror_active_mismatch_frames;
    uint64_t raw_probability_diff_frames;
    uint64_t upstream_guard_diff_frames;
    uint64_t transient_cap_diff_frames;
    uint64_t blend_diff_frames;
    uint64_t noise_update_diff_frames;
    uint64_t refresh_diff_frames;
    uint64_t hangover_before_diff_frames;
    uint64_t hangover_after_diff_frames;
    uint64_t active_diff_frames;
    uint64_t speech_shipping_active;
    uint64_t speech_pre_active;
    uint64_t noise_shipping_active;
    uint64_t noise_pre_active;
    uint64_t lost_speech_frames;
    uint64_t gained_speech_frames;
    uint64_t lost_raw_probability_lower;
    uint64_t lost_upstream_guard;
    uint64_t lost_transient_cap_added;
    uint64_t lost_noise_update_changed;
    uint64_t lost_refresh_changed;
    uint64_t lost_hangover_history;
    uint64_t lost_pre_below_decision;
    uint64_t lost_ship_above_decision;
    uint64_t lost_pre_below_local_guard;
    uint64_t lost_ship_above_local_guard;
    uint64_t lost_pre_noise_rms_higher;
    uint64_t lost_ratio_db_lower;
    float max_public_mirror_probability_delta;
    float max_raw_probability_delta;
    float max_final_probability_delta;
    float max_noise_rms_delta;
    float max_ratio_db_delta;
} counters_t;

_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char resampler_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char ns_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char vad_shipping_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char vad_pre_mem[AP_MODULE_STATE_MAX_BYTES];

static float clampf_local(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static void mirror_reset(mirror_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->noise_rms = 1.0e-3f;
}

static void mirror_process(mirror_state_t *state,
                           const float *x,
                           uint32_t n,
                           float upstream_probability,
                           mirror_result_t *out) {
    float e = 1.0e-12f;
    float peak = 0.0f;
    float prob;
    uint32_t i;

    memset(out, 0, sizeof(*out));
    out->noise_rms_before = state->noise_rms;
    out->hangover_before = state->hangover;

    for (i = 0u; i < n; ++i) {
        const float magnitude = fabsf(x[i]);
        e += x[i] * x[i];
        if (magnitude > peak) peak = magnitude;
    }
    out->rms = sqrtf(e / (float)n);
    if (state->noise_rms <= 0.0f)
        state->noise_rms = out->rms + 1.0e-6f;
    out->ratio_db =
        20.0f * log10f((out->rms + 1.0e-7f) / (state->noise_rms + 1.0e-7f));
    out->crest_db =
        20.0f * log10f((peak + 1.0e-7f) / (out->rms + 1.0e-7f));
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
    out->post_transient_probability = prob;

    if (upstream_probability > prob) {
        prob += VAD_UPSTREAM_BLEND * (upstream_probability - prob);
        prob = clampf_local(prob, 0.0f, 1.0f);
        out->blend_applied = 1u;
    }
    out->probability = prob;

    if (prob < 0.35f) {
        state->noise_rms = 0.98f * state->noise_rms + 0.02f * out->rms;
        out->noise_update = NOISE_UPDATE_SLOW;
    } else if (!out->upstream_speech &&
               out->crest_db >= VAD_NOISE_LIKE_CREST_DB &&
               out->crest_db <= VAD_TRANSIENT_CREST_DB) {
        state->noise_rms =
            (1.0f - VAD_FAST_NOISE_ALPHA) * state->noise_rms +
            VAD_FAST_NOISE_ALPHA * out->rms;
        out->noise_update = NOISE_UPDATE_FAST;
    } else {
        out->noise_update = NOISE_UPDATE_NONE;
    }
    out->noise_rms_after = state->noise_rms;

    if (prob >= VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = VAD_STRONG_HOLD_FRAMES;
        out->refresh = REFRESH_STRONG;
    } else if (prob > VAD_NS_DECISION_THRESHOLD) {
        if (state->hangover < VAD_WEAK_HOLD_FRAMES)
            state->hangover = VAD_WEAK_HOLD_FRAMES;
        out->refresh = REFRESH_WEAK;
    } else if (state->hangover) {
        state->hangover--;
        out->refresh = REFRESH_DECAY;
    } else {
        out->refresh = REFRESH_NONE;
    }
    out->hangover_after = state->hangover;
    out->active = (uint8_t)(state->hangover > 0u);
}

static void update_max(float value, float *maximum) {
    if (value > *maximum) *maximum = value;
}

static int read_label(FILE *labels, unsigned *label) {
    int rc = fscanf(labels, "%u", label);
    if (rc == EOF) return 0;
    if (rc != 1 || (*label != 0u && *label != 1u)) return -1;
    return 1;
}

int main(int argc, char **argv) {
    ap_resampler_module_t *resampler = NULL;
    ap_ns_module_t *ns = NULL;
    ap_vad_module_t *vad_shipping = NULL;
    ap_vad_module_t *vad_pre = NULL;
    const ap_module_ns_config_t ns_cfg = {16000u, 0.12f};
    mirror_state_t mirror_shipping, mirror_pre;
    counters_t count;
    int16_t pcm[FRAME];
    float input[FRAME];
    float processed[FRAME];
    FILE *audio = NULL;
    FILE *labels = NULL;
    FILE *output = NULL;
    uint64_t frame_index = 0u;

    if (argc != 4) {
        fprintf(stderr, "usage: %s <input-s16le.pcm> <labels.txt> <output.json>\n", argv[0]);
        return 2;
    }
    audio = fopen(argv[1], "rb");
    labels = fopen(argv[2], "rb");
    output = fopen(argv[3], "wb");
    if (!audio || !labels || !output) {
        perror("fopen");
        return 2;
    }

    if (ap_module_resampler_init(resampler_mem, sizeof(resampler_mem), &resampler) != AP_OK)
        return 3;
    if (ap_module_ns_init(ns_mem, sizeof(ns_mem), &ns_cfg, &ns) != AP_OK)
        return 3;
    if (ap_module_vad_init(vad_shipping_mem, sizeof(vad_shipping_mem), &vad_shipping) != AP_OK)
        return 3;
    if (ap_module_vad_init(vad_pre_mem, sizeof(vad_pre_mem), &vad_pre) != AP_OK)
        return 3;
    mirror_reset(&mirror_shipping);
    mirror_reset(&mirror_pre);
    memset(&count, 0, sizeof(count));

    while (fread(pcm, sizeof(int16_t), FRAME, audio) == FRAME) {
        ap_module_ns_result_t ns_result;
        ap_module_vad_result_t public_shipping, public_pre;
        mirror_result_t ship, pre;
        unsigned label;
        int label_rc = read_label(labels, &label);
        float delta;

        if (label_rc <= 0) {
            fprintf(stderr, "label stream ended before audio at frame %llu\n",
                    (unsigned long long)frame_index);
            return 4;
        }
        if (ap_module_resampler_input_s16(
                resampler, pcm, FRAME, 1u, 0u, input, FRAME) != AP_OK)
            return 5;
        if (ap_module_ns_process(
                ns, AP_QUALITY_FULL, input, NULL, processed, FRAME,
                0, 0, 0, &ns_result) != AP_OK)
            return 6;

        if (ap_module_vad_process(
                vad_shipping, processed, FRAME,
                ns_result.speech_probability, 1, &public_shipping) != AP_OK)
            return 7;
        if (ap_module_vad_process(
                vad_pre, input, FRAME,
                ns_result.speech_probability, 1, &public_pre) != AP_OK)
            return 8;

        mirror_process(&mirror_shipping, processed, FRAME,
                       ns_result.speech_probability, &ship);
        mirror_process(&mirror_pre, input, FRAME,
                       ns_result.speech_probability, &pre);

        delta = fabsf(public_shipping.probability - ship.probability);
        update_max(delta, &count.max_public_mirror_probability_delta);
        if (delta > PROB_EPS) count.mirror_probability_mismatch_frames++;
        delta = fabsf(public_pre.probability - pre.probability);
        update_max(delta, &count.max_public_mirror_probability_delta);
        if (delta > PROB_EPS) count.mirror_probability_mismatch_frames++;
        if (public_shipping.active != ship.active ||
            public_pre.active != pre.active)
            count.mirror_active_mismatch_frames++;

        delta = fabsf(ship.raw_probability - pre.raw_probability);
        update_max(delta, &count.max_raw_probability_delta);
        if (delta > PROB_EPS) count.raw_probability_diff_frames++;
        delta = fabsf(ship.probability - pre.probability);
        update_max(delta, &count.max_final_probability_delta);
        if (delta > PROB_EPS) count.active_diff_frames += 0u;
        delta = fabsf(ship.noise_rms_after - pre.noise_rms_after);
        update_max(delta, &count.max_noise_rms_delta);
        delta = fabsf(ship.ratio_db - pre.ratio_db);
        update_max(delta, &count.max_ratio_db_delta);

        if (ship.upstream_speech != pre.upstream_speech)
            count.upstream_guard_diff_frames++;
        if (ship.transient_capped != pre.transient_capped)
            count.transient_cap_diff_frames++;
        if (ship.blend_applied != pre.blend_applied)
            count.blend_diff_frames++;
        if (ship.noise_update != pre.noise_update)
            count.noise_update_diff_frames++;
        if (ship.refresh != pre.refresh)
            count.refresh_diff_frames++;
        if (ship.hangover_before != pre.hangover_before)
            count.hangover_before_diff_frames++;
        if (ship.hangover_after != pre.hangover_after)
            count.hangover_after_diff_frames++;
        if (public_shipping.active != public_pre.active)
            count.active_diff_frames++;

        if (label) {
            count.speech_frames++;
            if (public_shipping.active) count.speech_shipping_active++;
            if (public_pre.active) count.speech_pre_active++;
            if (public_shipping.active && !public_pre.active) {
                count.lost_speech_frames++;
                if (pre.raw_probability + PROB_EPS < ship.raw_probability)
                    count.lost_raw_probability_lower++;
                if (ship.upstream_speech && !pre.upstream_speech)
                    count.lost_upstream_guard++;
                if (!ship.transient_capped && pre.transient_capped)
                    count.lost_transient_cap_added++;
                if (ship.noise_update != pre.noise_update)
                    count.lost_noise_update_changed++;
                if (ship.refresh != pre.refresh)
                    count.lost_refresh_changed++;
                if (pre.hangover_before < ship.hangover_before)
                    count.lost_hangover_history++;
                if (pre.probability <= VAD_NS_DECISION_THRESHOLD)
                    count.lost_pre_below_decision++;
                if (ship.probability > VAD_NS_DECISION_THRESHOLD)
                    count.lost_ship_above_decision++;
                if (pre.raw_probability <= VAD_LOCAL_SPEECH_GUARD)
                    count.lost_pre_below_local_guard++;
                if (ship.raw_probability > VAD_LOCAL_SPEECH_GUARD)
                    count.lost_ship_above_local_guard++;
                if (pre.noise_rms_before > ship.noise_rms_before)
                    count.lost_pre_noise_rms_higher++;
                if (pre.ratio_db < ship.ratio_db)
                    count.lost_ratio_db_lower++;
            } else if (!public_shipping.active && public_pre.active) {
                count.gained_speech_frames++;
            }
        } else {
            count.noise_frames++;
            if (public_shipping.active) count.noise_shipping_active++;
            if (public_pre.active) count.noise_pre_active++;
        }

        count.frames++;
        frame_index++;
    }

    {
        unsigned extra;
        if (read_label(labels, &extra) > 0) {
            fprintf(stderr, "label stream has more frames than audio\n");
            return 4;
        }
    }

    fprintf(output,
        "{\n"
        "  \"schema_version\": 1,\n"
        "  \"frames\": %llu,\n"
        "  \"speech_frames\": %llu,\n"
        "  \"noise_frames\": %llu,\n"
        "  \"mirror_probability_mismatch_frames\": %llu,\n"
        "  \"mirror_active_mismatch_frames\": %llu,\n"
        "  \"max_public_mirror_probability_delta\": %.9g,\n"
        "  \"raw_probability_diff_frames\": %llu,\n"
        "  \"upstream_guard_diff_frames\": %llu,\n"
        "  \"transient_cap_diff_frames\": %llu,\n"
        "  \"blend_diff_frames\": %llu,\n"
        "  \"noise_update_diff_frames\": %llu,\n"
        "  \"refresh_diff_frames\": %llu,\n"
        "  \"hangover_before_diff_frames\": %llu,\n"
        "  \"hangover_after_diff_frames\": %llu,\n"
        "  \"active_diff_frames\": %llu,\n"
        "  \"speech_shipping_active\": %llu,\n"
        "  \"speech_pre_active\": %llu,\n"
        "  \"noise_shipping_active\": %llu,\n"
        "  \"noise_pre_active\": %llu,\n"
        "  \"lost_speech_frames\": %llu,\n"
        "  \"gained_speech_frames\": %llu,\n"
        "  \"lost_speech_attribution\": {\n"
        "    \"raw_probability_lower\": %llu,\n"
        "    \"upstream_guard_lost\": %llu,\n"
        "    \"transient_cap_added\": %llu,\n"
        "    \"noise_update_changed\": %llu,\n"
        "    \"refresh_changed\": %llu,\n"
        "    \"hangover_history_lower\": %llu,\n"
        "    \"pre_final_below_decision\": %llu,\n"
        "    \"shipping_final_above_decision\": %llu,\n"
        "    \"pre_raw_below_local_guard\": %llu,\n"
        "    \"shipping_raw_above_local_guard\": %llu,\n"
        "    \"pre_noise_rms_higher\": %llu,\n"
        "    \"pre_ratio_db_lower\": %llu\n"
        "  },\n"
        "  \"max_raw_probability_delta\": %.9g,\n"
        "  \"max_final_probability_delta\": %.9g,\n"
        "  \"max_noise_rms_delta\": %.9g,\n"
        "  \"max_ratio_db_delta\": %.9g\n"
        "}\n",
        (unsigned long long)count.frames,
        (unsigned long long)count.speech_frames,
        (unsigned long long)count.noise_frames,
        (unsigned long long)count.mirror_probability_mismatch_frames,
        (unsigned long long)count.mirror_active_mismatch_frames,
        (double)count.max_public_mirror_probability_delta,
        (unsigned long long)count.raw_probability_diff_frames,
        (unsigned long long)count.upstream_guard_diff_frames,
        (unsigned long long)count.transient_cap_diff_frames,
        (unsigned long long)count.blend_diff_frames,
        (unsigned long long)count.noise_update_diff_frames,
        (unsigned long long)count.refresh_diff_frames,
        (unsigned long long)count.hangover_before_diff_frames,
        (unsigned long long)count.hangover_after_diff_frames,
        (unsigned long long)count.active_diff_frames,
        (unsigned long long)count.speech_shipping_active,
        (unsigned long long)count.speech_pre_active,
        (unsigned long long)count.noise_shipping_active,
        (unsigned long long)count.noise_pre_active,
        (unsigned long long)count.lost_speech_frames,
        (unsigned long long)count.gained_speech_frames,
        (unsigned long long)count.lost_raw_probability_lower,
        (unsigned long long)count.lost_upstream_guard,
        (unsigned long long)count.lost_transient_cap_added,
        (unsigned long long)count.lost_noise_update_changed,
        (unsigned long long)count.lost_refresh_changed,
        (unsigned long long)count.lost_hangover_history,
        (unsigned long long)count.lost_pre_below_decision,
        (unsigned long long)count.lost_ship_above_decision,
        (unsigned long long)count.lost_pre_below_local_guard,
        (unsigned long long)count.lost_ship_above_local_guard,
        (unsigned long long)count.lost_pre_noise_rms_higher,
        (unsigned long long)count.lost_ratio_db_lower,
        (double)count.max_raw_probability_delta,
        (double)count.max_final_probability_delta,
        (double)count.max_noise_rms_delta,
        (double)count.max_ratio_db_delta);

    fclose(audio);
    fclose(labels);
    fclose(output);
    return 0;
}
