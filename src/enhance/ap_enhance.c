#include "enhance/ap_enhance.h"
#include "enhance/ap_window.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

static uint32_t ap_enhance_next_pow2(uint32_t x) {
    uint32_t p = 1u;
    while (p < x) p <<= 1u;
    return p;
}

void ap_enhance_init(ap_enhance_state_t *state,
                     uint32_t frame_samples,
                     float agc_target_dbfs,
                     float limiter_dbfs) {
    ap_ns_state_t *s = &state->ns;
    uint32_t i;
    s->nfft = ap_enhance_next_pow2(frame_samples * 2u);
    if (s->nfft > AP_NS_FFT_MAX) s->nfft = AP_NS_FFT_MAX;
    ap_noise_tracker_init(&s->noise_tracker);
    for (i = 0u; i < AP_NS_BINS_MAX; ++i) s->residual_gain_bins[i] = 1.0f;
    s->noise_rms_dbfs = -90.0f;
    state->agc_gain = 1.0f;
    state->agc_target_linear = powf(10.0f, agc_target_dbfs / 20.0f);
    state->limiter_linear = powf(10.0f, limiter_dbfs / 20.0f);
    state->residual_gain = 1.0f;
    state->vad_noise_rms = 1.0e-3f;
}

static float ap_enhance_broadband_res(ap_enhance_state_t *state,
                                      ap_enhance_mode_t mode,
                                      float *x,
                                      uint32_t frame_samples,
                                      int enabled,
                                      float echo_energy,
                                      float residual_energy,
                                      int far_end_active,
                                      int double_talk_active) {
    float target = 1.0f;
    uint32_t i;
    if (enabled && far_end_active && !double_talk_active) {
        const float floor_gain = mode == AP_ENHANCE_FULL ? 0.10f :
                                 (mode == AP_ENHANCE_LITE ? 0.16f : 0.24f);
        target = sqrtf(residual_energy /
                       (residual_energy + 0.8f * echo_energy + 1.0e-12f));
        target = ap_clampf(target, floor_gain, 1.0f);
    }
    if (target < state->residual_gain)
        state->residual_gain = 0.45f * state->residual_gain + 0.55f * target;
    else
        state->residual_gain = 0.92f * state->residual_gain + 0.08f * target;
    for (i = 0u; i < frame_samples; ++i) x[i] *= state->residual_gain;
    return state->residual_gain;
}

