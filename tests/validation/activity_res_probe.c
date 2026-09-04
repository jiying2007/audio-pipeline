#include "activity/ap_activity.h"
#include "enhance/ap_enhance.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FRAME_SAMPLES 160u
#define FAR_THRESHOLD 1.0e-7f
#define DT_RATIO 1.5f
#define HANGOVER 3u

static uint32_t lcg_next(uint32_t *state) {
    *state = (*state * 1664525u) + 1013904223u;
    return *state;
}

static float jitter(uint32_t *state, float span) {
    const float u = (float)(lcg_next(state) >> 8) / 16777215.0f;
    return 1.0f + span * (2.0f * u - 1.0f);
}

static int first_true_frame(const uint8_t *values, uint32_t count) {
    uint32_t i;
    for (i = 0u; i < count; ++i) {
        if (values[i]) return (int)i + 1;
    }
    return -1;
}

static uint32_t count_true(const uint8_t *values, uint32_t count) {
    uint32_t i;
    uint32_t total = 0u;
    for (i = 0u; i < count; ++i) total += values[i] ? 1u : 0u;
    return total;
}

static uint32_t frames_until_false(ap_activity_state_t *state,
                                   float mic_energy,
                                   float ref_energy,
                                   int check_double_talk,
                                   uint32_t limit) {
    uint32_t i;
    ap_activity_result_t result;
    for (i = 0u; i < limit; ++i) {
        ap_activity_process(state, mic_energy, ref_energy, &result);
        if (check_double_talk) {
            if (!result.double_talk_active) return i + 1u;
        } else if (!result.far_end_active) {
            return i + 1u;
        }
    }
    return limit + 1u;
}

static int run_activity(uint32_t seed) {
    ap_activity_state_t state;
    ap_activity_result_t result;
    uint8_t far_flags[24];
    uint8_t dt_flags[24];
    uint32_t rng = seed;
    uint32_t i;
    uint32_t far_release;
    uint32_t dt_release;
    uint32_t chatter_far = 0u;
    uint32_t chatter_dt = 0u;
    uint32_t near_false_far = 0u;
    uint32_t near_false_dt = 0u;
    int far_attack;
    int dt_attack;
    int failed = 0;

    ap_activity_init(&state, FAR_THRESHOLD, DT_RATIO, HANGOVER);
    for (i = 0u; i < 20u; ++i) {
        ap_activity_process(&state, 1.0e-10f, 1.0e-10f, &result);
        if (result.far_end_active || result.double_talk_active) failed = 1;
    }

    ap_activity_reset(&state);
    memset(far_flags, 0, sizeof(far_flags));
    memset(dt_flags, 0, sizeof(dt_flags));
    for (i = 0u; i < 24u; ++i) {
        ap_activity_process(&state, 1.0e-7f, 4.0e-7f, &result);
        far_flags[i] = result.far_end_active;
        dt_flags[i] = result.double_talk_active;
    }
    far_attack = first_true_frame(far_flags, 24u);
    if (far_attack < 1 || far_attack > 6 || count_true(far_flags, 24u) < 21u ||
        count_true(dt_flags, 24u) != 0u) failed = 1;

    far_release = frames_until_false(&state, 1.0e-10f, 1.0e-10f, 0, 50u);
    if (far_release > 36u) failed = 1;

    ap_activity_reset(&state);
    memset(far_flags, 0, sizeof(far_flags));
    memset(dt_flags, 0, sizeof(dt_flags));
    for (i = 0u; i < 24u; ++i) {
        ap_activity_process(&state, 1.0e-6f, 4.0e-7f, &result);
        far_flags[i] = result.far_end_active;
        dt_flags[i] = result.double_talk_active;
    }
    dt_attack = first_true_frame(dt_flags, 24u);
    if (dt_attack < 1 || dt_attack > 6 || count_true(dt_flags, 24u) < 20u) failed = 1;
    dt_release = frames_until_false(&state, 1.0e-7f, 4.0e-7f, 1, 12u);
    if (dt_release > 5u) failed = 1;

    ap_activity_reset(&state);
    for (i = 0u; i < 32u; ++i) {
        const float ref = 1.10e-7f * jitter(&rng, 0.28f);
        const float mic = 0.24f * ref;
        ap_activity_process(&state, mic, ref, &result);
        chatter_far += result.far_end_active ? 1u : 0u;
        chatter_dt += result.double_talk_active ? 1u : 0u;
    }
    if (chatter_far < 24u || chatter_dt != 0u) failed = 1;

    ap_activity_reset(&state);
    for (i = 0u; i < 32u; ++i) {
        const float ref = 4.0e-8f * jitter(&rng, 0.30f);
        const float mic = 8.0e-7f * jitter(&rng, 0.10f);
        ap_activity_process(&state, mic, ref, &result);
        near_false_far += result.far_end_active ? 1u : 0u;
        near_false_dt += result.double_talk_active ? 1u : 0u;
    }
    if (near_false_far != 0u || near_false_dt != 0u) failed = 1;

    ap_activity_reset(&state);
    for (i = 0u; i < 12u; ++i)
        ap_activity_process(&state, 1.0e-7f, 4.0e-7f, &result);
    ap_activity_process(&state, 1.0e-10f, 1.0e-10f, &result);
    if (!result.far_end_active) failed = 1;

    printf("ACTIVITY seed=%u far_attack=%d far_recall_frames=%u/24 far_release=%u "
           "dt_attack=%d dt_recall_frames=%u/24 dt_release=%u "
           "threshold_chatter_far=%u/32 threshold_chatter_dt=%u/32 "
           "near_false_far=%u near_false_dt=%u result=%s\n",
           seed, far_attack, count_true(far_flags, 24u), far_release,
           dt_attack, count_true(dt_flags, 24u), dt_release,
           chatter_far, chatter_dt, near_false_far, near_false_dt,
           failed ? "FAIL" : "PASS");
    return failed;
}

