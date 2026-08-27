#include "ap_internal.h"
#include <math.h>
#include <stdint.h>

static float ap_render_absolute(const ap_pipeline_t *p, int64_t index) {
    const int64_t oldest = (int64_t)p->render_total - (int64_t)AP_RENDER_CAP;
    if (index < 0 || index >= (int64_t)p->render_total || index < oldest) return 0.0f;
    return p->render_ring[(uint64_t)index & (AP_RENDER_CAP - 1u)];
}

void ap_sync_get_reference(ap_pipeline_t *p, uint32_t delay, float *out) {
    const int64_t start = (int64_t)p->render_total -
                          (int64_t)p->internal_frame - (int64_t)delay;
    uint32_t i;
    if (start < 0) p->metrics.render_underruns++;
    for (i = 0u; i < p->internal_frame; ++i)
        out[i] = ap_render_absolute(p, start + (int64_t)i);
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
        float raw_ppm = (float)delta * 10000000.0f / (float)fs;
        raw_ppm = ap_clampf(raw_ppm, -2000.0f, 2000.0f);
        p->drift_ppm = 0.95f * p->drift_ppm + 0.05f * raw_ppm;
    }
    p->last_best_delay = best_delay;
    p->have_last_best_delay = 1u;
    p->metrics.estimated_drift_ppm = p->drift_ppm;

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

void ap_sync_track_delay(ap_pipeline_t *p, const float *mic) {
    const uint32_t fs = p->cfg.internal_sample_rate_hz;
    const uint32_t max_delay = p->cfg.max_delay_ms * fs / 1000u;
    const uint32_t coarse_step = fs / 500u ? fs / 500u : 1u;
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
            ap_aec_backend_reset(p, 1);
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
