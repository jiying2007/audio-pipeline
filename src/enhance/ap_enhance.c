#include "ap_internal.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

static uint32_t ap_next_pow2(uint32_t x) {
    uint32_t p = 1u;
    while (p < x) p <<= 1u;
    return p;
}

void ap_enhance_init(ap_pipeline_t *p) {
    ap_ns_state_t *s = &p->ns;
    const uint32_t win = p->internal_frame * 2u;
    uint32_t i;
    s->nfft = ap_next_pow2(win);
    if (s->nfft > AP_NS_FFT_MAX) s->nfft = AP_NS_FFT_MAX;
    for (i = 0u; i < win; ++i)
        s->window[i] = sinf(AP_PI * ((float)i + 0.5f) / (float)win);
    for (i = 0u; i < AP_NS_BINS_MAX; ++i) s->residual_gain_bins[i] = 1.0f;
    s->noise_rms_dbfs = -90.0f;
    p->agc_gain = 1.0f;
    p->agc_target_linear = powf(10.0f, p->cfg.agc_target_dbfs / 20.0f);
    p->limiter_linear = powf(10.0f, p->cfg.limiter_dbfs / 20.0f);
    p->residual_gain = 1.0f;
    p->vad_noise_rms = 1.0e-3f;
}

float ap_apply_broadband_res(ap_pipeline_t *p, float *x,
                             float echo_energy, float residual_energy,
                             float ref_energy, float mic_energy) {
    float target = 1.0f;
    uint32_t i;
    const int far_active = ref_energy > 1.0e-7f;
    const int double_talk = far_active && mic_energy > ref_energy * 1.5f;
    if (p->cfg.enable_residual_echo_suppression && far_active && !double_talk) {
        const float floor_gain = p->quality == AP_QUALITY_FULL ? 0.10f :
                                 (p->quality == AP_QUALITY_LITE ? 0.16f : 0.24f);
        target = sqrtf(residual_energy /
                       (residual_energy + 0.8f * echo_energy + 1.0e-12f));
        target = ap_clampf(target, floor_gain, 1.0f);
    }
    if (target < p->residual_gain)
        p->residual_gain = 0.45f * p->residual_gain + 0.55f * target;
    else
        p->residual_gain = 0.92f * p->residual_gain + 0.08f * target;
    for (i = 0u; i < p->internal_frame; ++i) x[i] *= p->residual_gain;
    p->metrics.frequency_res_active = 0u;
    return p->residual_gain;
}

