#include "frontend/ap_frontend.h"
#include "dsp/ap_dsp.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

#define AP_BF_SCORE_ALPHA 0.25f
#define AP_BF_FALLBACK_ENTER_COHERENCE 0.980f
#define AP_BF_FALLBACK_ENTER_RATIO 0.45f
#define AP_BF_FALLBACK_RECOVER_COHERENCE 0.988f
#define AP_BF_FALLBACK_RECOVER_RATIO 0.52f
#define AP_BF_FALLBACK_RECOVER_UPDATES 8u
#define AP_BF_FALLBACK_MIN_SCORE_UPDATES 1u
#define AP_BF_FALLBACK_STRONG_WEIGHT 0.75f
#define AP_BF_FALLBACK_WEAK_WEIGHT 0.25f
#define AP_BF_HARD_FAULT_MIN_RATIO 0.25f
#define AP_BF_HARD_FAULT_ROUGHNESS_RATIO 0.40f

static float ap_beamformer_clampf(float value, float lo, float hi) {
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

static float ap_beamformer_roughness(const float *x, uint32_t n) {
    float energy = 1.0e-12f;
    float diff_energy = 1.0e-12f;
    uint32_t i;
    if (n == 0u) return 1.0f;
    energy += x[0] * x[0];
    for (i = 1u; i < n; ++i) {
        const float delta = x[i] - x[i - 1u];
        energy += x[i] * x[i];
        diff_energy += delta * delta;
    }
    return diff_energy / energy;
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
    s->counter = 3u;
    s->fallback_gain = 1.0f;
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
                                      float *coherence,
                                      float *best_aa,
                                      float *best_bb,
                                      float *best_xy) {
    const int max_lag = s->max_lag;
    float aa_by_lag[AP_BF_LAG_SCORE_COUNT];
    float bb_by_lag[AP_BF_LAG_SCORE_COUNT];
    float xy_by_lag[AP_BF_LAG_SCORE_COUNT];
    int lag;
    int best = s->lag;
    float best_score = -1.0e30f;

    if (coherence) *coherence = 0.0f;
    if (best_aa) *best_aa = 1.0e-12f;
    if (best_bb) *best_bb = 1.0e-12f;
    if (best_xy) *best_xy = 0.0f;
    if (max_lag < 1) return 0;

    memset(aa_by_lag, 0, sizeof(aa_by_lag));
    memset(bb_by_lag, 0, sizeof(bb_by_lag));
    memset(xy_by_lag, 0, sizeof(xy_by_lag));

    for (lag = -max_lag; lag <= max_lag; ++lag) {
        const uint32_t index = (uint32_t)(lag + (int)AP_BF_HISTORY);
        float xy = 0.0f;
        float aa = 1.0e-12f;
        float bb = 1.0e-12f;
        float score;
        uint32_t i;
        for (i = 0u; i < n; i += 2u) {
            float x;
            float y;
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
        score = xy / sqrtf(aa * bb);
        aa_by_lag[index] = aa;
        bb_by_lag[index] = bb;
        xy_by_lag[index] = xy;
        if (s->score_updates == 0u) {
            s->lag_score[index] = score;
        } else {
            s->lag_score[index] += AP_BF_SCORE_ALPHA * (score - s->lag_score[index]);
        }
    }

    if (s->score_updates != UINT32_MAX) s->score_updates++;
    for (lag = -max_lag; lag <= max_lag; ++lag) {
        const uint32_t index = (uint32_t)(lag + (int)AP_BF_HISTORY);
        const float score = s->lag_score[index];
        if (score > best_score) {
            best_score = score;
            best = lag;
        }
    }

    {
        const uint32_t index = (uint32_t)(best + (int)AP_BF_HISTORY);
        if (coherence) *coherence = best_score;
        if (best_aa) *best_aa = aa_by_lag[index];
        if (best_bb) *best_bb = bb_by_lag[index];
        if (best_xy) *best_xy = xy_by_lag[index];
    }
    return best_score > 0.15f ? best : s->lag;
}

static void ap_beamformer_update_fallback(ap_beamformer_state_t *s,
                                          float coherence,
                                          float aa,
                                          float bb,
                                          float xy,
                                          float roughness_a,
                                          float roughness_b) {
    const float high_energy = aa > bb ? aa : bb;
    const float low_energy = aa > bb ? bb : aa;
    const float ratio = sqrtf(low_energy / fmaxf(high_energy, 1.0e-12f));
    const int severe = s->score_updates >= AP_BF_FALLBACK_MIN_SCORE_UPDATES &&
                       coherence < AP_BF_FALLBACK_ENTER_COHERENCE &&
                       ratio < AP_BF_FALLBACK_ENTER_RATIO;
    const int recovered = coherence > AP_BF_FALLBACK_RECOVER_COHERENCE ||
                          ratio > AP_BF_FALLBACK_RECOVER_RATIO;
    const uint32_t energy_strong_channel = aa >= bb ? 0u : 1u;
    const float strong_roughness = energy_strong_channel == 0u ? roughness_a : roughness_b;
    const float weak_roughness = energy_strong_channel == 0u ? roughness_b : roughness_a;
    const int hard_contamination = severe &&
                                   ratio > AP_BF_HARD_FAULT_MIN_RATIO &&
                                   strong_roughness < AP_BF_HARD_FAULT_ROUGHNESS_RATIO *
                                                      fmaxf(weak_roughness, 1.0e-12f);
    float projection;
    float normal_coherent_gain;
    float fallback_coherent_gain;

    if (energy_strong_channel == 0u)
        projection = xy / fmaxf(aa, 1.0e-12f);
    else
        projection = xy / fmaxf(bb, 1.0e-12f);
    projection = ap_beamformer_clampf(projection, 0.0f, 1.0f);
    normal_coherent_gain = 0.5f * (1.0f + projection);
    fallback_coherent_gain = AP_BF_FALLBACK_STRONG_WEIGHT +
                             AP_BF_FALLBACK_WEAK_WEIGHT * projection;

    if (!s->fallback_active) {
        if (!severe) return;
        s->fallback_active = 1u;
        s->fallback_hard_fault = hard_contamination ? 1u : 0u;
        s->fallback_strong_channel = hard_contamination ?
                                     1u - energy_strong_channel : energy_strong_channel;
        s->fallback_recovery_count = 0u;
        s->fallback_lag = s->lag;
        s->fallback_gain = hard_contamination ? 1.0f :
                           normal_coherent_gain /
                           fmaxf(fallback_coherent_gain, 1.0e-12f);
        return;
    }

    if (hard_contamination && !s->fallback_hard_fault) {
        s->fallback_hard_fault = 1u;
        s->fallback_strong_channel = 1u - energy_strong_channel;
        s->fallback_recovery_count = 0u;
        s->fallback_lag = s->lag;
        s->fallback_gain = 1.0f;
    }

    if (recovered) {
        if (s->fallback_recovery_count < AP_BF_FALLBACK_RECOVER_UPDATES)
            s->fallback_recovery_count++;
        if (s->fallback_recovery_count >= AP_BF_FALLBACK_RECOVER_UPDATES) {
            s->fallback_active = 0u;
            s->fallback_hard_fault = 0u;
            s->fallback_recovery_count = 0u;
            s->fallback_gain = 1.0f;
        }
    } else {
        s->fallback_recovery_count = 0u;
    }
}

void ap_beamformer_process(ap_beamformer_state_t *s,
                           int track_direction,
                           float *a,
                           float *b,
                           float *out,
                           uint32_t n) {
    uint32_t i;
    if (track_direction && (++s->counter & 3u) == 0u) {
        float coherence = 0.0f;
        float aa = 1.0e-12f;
        float bb = 1.0e-12f;
        float xy = 0.0f;
        const float roughness_a = ap_beamformer_roughness(a, n);
        const float roughness_b = ap_beamformer_roughness(b, n);
        const int lag = ap_beamformer_estimate_lag(s, a, b, n,
                                                   &coherence, &aa, &bb, &xy);
        if (lag > s->lag) s->lag++;
        else if (lag < s->lag) s->lag--;
        ap_beamformer_update_fallback(s, coherence, aa, bb, xy,
                                      roughness_a, roughness_b);
    } else if (!track_direction) {
        s->fallback_active = 0u;
        s->fallback_hard_fault = 0u;
        s->fallback_recovery_count = 0u;
        s->fallback_gain = 1.0f;
    }

    for (i = 0u; i < n; ++i) {
        const int output_lag = s->fallback_active ? s->fallback_lag : s->lag;
        float x;
        float y;
        if (output_lag >= 0) {
            x = a[i];
            y = ap_beamformer_past_sample(s, b, 1u, (int)i - output_lag);
        } else {
            x = ap_beamformer_past_sample(s, a, 0u, (int)i + output_lag);
            y = b[i];
        }
        if (s->fallback_active) {
            const float strong = s->fallback_strong_channel == 0u ? x : y;
            if (s->fallback_hard_fault) {
                out[i] = strong;
            } else {
                const float weak = s->fallback_strong_channel == 0u ? y : x;
                out[i] = s->fallback_gain *
                         (AP_BF_FALLBACK_STRONG_WEIGHT * strong +
                          AP_BF_FALLBACK_WEAK_WEIGHT * weak);
            }
        } else {
            out[i] = 0.5f * (x + y);
        }
    }
    for (i = 0u; i < AP_BF_HISTORY; ++i) {
        const uint32_t src = n > AP_BF_HISTORY ? n - AP_BF_HISTORY + i : i;
        s->history[0][i] = src < n ? a[src] : 0.0f;
        s->history[1][i] = src < n ? b[src] : 0.0f;
    }
}
