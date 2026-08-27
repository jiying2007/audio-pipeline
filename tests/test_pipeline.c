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
}

static void test_invalid_config(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    c.io_sample_rate_hz = 44100u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_EINVAL);
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
        assert(ap_pipeline_push_render(p, render, 160) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, 160, out) == AP_OK);
    }
    for (i = 0; i < 160; ++i) assert(out[i] > -8 && out[i] < 8);
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
            assert(ap_pipeline_sample_rate_hz(p) == io_rate);
            assert(ap_pipeline_mic_channels(p) == 2u);
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
                assert(ap_pipeline_push_render(p, render, io_frames) == AP_OK);
                assert(ap_pipeline_process_capture(p, mic, io_frames, out) == AP_OK);
            }
            ap_pipeline_get_metrics(p, &m);
            assert(m.processed_frames == 20u);
            assert(m.active_aec_taps > 0u);
            assert(m.quality == AP_QUALITY_FULL);
        }
    }
}

static void test_aec_convergence(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    int16_t mic[320];
    int16_t render[160];
    int16_t out[160];
    int16_t echo_delay[4096] = {0};
    unsigned wp = 0, frame, i;
    double in_e = 1.0, out_e = 1.0;
    c.mic_channels = 1u;
    c.enable_beamformer = 0u;
    c.enable_delay_tracking = 0u;
    c.initial_delay_ms = 40u;
    c.enable_residual_echo_suppression = 0u;
    c.enable_noise_suppression = 0u;
    c.enable_agc = 0u;
    c.enable_vad = 0u;
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
    /* Deterministic synthetic echo should show material cancellation after convergence. */
    assert(out_e < in_e * 0.70);
}

int main(void) {
    test_state_budget();
    test_invalid_config();
    test_silence();
    test_all_rate_geometries();
    test_aec_convergence();
    puts("audio-pipeline tests: OK");
    return 0;
}
