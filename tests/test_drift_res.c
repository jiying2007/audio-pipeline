#include "audio_pipeline/audio_pipeline.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define PI_F 3.14159265358979323846f
#define HIST 16384u
#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static AP_ALIGN16 unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];

static int16_t prn_sample(uint32_t n) {
    uint32_t x = n * 1664525u + 1013904223u;
    return (int16_t)((int32_t)(x >> 16u) - 32768);
}

static void run_delay_frame(ap_pipeline_t *p, int16_t *history, uint32_t *wp,
                            uint32_t *sample_index, uint32_t delay_samples,
                            int16_t *out) {
    int16_t render[160];
    int16_t mic[160];
    uint32_t i;
    for (i = 0u; i < 160u; ++i) {
        const int16_t r = (int16_t)(prn_sample((*sample_index)++) / 2);
        const int16_t delayed = history[(*wp + HIST - delay_samples) & (HIST - 1u)];
        history[*wp] = r;
        *wp = (*wp + 1u) & (HIST - 1u);
        render[i] = r;
        mic[i] = (int16_t)((int32_t)delayed / 2);
    }
    assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
    assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
}

static void test_clock_drift_and_route_jump(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    int16_t history[HIST];
    int16_t out[160];
    uint32_t wp = 0u, sample_index = 0u, frame;
    ap_metrics_t before_jump, after_jump;

    memset(history, 0, sizeof(history));
    c.mic_channels = 1u;
    c.stages = AP_STAGE_SYNC | AP_STAGE_AEC;
    c.enable_delay_tracking = 1u;
    c.enable_clock_drift_compensation = 1u;
    c.initial_delay_ms = 40u;
    c.max_delay_ms = 100u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);

    for (frame = 0u; frame < 250u; ++frame)
        run_delay_frame(p, history, &wp, &sample_index, 640u, out);

    for (frame = 0u; frame < 1000u; ++frame) {
        const uint32_t delay = 640u + frame / 100u;
        run_delay_frame(p, history, &wp, &sample_index, delay, out);
    }
    ap_pipeline_get_metrics(p, &before_jump);
    assert(before_jump.reference_sample_slips > 0u);
    assert(isfinite(before_jump.estimated_drift_ppm));
    assert(fabsf(before_jump.estimated_drift_ppm) <= 2000.0f);
    assert(before_jump.estimated_delay_ms >= 39u && before_jump.estimated_delay_ms <= 43u);

    for (frame = 0u; frame < 120u; ++frame)
        run_delay_frame(p, history, &wp, &sample_index, 1280u, out);
    ap_pipeline_get_metrics(p, &after_jump);
    assert(after_jump.delay_jumps > before_jump.delay_jumps);
    assert(after_jump.aec_resets > before_jump.aec_resets);
    assert(after_jump.estimated_delay_ms >= 75u && after_jump.estimated_delay_ms <= 85u);
}

static void fill_tone_frame(unsigned frame, int16_t *render, int16_t *mic,
                            int double_talk) {
    unsigned i;
    for (i = 0u; i < 160u; ++i) {
        const unsigned s = frame * 160u + i;
        const float far = 0.28f * sinf(2.0f * PI_F * 733.0f * (float)s / 16000.0f) +
                          0.14f * sinf(2.0f * PI_F * 1187.0f * (float)s / 16000.0f);
        const float near = double_talk ?
                           0.65f * sinf(2.0f * PI_F * 241.0f * (float)s / 16000.0f) : 0.0f;
        render[i] = (int16_t)(far * 26000.0f);
        mic[i] = (int16_t)((0.42f * far + near) * 26000.0f);
    }
}

static void test_frequency_res_and_degradation(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    int16_t render[160], mic[160], out[160];
    unsigned frame;
    ap_metrics_t full, safe, dt;

    c.mic_channels = 1u;
    c.stages = AP_STAGE_SYNC | AP_STAGE_AEC | AP_STAGE_RES | AP_STAGE_NS;
    c.enable_delay_tracking = 0u;
    c.enable_clock_drift_compensation = 0u;
    c.initial_delay_ms = 0u;
    c.aec_filter_ms = 64u;
    c.aec_adapt_stride = 1u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);

    for (frame = 0u; frame < 360u; ++frame) {
        fill_tone_frame(frame, render, mic, 0);
        assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
    }
    ap_pipeline_get_metrics(p, &full);
    assert(full.frequency_res_active != 0u);
    assert(full.residual_echo_gain >= 0.05f && full.residual_echo_gain < 0.999f);

    assert(ap_pipeline_set_quality(p, AP_QUALITY_SAFE) == AP_OK);
    for (frame = 360u; frame < 380u; ++frame) {
        fill_tone_frame(frame, render, mic, 0);
        assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
    }
    ap_pipeline_get_metrics(p, &safe);
    assert(safe.frequency_res_active == 0u);
    assert(safe.residual_echo_gain > 0.0f && safe.residual_echo_gain <= 1.0f);

    assert(ap_pipeline_set_quality(p, AP_QUALITY_FULL) == AP_OK);
    for (frame = 380u; frame < 400u; ++frame) {
        fill_tone_frame(frame, render, mic, 1);
        assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
    }
    ap_pipeline_get_metrics(p, &dt);
    assert(dt.double_talk_active != 0u);
    assert(dt.frequency_res_active == 0u);
}

int main(void) {
    test_clock_drift_and_route_jump();
    test_frequency_res_and_degradation();
    puts("audio-pipeline drift/RES tests: OK");
    return 0;
}
