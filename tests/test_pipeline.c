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
    int16_t mic[320] = {0};
    int16_t render[160] = {0};
    int16_t out[160];
    unsigned f, i;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    for (f = 0; f < 30; ++f) {
        if (c.stages & AP_STAGE_SYNC)
            assert(ap_pipeline_push_render(p, render, 160) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, 160, out) == AP_OK);
    }
    for (i = 0; i < 160; ++i) assert(out[i] > -8 && out[i] < 8);
}

static void test_partial_composition(void) {
    const ap_stage_mask_t compiled = ap_pipeline_compiled_stages();
    ap_config_t c = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_pipeline_t *p = NULL;
    int16_t mic[160] = {0};
    int16_t render[160] = {0};
    int16_t out[160];
    c.mic_channels = 1u;
    c.stages = compiled & (AP_STAGE_HPF | AP_STAGE_NS | AP_STAGE_AGC | AP_STAGE_VAD);
    c.enable_delay_tracking = 0u;
    c.enable_clock_drift_compensation = 0u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    assert(ap_pipeline_push_render(p, render, 160u) == AP_ESTATE);
    assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
    assert(ap_pipeline_algorithmic_latency_ms(p) ==
           ((c.stages & AP_STAGE_NS) ? AP_FRAME_MS : 0u));
}

static void test_shared_double_talk_hangover(void) {
    if (!(ap_pipeline_compiled_stages() & AP_STAGE_SYNC)) return;
    {
        ap_config_t c = ap_config_default(AP_PROFILE_CALL);
        ap_pipeline_t *p = NULL;
        ap_metrics_t m;
        int16_t mic[160];
        int16_t render[160];
        int16_t out[160];
        unsigned frame, i;

        c.mic_channels = 1u;
        c.stages = AP_STAGE_SYNC;
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
        c.initial_delay_ms = 0u;
        assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);

        for (i = 0u; i < 160u; ++i) render[i] = 2000;
        for (frame = 0u; frame < 4u; ++frame) {
            const int16_t mic_level = frame == 0u ? 6000 : 1000;
            for (i = 0u; i < 160u; ++i) mic[i] = mic_level;
            assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
            assert(ap_pipeline_process_capture(p, mic, 160u, out) == AP_OK);
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
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    size_t r, ir;

    for (r = 0u; r < sizeof(io_rates) / sizeof(io_rates[0]); ++r) {
        for (ir = 0u; ir < sizeof(internal_rates) / sizeof(internal_rates[0]); ++ir) {
            ap_config_t c = ap_config_default(AP_PROFILE_CALL);
            ap_pipeline_t *p = NULL;
            ap_metrics_t m;
            const uint32_t io_rate = io_rates[r];
            const uint32_t io_frames = io_rate / 100u;
            uint32_t frame, i;
            c.io_sample_rate_hz = io_rate;
            c.internal_sample_rate_hz = internal_rates[ir];
            assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
            assert(ap_pipeline_frame_samples(p) == io_frames);
            for (frame = 0u; frame < 20u; ++frame) {
                for (i = 0u; i < io_frames; ++i) {
                    const uint32_t n = frame * io_frames + i;
                    const float far = 0.10f * sinf(2.0f * PI_F * 731.0f *
                                                   (float)n / (float)io_rate);
                    const float near = 0.04f * sinf(2.0f * PI_F * 223.0f *
                                                    (float)n / (float)io_rate);
                    render[i] = (int16_t)(far * 32767.0f);
                    mic[2u * i] = (int16_t)((near + 0.18f * far) * 32767.0f);
                    mic[2u * i + 1u] = (int16_t)((near + 0.16f * far) * 32767.0f);
                }
                if (c.stages & AP_STAGE_SYNC)
                    assert(ap_pipeline_push_render(p, render, io_frames) == AP_OK);
                assert(ap_pipeline_process_capture(p, mic, io_frames, out) == AP_OK);
            }
            ap_pipeline_get_metrics(p, &m);
            assert(m.processed_frames == 20u);
            if (c.stages & AP_STAGE_AEC) assert(m.active_aec_taps > 0u);
            assert(m.quality == AP_QUALITY_FULL);
        }
    }
}

static void test_aec_convergence(void) {
    if ((ap_pipeline_compiled_stages() & (AP_STAGE_SYNC | AP_STAGE_AEC)) !=
        (AP_STAGE_SYNC | AP_STAGE_AEC)) return;
    {
        ap_config_t c = ap_config_default(AP_PROFILE_CALL);
        ap_pipeline_t *p = NULL;
        int16_t mic[320];
        int16_t render[160];
        int16_t out[160];
        int16_t echo_delay[4096] = {0};
        unsigned wp = 0, frame, i;
        double in_e = 1.0, out_e = 1.0;
        c.mic_channels = 1u;
        c.stages = AP_STAGE_SYNC | AP_STAGE_AEC;
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
        c.initial_delay_ms = 40u;
        c.aec_filter_ms = 64u;
        c.aec_adapt_stride = 1u;
        assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
        for (frame = 0; frame < 500; ++frame) {
            for (i = 0; i < 160; ++i) {
                const unsigned sample = frame * 160u + i;
                const float r = 0.45f * sinf(2.0f * PI_F * 937.0f * (float)sample / 16000.0f) +
                                0.20f * sinf(2.0f * PI_F * 613.0f * (float)sample / 16000.0f);
                const int16_t rs = (int16_t)(r * 22000.0f);
                const int16_t delayed = echo_delay[(wp + 4096u - 640u) & 4095u];
                echo_delay[wp] = rs;
                wp = (wp + 1u) & 4095u;
                render[i] = rs;
                mic[i] = (int16_t)(0.45f * delayed);
                mic[160u + i] = 0;
            }
            assert(ap_pipeline_push_render(p, render, 160) == AP_OK);
            assert(ap_pipeline_process_capture(p, mic, 160, out) == AP_OK);
            if (frame > 300u) {
                for (i = 0; i < 160; ++i) {
                    in_e += (double)mic[i] * mic[i];
                    out_e += (double)out[i] * out[i];
                }
            }
        }
        assert(out_e < in_e * 0.70);
    }
}

int main(void) {
    test_state_budget();
    test_invalid_config();
    test_silence();
    test_partial_composition();
    test_shared_double_talk_hangover();
    test_all_rate_geometries();
    test_aec_convergence();
    puts("audio-pipeline tests: OK");
    return 0;
}
