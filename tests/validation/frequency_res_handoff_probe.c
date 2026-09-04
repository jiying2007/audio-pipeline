#include "enhance/ap_enhance.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define FRAME_SAMPLES 160u
#define MAX_HALF_RECOVERY_FRAMES 5
#define MAX_90_RECOVERY_FRAMES 12

static uint32_t lcg_next(uint32_t *state) {
    *state = (*state * 1664525u) + 1013904223u;
    return *state;
}

static float signed_noise(uint32_t *state) {
    const float u = (float)(lcg_next(state) >> 8) / 16777215.0f;
    return 2.0f * u - 1.0f;
}

static void make_frame(uint32_t *rng,
                       float *input,
                       float *echo,
                       int near_active) {
    uint32_t i;
    for (i = 0u; i < FRAME_SAMPLES; ++i) {
        const float e = 0.10f * signed_noise(rng);
        const float near = near_active ? 0.045f * signed_noise(rng) : 0.0f;
        echo[i] = e;
        input[i] = 0.10f * e + near;
    }
}

static float mean_masked_gain(const ap_ns_state_t *state,
                              const uint8_t *mask,
                              uint32_t bins) {
    float sum = 0.0f;
    uint32_t count = 0u;
    uint32_t k;
    for (k = 0u; k < bins; ++k) {
        if (!mask[k]) continue;
        sum += state->residual_gain_bins[k];
        count++;
    }
    return count ? sum / (float)count : 1.0f;
}

int main(int argc, char **argv) {
    ap_ns_state_t state;
    ap_ns_result_t result;
    float input[FRAME_SAMPLES];
    float echo[FRAME_SAMPLES];
    float output[FRAME_SAMPLES];
    uint8_t suppressed[AP_NS_BINS_MAX] = {0};
    uint32_t seed = 1307u;
    uint32_t rng;
    uint32_t bins;
    uint32_t suppressed_bins = 0u;
    uint32_t i;
    uint32_t k;
    float pre_mean;
    float gain1 = 0.0f;
    float gain3 = 0.0f;
    int first_half = -1;
    int first_90 = -1;
    int failed = 0;

    if (argc > 2) return 2;
    if (argc == 2) {
        char *end = NULL;
        unsigned long value = strtoul(argv[1], &end, 10);
        if (!end || *end != '\0' || value > 0xfffffffful) return 2;
        seed = (uint32_t)value;
    }
    rng = seed;
    ap_ns_init(&state, FRAME_SAMPLES);
    bins = state.nfft / 2u + 1u;

    /* Preserve the shipping far-only frequency-RES operating point as an
     * anti-regression guard before measuring the near-protection release. */
    for (i = 0u; i < 40u; ++i) {
        make_frame(&rng, input, echo, 0);
        ap_ns_process(&state, AP_ENHANCE_FULL, 0.20f,
                      input, echo, output, FRAME_SAMPLES,
                      1, 1, 0, &result);
    }
    for (k = 0u; k < bins; ++k) {
        if (state.residual_gain_bins[k] <= 0.30f) {
            suppressed[k] = 1u;
            suppressed_bins++;
        }
    }
    pre_mean = mean_masked_gain(&state, suppressed, bins);
    if (suppressed_bins < bins / 2u || pre_mean > 0.22f) failed = 1;

    /* Enter double-talk. Frequency RES must disable immediately and its
     * historical gains must recover fast enough to preserve near-end onset. */
    for (i = 0u; i < 60u; ++i) {
        float mean_gain;
        make_frame(&rng, input, echo, 1);
        ap_ns_process(&state, AP_ENHANCE_FULL, 0.20f,
                      input, echo, output, FRAME_SAMPLES,
                      1, 1, 1, &result);
        mean_gain = mean_masked_gain(&state, suppressed, bins);
        if (i == 0u) gain1 = mean_gain;
        if (i == 2u) gain3 = mean_gain;
        if (first_half < 0 && mean_gain >= 0.50f) first_half = (int)i + 1;
        if (first_90 < 0 && mean_gain >= 0.90f) first_90 = (int)i + 1;
        if (result.frequency_res_active) failed = 1;
    }

    if (first_half < 1 || first_half > MAX_HALF_RECOVERY_FRAMES ||
        first_90 < 1 || first_90 > MAX_90_RECOVERY_FRAMES)
        failed = 1;

    printf("FREQ_RES_HANDOFF seed=%u suppressed_bins=%u/%u pre_mean=%.6f "
           "gain_f1=%.6f gain_f3=%.6f gain_ge_0.50_frame=%d "
           "gain_ge_0.90_frame=%d final_mean=%.6f result=%s\n",
           seed, suppressed_bins, bins, pre_mean, gain1, gain3,
           first_half, first_90,
           mean_masked_gain(&state, suppressed, bins),
           failed ? "FAIL" : "PASS");
    return failed ? 1 : 0;
}
