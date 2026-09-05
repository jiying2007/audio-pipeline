#include "sync/ap_sync.h"
#include <stdint.h>
#include <string.h>

#define AP_SYNC_MIN_CORRELATION_SQUARED 0.0324f
#define AP_SYNC_MIN_PEAK_RATIO 1.01f
#define AP_SYNC_ROUTE_CONFIRMATIONS 3u

static float ap_sync_clamp(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static float ap_sync_delay_score(const ap_sync_state_t *s,
                                 const float *mic,
                                 uint32_t frame_samples,
                                 uint32_t delay,
                                 uint32_t sample_step);

static uint32_t ap_sync_distance(uint32_t a, uint32_t b) {
    return a > b ? a - b : b - a;
}

static int ap_sync_peak_is_unique(const ap_sync_state_t *s,
                                  const float *mic,
                                  uint32_t frame_samples,
                                  uint32_t max_delay,
                                  uint32_t best_delay,
                                  float best_score,
                                  uint32_t coarse_step,
                                  uint32_t sample_step) {
    float runner_up = 0.0f;
    uint32_t d;
    const uint32_t guard = coarse_step ? coarse_step : 1u;

    if (best_score < AP_SYNC_MIN_CORRELATION_SQUARED) return 0;
    for (d = 0u; d <= max_delay; d += coarse_step) {
        float score;
        if (ap_sync_distance(d, best_delay) <= guard) continue;
        score = ap_sync_delay_score(s, mic, frame_samples, d, sample_step);
        if (score > runner_up) runner_up = score;
    }
    return runner_up <= 1.0e-12f || best_score >= runner_up * AP_SYNC_MIN_PEAK_RATIO;
}

static int ap_sync_confirm_route_candidate(ap_sync_state_t *s,
                                           uint32_t candidate,
                                           uint32_t tolerance) {
    if (s->route_candidate_confirmations == 0u ||
        ap_sync_distance(candidate, s->last_best_delay) > tolerance) {
        s->last_best_delay = candidate;
        s->route_candidate_confirmations = 1u;
        return 0;
    }
    if (s->route_candidate_confirmations < UINT8_MAX)
        s->route_candidate_confirmations++;
    if (s->route_candidate_confirmations < AP_SYNC_ROUTE_CONFIRMATIONS) return 0;
    s->route_candidate_delay = s->last_best_delay;
    s->route_candidate_confirmations = 0u;
    return 1;
}

void ap_sync_init(ap_sync_state_t *s, uint32_t initial_delay_samples) {
    memset(s, 0, sizeof(*s));
    s->initial_delay_samples = initial_delay_samples;
    s->delay_samples = initial_delay_samples;
    s->route_candidate_delay = initial_delay_samples;
}

void ap_sync_reset(ap_sync_state_t *s) {
    const uint32_t initial = s->initial_delay_samples;
    ap_sync_init(s, initial);
}

void ap_sync_push_render(ap_sync_state_t *s, const float *render,
                         uint32_t samples, uint64_t processed_frames) {
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

int ap_sync_get_reference(ap_sync_state_t *s, uint32_t frame_samples, float *out) {
    const int64_t start = (int64_t)s->render_total -
                          (int64_t)frame_samples - (int64_t)s->delay_samples;
    const float frac = ap_sync_clamp(s->drift_credit, -0.999f, 0.999f);
    uint32_t i;

    if (frac >= 0.0f) {
        for (i = 0u; i < frame_samples; ++i) {
            const int64_t at = start + (int64_t)i;
            const float current = ap_sync_render_absolute(s, at);
            const float previous = ap_sync_render_absolute(s, at - 1);
            out[i] = current + frac * (previous - current);
        }
    } else {
        const float advance = -frac;
        for (i = 0u; i < frame_samples; ++i) {
            const int64_t at = start + (int64_t)i;
            const float current = ap_sync_render_absolute(s, at);
            const float next = ap_sync_render_absolute(s, at + 1);
            out[i] = current + advance * (next - current);
        }
    }
    return start < 0;
}

static float ap_sync_delay_score(const ap_sync_state_t *s, const float *mic,
                                 uint32_t frame_samples, uint32_t delay,
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
    return (xy * xy) / (xx * yy);
}

static int ap_sync_select_incumbent_peak(const ap_sync_state_t *s,
                                         const float *mic,
                                         uint32_t frame_samples,
                                         uint32_t max_delay,
                                         uint32_t coarse_step,
                                         uint32_t sample_step,
                                         uint32_t *selected_delay,
                                         float *selected_score) {
    const uint32_t radius = 2u * coarse_step;
    const uint32_t anchor = s->route_candidate_delay;
    uint32_t local_delay = anchor;
    float local_score = 0.0f;
    int found = 0;
    uint32_t d;

    for (d = 0u; d <= max_delay; d += coarse_step) {
        float score, left = -1.0f, right = -1.0f;
        if (ap_sync_distance(d, anchor) > radius) continue;
        score = ap_sync_delay_score(s, mic, frame_samples, d, sample_step);
        if (score < AP_SYNC_MIN_CORRELATION_SQUARED) continue;
        if (d >= coarse_step)
            left = ap_sync_delay_score(s, mic, frame_samples, d - coarse_step, sample_step);
        if (d + coarse_step <= max_delay)
            right = ap_sync_delay_score(s, mic, frame_samples, d + coarse_step, sample_step);
        if (score < left || score < right) continue;
        if (!found || score > local_score || (score == local_score && d < local_delay)) {
            found = 1;
            local_delay = d;
            local_score = score;
        }
    }
    if (!found) return 0;
    *selected_delay = local_delay;
    *selected_score = local_score;
    return 1;
}

static void ap_sync_apply_drift(ap_sync_state_t *s, uint32_t best_delay,
                                uint32_t sample_rate_hz, uint32_t max_delay_ms,
                                ap_sync_event_t *event) {
    int32_t error = (int32_t)best_delay - (int32_t)s->delay_samples;
    uint32_t corrections = 0u;
    if (s->have_last_best_delay) {
        const int32_t delta = (int32_t)best_delay - (int32_t)s->last_best_delay;
        float raw_ppm = (float)delta * 10000000.0f / (float)sample_rate_hz;
        raw_ppm = ap_sync_clamp(raw_ppm, -2000.0f, 2000.0f);
        s->drift_ppm = 0.95f * s->drift_ppm + 0.05f * raw_ppm;
    }
    s->last_best_delay = best_delay;
    s->have_last_best_delay = 1u;
    s->drift_credit += s->drift_ppm * (float)sample_rate_hz / 10000000.0f;
    if (error > 4)
        s->drift_credit += ap_sync_clamp((float)error * 0.05f, 0.0f, 0.5f);
    else if (error < -4)
        s->drift_credit += ap_sync_clamp((float)error * 0.05f, -0.5f, 0.0f);
    while (s->drift_credit >= 1.0f &&
           s->delay_samples < max_delay_ms * sample_rate_hz / 1000u &&
           corrections < 4u) {
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

void ap_sync_track_delay(ap_sync_state_t *s, const float *mic,
                         uint32_t frame_samples, uint32_t sample_rate_hz,
                         uint32_t max_delay_ms, int enable_delay_tracking,
                         int enable_clock_drift_compensation,
                         ap_sync_event_t *event) {
    const uint32_t max_delay = max_delay_ms * sample_rate_hz / 1000u;
    const uint32_t coarse_step = sample_rate_hz / 500u ? sample_rate_hz / 500u : 1u;
    const uint32_t sample_step = 4u;
    float best = 0.0f;
    uint32_t best_delay = s->delay_samples, d;
    int used_incumbent_peak;
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
    used_incumbent_peak = ap_sync_select_incumbent_peak(
        s, mic, frame_samples, max_delay, coarse_step, sample_step, &best_delay, &best);
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
    if (best < AP_SYNC_MIN_CORRELATION_SQUARED) {
        s->route_candidate_confirmations = 0u;
        return;
    }
    {
        const uint32_t old = s->delay_samples;
        const uint32_t raw_jump = old > best_delay ? old - best_delay : best_delay - old;
        event->delay_observed = 1u;
        event->delay_error_samples = (int32_t)best_delay - (int32_t)old;
        if (raw_jump > sample_rate_hz / 50u) {
            if (!ap_sync_confirm_route_candidate(s, best_delay, coarse_step)) {
                event->delay_observed = 0u;
                return;
            }
            best_delay = s->route_candidate_delay;
            s->delay_samples = best_delay;
            s->drift_ppm = 0.0f;
            s->drift_credit = 0.0f;
            s->last_best_delay = best_delay;
            s->have_last_best_delay = 1u;
            event->route_jump = 1u;
        } else if (!used_incumbent_peak &&
                   !ap_sync_peak_is_unique(s, mic, frame_samples, max_delay,
                                           best_delay, best, coarse_step, sample_step)) {
            s->route_candidate_confirmations = 0u;
            event->delay_observed = 0u;
        } else if (enable_clock_drift_compensation) {
            s->route_candidate_confirmations = 0u;
            ap_sync_apply_drift(s, best_delay, sample_rate_hz, max_delay_ms, event);
        } else {
            s->route_candidate_confirmations = 0u;
            uint32_t next = (7u * old + best_delay) / 8u;
            const uint32_t max_slew = sample_rate_hz / 1000u ?
                                      sample_rate_hz / 1000u : 1u;
            if (next > old + max_slew) next = old + max_slew;
            else if (old > next + max_slew) next = old - max_slew;
            s->delay_samples = next;
            s->drift_ppm = 0.0f;
            s->drift_credit = 0.0f;
        }
    }
}

int ap_sync_observe_timestamps(ap_sync_state_t *s,
                               uint64_t capture_timestamp_ns,
                               uint64_t render_timestamp_ns,
                               uint32_t sample_rate_hz,
                               uint32_t max_delay_ms,
                               ap_sync_event_t *event) {
    uint64_t delta_ns, samples64;
    uint32_t observed, old, jump;
    memset(event, 0, sizeof(*event));
    if (!capture_timestamp_ns || !render_timestamp_ns ||
        capture_timestamp_ns <= render_timestamp_ns)
        return 0;
    delta_ns = capture_timestamp_ns - render_timestamp_ns;
    samples64 = (delta_ns * (uint64_t)sample_rate_hz + 500000000ull) / 1000000000ull;
    if (samples64 > (uint64_t)max_delay_ms * sample_rate_hz / 1000u ||
        samples64 >= AP_RENDER_CAP)
        return 0;
    observed = (uint32_t)samples64;
    old = s->delay_samples;
    jump = old > observed ? old - observed : observed - old;
    s->delay_samples = observed;
    s->route_candidate_delay = observed;
    s->last_best_delay = observed;
    s->have_last_best_delay = 1u;
    s->drift_ppm = 0.0f;
    s->drift_credit = 0.0f;
    s->route_candidate_confirmations = 0u;
    event->timestamp_observed = 1u;
    event->delay_observed = 1u;
    event->delay_error_samples = (int32_t)observed - (int32_t)old;
    event->route_jump = (uint8_t)(jump > sample_rate_hz / 50u ? 1u : 0u);
    return 1;
}

int ap_sync_note_capture(const ap_sync_state_t *s, uint64_t processed_frames) {
    return processed_frames > s->last_render_capture_frame + 2u;
}

void ap_sync_get_status(const ap_sync_state_t *s, ap_sync_status_t *status) {
    status->estimated_drift_ppm = s->drift_ppm;
    status->delay_samples = s->delay_samples;
}
