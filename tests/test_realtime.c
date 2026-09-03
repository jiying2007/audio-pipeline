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
    assert((c.stages & (AP_STAGE_SYNC | AP_STAGE_AEC)) ==
           (AP_STAGE_SYNC | AP_STAGE_AEC));
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    ap_pipeline_get_metrics(p, &full);
    assert(full.quality == AP_QUALITY_FULL);
    assert(full.active_aec_taps > 0u);
    assert(full.active_aec_adapt_stride == c.aec_adapt_stride);
    if (full.aec_backend == AP_AEC_BACKEND_MDF) {
        assert(full.aec_block_samples == c.internal_sample_rate_hz / 500u);
        assert(full.active_aec_partitions > 0u);
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
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    const uint32_t io_rate = c.io_sample_rate_hz;
    const uint32_t io_frame = io_rate / 100u;
    unsigned frame, i;
    double near_e = 1.0, out_e = 1.0;
    c.mic_channels = 1u;
    c.stages = AP_STAGE_SYNC | AP_STAGE_AEC;
    c.enable_delay_tracking = 0u;
    c.enable_clock_drift_compensation = 0u;
    c.initial_delay_ms = 0u;
    if (c.aec_filter_ms > 64u) c.aec_filter_ms = 64u;
    c.aec_adapt_stride = 1u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);

    for (frame = 0u; frame < 220u; ++frame) {
        for (i = 0u; i < io_frame; ++i) {
            const unsigned s = frame * io_frame + i;
            const float far = 0.18f * sinf(2.0f * PI_F * 733.0f * (float)s / (float)io_rate) +
                              0.09f * sinf(2.0f * PI_F * 997.0f * (float)s / (float)io_rate);
            render[i] = (int16_t)(far * 32767.0f);
            mic[i] = (int16_t)(0.35f * far * 32767.0f);
        }
        assert(ap_pipeline_push_render(p, render, io_frame) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, io_frame, out) == AP_OK);
    }
    {
        ap_metrics_t stable;
        ap_pipeline_get_metrics(p, &stable);
        assert(stable.active_aec_adapt_stride == 2u);
    }

    for (frame = 0u; frame < 20u; ++frame) {
        ap_metrics_t m;
        for (i = 0u; i < io_frame; ++i) {
            const unsigned s = (220u + frame) * io_frame + i;
            const float far = 0.18f * sinf(2.0f * PI_F * 733.0f * (float)s / (float)io_rate) +
                              0.09f * sinf(2.0f * PI_F * 997.0f * (float)s / (float)io_rate);
            const float near = 0.55f * sinf(2.0f * PI_F * 241.0f * (float)s / (float)io_rate);
            render[i] = (int16_t)(far * 32767.0f);
            mic[i] = (int16_t)((near + 0.35f * far) * 32767.0f);
            near_e += (double)(near * 32767.0f) * (near * 32767.0f);
        }
        assert(ap_pipeline_push_render(p, render, io_frame) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, io_frame, out) == AP_OK);
        ap_pipeline_get_metrics(p, &m);
        assert(m.double_talk_active != 0u);
        assert(m.erle_valid == 0u);
        assert(m.active_aec_adapt_stride == c.aec_adapt_stride);
        for (i = 0u; i < io_frame; ++i) out_e += (double)out[i] * out[i];
    }
    assert(out_e > near_e * 0.25);
}

static void test_long_running_state_is_bounded_and_delay_jump_resets(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_pipeline_t *p = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    const uint32_t io_frame = c.io_sample_rate_hz / 100u;
    unsigned frame, i, ch;
    assert((c.stages & (AP_STAGE_SYNC | AP_STAGE_AEC)) ==
           (AP_STAGE_SYNC | AP_STAGE_AEC));
    assert(ap_pipeline_state_size() <= AP_PIPELINE_STATE_MAX_BYTES);
    assert(c.initial_delay_ms <= c.max_delay_ms);
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    memset(mic, 0, sizeof(mic));
    for (frame = 0u; frame < 1200u; ++frame) {
        for (i = 0u; i < io_frame; ++i) {
            const uint32_t s = frame * io_frame + i;
            const int32_t prn = (int32_t)((s * 1664525u + 1013904223u) >> 16u) - 32768;
            render[i] = (int16_t)(prn / 8);
            for (ch = 0u; ch < c.mic_channels; ++ch)
                mic[i * c.mic_channels + ch] = (int16_t)(prn / (12 + (int32_t)ch));
        }
        assert(ap_pipeline_push_render(p, render, io_frame) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, io_frame, out) == AP_OK);
    }
    {
        ap_metrics_t m;
        ap_pipeline_get_metrics(p, &m);
        assert(m.processed_frames == 1200u);
        assert(m.active_aec_taps > 0u);
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
