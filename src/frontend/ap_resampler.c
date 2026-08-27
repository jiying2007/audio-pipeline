#include "ap_internal.h"
#include <stdint.h>

static float ap_s16_to_f32(int16_t x) { return (float)x * (1.0f / 32768.0f); }

static int16_t ap_f32_to_s16(float x) {
    const float y = ap_clampf(x, -0.999969f, 0.999969f) * 32768.0f;
    return (int16_t)(y >= 0.0f ? y + 0.5f : y - 0.5f);
}

int ap_supported_io_rate(uint32_t hz) {
    return hz == 8000u || hz == 16000u || hz == 24000u ||
           hz == 32000u || hz == 48000u;
}

void ap_resample_input_channel(const int16_t *in, uint32_t in_frames,
                               uint32_t channels, uint32_t channel,
                               float *out, uint32_t out_frames) {
    uint32_t i;
    if (in_frames == out_frames) {
        for (i = 0u; i < out_frames; ++i)
            out[i] = ap_s16_to_f32(in[i * channels + channel]);
        return;
    }
    if (in_frames > out_frames && in_frames % out_frames == 0u) {
        const uint32_t step = in_frames / out_frames;
        for (i = 0u; i < out_frames; ++i)
            out[i] = ap_s16_to_f32(in[(i * step) * channels + channel]);
        return;
    }
    if (in_frames * 2u == out_frames * 3u) {
        uint32_t src = 0u;
        for (i = 0u; i + 1u < out_frames; i += 2u, src += 3u) {
            out[i] = ap_s16_to_f32(in[src * channels + channel]);
            out[i + 1u] = 0.5f *
                (ap_s16_to_f32(in[(src + 1u) * channels + channel]) +
                 ap_s16_to_f32(in[(src + 2u) * channels + channel]));
        }
        return;
    }
    if (out_frames == in_frames * 2u) {
        for (i = 0u; i < in_frames; ++i) {
            const uint32_t next = i + 1u < in_frames ? i + 1u : i;
            const float a = ap_s16_to_f32(in[i * channels + channel]);
            const float b = ap_s16_to_f32(in[next * channels + channel]);
            out[2u * i] = a;
            out[2u * i + 1u] = 0.5f * (a + b);
        }
        return;
    }
    for (i = 0u; i < out_frames; ++i) {
        const float pos = (float)i * (float)in_frames / (float)out_frames;
        uint32_t i0 = (uint32_t)pos;
        const float frac = pos - (float)i0;
        uint32_t i1;
        if (i0 >= in_frames) i0 = in_frames - 1u;
        i1 = i0 + 1u < in_frames ? i0 + 1u : i0;
        out[i] = ap_s16_to_f32(in[i0 * channels + channel]) * (1.0f - frac) +
                 ap_s16_to_f32(in[i1 * channels + channel]) * frac;
    }
}

void ap_resample_output(const float *in, uint32_t in_frames,
                        int16_t *out, uint32_t out_frames) {
    uint32_t i;
    if (in_frames == out_frames) {
        for (i = 0u; i < out_frames; ++i) out[i] = ap_f32_to_s16(in[i]);
        return;
    }
    if (in_frames > out_frames && in_frames % out_frames == 0u) {
        const uint32_t step = in_frames / out_frames;
        for (i = 0u; i < out_frames; ++i) out[i] = ap_f32_to_s16(in[i * step]);
        return;
    }
    if (out_frames * 2u == in_frames * 3u) {
        uint32_t src = 0u;
        const float one_third = 1.0f / 3.0f;
        const float two_thirds = 2.0f / 3.0f;
        for (i = 0u; i + 2u < out_frames; i += 3u, src += 2u) {
            const uint32_t next = src + 1u < in_frames ? src + 1u : src;
            const uint32_t next2 = src + 2u < in_frames ? src + 2u : next;
            out[i] = ap_f32_to_s16(in[src]);
            out[i + 1u] = ap_f32_to_s16(one_third * in[src] + two_thirds * in[next]);
            out[i + 2u] = ap_f32_to_s16(two_thirds * in[next] + one_third * in[next2]);
        }
        return;
    }
    if (out_frames > in_frames && out_frames % in_frames == 0u) {
        const uint32_t phases = out_frames / in_frames;
        const float inv_phases = 1.0f / (float)phases;
        uint32_t src = 0u, phase = 0u;
        for (i = 0u; i < out_frames; ++i) {
            const uint32_t next = src + 1u < in_frames ? src + 1u : src;
            const float frac = (float)phase * inv_phases;
            out[i] = ap_f32_to_s16(in[src] * (1.0f - frac) + in[next] * frac);
            if (++phase == phases) {
                phase = 0u;
                if (src + 1u < in_frames) src++;
            }
        }
        return;
    }
    for (i = 0u; i < out_frames; ++i) {
        const float pos = (float)i * (float)in_frames / (float)out_frames;
        uint32_t i0 = (uint32_t)pos;
        const float frac = pos - (float)i0;
        uint32_t i1;
        if (i0 >= in_frames) i0 = in_frames - 1u;
        i1 = i0 + 1u < in_frames ? i0 + 1u : i0;
        out[i] = ap_f32_to_s16(in[i0] * (1.0f - frac) + in[i1] * frac);
    }
}
