#include "sync/ap_sync.h"
#include "dsp/ap_dsp.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

void ap_sync_init(ap_sync_state_t *s, uint32_t initial_delay_samples) {
    memset(s, 0, sizeof(*s));
    s->delay_samples = initial_delay_samples;
}

void ap_sync_push_render(ap_sync_state_t *s,
                         const float *render,
                         uint32_t samples,
                         uint64_t processed_frames) {
    uint32_t i;
    for (i = 0u; i < samples; ++i) {
        s->render_ring[s->render_total & (AP_RENDER_CAP - 1u)] = render[i];
        s->render_total++;
    }
    s->last_render_capture_frame = processed_frames;
}

static float ap_sync_render_absolute(const ap_sync_state_t *s, int64_t index) {
    const int64_t oldest = (int64_t)s->render_total - (int64_t)AP_RENDER_CAP;
    if (index < 0 || index >= (int64_t)s->render_total || index < oldest) return 0.0f;
    return s->render_ring[(uint64_t)index & (AP_RENDER_CAP - 1u)];
}

int ap_sync_get_reference(ap_sync_state_t *s,
                          uint32_t frame_samples,
                          float *out) {
    const int64_t start = (int64_t)s->render_total -
                          (int64_t)frame_samples - (int64_t)s->delay_samples;
    uint32_t i;
    for (i = 0u; i < frame_samples; ++i)
        out[i] = ap_sync_render_absolute(s, start + (int64_t)i);
    return start < 0;
}

static float ap_sync_delay_score(const ap_sync_state_t *s,
                                 const float *mic,
                                 uint32_t frame_samples,
                                 uint32_t delay,
                                 uint32_t sample_step) {
    const int64_t start = (int64_t)s->render_total -
                          (int64_t)frame_samples - (int64_t)delay;
    float xy = 0.0f, xx = 1.0e-12f, yy = 1.0e-12f;
    uint32_t i;
    for (i = 0u; i < frame_samples; i += sample_step) {
        const float x = ap_sync_render_absolute(s, start + (int64_t)i);
        const float y = mic[i];
        xy += x * y;
        xx += x * x;
        yy += y * y;
    }
    return fabsf(xy / sqrtf(xx * yy));
}

static void ap_sync_apply_drift(ap_sync_state_t *s,
                                uint32_t best_delay,
                                uint32_t sample_rate_hz,
                                uint32_t max_delay_ms,
                                ap_sync_event_t *event) {
    int32_t error = (int32_t)best_delay - (int32_t)s->delay_samples;
    uint32_t corrections = 0u;

    if (s->have_last_best_delay) {
        const int32_t delta = (int32_t)best_delay - (int32_t)s->last_best_delay;
        float raw_ppm = (float)delta * 10000000.0f / (float)sample_rate_hz;
        raw_ppm = ap_clampf(raw_ppm, -2000.0f, 2000.0f);
        s->drift_ppm = 0.95f * s->drift_ppm + 0.05f * raw_ppm;
    }
    s->last_best_delay = best_delay;
    s->have_last_best_delay = 1u;

    s->drift_credit += s->drift_ppm * (float)sample_rate_hz / 10000000.0f;
    if (error > 4) s->drift_credit += ap_clampf((float)error * 0.05f, 0.0f, 0.5f);
    else if (error < -4) s->drift_credit += ap_clampf((float)error * 0.05f, -0.5f, 0.0f);

    while (s->drift_credit >= 1.0f && s->delay_samples <
           max_delay_ms * sample_rate_hz / 1000u && corrections < 4u) {
        s->delay_samples++;
        s->drift_credit -= 1.0f;
        event->reference_sample_slips++;
        corrections++;
    }
    while (s->drift_credit <= -1.0f && s->delay_samples > 0u && corrections < 4u) {
        s->delay_samples--;
        s->drift_credit += 1.0f;
        event->reference_sample_slips++;
        corrections++;
    }
}

void ap_sync_track_delay(ap_sync_state_t *s,
                         const float *mic,
                         uint32_t frame_samples,
                         uint32_t sample_rate_hz,
                         uint32_t max_delay_ms,
                         int enable_delay_tracking,
                         int enable_clock_drift_compensation,
                         ap_sync_event_t *event) {
    const uint32_t max_delay = max_delay_ms * sample_rate_hz / 1000u;
    const uint32_t coarse_step = sample_rate_hz / 500u ? sample_rate_hz / 500u : 1u;
    const uint32_t sample_step = 4u;
    float best = 0.0f;
    uint32_t best_delay = s->delay_samples, d;

    memset(event, 0, sizeof(*event));
    if (!enable_delay_tracking ||
        s->render_total < (uint64_t)(max_delay + frame_samples)) return;
    if (++s->delay_update_counter < 10u) return;
    s->delay_update_counter = 0u;

    for (d = 0u; d <= max_delay; d += coarse_step) {
        const float score = ap_sync_delay_score(s, mic, frame_samples, d, sample_step);
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
            const float score = ap_sync_delay_score(s, mic, frame_samples, d, sample_step);
            if (score > best) {
                best = score;
                best_delay = d;
            }
        }
    }

    if (best > 0.18f) {
        const uint32_t old = s->delay_samples;
        const uint32_t raw_jump = old > best_delay ? old - best_delay : best_delay - old;
        event->delay_observed = 1u;
        event->delay_error_samples = (int32_t)best_delay - (int32_t)old;
        if (raw_jump > sample_rate_hz / 50u) {
            s->delay_samples = best_delay;
            s->drift_ppm = 0.0f;
            s->drift_credit = 0.0f;
            s->last_best_delay = best_delay;
            s->have_last_best_delay = 1u;
            event->route_jump = 1u;
        } else if (enable_clock_drift_compensation) {
            ap_sync_apply_drift(s, best_delay, sample_rate_hz, max_delay_ms, event);
        } else {
            uint32_t next = (7u * old + best_delay) / 8u;
            const uint32_t max_slew = sample_rate_hz / 1000u ?
                                      sample_rate_hz / 1000u : 1u;
            if (next > old + max_slew) next = old + max_slew;
            else if (old > next + max_slew) next = old - max_slew;
            s->delay_samples = next;
            s->drift_ppm = 0.0f;
        }
    }
}

int ap_sync_note_capture(const ap_sync_state_t *s, uint64_t processed_frames) {
    return processed_frames > s->last_render_capture_frame + 2u;
}

void ap_sync_get_status(const ap_sync_state_t *s, ap_sync_status_t *status) {
    status->estimated_drift_ppm = s->drift_ppm;
    status->delay_samples = s->delay_samples;
}