static void ap_enhance_ns(ap_enhance_state_t *state,
                          ap_enhance_mode_t mode,
                          const ap_enhance_params_t *params,
                          const float *in,
                          const float *echo,
                          float *out,
                          uint32_t f,
                          int far_end_active,
                          int double_talk_active,
                          ap_enhance_result_t *result) {
    ap_ns_state_t *s = &state->ns;
    const float *window = ap_window_half(f);
    const uint32_t win = f * 2u;
    const uint32_t nfft = s->nfft;
    const uint32_t bins = nfft / 2u + 1u;
    const int freq_res = params->enable_residual_echo_suppression &&
                         params->enable_noise_suppression &&
                         mode != AP_ENHANCE_SAFE && far_end_active &&
                         !double_talk_active;
    uint32_t i, k;
    float speech_sum = 0.0f;
    float res_gain_sum = 0.0f;
    float noise_sum = 1.0e-18f;

    if (!params->enable_noise_suppression) {
        memcpy(out, in, f * sizeof(float));
        memcpy(s->previous_echo, echo, f * sizeof(float));
        s->speech_probability = 0.0f;
        result->frequency_res_active = 0u;
        result->noise_rms_dbfs = s->noise_rms_dbfs;
        return;
    }

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

    for (i = 0u; i < f; ++i) {
        const float w0 = window[i];
        const float w1 = window[f - 1u - i];
        const float previous = s->previous[i];
        s->spectrum[i].re = previous * w0;
        s->spectrum[i].im = 0.0f;
        s->spectrum[f + i].re = in[i] * w1;
        s->spectrum[f + i].im = 0.0f;
        s->previous[i] = in[i];
        s->previous_echo[i] = echo[i];
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
        if (freq_res) {
            const float echo_power = s->echo_power[k];
            const float beta = mode == AP_ENHANCE_FULL ? 1.4f : 0.75f;
            const float floor_gain = mode == AP_ENHANCE_FULL ? 0.10f : 0.18f;
            const float target = ap_clampf(
                sqrtf(power / (power + beta * echo_power + 1.0e-12f)),
                floor_gain, 1.0f);
            const float old = s->residual_gain_bins[k] > 0.0f ?
                              s->residual_gain_bins[k] : 1.0f;
            res_gain = target < old ? 0.55f * old + 0.45f * target :
                                      0.92f * old + 0.08f * target;
            s->residual_gain_bins[k] = res_gain;
        } else {
            s->residual_gain_bins[k] = 0.95f * s->residual_gain_bins[k] + 0.05f;
        }
        res_gain_sum += res_gain;

        ap_noise_tracker_update(&s->noise_tracker, k, power, &noise_result);
        noise = noise_result.noise;
        speech = noise_result.speech_probability;
        if (k > nfft / 64u && k < nfft * 7u / 16u) speech_sum += speech;
        post = power / (noise + 1.0e-12f);
        gain = post > 1.0f ? sqrtf((post - 1.0f) / post) : 0.0f;
        gain = ap_clampf(gain, params->ns_floor, 1.0f) * res_gain;
        if (mode == AP_ENHANCE_SAFE)
            gain = ap_clampf(gain + 0.06f, params->ns_floor, 1.0f);
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
    if (freq_res) {
        result->residual_echo_gain = res_gain_sum / (float)bins;
        result->frequency_res_active = 1u;
    } else if (params->enable_residual_echo_suppression && mode != AP_ENHANCE_SAFE) {
        result->residual_echo_gain = 1.0f;
        result->frequency_res_active = 0u;
    }
    result->noise_rms_dbfs = s->noise_rms_dbfs;

    ap_fft(s->spectrum, nfft, 1);
    for (i = 0u; i < f; ++i) {
        const float w0 = window[i];
        const float w1 = window[f - 1u - i];
        out[i] = s->spectrum[i].re * w0 + s->overlap[i];
        s->overlap[i] = s->spectrum[i + f].re * w1;
    }
}

static void ap_enhance_agc(ap_enhance_state_t *state,
                           int enabled,
                           float *x,
                           uint32_t n) {
    uint32_t i;
    float e = 1.0e-12f;
    float peak = 0.0f, target_gain, alpha;
    if (!enabled) return;
    for (i = 0u; i < n; ++i) {
        const float a = fabsf(x[i]);
        e += x[i] * x[i];
        if (a > peak) peak = a;
    }
    {
        const float rms = sqrtf(e / (float)n);
        target_gain = ap_clampf(state->agc_target_linear / (rms + 1.0e-6f), 0.25f, 8.0f);
    }
    alpha = target_gain < state->agc_gain ? 0.25f : 0.015f;
    state->agc_gain += alpha * (target_gain - state->agc_gain);
    {
        const float limit = state->limiter_linear;
        float gain = state->agc_gain;
        if (peak * gain > limit && peak > 1.0e-6f) gain = limit / peak;
        for (i = 0u; i < n; ++i) x[i] = ap_clampf(x[i] * gain, -limit, limit);
    }
}

static void ap_enhance_vad(ap_enhance_state_t *state,
                           const ap_enhance_params_t *params,
                           const float *x,
                           uint32_t n,
                           ap_enhance_result_t *result) {
    float e = 1.0e-12f;
    uint32_t i;
    float rms, ratio_db, prob;
    for (i = 0u; i < n; ++i) e += x[i] * x[i];
    rms = sqrtf(e / (float)n);
    if (state->vad_noise_rms <= 0.0f) state->vad_noise_rms = rms + 1.0e-6f;
    ratio_db = 20.0f * log10f((rms + 1.0e-7f) /
                              (state->vad_noise_rms + 1.0e-7f));
    prob = ap_clampf((ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);
    if (params->enable_noise_suppression && state->ns.speech_probability > prob)
        prob = state->ns.speech_probability;
    if (prob < 0.35f)
        state->vad_noise_rms = 0.98f * state->vad_noise_rms + 0.02f * rms;
    if (params->enable_vad && prob > 0.45f) state->vad_hangover = 8u;
    else if (state->vad_hangover) state->vad_hangover--;
    result->vad_probability = params->enable_vad ? prob : 0.0f;
    result->vad_active = (uint8_t)(params->enable_vad && state->vad_hangover > 0u);
}

void ap_enhance_process(ap_enhance_state_t *state,
                        ap_enhance_mode_t mode,
                        const ap_enhance_params_t *params,
                        float *aec_residual,
                        const float *echo,
                        float *out,
                        uint32_t frame_samples,
                        float echo_energy,
                        float residual_energy,
                        int far_end_active,
                        int double_talk_active,
                        ap_enhance_result_t *result) {
    const int frequency_res_policy = params->enable_residual_echo_suppression &&
                                     params->enable_noise_suppression &&
                                     mode != AP_ENHANCE_SAFE;
    memset(result, 0, sizeof(*result));
    result->residual_echo_gain = 1.0f;
    result->noise_rms_dbfs = state->ns.noise_rms_dbfs;
    if (!frequency_res_policy) {
        result->residual_echo_gain = ap_enhance_broadband_res(
            state, mode, aec_residual, frame_samples,
            params->enable_residual_echo_suppression,
            echo_energy, residual_energy, far_end_active, double_talk_active);
    }
    ap_enhance_ns(state, mode, params, aec_residual, echo, out,
                  frame_samples, far_end_active, double_talk_active, result);
    ap_enhance_agc(state, params->enable_agc, out, frame_samples);
    ap_enhance_vad(state, params, out, frame_samples, result);
}
