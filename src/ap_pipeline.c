#include "ap_internal.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(AP_ENABLE_NEON) && (defined(__ARM_NEON) || defined(__ARM_NEON__))
#include <arm_neon.h>
#define AP_HAVE_NEON 1
#else
#define AP_HAVE_NEON 0
#endif

static int ap_supported_io_rate(uint32_t hz) {
    return hz == 8000u || hz == 16000u || hz == 24000u || hz == 32000u || hz == 48000u;
}

static uint32_t ap_next_pow2(uint32_t x) {
    uint32_t p = 1u;
    while (p < x) p <<= 1u;
    return p;
}

static float ap_s16_to_f32(int16_t x) { return (float)x * (1.0f / 32768.0f); }

static int16_t ap_f32_to_s16(float x) {
    const float y = ap_clampf(x, -0.999969f, 0.999969f) * 32768.0f;
    return (int16_t)(y >= 0.0f ? y + 0.5f : y - 0.5f);
}

static void ap_resample_input_channel(const int16_t *in, uint32_t in_frames,
                                      uint32_t channels, uint32_t channel,
                                      float *out, uint32_t out_frames) {
    uint32_t i;
    if (in_frames == out_frames) {
        for (i = 0u; i < out_frames; ++i) out[i] = ap_s16_to_f32(in[i * channels + channel]);
        return;
    }
    for (i = 0u; i < out_frames; ++i) {
        const float pos = (float)i * (float)in_frames / (float)out_frames;
        uint32_t i0 = (uint32_t)pos;
        float frac = pos - (float)i0;
        uint32_t i1;
        if (i0 >= in_frames) i0 = in_frames - 1u;
        i1 = i0 + 1u < in_frames ? i0 + 1u : i0;
        out[i] = ap_s16_to_f32(in[i0 * channels + channel]) * (1.0f - frac) +
                 ap_s16_to_f32(in[i1 * channels + channel]) * frac;
    }
}

static void ap_resample_output(const float *in, uint32_t in_frames,
                               int16_t *out, uint32_t out_frames) {
    uint32_t i;
    if (in_frames == out_frames) {
        for (i = 0u; i < out_frames; ++i) out[i] = ap_f32_to_s16(in[i]);
        return;
    }
    for (i = 0u; i < out_frames; ++i) {
        const float pos = (float)i * (float)in_frames / (float)out_frames;
        uint32_t i0 = (uint32_t)pos;
        float frac = pos - (float)i0;
        uint32_t i1;
        if (i0 >= in_frames) i0 = in_frames - 1u;
        i1 = i0 + 1u < in_frames ? i0 + 1u : i0;
        out[i] = ap_f32_to_s16(in[i0] * (1.0f - frac) + in[i1] * frac);
    }
}

static void ap_hpf(ap_pipeline_t *p, float *x, uint32_t n, uint32_t ch) {
    uint32_t i;
    float px = p->hpf_x[ch], py = p->hpf_y[ch];
    for (i = 0u; i < n; ++i) {
        const float in = x[i];
        const float y = in - px + p->hpf_r * py;
        x[i] = y;
        px = in;
        py = y;
    }
    p->hpf_x[ch] = px;
    p->hpf_y[ch] = py;
}

static float ap_past_sample(const ap_pipeline_t *p, const float *x,
                            uint32_t ch, int index) {
    if (index >= 0) return x[(uint32_t)index];
    if (index < -(int)AP_BF_HISTORY) return 0.0f;
    return p->bf_history[ch][AP_BF_HISTORY + index];
}

static int ap_estimate_bf_lag(ap_pipeline_t *p, const float *a,
                              const float *b, uint32_t n) {
    const int max_lag = p->bf_max_lag;
    int lag, best = 0;
    float best_score = -1.0e30f;
    if (max_lag < 1) return 0;
    for (lag = -max_lag; lag <= max_lag; ++lag) {
        float xy = 0.0f, aa = 1.0e-12f, bb = 1.0e-12f;
        uint32_t i;
        for (i = 0u; i < n; i += 2u) {
            float x, y;
            if (lag >= 0) {
                x = a[i];
                y = ap_past_sample(p, b, 1u, (int)i - lag);
            } else {
                x = ap_past_sample(p, a, 0u, (int)i + lag);
                y = b[i];
            }
            xy += x * y;
            aa += x * x;
            bb += y * y;
        }
        {
            const float score = xy / sqrtf(aa * bb);
            if (score > best_score) {
                best_score = score;
                best = lag;
            }
        }
    }
    return best_score > 0.15f ? best : p->bf_lag;
}

