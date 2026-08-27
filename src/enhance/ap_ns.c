#include "enhance/ap_enhance.h"
#include "enhance/ap_window.h"
#include "dsp/ap_dsp.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

static uint32_t ap_ns_next_pow2(uint32_t x) {
    uint32_t p = 1u;
    while (p < x) p <<= 1u;
    return p;
}

void ap_ns_init(ap_ns_state_t *s, uint32_t frame_samples) {
    memset(s, 0, sizeof(*s));
    s->nfft = ap_ns_next_pow2(frame_samples * 2u);
    if (s->nfft > AP_NS_FFT_MAX) s->nfft = AP_NS_FFT_MAX;
    ap_noise_tracker_init(&s->noise_tracker);
#if AP_BUILD_STAGE_RES
    {
        uint32_t i;
        for (i = 0u; i < AP_NS_BINS_MAX; ++i) s->residual_gain_bins[i] = 1.0f;
    }
#endif
    s->noise_rms_dbfs = -90.0f;
}

void ap_ns_process(ap_ns_state_t *s,
                   ap_enhance_mode_t mode,
                   float floor_gain,
                   const float *in,
                   const float *echo,
                   float *out,
                   uint32_t f,
                   int enable_frequency_res,
                   int far_end_active,
                   int double_talk_active,
                   ap_ns_result_t *result) {
    const float *window = ap_window_half(f);
    const uint32_t win = f * 2u;
    const uint32_t nfft = s->nfft;
    const uint32_t bins = nfft / 2u + 1u;
#if AP_BUILD_STAGE_RES
    const int freq_res = enable_frequency_res && echo && mode != AP_ENHANCE_SAFE &&
                         far_end_active && !double_talk_active;
#else
    (void)enable_frequency_res;
    (void)echo;
    (void)far_end_active;
    (void)double_talk_active;
#endif
    uint32_t i, k;
    float speech_sum = 0.0f;
#if AP_BUILD_STAGE_RES
    float res_gain_sum = 0.0f;
#endif
    float noise_sum = 1.0e-18f;

    memset(result, 0, sizeof(*result));
    result->residual_echo_gain = 1.0f;
    result->noise_rms_dbfs = s->noise_rms_dbfs;

#if AP_BUILD_STAGE_RES
    if (freq_res) {
        for (i = 0u; i < f; ++i) {
            const float w0 = window[i];
            const float w1 = window[f - 1u - i];
            s->spectrum[i].re = s->previous_echo[i] * w0;
            s->spectrum[i].im = 0.0f;
            s->spectrum[f + i].re = echo[i] * w1;
            s->spectrum[f + i].im = 0.0f;
        }
        memset(s->spectrum + win, 0, (nfft - win) * sizeof(s->spectrum[0]));
        ap_fft(s->spectrum, nfft, 0);
        for (k = 0u; k < bins; ++k) {
            const float er = s->spectrum[k].re;
            const float ei = s->spectrum[k].im;
            s->echo_power[k] = er * er + ei * ei;
        }
    }
#endif

    for (i = 0u; i < f; ++i) {
        const float w0 = window[i];
        const float w1 = window[f - 1u - i];
        const float previous = s->previous[i];
        s->spectrum[i].re = previous * w0;
        s->spectrum[i].im = 0.0f;
        s->spectrum[f + i].re = in[i] * w1;
        s->spectrum[f + i].im = 0.0f;
        s->previous[i] = in[i];
#if AP_BUILD_STAGE_RES
        if (echo) s->previous_echo[i] = echo[i];
#endif
    }
    memset(s->spectrum + win, 0, (nfft - win) * sizeof(s->spectrum[0]));
    ap_fft(s->spectrum, nfft, 0);

    for (k = 0u; k < bins; ++k) {
        const float re = s->spectrum[k].re;
        const float im = s->spectrum[k].im;
        const float power = re * re + im * im + 1.0e-12f;
        ap_noise_tracker_result_t noise_result;
        float noise, post, gain, speech;
        float res_gain = 1.0f;
#if AP_BUILD_STAGE_RES
        if (freq_res) {
            const float echo_power = s->echo_power[k];
            const float beta = mode == AP_ENHANCE_FULL ? 1.4f : 0.75f;
            const float res_floor = mode == AP_ENHANCE_FULL ? 0.10f : 0.18f;
            const float target = ap_clampf(
                sqrtf(power / (power + beta * echo_power + 1.0e-12f)),
                res_floor, 1.0f);
            const float old = s->residual_gain_bins[k] > 0.0f ?
                              s->residual_gain_bins[k] : 1.0f;
            res_gain = target < old ? 0.55f * old + 0.45f * target :
                                      0.92f * old + 0.08f * target;
            s->residual_gain_bins[k] = res_gain;
        } else {
            s->residual_gain_bins[k] = 0.95f * s->residual_gain_bins[k] + 0.05f;
        }
        res_gain_sum += res_gain;
#endif

        ap_noise_tracker_update(&s->noise_tracker, k, power, &noise_result);
        noise = noise_result.noise;
        speech = noise_result.speech_probability;
        if (k > nfft / 64u && k < nfft * 7u / 16u) speech_sum += speech;
        post = power / (noise + 1.0e-12f);
        gain = post > 1.0f ? sqrtf((post - 1.0f) / post) : 0.0f;
        gain = ap_clampf(gain, floor_gain, 1.0f) * res_gain;
        if (mode == AP_ENHANCE_SAFE)
            gain = ap_clampf(gain + 0.06f, floor_gain, 1.0f);
        s->spectrum[k].re *= gain;
        s->spectrum[k].im *= gain;
        if (k != 0u && k != nfft / 2u) {
            s->spectrum[nfft - k].re *= gain;
            s->spectrum[nfft - k].im *= gain;
        }
        noise_sum += noise;
    }
    ap_noise_tracker_next_frame(&s->noise_tracker);

    {
        const uint32_t speech_bins = (nfft * 7u / 16u) - (nfft / 64u);
        s->speech_probability = ap_clampf(
            speech_sum / (float)(speech_bins ? speech_bins : 1u), 0.0f, 1.0f);
        s->noise_rms_dbfs = 10.0f * log10f(
            noise_sum / (float)bins / ((float)nfft * (float)nfft) + 1.0e-18f);
    }
    result->speech_probability = s->speech_probability;
    result->noise_rms_dbfs = s->noise_rms_dbfs;
#if AP_BUILD_STAGE_RES
    if (freq_res) {
        result->residual_echo_gain = res_gain_sum / (float)bins;
        result->frequency_res_active = 1u;
    }
#endif

    ap_fft(s->spectrum, nfft, 1);
    for (i = 0u; i < f; ++i) {
        const float w0 = window[i];
        const float w1 = window[f - 1u - i];
        out[i] = s->spectrum[i].re * w0 + s->overlap[i];
        s->overlap[i] = s->spectrum[i + f].re * w1;
    }
}