static float run_res_frames(ap_res_state_t *state,
                            ap_enhance_mode_t mode,
                            uint32_t frames,
                            float echo_energy,
                            float residual_energy,
                            int far,
                            int dt,
                            uint32_t *first_below_012,
                            uint32_t *first_above_090,
                            int *sample_mismatch) {
    float frame[FRAME_SAMPLES];
    float gain = state->gain;
    uint32_t f;
    if (first_below_012) *first_below_012 = 0u;
    if (first_above_090) *first_above_090 = 0u;
    for (f = 0u; f < frames; ++f) {
        uint32_t i;
        for (i = 0u; i < FRAME_SAMPLES; ++i) frame[i] = 1.0f;
        gain = ap_res_process(state, mode, frame, FRAME_SAMPLES,
                              echo_energy, residual_energy, far, dt);
        if (fabsf(frame[0] - gain) > 1.0e-6f && sample_mismatch)
            *sample_mismatch = 1;
        if (first_below_012 && *first_below_012 == 0u && gain <= 0.12f)
            *first_below_012 = f + 1u;
        if (first_above_090 && *first_above_090 == 0u && gain >= 0.90f)
            *first_above_090 = f + 1u;
    }
    return gain;
}

static int run_res(void) {
    ap_res_state_t full;
    ap_res_state_t lite;
    ap_res_state_t safe;
    ap_res_state_t moderate;
    ap_res_state_t preserve;
    float full_gain;
    float lite_gain;
    float safe_gain;
    float moderate_gain;
    float near_gain;
    float dt_gain;
    uint32_t attack = 0u;
    uint32_t recovery = 0u;
    int sample_mismatch = 0;
    int failed = 0;

    ap_res_init(&preserve);
    near_gain = run_res_frames(&preserve, AP_ENHANCE_FULL, 12u,
                               0.0f, 1.0e-4f, 0, 0, NULL, NULL,
                               &sample_mismatch);
    if (near_gain < 0.999f) failed = 1;

    ap_res_init(&preserve);
    dt_gain = run_res_frames(&preserve, AP_ENHANCE_FULL, 12u,
                             1.0e-3f, 1.0e-4f, 1, 1, NULL, NULL,
                             &sample_mismatch);
    if (dt_gain < 0.999f) failed = 1;

    ap_res_init(&full);
    full_gain = run_res_frames(&full, AP_ENHANCE_FULL, 30u,
                               1.0e-3f, 1.0e-6f, 1, 0, &attack, NULL,
                               &sample_mismatch);
    if (full_gain < 0.099f || full_gain > 0.105f || attack == 0u || attack > 7u)
        failed = 1;

    ap_res_init(&lite);
    lite_gain = run_res_frames(&lite, AP_ENHANCE_LITE, 30u,
                               1.0e-3f, 1.0e-6f, 1, 0, NULL, NULL,
                               &sample_mismatch);
    ap_res_init(&safe);
    safe_gain = run_res_frames(&safe, AP_ENHANCE_SAFE, 30u,
                               1.0e-3f, 1.0e-6f, 1, 0, NULL, NULL,
                               &sample_mismatch);
    if (!(full_gain < lite_gain && lite_gain < safe_gain) ||
        lite_gain < 0.159f || lite_gain > 0.165f ||
        safe_gain < 0.239f || safe_gain > 0.245f)
        failed = 1;

    ap_res_init(&moderate);
    moderate_gain = run_res_frames(&moderate, AP_ENHANCE_FULL, 30u,
                                   1.0e-3f, 1.0e-4f, 1, 0, NULL, NULL,
                                   &sample_mismatch);
    if (moderate_gain < 0.30f || moderate_gain > 0.37f) failed = 1;

    recovery = 0u;
    run_res_frames(&full, AP_ENHANCE_FULL, 50u,
                   1.0e-3f, 1.0e-4f, 1, 1, NULL, &recovery,
                   &sample_mismatch);
    if (recovery == 0u || recovery > 36u || full.gain < 0.98f) failed = 1;
    if (sample_mismatch) failed = 1;

    printf("RES full_floor=%.6f lite_floor=%.6f safe_floor=%.6f "
           "moderate_gain=%.6f near_gain=%.6f dt_gain=%.6f "
           "attack_to_0.12=%u recovery_to_0.90=%u final_recovery=%.6f result=%s\n",
           full_gain, lite_gain, safe_gain, moderate_gain, near_gain, dt_gain,
           attack, recovery, full.gain, failed ? "FAIL" : "PASS");
    return failed;
}

int main(int argc, char **argv) {
    uint32_t seed = 1307u;
    int failed = 0;
    if (argc > 2) {
        fprintf(stderr, "usage: %s [seed]\n", argv[0]);
        return 2;
    }
    if (argc == 2) {
        char *end = NULL;
        unsigned long value = strtoul(argv[1], &end, 10);
        if (!end || *end != '\0' || value > 0xfffffffful) return 2;
        seed = (uint32_t)value;
    }
    failed |= run_activity(seed);
    failed |= run_res();
    return failed ? 1 : 0;
}