static void ap_beamform(ap_pipeline_t *p, float *a, float *b,
                        float *out, uint32_t n) {
    uint32_t i;
    if (p->quality == AP_QUALITY_FULL && (++p->bf_counter & 3u) == 0u) {
        const int lag = ap_estimate_bf_lag(p, a, b, n);
        if (lag > p->bf_lag) p->bf_lag++;
        else if (lag < p->bf_lag) p->bf_lag--;
    }
    for (i = 0u; i < n; ++i) {
        float x, y;
        if (p->bf_lag >= 0) {
            x = a[i];
            y = ap_past_sample(p, b, 1u, (int)i - p->bf_lag);
        } else {
            x = ap_past_sample(p, a, 0u, (int)i + p->bf_lag);
            y = b[i];
        }
        out[i] = 0.5f * (x + y);
    }
    for (i = 0u; i < AP_BF_HISTORY; ++i) {
        const uint32_t src = n > AP_BF_HISTORY ? n - AP_BF_HISTORY + i : i;
        p->bf_history[0][i] = src < n ? a[src] : 0.0f;
        p->bf_history[1][i] = src < n ? b[src] : 0.0f;
    }
}

static float ap_render_absolute(const ap_pipeline_t *p, int64_t index) {
    const int64_t oldest = (int64_t)p->render_total - (int64_t)AP_RENDER_CAP;
    if (index < 0 || index >= (int64_t)p->render_total || index < oldest) return 0.0f;
    return p->render_ring[(uint64_t)index & (AP_RENDER_CAP - 1u)];
}

static void ap_get_reference(ap_pipeline_t *p, uint32_t delay, float *out) {
    const int64_t start = (int64_t)p->render_total -
                          (int64_t)p->internal_frame - (int64_t)delay;
    uint32_t i;
    if (start < 0) p->metrics.render_underruns++;
    for (i = 0u; i < p->internal_frame; ++i)
        out[i] = ap_render_absolute(p, start + (int64_t)i);
}

static void ap_reset_aec_weights(ap_pipeline_t *p) {
#if defined(AP_ENABLE_MDF_AEC)
    ap_mdf_reset(p, 1);
#else
    memset(p->aec_weights, 0, sizeof(p->aec_weights));
    memset(p->aec_history, 0, sizeof(p->aec_history));
    p->aec_pos = 0u;
    p->aec_adapt_phase = 0u;
    p->metrics.aec_resets++;
#endif
}

static float ap_delay_score(const ap_pipeline_t *p, const float *mic,
                            uint32_t delay, uint32_t sample_step) {
    const int64_t start = (int64_t)p->render_total -
                          (int64_t)p->internal_frame - (int64_t)delay;
    float xy = 0.0f, xx = 1.0e-12f, yy = 1.0e-12f;
    uint32_t i;
    for (i = 0u; i < p->internal_frame; i += sample_step) {
        const float x = ap_render_absolute(p, start + (int64_t)i);
        const float y = mic[i];
        xy += x * y;
        xx += x * x;
        yy += y * y;
    }
    return fabsf(xy / sqrtf(xx * yy));
}

static void ap_apply_drift_correction(ap_pipeline_t *p, uint32_t best_delay) {
    const uint32_t fs = p->cfg.internal_sample_rate_hz;
    int32_t error = (int32_t)best_delay - (int32_t)p->delay_samples;
    uint32_t corrections = 0u;
    p->metrics.delay_error_samples = error;

    if (p->have_last_best_delay) {
        const int32_t delta = (int32_t)best_delay - (int32_t)p->last_best_delay;
        float raw_ppm = (float)delta * 10000000.0f / (float)fs; /* tracker runs every 100 ms */
        raw_ppm = ap_clampf(raw_ppm, -2000.0f, 2000.0f);
        p->drift_ppm = 0.95f * p->drift_ppm + 0.05f * raw_ppm;
    }
    p->last_best_delay = best_delay;
    p->have_last_best_delay = 1u;
    p->metrics.estimated_drift_ppm = p->drift_ppm;

    /* ppm integration gives one reference insert/drop only when accumulated
     * fractional clock error reaches a full sample. A persistent alignment
     * error adds a bounded catch-up term but never causes a large discontinuity. */
    p->drift_credit += p->drift_ppm * (float)fs / 10000000.0f;
    if (error > 4) p->drift_credit += ap_clampf((float)error * 0.05f, 0.0f, 0.5f);
    else if (error < -4) p->drift_credit += ap_clampf((float)error * 0.05f, -0.5f, 0.0f);

    while (p->drift_credit >= 1.0f && p->delay_samples <
           p->cfg.max_delay_ms * fs / 1000u && corrections < 4u) {
        p->delay_samples++;
        p->drift_credit -= 1.0f;
        p->metrics.reference_sample_slips++;
        corrections++;
    }
    while (p->drift_credit <= -1.0f && p->delay_samples > 0u && corrections < 4u) {
        p->delay_samples--;
        p->drift_credit += 1.0f;
        p->metrics.reference_sample_slips++;
        corrections++;
    }
}

