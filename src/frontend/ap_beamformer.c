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
#define AP_BF_FALLBACK_MIN_SCORE_UPDATES 4u

static float ap_beamformer_clampf(float value, float lo, float hi) {
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
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
                                          float xy) {
    const float high_energy = aa > bb ? aa : bb;
    const float low_energy = aa > bb ? bb : aa;
    const float ratio = sqrtf(low_energy / fmaxf(high_energy, 1.0e-12f));
    const int severe = s->score_updates >= AP_BF_FALLBACK_MIN_SCORE_UPDATES &&
                       coherence < AP_BF_FALLBACK_ENTER_COHERENCE &&
                       ratio < AP_BF_FALLBACK_ENTER_RATIO;
    const int recovered = coherence > AP_BF_FALLBACK_RECOVER_COHERENCE ||
                          ratio > AP_BF_FALLBACK_RECOVER_RATIO;
    const uint32_t strong_channel = aa >= bb ? 0u : 1u;
    float projection;
    float target_gain;

    if (strong_channel == 0u)
        projection = xy / fmaxf(aa, 1.0e-12f);
    else
        projection = xy / fmaxf(bb, 1.0e-12f);
    projection = ap_beamformer_clampf(projection, 0.0f, 1.0f);
    target_gain = 0.5f * (1.0f + projection);

    if (!s->fallback_active) {
        if (!severe) return;
        s->fallback_active = 1u;
        s->fallback_strong_channel = strong_channel;
        s->fallback_recovery_count = 0u;
        s->fallback_lag = s->lag;
        s->fallback_gain = target_gain;
        return;
    }

    if (recovered) {
        if (s->fallback_recovery_count < AP_BF_FALLBACK_RECOVER_UPDATES)
            s->fallback_recovery_count++;
        if (s->fallback_recovery_count >= AP_BF_FALLBACK_RECOVER_UPDATES) {
            s->fallback_active = 0u;
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
        const int lag = ap_beamformer_estimate_lag(s, a, b, n,
                                                   &coherence, &aa, &bb, &xy);
        if (lag > s->lag) s->lag++;
        else if (lag < s->lag) s->lag--;
        ap_beamformer_update_fallback(s, coherence, aa, bb, xy);
    } else if (!track_direction) {
        s->fallback_active = 0u;
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
            out[i] = s->fallback_gain * strong;
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
