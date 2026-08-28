#include "audio_pipeline/audio_modules.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

#define AP_PI 3.14159265358979323846

static AP_ALIGN16 unsigned char module_mem[AP_MODULE_STATE_MAX_BYTES];

static float ref_s16_to_f32(int16_t x) {
    return (float)x * (1.0f / 32768.0f);
}

static float ref_clampf(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static int16_t ref_f32_to_s16(float x) {
    const float y = ref_clampf(x, -0.999969f, 0.999969f) * 32768.0f;
    return (int16_t)(y >= 0.0f ? y + 0.5f : y - 0.5f);
}

static void ref_input(const int16_t *in, uint32_t in_frames,
                      float *out, uint32_t out_frames) {
    uint32_t i;
    if (in_frames == out_frames) {
        for (i = 0u; i < out_frames; ++i) out[i] = ref_s16_to_f32(in[i]);
        return;
    }
    for (i = 0u; i < out_frames; ++i) {
        const float pos = (float)i * (float)in_frames / (float)out_frames;
        uint32_t i0 = (uint32_t)pos;
        const float frac = pos - (float)i0;
        uint32_t i1;
        if (i0 >= in_frames) i0 = in_frames - 1u;
        i1 = i0 + 1u < in_frames ? i0 + 1u : i0;
        out[i] = ref_s16_to_f32(in[i0]) * (1.0f - frac) +
                 ref_s16_to_f32(in[i1]) * frac;
    }
}

static void ref_output(const float *in, uint32_t in_frames,
                       int16_t *out, uint32_t out_frames) {
    uint32_t i;
    if (in_frames == out_frames) {
        for (i = 0u; i < out_frames; ++i) out[i] = ref_f32_to_s16(in[i]);
        return;
    }
    for (i = 0u; i < out_frames; ++i) {
        const float pos = (float)i * (float)in_frames / (float)out_frames;
        uint32_t i0 = (uint32_t)pos;
        const float frac = pos - (float)i0;
        uint32_t i1;
        if (i0 >= in_frames) i0 = in_frames - 1u;
        i1 = i0 + 1u < in_frames ? i0 + 1u : i0;
        out[i] = ref_f32_to_s16(in[i0] * (1.0f - frac) + in[i1] * frac);
    }
}

static void check_fast_pair(uint32_t io_rate, uint32_t internal_rate) {
    ap_resampler_module_t *m = NULL;
    int16_t input[AP_MAX_IO_FRAME_SAMPLES];
    int16_t actual[AP_MAX_IO_FRAME_SAMPLES];
    int16_t expected[AP_MAX_IO_FRAME_SAMPLES];
    float internal[AP_MAX_IO_FRAME_SAMPLES];
    float expected_internal[AP_MAX_IO_FRAME_SAMPLES];
    const uint32_t io_frames = io_rate / 100u;
    const uint32_t internal_frames = internal_rate / 100u;
    uint32_t frame, i;

    assert(ap_module_resampler_init(module_mem, sizeof(module_mem), &m) == AP_OK);
    for (frame = 0u; frame < 4u; ++frame) {
        for (i = 0u; i < io_frames; ++i) {
            const uint32_t x = 1103515245u * (i + 1u + frame * 997u) + 12345u;
            input[i] = (int16_t)((int32_t)((x >> 8u) % 40001u) - 20000);
        }
        ref_input(input, io_frames, expected_internal, internal_frames);
        ref_output(expected_internal, internal_frames, expected, io_frames);
        assert(ap_module_resampler_input_s16(m, input, io_frames, 1u, 0u,
                                             internal, internal_frames) == AP_OK);
        assert(ap_module_resampler_output_s16(m, internal, internal_frames,
                                              actual, io_frames) == AP_OK);
        for (i = 0u; i < io_frames; ++i)
            assert(abs((int)actual[i] - (int)expected[i]) <= 1);
    }
}

static double measure_downsample_rms(uint32_t in_rate, uint32_t out_rate,
                                     double tone_hz) {
    ap_resampler_module_t *m = NULL;
    int16_t input[AP_MAX_IO_FRAME_SAMPLES];
    float output[AP_MAX_IO_FRAME_SAMPLES];
    const uint32_t in_frames = in_rate / 100u;
    const uint32_t out_frames = out_rate / 100u;
    uint32_t frame, i;
    double energy = 0.0;
    uint64_t count = 0u;

    assert(ap_module_resampler_init(module_mem, sizeof(module_mem), &m) == AP_OK);
    for (frame = 0u; frame < 24u; ++frame) {
        for (i = 0u; i < in_frames; ++i) {
            const uint64_t n = (uint64_t)frame * in_frames + i;
            const double x = 0.5 * sin(2.0 * AP_PI * tone_hz * (double)n /
                                       (double)in_rate);
            input[i] = (int16_t)(x * 32767.0);
        }
        assert(ap_module_resampler_input_s16(m, input, in_frames, 1u, 0u,
                                             output, out_frames) == AP_OK);
        if (frame >= 4u) {
            for (i = 0u; i < out_frames; ++i) {
                energy += (double)output[i] * (double)output[i];
                count++;
            }
        }
    }
    assert(count != 0u);
    return sqrt(energy / (double)count);
}

static void check_bandlimited_pair(uint32_t in_rate, uint32_t out_rate,
                                   double stop_tone_hz) {
    const double pass_rms = measure_downsample_rms(in_rate, out_rate, 1000.0);
    const double stop_rms = measure_downsample_rms(in_rate, out_rate, stop_tone_hz);
    assert(pass_rms > 0.20);
    /* At least ~14 dB attenuation for a tone well into the stopband. */
    assert(stop_rms < pass_rms * 0.20);
}

static void test_reset_reproducibility(void) {
    ap_resampler_module_t *m = NULL;
    int16_t input[160];
    float a[80], b[80];
    uint32_t i;
    for (i = 0u; i < 160u; ++i) input[i] = (int16_t)(i * 127 - 10000);
    assert(ap_module_resampler_init(module_mem, sizeof(module_mem), &m) == AP_OK);
    assert(ap_module_resampler_input_s16(m, input, 160u, 1u, 0u, a, 80u) == AP_OK);
    ap_module_resampler_reset(m);
    assert(ap_module_resampler_input_s16(m, input, 160u, 1u, 0u, b, 80u) == AP_OK);
    for (i = 0u; i < 80u; ++i) assert(fabsf(a[i] - b[i]) < 1.0e-7f);
}

int main(void) {
    static const uint32_t io_rates[] = {8000u, 16000u, 24000u, 32000u, 48000u};
    static const uint32_t internal_rates[] = {8000u, 16000u};
    size_t i, j;

    assert(ap_module_resampler_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    test_reset_reproducibility();

    if (strcmp(AP_BUILD_RESAMPLER_MODE_NAME, "FAST") == 0) {
        for (i = 0u; i < sizeof(io_rates) / sizeof(io_rates[0]); ++i)
            for (j = 0u; j < sizeof(internal_rates) / sizeof(internal_rates[0]); ++j)
                check_fast_pair(io_rates[i], internal_rates[j]);
    } else {
        check_bandlimited_pair(16000u, 8000u, 6000.0);
        check_bandlimited_pair(24000u, 8000u, 10000.0);
        check_bandlimited_pair(32000u, 8000u, 12000.0);
        check_bandlimited_pair(48000u, 8000u, 12000.0);
        check_bandlimited_pair(24000u, 16000u, 10000.0);
        check_bandlimited_pair(32000u, 16000u, 12000.0);
        check_bandlimited_pair(48000u, 16000u, 16000.0);
    }

    puts("audio resampler quality contracts: OK");
    return 0;
}
