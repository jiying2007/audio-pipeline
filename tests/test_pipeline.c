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

static void test_state_budget(void) {
    assert(ap_pipeline_state_size() <= AP_PIPELINE_STATE_MAX_BYTES);
    assert((ap_pipeline_compiled_stages() & ~AP_STAGE_ALL) == 0u);
}

static void test_invalid_config(void) {
    const ap_stage_mask_t compiled = ap_pipeline_compiled_stages();
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    c.io_sample_rate_hz = 44100u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_EINVAL);

    if (compiled & AP_STAGE_RES) {
        c = ap_config_default(AP_PROFILE_CALL);
        c.stages = AP_STAGE_RES;
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
    if (compiled & AP_STAGE_AEC) {
        c = ap_config_default(AP_PROFILE_CALL);
        c.stages = AP_STAGE_AEC;
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
    if (compiled & AP_STAGE_BF) {
        c = ap_config_default(AP_PROFILE_CALL);
        c.mic_channels = 1u;
        c.stages |= AP_STAGE_BF;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
}

static void test_silence(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_pipeline_t *p = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    const size_t frame = c.io_sample_rate_hz / 100u;
    unsigned f, i;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    for (f = 0; f < 30; ++f) {
        if (c.stages & AP_STAGE_SYNC)
            assert(ap_pipeline_push_render(p, render, frame) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, frame, out) == AP_OK);
    }
    for (i = 0; i < frame; ++i) assert(out[i] > -8 && out[i] < 8);
}

static void test_partial_composition(void) {
    const ap_stage_mask_t compiled = ap_pipeline_compiled_stages();
    ap_config_t c = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_pipeline_t *p = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    const uint32_t base_latency = (compiled & AP_STAGE_NS) ? AP_FRAME_MS : 0u;
    const size_t frame = c.io_sample_rate_hz / 100u;
    c.mic_channels = 1u;
    c.stages = compiled & (AP_STAGE_HPF | AP_STAGE_NS | AP_STAGE_AGC | AP_STAGE_VAD);
    c.enable_delay_tracking = 0u;
    c.enable_clock_drift_compensation = 0u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    assert(ap_pipeline_push_render(p, render, frame) == AP_ESTATE);
    assert(ap_pipeline_process_capture(p, mic, frame, out) == AP_OK);
    assert(ap_pipeline_algorithmic_latency_ms(p) >= base_latency);
}

static void test_shared_double_talk_hangover(void) {
    if (!(ap_pipeline_compiled_stages() & AP_STAGE_SYNC)) return;
    {
        ap_config_t c = ap_config_default(AP_PROFILE_CALL);
        ap_pipeline_t *p = NULL;
        ap_metrics_t m;
        int16_t mic[AP_MAX_IO_FRAME_SAMPLES];
        int16_t render[AP_MAX_IO_FRAME_SAMPLES];
        int16_t out[AP_MAX_IO_FRAME_SAMPLES];
        const uint32_t frame_samples = c.io_sample_rate_hz / 100u;
        unsigned frame, i;

        c.mic_channels = 1u;
        c.stages = AP_STAGE_SYNC;
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
        c.initial_delay_ms = 0u;
        assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);

        for (i = 0u; i < frame_samples; ++i) render[i] = 2000;
        for (frame = 0u; frame < 4u; ++frame) {
            const int16_t mic_level = frame == 0u ? 6000 : 1000;
            for (i = 0u; i < frame_samples; ++i) mic[i] = mic_level;
            assert(ap_pipeline_push_render(p, render, frame_samples) == AP_OK);
            assert(ap_pipeline_process_capture(p, mic, frame_samples, out) == AP_OK);
            ap_pipeline_get_metrics(p, &m);
            assert(m.far_end_active == 1u);
            if (frame < 3u) assert(m.double_talk_active == 1u);
            else assert(m.double_talk_active == 0u);
        }
    }
}

static void test_all_rate_geometries(void) {
    static const uint32_t io_rates[] = {8000u, 16000u, 24000u, 32000u, 48000u};
    static const uint32_t internal_rates[] = {8000u, 16000u};
    const ap_build_info_t *bi = ap_build_info();
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    size_t r, ir;

    for (r = 0u; r < sizeof(io_rates) / sizeof(io_rates[0]); ++r) {
        for (ir = 0u; ir < sizeof(internal_rates) / sizeof(internal_rates[0]); ++ir) {
            ap_config_t c;
            ap_pipeline_t *p = NULL;
            ap_metrics_t m;
            const uint32_t io_rate = io_rates[r];
            const uint32_t internal_rate = internal_rates[ir];
            const uint32_t io_frame = io_rate / 100u;
            unsigned frame, i;
            if (io_rate > bi->max_io_rate_hz || internal_rate > bi->max_internal_rate_hz)
                continue;
            c = ap_config_default(AP_PROFILE_CALL);
            c.io_sample_rate_hz = io_rate;
            c.internal_sample_rate_hz = internal_rate;
            c.mic_channels = bi->max_mic_channels >= 2u ? 2u : 1u;
            if (c.mic_channels < 2u) c.stages &= ~AP_STAGE_BF;
            memset(mic, 0, sizeof(mic));
            memset(render, 0, sizeof(render));
            assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
            for (frame = 0u; frame < 20u; ++frame) {
                for (i = 0u; i < io_frame; ++i) {
                    render[i] = (int16_t)(1000.0f * sinf(2.0f * PI_F * 733.0f *
                                                         (float)(frame * io_frame + i) /
                                                         (float)io_rate));
                    mic[i * c.mic_channels] = render[i] / 3;
                    if (c.mic_channels == 2u) mic[i * 2u + 1u] = render[i] / 3;
                }
                if (c.stages & AP_STAGE_SYNC)
                    assert(ap_pipeline_push_render(p, render, io_frame) == AP_OK);
                assert(ap_pipeline_process_capture(p, mic, io_frame, out) == AP_OK);
            }
            ap_pipeline_get_metrics(p, &m);
            assert(m.processed_frames == 20u);
        }
    }
}

int main(void) {
    test_state_budget();
    test_invalid_config();
    test_silence();
    test_partial_composition();
    test_shared_double_talk_hangover();
    test_all_rate_geometries();
    puts("audio-pipeline tests: OK");
    return 0;
}
