#include "activity/ap_activity.h"
#include "enhance/ap_enhance.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

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

static float process_res_frame(ap_res_state_t *res,
                               float echo_energy,
                               float residual_energy,
                               int far,
                               int dt) {
    float frame[FRAME_SAMPLES];
    uint32_t i;
    for (i = 0u; i < FRAME_SAMPLES; ++i) frame[i] = 1.0f;
    return ap_res_process(res, AP_ENHANCE_FULL, frame, FRAME_SAMPLES,
                          echo_energy, residual_energy, far, dt);
}

int main(int argc, char **argv) {
    ap_activity_state_t activity;
    ap_activity_result_t result;
    ap_res_state_t res;
    uint32_t seed = 1307u;
    uint32_t rng;
    uint32_t i;
    int dt_attack = -1;
    int first_half = -1;
    int first_90 = -1;
    float pre_gain = 1.0f;
    float gain1 = 0.0f;
    float gain2 = 0.0f;
    float gain3 = 0.0f;
    float gain_at_dt = 0.0f;
    int failed = 0;

    if (argc > 2) return 2;
    if (argc == 2) {
        char *end = NULL;
        unsigned long value = strtoul(argv[1], &end, 10);
        if (!end || *end != '\0' || value > 0xfffffffful) return 2;
        seed = (uint32_t)value;
    }
    rng = seed;

    ap_activity_init(&activity, FAR_THRESHOLD, DT_RATIO, HANGOVER);
    ap_res_init(&res);

    /* Establish a stable far-only epoch with severe residual echo, matching
     * the standalone RES floor test before switching to near-end speech. */
    for (i = 0u; i < 30u; ++i) {
        const float ref = 4.0e-7f * jitter(&rng, 0.04f);
        const float mic = 1.0e-7f * jitter(&rng, 0.04f);
        ap_activity_process(&activity, mic, ref, &result);
        pre_gain = process_res_frame(&res, 1.0e-3f, 1.0e-6f,
                                     result.far_end_active,
                                     result.double_talk_active);
    }
    if (pre_gain < 0.099f || pre_gain > 0.105f) failed = 1;

    /* Render stops and near-end speech begins while the acoustic/AEC echo
     * estimate is conservatively allowed to linger. Activity output drives
     * RES exactly as the composed pipeline does. These recovery numbers are
     * discovery evidence; the loose bounds below only reject broken coupling. */
    for (i = 0u; i < 40u; ++i) {
        const float ref = 1.0e-10f;
        const float mic = 8.0e-7f * jitter(&rng, 0.08f);
        const float echo_energy = 1.0e-3f * jitter(&rng, 0.05f);
        const float residual_energy = 1.0e-4f * jitter(&rng, 0.08f);
        float gain;
        ap_activity_process(&activity, mic, ref, &result);
        gain = process_res_frame(&res, echo_energy, residual_energy,
                                 result.far_end_active,
                                 result.double_talk_active);
        if (i == 0u) gain1 = gain;
        if (i == 1u) gain2 = gain;
        if (i == 2u) gain3 = gain;
        if (dt_attack < 0 && result.double_talk_active) {
            dt_attack = (int)i + 1;
            gain_at_dt = gain;
        }
        if (first_half < 0 && gain >= 0.50f) first_half = (int)i + 1;
        if (first_90 < 0 && gain >= 0.90f) first_90 = (int)i + 1;
    }

    if (dt_attack < 1 || dt_attack > 3 || first_half < 1 || first_half > 15 ||
        first_90 < 1 || first_90 > 40 || res.gain < 0.95f)
        failed = 1;

    printf("HANDOFF seed=%u pre_gain=%.6f dt_attack=%d gain_f1=%.6f "
           "gain_f2=%.6f gain_f3=%.6f gain_at_dt=%.6f "
           "gain_ge_0.50_frame=%d gain_ge_0.90_frame=%d final_gain=%.6f "
           "result=%s\n",
           seed, pre_gain, dt_attack, gain1, gain2, gain3, gain_at_dt,
           first_half, first_90, res.gain, failed ? "FAIL" : "PASS");
    return failed ? 1 : 0;
}
