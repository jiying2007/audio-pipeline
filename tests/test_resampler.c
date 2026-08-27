#include "audio_pipeline/audio_modules.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

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

static void check_rate_pair(uint32_t io_rate, uint32_t internal_rate) {
    int16_t input[AP_MAX_IO_FRAME_SAMPLES];
    int16_t actual[AP_MAX_IO_FRAME_SAMPLES];
    int16_t expected[AP_MAX_IO_FRAME_SAMPLES];
    float internal[160];
    float expected_internal[160];
    const uint32_t io_frames = io_rate / 100u;
    const uint32_t internal_frames = internal_rate / 100u;
    uint32_t frame, i;

    for (frame = 0u; frame < 4u; ++frame) {
        for (i = 0u; i < io_frames; ++i) {
            const uint32_t x = 1103515245u * (i + 1u + frame * 997u) + 12345u;
            input[i] = (int16_t)((int32_t)((x >> 8u) % 40001u) - 20000);
        }
        ref_input(input, io_frames, expected_internal, internal_frames);
        ref_output(expected_internal, internal_frames, expected, io_frames);
        assert(ap_module_resampler_input_s16(input, io_frames, 1u, 0u,
                                             internal, internal_frames) == AP_OK);
        assert(ap_module_resampler_output_s16(internal, internal_frames,
                                              actual, io_frames) == AP_OK);
        for (i = 0u; i < io_frames; ++i) {
            const int diff = (int)actual[i] - (int)expected[i];
            if (abs(diff) > 1) {
                fprintf(stderr,
                        "resampler mismatch io=%u internal=%u frame=%u i=%u actual=%d expected=%d diff=%d\n",
                        io_rate, internal_rate, frame, i,
                        (int)actual[i], (int)expected[i], diff);
            }
            assert(abs(diff) <= 1);
        }
    }
}

int main(void) {
    static const uint32_t io_rates[] = {8000u, 16000u, 24000u, 32000u, 48000u};
    static const uint32_t internal_rates[] = {8000u, 16000u};
    size_t i, j;
    for (i = 0u; i < sizeof(io_rates) / sizeof(io_rates[0]); ++i)
        for (j = 0u; j < sizeof(internal_rates) / sizeof(internal_rates[0]); ++j)
            check_rate_pair(io_rates[i], internal_rates[j]);
    puts("audio resampler module contracts: OK");
    return 0;
}