void ap_ns_process(ap_pipeline_t *p, const float *in, const float *echo,
                   float *out, float ref_energy, float mic_energy) {
    ap_ns_state_t *s = &p->ns;
    const uint32_t f = p->internal_frame;
    const uint32_t win = f * 2u;
    const uint32_t nfft = s->nfft;
    const uint32_t bins = nfft / 2u + 1u;
    const int far_active = ref_energy > 1.0e-7f;
    const int double_talk = far_active && mic_energy > ref_energy * 1.5f;
    const int freq_res = p->cfg.enable_residual_echo_suppression &&
                         p->cfg.enable_noise_suppression &&
                         p->quality != AP_QUALITY_SAFE && far_active && !double_talk;
    uint32_t i, k;
    float speech_sum = 0.0f;
    float res_gain_sum = 0.0f;
    float noise_sum = 1.0e-18f;

    if (!p->cfg.enable_noise_suppression) {
        memcpy(out, in, f * sizeof(float));
        memcpy(s->previous_echo, echo, f * sizeof(float));
        s->speech_probability = 0.0f;
        p->metrics.frequency_res_active = 0u;
        return;
    }

    if (freq_res) {
        for (i = 0u; i < f; ++i) {
            s->spectrum[i].re = s->previous_echo[i] * s->window[i];
            s->spectrum[i].im = 0.0f;
            s->spectrum[f + i].re = echo[i] * s->window[f + i];
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
        const float previous = s->previous[i];
        s->spectrum[i].re = previous * s->window[i];
        s->spectrum[i].im = 0.0f;
        s->spectrum[f + i].re = in[i] * s->window[f + i];
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
        float noise = s->noise_psd[k], post, gain, speech;
        float res_gain = 1.0f;
        if (freq_res) {
            const float echo_power = s->echo_power[k];
            const float beta = p->quality == AP_QUALITY_FULL ? 1.4f : 0.75f;
            const float floor_gain = p->quality == AP_QUALITY_FULL ? 0.10f : 0.18f;
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
        if (s->frame < 20u || noise <= 0.0f) noise = power;
        post = power / (noise + 1.0e-12f);
        speech = ap_clampf((post - 1.4f) * 0.35f, 0.0f, 1.0f);
        if (k > nfft / 64u && k < nfft * 7u / 16u) speech_sum += speech;
        {
            const float alpha = speech > 0.35f ? 0.995f : 0.92f;
            noise = alpha * noise + (1.0f - alpha) * power;
            s->noise_psd[k] = noise;
        }
        post = power / (noise + 1.0e-12f);
        gain = post > 1.0f ? sqrtf((post - 1.0f) / post) : 0.0f;
        gain = ap_clampf(gain, p->cfg.ns_floor, 1.0f) * res_gain;
        if (p->quality == AP_QUALITY_SAFE)
            gain = ap_clampf(gain + 0.06f, p->cfg.ns_floor, 1.0f);
        s->spectrum[k].re *= gain;
        s->spectrum[k].im *= gain;
        if (k != 0u && k != nfft / 2u) {
            s->spectrum[nfft - k].re *= gain;
            s->spectrum[nfft - k].im *= gain;
        }
        noise_sum += noise;
    }

    {
        const uint32_t speech_bins = (nfft * 7u / 16u) - (nfft / 64u);
        s->speech_probability = ap_clampf(
            speech_sum / (float)(speech_bins ? speech_bins : 1u), 0.0f, 1.0f);
        s->noise_rms_dbfs = 10.0f * log10f(
            noise_sum / (float)bins / ((float)nfft * (float)nfft) + 1.0e-18f);
    }
    if (freq_res) {
        p->metrics.residual_echo_gain = res_gain_sum / (float)bins;
        p->metrics.frequency_res_active = 1u;
    } else if (p->cfg.enable_residual_echo_suppression && p->quality != AP_QUALITY_SAFE) {
        p->metrics.residual_echo_gain = 1.0f;
        p->metrics.frequency_res_active = 0u;
    }

    ap_fft(s->spectrum, nfft, 1);
    for (i = 0u; i < f; ++i) {
        out[i] = s->spectrum[i].re * s->window[i] + s->overlap[i];
        s->overlap[i] = s->spectrum[i + f].re * s->window[i + f];
    }
    s->frame++;
}

void ap_agc_process(ap_pipeline_t *p, float *x, uint32_t n) {
    uint32_t i;
    float e = 1.0e-12f;
    float peak = 0.0f, target_gain, alpha;
    if (!p->cfg.enable_agc) return;
    for (i = 0u; i < n; ++i) {
        const float a = fabsf(x[i]);
        e += x[i] * x[i];
        if (a > peak) peak = a;
    }
    {
        const float rms = sqrtf(e / (float)n);
        target_gain = ap_clampf(p->agc_target_linear / (rms + 1.0e-6f), 0.25f, 8.0f);
    }
    alpha = target_gain < p->agc_gain ? 0.25f : 0.015f;
    p->agc_gain += alpha * (target_gain - p->agc_gain);
    {
        const float limit = p->limiter_linear;
        float gain = p->agc_gain;
        if (peak * gain > limit && peak > 1.0e-6f) gain = limit / peak;
        for (i = 0u; i < n; ++i) x[i] = ap_clampf(x[i] * gain, -limit, limit);
    }
}

void ap_vad_process(ap_pipeline_t *p, const float *x, uint32_t n) {
    float e = 1.0e-12f;
    uint32_t i;
    float rms, ratio_db, prob;
    for (i = 0u; i < n; ++i) e += x[i] * x[i];
    rms = sqrtf(e / (float)n);
    if (p->vad_noise_rms <= 0.0f) p->vad_noise_rms = rms + 1.0e-6f;
    ratio_db = 20.0f * log10f((rms + 1.0e-7f) /
                              (p->vad_noise_rms + 1.0e-7f));
    prob = ap_clampf((ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);
    if (p->cfg.enable_noise_suppression && p->ns.speech_probability > prob)
        prob = p->ns.speech_probability;
    if (prob < 0.35f)
        p->vad_noise_rms = 0.98f * p->vad_noise_rms + 0.02f * rms;
    if (p->cfg.enable_vad && prob > 0.45f) p->vad_hangover = 8u;
    else if (p->vad_hangover) p->vad_hangover--;
    p->metrics.vad_probability = p->cfg.enable_vad ? prob : 0.0f;
    p->metrics.vad_active = (uint8_t)(p->cfg.enable_vad && p->vad_hangover > 0u);
}
