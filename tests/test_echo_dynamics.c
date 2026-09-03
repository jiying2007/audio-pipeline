#include "aec/ap_aec.h"
#include "enhance/ap_enhance.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>

static ap_aec_state_t aec_state;
static float mic[160], ref_signal[160], out[160], echo[160];

static float max_abs(const float *x, uint32_t n) {
    float peak = 0.0f;
    uint32_t i;
    for (i = 0u; i < n; ++i) {
        const float a = fabsf(x[i]);
        if (a > peak) peak = a;
    }
    return peak;
}

static void fill_low(float *x, uint32_t n) {
    uint32_t i;
    for (i = 0u; i < n; ++i)
        x[i] = 0.01f * sinf(0.13f * (float)i);
}

static void test_far_end_agc_does_not_gain_up(void) {
    ap_agc_state_t state;
    float samples[160];
    float boosted_gain;
    uint32_t frame;
    ap_agc_init(&state, -20.0f, -2.0f);
    for (frame = 0u; frame < 40u; ++frame) {
        fill_low(samples, 160u);
        ap_agc_process(&state, samples, 160u);
    }
    boosted_gain = state.gain;
    assert(boosted_gain > 1.0f);
    fill_low(samples, 160u);
    {
        const float before = max_abs(samples, 160u);
        ap_agc_process_controlled(&state, samples, 160u, 0);
        assert(max_abs(samples, 160u) <= before + 1.0e-6f);
        assert(state.gain < boosted_gain);
    }
    ap_agc_init(&state, -20.0f, -2.0f);
    for (frame = 0u; frame < 80u; ++frame) {
        fill_low(samples, 160u);
        ap_agc_process_controlled(&state, samples, 160u, 0);
    }
    assert(state.gain <= 1.000001f);
}

static void fill_echo_frame(uint32_t frame) {
    uint32_t i;
    for (i = 0u; i < 160u; ++i) {
        const float v = 0.08f * sinf(0.031f * (float)(frame * 160u + i));
        ref_signal[i] = v;
        mic[i] = 0.65f * v;
    }
}

static void run_far_end_frames(uint32_t configured_stride,
                     uint32_t expected_steady_stride) {
    ap_aec_result_t result;
    ap_aec_status_t status;
    uint32_t frame;
    ap_aec_backend_init(&aec_state, 160u, 960u, configured_stride);
    for (frame = 0u; frame < AP_AEC_STEADY_FRAMES + 8u; ++frame) {
        fill_echo_frame(frame);
        ap_aec_backend_process(&aec_state, 1, 0.2f, 160u,
                     mic, ref_signal, out, echo,
                     1, 0, &result);
    }
    ap_aec_backend_get_status(&aec_state, &status);
    assert(status.active_adapt_stride == expected_steady_stride);
}

static void test_aec_steady_stride_preserves_movement_tracking(void) {
    run_far_end_frames(2u, 2u);
    run_far_end_frames(1u, 2u);
}

int main(void) {
    test_far_end_agc_does_not_gain_up();
    test_aec_steady_stride_preserves_movement_tracking();
    return 0;
}
