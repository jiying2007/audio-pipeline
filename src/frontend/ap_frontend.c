#include "ap_internal.h"
#include <math.h>
#include <stdint.h>

void ap_frontend_init(ap_pipeline_t *p) {
    const float sound_mm_s = 343000.0f;
    int max_lag;
    p->hpf_r = expf(-2.0f * AP_PI * 80.0f /
                    (float)p->cfg.internal_sample_rate_hz);
    max_lag = (int)ceilf(p->cfg.mic_spacing_mm *
                         (float)p->cfg.internal_sample_rate_hz / sound_mm_s) + 1;
    if (max_lag > (int)AP_BF_HISTORY) max_lag = (int)AP_BF_HISTORY;
    if (max_lag < 0) max_lag = 0;
    p->bf_max_lag = max_lag;
}

void ap_hpf_process(ap_pipeline_t *p, float *x, uint32_t n, uint32_t ch) {
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

void ap_beamform(ap_pipeline_t *p, float *a, float *b, float *out, uint32_t n) {
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
