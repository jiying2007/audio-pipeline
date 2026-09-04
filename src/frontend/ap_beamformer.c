#include "frontend/ap_frontend.h"
#include "dsp/ap_dsp.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

static float ap_beamformer_clampf(float x, float lo, float hi) {
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
}

void ap_beamformer_init(ap_beamformer_state_t *s,
                        uint32_t sample_rate_hz,
                        float mic_spacing_mm) {
    const float sound_mm_s = 343000.0f;
    int max_lag;
    memset(s, 0, sizeof(*s));
    max_lag = (int)ceilf(mic_spacing_mm * (float)sample_rate_hz / sound_mm_s) + 1;
    if (max_lag > (int)AP_BF_HISTORY) max_lag = (int)AP_BF_HISTORY;
    if (max_lag < 0) max_lag = 0;
    s->max_lag = max_lag;
    s->weight_a = 0.5f;
}

static float ap_beamformer_past_sample(const ap_beamformer_state_t *s,
                                       const float *x,
                                       uint32_t ch,
                                       int index) {
    if (index >= 0) return x[(uint32_t)index];
    if (index < -(int)AP_BF_HISTORY) return 0.0f;
    return s->history[ch][AP_BF_HISTORY + index];
}

static int ap_beamformer_estimate_lag(ap_beamformer_state_t *s,
                                      const float *a,
                                      const float *b,
                                      uint32_t n,
                                      float *score_out,
                                      float *energy_a_out,
                                      float *energy_b_out) {
    const int max_lag = s->max_lag;
    int lag, best = 0;
    float best_score = -1.0e30f;
    float best_aa = 1.0e-12f;
    float best_bb = 1.0e-12f;
    if (max_lag < 1) {
        *score_out = 0.0f;
        *energy_a_out = best_aa;
        *energy_b_out = best_bb;
        return 0;
    }
    for (lag = -max_lag; lag <= max_lag; ++lag) {
        float xy = 0.0f, aa = 1.0e-12f, bb = 1.0e-12f;
        uint32_t i;
        for (i = 0u; i < n; i += 2u) {
            float x, y;
            if (lag >= 0) {
                x = a[i];
                y = ap_beamformer_past_sample(s, b, 1u, (int)i - lag);
            } else {
                x = ap_beamformer_past_sample(s, a, 0u, (int)i + lag);
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
                best_aa = aa;
                best_bb = bb;
            }
        }
    }
    *score_out = best_score;
    *energy_a_out = best_aa;
    *energy_b_out = best_bb;
    return best_score > 0.15f ? best : s->lag;
}

static float ap_beamformer_reliability_weight(float score,
                                               float energy_a,
                                               float energy_b) {
    const float min_weight = 0.25f;
    const float max_weight = 0.75f;
    const float coherence_enable = 0.80f;
    const float coherence_nominal = 0.995f;
    const float coherence_full_weight = 0.960f;
    float rms_a, rms_b, level_weight, reliability_need;

    if (!isfinite(score) || !isfinite(energy_a) || !isfinite(energy_b) ||
        energy_a <= 0.0f || energy_b <= 0.0f || score < coherence_enable)
        return 0.5f;

    rms_a = sqrtf(energy_a);
    rms_b = sqrtf(energy_b);
    if (!isfinite(rms_a) || !isfinite(rms_b) || rms_a + rms_b <= 1.0e-9f)
        return 0.5f;

    level_weight = ap_beamformer_clampf(rms_a / (rms_a + rms_b),
                                        min_weight, max_weight);
    reliability_need = ap_beamformer_clampf(
        (coherence_nominal - score) /
            (coherence_nominal - coherence_full_weight),
        0.0f, 1.0f);
    return 0.5f + reliability_need * (level_weight - 0.5f);
}

void ap_beamformer_process(ap_beamformer_state_t *s,
                           int track_direction,
                           float *a,
                           float *b,
                           float *out,
                           uint32_t n) {
    uint32_t i;
    if (track_direction && (++s->counter & 3u) == 0u) {
        float score, energy_a, energy_b;
        const int lag = ap_beamformer_estimate_lag(
            s, a, b, n, &score, &energy_a, &energy_b);
        const float target_weight = ap_beamformer_reliability_weight(
            score, energy_a, energy_b);
        if (lag > s->lag) s->lag++;
        else if (lag < s->lag) s->lag--;
        s->weight_a += 0.25f * (target_weight - s->weight_a);
        s->weight_a = ap_beamformer_clampf(s->weight_a, 0.25f, 0.75f);
    }
    for (i = 0u; i < n; ++i) {
        float x, y;
        const float weight_a = track_direction ? s->weight_a : 0.5f;
        if (s->lag >= 0) {
            x = a[i];
            y = ap_beamformer_past_sample(s, b, 1u, (int)i - s->lag);
        } else {
            x = ap_beamformer_past_sample(s, a, 0u, (int)i + s->lag);
            y = b[i];
        }
        out[i] = weight_a * x + (1.0f - weight_a) * y;
    }
    for (i = 0u; i < AP_BF_HISTORY; ++i) {
        const uint32_t src = n > AP_BF_HISTORY ? n - AP_BF_HISTORY + i : i;
        s->history[0][i] = src < n ? a[src] : 0.0f;
        s->history[1][i] = src < n ? b[src] : 0.0f;
    }
}
