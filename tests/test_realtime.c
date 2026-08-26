#include "audio_pipeline/audio_pipeline.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define PI_F 3.14159265358979323846f
#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static AP_ALIGN16 unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];

static void test_backend_geometry_and_quality(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    ap_metrics_t full, lite, safe, restored;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    ap_pipeline_get_metrics(p, &full);
    assert(full.quality == AP_QUALITY_FULL);
    assert(full.active_aec_taps > 0u);
    assert(full.active_aec_adapt_stride == c.aec_adapt_stride);
    if (full.aec_backend == AP_AEC_BACKEND_MDF) {
        assert(full.aec_block_samples == c.internal_sample_rate_hz / 500u);
        assert(full.active_aec_partitions > 0u);
        assert(full.active_aec_partitions <= 60u);
    } else {
        assert(full.aec_backend == AP_AEC_BACKEND_NLMS);
        assert(full.aec_block_samples == 1u);
        assert(full.active_aec_partitions == 0u);
    }

    assert(ap_pipeline_set_quality(p, AP_QUALITY_LITE) == AP_OK);
    ap_pipeline_get_metrics(p, &lite);
    assert(lite.quality == AP_QUALITY_LITE);
    assert(lite.active_aec_taps <= full.active_aec_taps);
    assert(lite.active_aec_adapt_stride >= full.active_aec_adapt_stride);
    if (full.aec_backend == AP_AEC_BACKEND_MDF)
        assert(lite.active_aec_partitions <= full.active_aec_partitions);

    assert(ap_pipeline_set_quality(p, AP_QUALITY_SAFE) == AP_OK);
    ap_pipeline_get_metrics(p, &safe);
    assert(safe.quality == AP_QUALITY_SAFE);
    assert(safe.active_aec_taps <= lite.active_aec_taps);
    assert(safe.active_aec_adapt_stride >= 4u);
    if (full.aec_backend == AP_AEC_BACKEND_MDF)
        assert(safe.active_aec_partitions <= lite.active_aec_partitions);

    assert(ap_pipeline_set_quality(p, AP_QUALITY_FULL) == AP_OK);
    ap_pipeline_get_metrics(p, &restored);
    assert(restored.active_aec_taps == full.active_aec_taps);
    assert(restored.active_aec_adapt_stride == full.active_aec_adapt_stride);
    if (full.aec_backend == AP_AEC_BACKEND_MDF)
        assert(restored.active_aec_partitions == full.active_aec_partitions);
}

static void test_double_talk_freezes_adaptation_and_preserves_near_end(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    int16_t render[160];
    int16_t mic[160];
    int16_t out[160];
    unsigned frame, i;
    double near_e = 1.0, out_e = 1.0;
    c.mic_channels = 1u;
    c.enable_beamformer = 0u;
    c.enable_delay_tracking = 0u;
    c.initial_delay_ms = 0u;
    c.enable_residual_echo_suppression = 0u;
    c.enable_noise_suppression = 0u;
    c.enable_agc = 0u;
    c.enable_vad = 0u;
    c.aec_filter_ms = 64u;
    c.aec_adapt_stride = 1u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);

    for (frame = 0u; frame < 220u; ++frame) {
        for (i = 0u; i < 160u; ++i) {
            const unsigned s = frame * 160u + i;
            const float far = 0.18f * sinf(2.0f * PI_F * 733.0f * (float)s / 16000.0f) +
                              0.09f * sinf(2.0f * PI_F * 997.0f * (float)s / 16000.0f);
            render[i] = (int16_t)(far * 32767.0f);
            mic[i] = (int16_t)(0.35f * far * 32767.0f);
        }
        assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
    }

    for (frame = 0u; frame < 20u; ++frame) {
        ap_metrics_t m;
        for (i = 0u; i < 160u; ++i) {
            const unsigned s = (220u + frame) * 160u + i;
            const float far = 0.18f * sinf(2.0f * PI_F * 733.0f * (float)s / 16000.0f) +
                              0.09f * sinf(2.0f * PI_F * 997.0f * (float)s / 16000.0f);
            const float near = 0.55f * sinf(2.0f * PI_F * 241.0f * (float)s / 16000.0f);
            render[i] = (int16_t)(far * 32767.0f);
            mic[i] = (int16_t)((near + 0.35f * far) * 32767.0f);
            near_e += (double)(near * 32767.0f) * (near * 32767.0f);
        }
        assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
        ap_pipeline_get_metrics(p, &m);
        assert(m.double_talk_active != 0u);
        for (i = 0u; i < 160u; ++i) out_e += (double)out[i] * out[i];
    }
    /* The AEC may leave echo, but it must not erase a strong near-end talker. */
    assert(out_e > near_e * 0.25);
}

static void test_long_running_state_is_bounded_and_delay_jump_resets(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_pipeline_t *p = NULL;
    int16_t mic[320];
    int16_t render[160];
    int16_t out[160];
    unsigned frame, i;
    assert(ap_pipeline_state_size() <= AP_PIPELINE_STATE_MAX_BYTES);
    /* This is a default two-mic/HPF/beamforming long-run stress case. It
     * verifies bounded state and that a materially different render path can
     * invalidate AEC state. Exact delay convergence belongs to
     * test_drift_res.c, which disables front-end transforms and drives a
     * controlled delayed render history. */
    assert(c.initial_delay_ms == 40u);
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    for (frame = 0u; frame < 1200u; ++frame) {
        for (i = 0u; i < 160u; ++i) {
            const uint32_t s = frame * 160u + i;
            const int32_t prn = (int32_t)((s * 1664525u + 1013904223u) >> 16u) - 32768;
            render[i] = (int16_t)(prn / 8);
            mic[2u * i] = (int16_t)(prn / 12);
            mic[2u * i + 1u] = (int16_t)(prn / 13);
        }
        assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
    }
    {
        ap_metrics_t m;
        ap_pipeline_get_metrics(p, &m);
        assert(m.processed_frames == 1200u);
        assert(m.active_aec_taps > 0u);
        assert(m.aec_resets > 0u);
        assert(m.estimated_delay_ms <= c.max_delay_ms);
    }
}

int main(void) {
    test_backend_geometry_and_quality();
    test_double_talk_freezes_adaptation_and_preserves_near_end();
    test_long_running_state_is_bounded_and_delay_jump_resets();
    puts("audio-pipeline realtime tests: OK");
    return 0;
}