static void ap_track_delay(ap_pipeline_t *p, const float *mic) {
    const uint32_t fs = p->cfg.internal_sample_rate_hz;
    const uint32_t max_delay = p->cfg.max_delay_ms * fs / 1000u;
    const uint32_t coarse_step = fs / 500u ? fs / 500u : 1u; /* 2 ms */
    const uint32_t sample_step = 4u;
    float best = 0.0f;
    uint32_t best_delay = p->delay_samples, d;

    if (!p->cfg.enable_delay_tracking ||
        p->render_total < (uint64_t)(max_delay + p->internal_frame)) return;
    if (++p->delay_update_counter < 10u) return;
    p->delay_update_counter = 0u;

    for (d = 0u; d <= max_delay; d += coarse_step) {
        const float score = ap_delay_score(p, mic, d, sample_step);
        if (score > best) {
            best = score;
            best_delay = d;
        }
    }

    /* Fine search only around the best coarse cell. It resolves one-sample
     * drift without paying a full max-delay x sample-resolution search. */
    {
        const uint32_t lo = best_delay > coarse_step ? best_delay - coarse_step : 0u;
        const uint32_t hi = best_delay + coarse_step < max_delay ?
                            best_delay + coarse_step : max_delay;
        for (d = lo; d <= hi; ++d) {
            const float score = ap_delay_score(p, mic, d, sample_step);
            if (score > best) {
                best = score;
                best_delay = d;
            }
        }
    }

    if (best > 0.18f) {
        const uint32_t old = p->delay_samples;
        const uint32_t raw_jump = old > best_delay ? old - best_delay : best_delay - old;
        p->metrics.delay_error_samples = (int32_t)best_delay - (int32_t)old;
        if (raw_jump > fs / 50u) {
            p->delay_samples = best_delay;
            p->drift_ppm = 0.0f;
            p->drift_credit = 0.0f;
            p->last_best_delay = best_delay;
            p->have_last_best_delay = 1u;
            p->metrics.estimated_drift_ppm = 0.0f;
            p->metrics.delay_jumps++;
            ap_reset_aec_weights(p);
        } else if (p->cfg.enable_clock_drift_compensation) {
            ap_apply_drift_correction(p, best_delay);
        } else {
            uint32_t next = (7u * old + best_delay) / 8u;
            const uint32_t max_slew = fs / 1000u ? fs / 1000u : 1u;
            if (next > old + max_slew) next = old + max_slew;
            else if (old > next + max_slew) next = old - max_slew;
            p->delay_samples = next;
            p->metrics.estimated_drift_ppm = 0.0f;
        }
    }
}

#if !defined(AP_ENABLE_MDF_AEC)
static float ap_dot(const float *a, const float *b, uint32_t n) {
    float s = 0.0f;
    uint32_t i = 0u;
#if AP_HAVE_NEON
    float32x4_t acc = vdupq_n_f32(0.0f);
    for (; i + 4u <= n; i += 4u)
        acc = vmlaq_f32(acc, vld1q_f32(a + i), vld1q_f32(b + i));
    {
        float tmp[4];
        vst1q_f32(tmp, acc);
        s = tmp[0] + tmp[1] + tmp[2] + tmp[3];
    }
#endif
    for (; i < n; ++i) s += a[i] * b[i];
    return s;
}

static void ap_aec(ap_pipeline_t *p, const float *mic, const float *ref,
                   float *out, float *echo_out, float mic_energy,
                   float ref_energy, float *echo_energy_out) {
    uint32_t i;
    float echo_energy = 1.0e-12f;
    const int far_active = ref_energy > 1.0e-7f;
    const int double_talk = far_active && mic_energy > ref_energy * 1.5f;
    const uint32_t taps = p->active_aec_taps;
    const uint32_t woff = p->aec_taps - taps;
    float *w = p->aec_weights + woff;
    p->metrics.double_talk_active = (uint8_t)(double_talk ? 1u : 0u);
    if (!p->cfg.enable_aec || taps == 0u) {
        memcpy(out, mic, p->internal_frame * sizeof(float));
        memset(echo_out, 0, p->internal_frame * sizeof(float));
        *echo_energy_out = 0.0f;
        return;
    }
    for (i = 0u; i < p->internal_frame; ++i) {
        const float x = ref[i];
        const uint32_t pos = p->aec_pos;
        const float *hist;
        float y, e;
        p->aec_history[pos] = x;
        p->aec_history[pos + AP_AEC_CAP] = x;
        hist = p->aec_history + pos + AP_AEC_CAP - taps + 1u;
        y = ap_dot(w, hist, taps);
        e = mic[i] - y;
        echo_out[i] = y;
        out[i] = e;
        echo_energy += y * y;
        if (far_active && !double_talk) {
            p->aec_adapt_phase++;
            if (p->aec_adapt_phase >= p->active_aec_adapt_stride) {
                const float norm = 1.0e-6f + ap_dot(hist, hist, taps);
                const float step = p->cfg.aec_mu * e / norm;
                uint32_t k = 0u;
                p->aec_adapt_phase = 0u;
#if AP_HAVE_NEON
                for (; k + 4u <= taps; k += 4u) {
                    float32x4_t vw = vld1q_f32(w + k);
                    vw = vmlaq_n_f32(vw, vld1q_f32(hist + k), step);
                    vst1q_f32(w + k, vw);
                }
#endif
                for (; k < taps; ++k) w[k] += step * hist[k];
            }
        }
        p->aec_pos = pos + 1u == AP_AEC_CAP ? 0u : pos + 1u;
    }
    *echo_energy_out = echo_energy / (float)p->internal_frame;
}
#else
static void ap_aec(ap_pipeline_t *p, const float *mic, const float *ref,
                   float *out, float *echo_out, float mic_energy,
                   float ref_energy, float *echo_energy_out) {
    ap_mdf_process(p, mic, ref, out, echo_out,
                   mic_energy, ref_energy, echo_energy_out);
}
#endif

static float ap_apply_broadband_res(ap_pipeline_t *p, float *x,
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

static void ap_ns_init(ap_pipeline_t *p) {
    ap_ns_state_t *s = &p->ns;
    const uint32_t win = p->internal_frame * 2u;
    uint32_t i;
    s->nfft = ap_next_pow2(win);
    if (s->nfft > AP_NS_FFT_MAX) s->nfft = AP_NS_FFT_MAX;
    for (i = 0u; i < win; ++i)
        s->window[i] = sinf(AP_PI * ((float)i + 0.5f) / (float)win);
    for (i = 0u; i < AP_NS_BINS_MAX; ++i) s->residual_gain_bins[i] = 1.0f;
    s->noise_rms_dbfs = -90.0f;
}

static void ap_ns_process(ap_pipeline_t *p, const float *in, const float *echo,
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

    for (i = 0u; i < f; ++i) {
        const float previous = s->previous[i];
        const float previous_echo = s->previous_echo[i];
        s->spectrum[i].re = previous * s->window[i];
        s->spectrum[i].im = 0.0f;
        s->spectrum[f + i].re = in[i] * s->window[f + i];
        s->spectrum[f + i].im = 0.0f;
        s->previous[i] = in[i];

        if (freq_res) {
            s->echo_spectrum[i].re = previous_echo * s->window[i];
            s->echo_spectrum[i].im = 0.0f;
            s->echo_spectrum[f + i].re = echo[i] * s->window[f + i];
            s->echo_spectrum[f + i].im = 0.0f;
        }
        s->previous_echo[i] = echo[i];
    }
    memset(s->spectrum + win, 0, (nfft - win) * sizeof(s->spectrum[0]));
    if (freq_res)
        memset(s->echo_spectrum + win, 0,
               (nfft - win) * sizeof(s->echo_spectrum[0]));
    ap_fft(s->spectrum, nfft, 0);
    if (freq_res) ap_fft(s->echo_spectrum, nfft, 0);

    for (k = 0u; k < bins; ++k) {
        const float re = s->spectrum[k].re;
        const float im = s->spectrum[k].im;
        const float power = re * re + im * im + 1.0e-12f;
        float noise = s->noise_psd[k], post, gain, speech;
        float res_gain = 1.0f;

        if (freq_res) {
            const float er = s->echo_spectrum[k].re;
            const float ei = s->echo_spectrum[k].im;
            const float echo_power = er * er + ei * ei;
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

static void ap_agc(ap_pipeline_t *p, float *x, uint32_t n) {
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

static void ap_vad(ap_pipeline_t *p, const float *x, uint32_t n) {
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

ap_config_t ap_config_default(ap_profile_t profile) {
    ap_config_t c;
    memset(&c, 0, sizeof(c));
    c.io_sample_rate_hz = 16000u;
    c.internal_sample_rate_hz = 16000u;
    c.mic_channels = 2u;
    c.mic_spacing_mm = 35.0f;
    c.max_delay_ms = 180u;
    c.initial_delay_ms = 40u;
    c.aec_adapt_stride = 2u;
    c.enable_hpf = 1u;
    c.enable_beamformer = 1u;
    c.enable_delay_tracking = 1u;
    c.enable_clock_drift_compensation = 1u;
    c.enable_aec = 1u;
    c.enable_residual_echo_suppression = 1u;
    c.enable_noise_suppression = 1u;
    c.enable_agc = 1u;
    c.enable_vad = 1u;
    if (profile == AP_PROFILE_CALL) {
        c.aec_filter_ms = 96u;
        c.aec_mu = 0.22f;
        c.ns_floor = 0.12f;
        c.agc_target_dbfs = -20.0f;
        c.limiter_dbfs = -2.0f;
    } else {
        c.aec_filter_ms = 80u;
        c.aec_mu = 0.18f;
        c.ns_floor = 0.18f;
        c.agc_target_dbfs = -18.0f;
        c.limiter_dbfs = -2.0f;
    }
    return c;
}

size_t ap_pipeline_state_size(void) { return sizeof(ap_pipeline_t); }
size_t ap_pipeline_io_frame_samples(const ap_config_t *c) {
    return c ? c->io_sample_rate_hz / 100u : 0u;
}
size_t ap_pipeline_internal_frame_samples(const ap_config_t *c) {
    return c ? c->internal_sample_rate_hz / 100u : 0u;
}
size_t ap_pipeline_frame_samples(const ap_pipeline_t *p) { return p ? p->io_frame : 0u; }
uint32_t ap_pipeline_mic_channels(const ap_pipeline_t *p) {
    return p ? p->cfg.mic_channels : 0u;
}
uint32_t ap_pipeline_sample_rate_hz(const ap_pipeline_t *p) {
    return p ? p->cfg.io_sample_rate_hz : 0u;
}

ap_status_t ap_pipeline_init(void *memory, size_t memory_size,
                             const ap_config_t *c, ap_pipeline_t **out) {
    ap_pipeline_t *p;
    uint32_t taps;
    if (!memory || !c || !out || memory_size < sizeof(ap_pipeline_t)) return AP_ENOMEM;
    if (!ap_supported_io_rate(c->io_sample_rate_hz)) return AP_EINVAL;
    if (c->internal_sample_rate_hz != 8000u && c->internal_sample_rate_hz != 16000u)
        return AP_EINVAL;
    if (c->mic_channels < 1u || c->mic_channels > 2u) return AP_EINVAL;
    if (c->aec_adapt_stride == 0u || c->aec_filter_ms < 20u || c->aec_filter_ms > 120u)
        return AP_EINVAL;
    if (!(c->aec_mu > 0.0f && c->aec_mu <= 1.0f)) return AP_EINVAL;
    if (c->max_delay_ms > 300u || c->initial_delay_ms > c->max_delay_ms)
        return AP_EINVAL;
    if (c->ns_floor < 0.02f || c->ns_floor > 1.0f) return AP_EINVAL;

    p = (ap_pipeline_t *)memory;
    memset(p, 0, sizeof(*p));
    p->cfg = *c;
    p->io_frame = c->io_sample_rate_hz / 100u;
    p->internal_frame = c->internal_sample_rate_hz / 100u;
    taps = c->aec_filter_ms * c->internal_sample_rate_hz / 1000u;
    if (taps > AP_AEC_CAP) taps = AP_AEC_CAP;
    p->aec_taps = taps;
    p->active_aec_taps = taps;
    p->active_aec_adapt_stride = c->aec_adapt_stride;
    p->delay_samples = c->initial_delay_ms * c->internal_sample_rate_hz / 1000u;
    p->hpf_r = expf(-2.0f * AP_PI * 80.0f /
                    (float)c->internal_sample_rate_hz);
    {
        const float sound_mm_s = 343000.0f;
        int max_lag = (int)ceilf(c->mic_spacing_mm *
                                 (float)c->internal_sample_rate_hz / sound_mm_s) + 1;
        if (max_lag > (int)AP_BF_HISTORY) max_lag = (int)AP_BF_HISTORY;
        if (max_lag < 0) max_lag = 0;
        p->bf_max_lag = max_lag;
    }
    p->agc_gain = 1.0f;
    p->agc_target_linear = powf(10.0f, c->agc_target_dbfs / 20.0f);
    p->limiter_linear = powf(10.0f, c->limiter_dbfs / 20.0f);
    p->residual_gain = 1.0f;
    p->vad_noise_rms = 1.0e-3f;
    p->quality = AP_QUALITY_FULL;
    p->metrics.quality = AP_QUALITY_FULL;
    p->metrics.residual_echo_gain = 1.0f;
    p->metrics.active_aec_taps = p->active_aec_taps;
    p->metrics.active_aec_adapt_stride = p->active_aec_adapt_stride;
#if defined(AP_ENABLE_MDF_AEC)
    ap_mdf_init(p);
#else
    p->metrics.aec_backend = AP_AEC_BACKEND_NLMS;
    p->metrics.aec_block_samples = 1u;
    p->metrics.active_aec_partitions = 0u;
#endif
    ap_ns_init(p);
    *out = p;
    return AP_OK;
}

void ap_pipeline_reset(ap_pipeline_t *p) {
    ap_pipeline_t *out = NULL;
    ap_config_t c;
    if (!p) return;
    c = p->cfg;
    (void)ap_pipeline_init(p, sizeof(*p), &c, &out);
}

ap_status_t ap_pipeline_set_quality(ap_pipeline_t *p, ap_quality_t q) {
    uint32_t ms, stride;
    if (!p || q < AP_QUALITY_SAFE || q > AP_QUALITY_FULL) return AP_EINVAL;
    p->quality = q;
    if (q == AP_QUALITY_FULL) {
        ms = p->cfg.aec_filter_ms;
        stride = p->cfg.aec_adapt_stride;
    } else if (q == AP_QUALITY_LITE) {
        ms = p->cfg.aec_filter_ms < 64u ? p->cfg.aec_filter_ms : 64u;
        stride = p->cfg.aec_adapt_stride < 2u ? 2u : p->cfg.aec_adapt_stride;
    } else {
        ms = p->cfg.aec_filter_ms < 40u ? p->cfg.aec_filter_ms : 40u;
        stride = p->cfg.aec_adapt_stride < 4u ? 4u : p->cfg.aec_adapt_stride;
    }
    p->active_aec_taps = ms * p->cfg.internal_sample_rate_hz / 1000u;
    if (p->active_aec_taps > p->aec_taps) p->active_aec_taps = p->aec_taps;
    p->active_aec_adapt_stride = stride;
    p->metrics.quality = q;
    p->metrics.active_aec_taps = p->active_aec_taps;
    p->metrics.active_aec_adapt_stride = stride;
#if defined(AP_ENABLE_MDF_AEC)
    ap_mdf_set_active(p);
#else
    if (p->aec_adapt_phase >= stride) p->aec_adapt_phase = 0u;
#endif
    return AP_OK;
}

ap_status_t ap_pipeline_push_render(ap_pipeline_t *p,
                                    const int16_t *render, size_t samples) {
    uint32_t i;
    if (!p || !render || samples != p->io_frame) return AP_EINVAL;
    ap_resample_input_channel(render, p->io_frame, 1u, 0u,
                              p->work, p->internal_frame);
    for (i = 0u; i < p->internal_frame; ++i) {
        p->render_ring[p->render_total & (AP_RENDER_CAP - 1u)] = p->work[i];
        p->render_total++;
    }
    p->last_render_capture_frame = p->metrics.processed_frames;
    return AP_OK;
}

ap_status_t ap_pipeline_process_capture(ap_pipeline_t *p, const int16_t *mic,
                                        size_t frames, int16_t *output) {
    uint32_t i;
    float mic_e = 1.0e-12f, ref_e = 1.0e-12f;
    float res_e = 1.0e-12f, echo_e = 0.0f;
    const int use_frequency_res = p && p->cfg.enable_residual_echo_suppression &&
                                  p->cfg.enable_noise_suppression &&
                                  p->quality != AP_QUALITY_SAFE;
    if (!p || !mic || !output || frames != p->io_frame) return AP_EINVAL;

    ap_resample_input_channel(mic, p->io_frame, p->cfg.mic_channels,
                              0u, p->mic0, p->internal_frame);
    if (p->cfg.mic_channels == 2u)
        ap_resample_input_channel(mic, p->io_frame, 2u, 1u,
                                  p->mic1, p->internal_frame);
    if (p->cfg.enable_hpf) {
        ap_hpf(p, p->mic0, p->internal_frame, 0u);
        if (p->cfg.mic_channels == 2u)
            ap_hpf(p, p->mic1, p->internal_frame, 1u);
    }
    if (p->cfg.mic_channels == 2u && p->cfg.enable_beamformer &&
        p->quality != AP_QUALITY_SAFE)
        ap_beamform(p, p->mic0, p->mic1, p->mono, p->internal_frame);
    else
        memcpy(p->mono, p->mic0, p->internal_frame * sizeof(float));

    ap_track_delay(p, p->mono);
    ap_get_reference(p, p->delay_samples, p->reference);
    for (i = 0u; i < p->internal_frame; ++i) {
        mic_e += p->mono[i] * p->mono[i];
        ref_e += p->reference[i] * p->reference[i];
    }
    mic_e /= p->internal_frame;
    ref_e /= p->internal_frame;

    ap_aec(p, p->mono, p->reference, p->aec_out, p->echo_estimate,
           mic_e, ref_e, &echo_e);
    for (i = 0u; i < p->internal_frame; ++i)
        res_e += p->aec_out[i] * p->aec_out[i];
    res_e /= p->internal_frame;

    if (!use_frequency_res) {
        p->metrics.residual_echo_gain = ap_apply_broadband_res(
            p, p->aec_out, echo_e, res_e, ref_e, mic_e);
    } else {
        p->metrics.residual_echo_gain = 1.0f;
    }
    ap_ns_process(p, p->aec_out, p->echo_estimate,
                  p->ns_out, ref_e, mic_e);
    ap_agc(p, p->ns_out, p->internal_frame);
    ap_vad(p, p->ns_out, p->internal_frame);

    p->metrics.input_rms_dbfs = 10.0f * log10f(mic_e + 1.0e-18f);
    p->metrics.output_rms_dbfs = ap_rms_dbfs(p->ns_out, p->internal_frame);
    p->metrics.noise_rms_dbfs = p->ns.noise_rms_dbfs;
    if (ref_e > 1.0e-7f && res_e > 1.0e-12f) {
        const float erle = 10.0f * log10f(
            (mic_e + 1.0e-12f) / (res_e + 1.0e-12f));
        p->metrics.erle_db = p->metrics.processed_frames ?
            0.95f * p->metrics.erle_db + 0.05f * erle : erle;
    }
    p->metrics.estimated_delay_ms =
        p->delay_samples * 1000u / p->cfg.internal_sample_rate_hz;
    p->metrics.active_aec_taps = p->active_aec_taps;
    p->metrics.active_aec_adapt_stride = p->active_aec_adapt_stride;
    p->metrics.processed_frames++;
    if (p->metrics.processed_frames > p->last_render_capture_frame + 2u)
        p->metrics.render_underruns++;
    ap_resample_output(p->ns_out, p->internal_frame, output, p->io_frame);
    return AP_OK;
}

void ap_pipeline_get_metrics(const ap_pipeline_t *p, ap_metrics_t *m) {
    if (p && m) *m = p->metrics;
}

uint32_t ap_pipeline_algorithmic_latency_ms(const ap_pipeline_t *p) {
    if (!p) return 0u;
    return p->cfg.enable_noise_suppression ? AP_FRAME_MS : 0u;
}
