#include "array_native.h"
#include <math.h>
#include <string.h>

#ifdef __FAST_MATH__
#error "FE array research requires finite-input checks; fast math is not qualified"
#endif

#define FE_ARRAY_MAGIC UINT32_C(0x46454131)
struct fe_array {
    uint32_t magic, rate, count, mask, delay, cursor;
    fe_array_interpolation interpolation;
    uint32_t channel[FE_ARRAY_MAX_MICS];
    uint32_t offset[FE_ARRAY_MAX_MICS][4];
    float weight[FE_ARRAY_MAX_MICS][4];
    float gain[FE_ARRAY_MAX_MICS];
    double compensation[FE_ARRAY_MAX_MICS];
    uint64_t samples;
    double relative[FE_ARRAY_MAX_MICS][3], calibration_latency[FE_ARRAY_MAX_MICS];
    double direction[3], target_direction[3], target_compensation[FE_ARRAY_MAX_MICS];
    uint32_t next_offset[FE_ARRAY_MAX_MICS][4];
    float next_weight[FE_ARRAY_MAX_MICS][4];
    uint32_t transition_total, transition_done;
    uint64_t steering_accepted, steering_completed, steering_cancelled;
    float history[];
};

static int count_ok(uint32_t n) { return n == 1u || n == 2u || n == 4u; }
static int rate_ok(uint32_t r) {
    return r == 8000u || r == 16000u || r == 24000u || r == 32000u || r == 48000u;
}
static int mask_ok(uint32_t n, uint32_t mask) {
    return mask != 0u && (mask & ~((1u << n) - 1u)) == 0u;
}
static int valid(const fe_array *s) {
    return s && s->magic == FE_ARRAY_MAGIC && count_ok(s->count);
}
static int overlaps(const void *p, size_t n, const void *q, size_t m) {
    const uintptr_t a = (uintptr_t)p, b = (uintptr_t)q;
    if (n > UINTPTR_MAX - a || m > UINTPTR_MAX - b) return 1;
    return a < b + m && b < a + n;
}
size_t fe_array_state_bytes(uint32_t n) {
    return count_ok(n) ? sizeof(fe_array) + (size_t)n * FE_ARRAY_HISTORY * sizeof(float) : 0u;
}

static int geometry(const fe_array_config *c, double delays[4], uint32_t *common) {
    double norm = 0.0, radius = 0.0, calibration = 0.0;
    uint32_t i, j, k, seen = 0u;
    if (!c || !count_ok(c->mic_count) || !rate_ok(c->sample_rate_hz) ||
        c->reference_mic >= c->mic_count || !mask_ok(c->mic_count, c->active_mask) ||
        (c->interpolation != FE_ARRAY_LINEAR && c->interpolation != FE_ARRAY_LAGRANGE3)) return 0;
    for (k = 0u; k < 3u; ++k) {
        if (!isfinite(c->direction[k]) || fabs(c->direction[k]) > 1.0) return 0;
        norm += c->direction[k] * c->direction[k];
    }
    if (fabs(norm - 1.0) > 1.0e-6) return 0; /* No hidden direction normalization. */
    for (i = 0u; i < c->mic_count; ++i) {
        const fe_array_microphone *m = &c->microphones[i];
        if (m->input_channel >= c->mic_count || (seen & (1u << m->input_channel)) ||
            !isfinite(m->gain) || fabs(m->gain) < 0.25 || fabs(m->gain) > 4.0 ||
            !isfinite(m->latency_samples) || fabs(m->latency_samples) > 8.0) return 0;
        seen |= 1u << m->input_channel;
        for (k = 0u; k < 3u; ++k)
            if (!isfinite(m->position_m[k]) || fabs(m->position_m[k]) > 1.0) return 0;
        if (fabs(m->latency_samples) > calibration) calibration = fabs(m->latency_samples);
    }
    for (i = 0u; i < c->mic_count; ++i) {
        double radius2 = 0.0, projection = 0.0;
        for (k = 0u; k < 3u; ++k) {
            const double delta = c->microphones[i].position_m[k] -
                                 c->microphones[c->reference_mic].position_m[k];
            radius2 += delta * delta;
            projection += delta * c->direction[k];
        }
        if (sqrt(radius2) > radius) radius = sqrt(radius2);
        delays[i] = projection * (double)c->sample_rate_hz / 343.0 -
                    c->microphones[i].latency_samples;
        for (j = 0u; j < i; ++j) {
            double distance2 = 0.0;
            for (k = 0u; k < 3u; ++k) {
                const double delta = c->microphones[i].position_m[k] - c->microphones[j].position_m[k];
                distance2 += delta * delta;
            }
            if (distance2 < 1.0e-12) return 0; /* Distinct physical microphones. */
        }
    }
    norm = ceil(radius * (double)c->sample_rate_hz / 343.0 + calibration) + 1.0;
    if (norm > (double)(FE_ARRAY_HISTORY - 3u)) return 0;
    *common = (uint32_t)norm;
    for (i = 0u; i < c->mic_count; ++i) {
        delays[i] += norm;
        if (delays[i] < 1.0 || delays[i] > (double)(FE_ARRAY_HISTORY - 3u)) return 0;
    }
    return 1;
}

fe_array_status fe_array_init(void *memory, size_t bytes, const fe_array_config *c, fe_array **out) {
    double d[4] = {0.0, 0.0, 0.0, 0.0};
    uint32_t common = 0u, i;
    size_t wanted;
    fe_array *s;
    if (!out || (memory && overlaps(memory, bytes, out, sizeof(*out))) ||
        (c && overlaps(c, sizeof(*c), out, sizeof(*out)))) return FE_ARRAY_EINVAL;
    *out = NULL;
    if (!memory || !c || (uintptr_t)memory % FE_ARRAY_ALIGNMENT ||
        overlaps(memory, bytes, c, sizeof(*c)) || !geometry(c, d, &common)) return FE_ARRAY_EINVAL;
    wanted = fe_array_state_bytes(c->mic_count);
    if (bytes < wanted) return FE_ARRAY_ENOMEM;
    s = (fe_array *)memory;
    memset(s, 0, wanted);
    s->magic = FE_ARRAY_MAGIC; s->rate = c->sample_rate_hz; s->count = c->mic_count;
    s->mask = c->active_mask; s->delay = common; s->interpolation = c->interpolation;
    for (i = 0u; i < s->count; ++i) {
        const uint32_t m = (uint32_t)floor(d[i]);
        const double f = d[i] - floor(d[i]);
        uint32_t k;
        s->channel[i] = c->microphones[i].input_channel;
        s->gain[i] = (float)c->microphones[i].gain;
        s->compensation[i] = d[i];
        s->target_compensation[i] = d[i];
        s->calibration_latency[i] = c->microphones[i].latency_samples;
        for (k = 0u; k < 3u; ++k)
            s->relative[i][k] = c->microphones[i].position_m[k] -
                               c->microphones[c->reference_mic].position_m[k];
        if (c->interpolation == FE_ARRAY_LINEAR) {
            s->offset[i][0] = m; s->offset[i][1] = m + 1u;
            s->weight[i][0] = (float)(1.0 - f); s->weight[i][1] = (float)f;
        } else {
            for (k = 0u; k < 4u; ++k) s->offset[i][k] = m - 1u + k;
            s->weight[i][0] = (float)(-f * (1.0-f) * (2.0-f) / 6.0);
            s->weight[i][1] = (float)((1.0+f) * (1.0-f) * (2.0-f) / 2.0);
            s->weight[i][2] = (float)((1.0+f) * f * (2.0-f) / 2.0);
            s->weight[i][3] = (float)(-(1.0+f) * f * (1.0-f) / 6.0);
        }
    }
    memcpy(s->direction, c->direction, sizeof(s->direction));
    memcpy(s->target_direction, c->direction, sizeof(s->target_direction));
    *out = s;
    return FE_ARRAY_OK;
}

fe_array_status fe_array_get_info(const fe_array *s, fe_array_info *out) {
    uint32_t i;
    if (!valid(s)) return FE_ARRAY_ESTATE;
    if (!out || overlaps(s, fe_array_state_bytes(s->count), out, sizeof(*out))) return FE_ARRAY_EINVAL;
    memset(out, 0, sizeof(*out));
    out->sample_rate_hz = s->rate; out->mic_count = s->count; out->active_mask = s->mask;
    out->common_delay_samples = s->delay; out->interpolation = s->interpolation;
    out->state_bytes = fe_array_state_bytes(s->count); out->samples_processed = s->samples;
    memcpy(out->direction, s->direction, sizeof(out->direction));
    memcpy(out->target_direction, s->target_direction, sizeof(out->target_direction));
    out->transition_total_samples = s->transition_total;
    out->transition_done_samples = s->transition_done;
    out->steering_accepted = s->steering_accepted;
    out->steering_completed = s->steering_completed;
    out->steering_cancelled = s->steering_cancelled;
    for (i = 0u; i < s->count; ++i) out->compensation_samples[i] = s->compensation[i];
    return FE_ARRAY_OK;
}

static void cancel_steering(fe_array *s) {
    if (s->transition_total != 0u) ++s->steering_cancelled;
    s->transition_total = 0u; s->transition_done = 0u;
    memcpy(s->target_direction, s->direction, sizeof(s->direction));
    memcpy(s->target_compensation, s->compensation, sizeof(s->compensation));
    memset(s->next_offset, 0, sizeof(s->next_offset));
    memset(s->next_weight, 0, sizeof(s->next_weight));
}

fe_array_status fe_array_request_steer(fe_array *s, const double direction[3], uint32_t total) {
    double norm = 0.0, delays[FE_ARRAY_MAX_MICS] = {0.0};
    uint32_t offsets[FE_ARRAY_MAX_MICS][4] = {{0u}};
    float weights[FE_ARRAY_MAX_MICS][4] = {{0.0f}};
    uint32_t i, k;
    if (!valid(s)) return FE_ARRAY_ESTATE;
    if (!direction || overlaps(s, fe_array_state_bytes(s->count), direction, 3u * sizeof(double)) ||
        total < 2u || total > s->rate / 10u) return FE_ARRAY_EINVAL;
    for (k = 0u; k < 3u; ++k) {
        if (!isfinite(direction[k]) || fabs(direction[k]) > 1.0) return FE_ARRAY_EINVAL;
        norm += direction[k] * direction[k];
    }
    if (fabs(norm - 1.0) > 1.0e-6) return FE_ARRAY_EINVAL;
    if (s->transition_total != 0u) return FE_ARRAY_EBUSY;
    for (i = 0u; i < s->count; ++i) {
        double projection = 0.0, f;
        uint32_t m;
        for (k = 0u; k < 3u; ++k) projection += s->relative[i][k] * direction[k];
        delays[i] = projection * (double)s->rate / 343.0 - s->calibration_latency[i];
        delays[i] += (double)s->delay;
        if (delays[i] < 1.0 || delays[i] > (double)(FE_ARRAY_HISTORY - 3u)) return FE_ARRAY_EINVAL;
        m = (uint32_t)floor(delays[i]); f = delays[i] - floor(delays[i]);
        if (s->interpolation == FE_ARRAY_LINEAR) {
            offsets[i][0] = m; offsets[i][1] = m + 1u;
            weights[i][0] = (float)(1.0 - f); weights[i][1] = (float)f;
        } else {
            for (k = 0u; k < 4u; ++k) offsets[i][k] = m - 1u + k;
            weights[i][0] = (float)(-f * (1.0-f) * (2.0-f) / 6.0);
            weights[i][1] = (float)((1.0+f) * (1.0-f) * (2.0-f) / 2.0);
            weights[i][2] = (float)((1.0+f) * f * (2.0-f) / 2.0);
            weights[i][3] = (float)(-(1.0+f) * f * (1.0-f) / 6.0);
        }
    }
    if (direction[0] == s->direction[0] && direction[1] == s->direction[1] &&
        direction[2] == s->direction[2]) return FE_ARRAY_OK;
    if (s->steering_accepted == UINT64_MAX) return FE_ARRAY_EINVAL;
    memcpy(s->next_offset, offsets, sizeof(offsets));
    memcpy(s->next_weight, weights, sizeof(weights));
    memcpy(s->target_direction, direction, sizeof(s->target_direction));
    memcpy(s->target_compensation, delays, sizeof(delays));
    s->transition_total = total; s->transition_done = 0u;
    ++s->steering_accepted;
    return FE_ARRAY_OK;
}

fe_array_status fe_array_reset(fe_array *s) {
    if (!valid(s)) return FE_ARRAY_ESTATE;
    memset(s->history, 0, (size_t)s->count * FE_ARRAY_HISTORY * sizeof(float));
    s->samples = 0u; s->cursor = 0u;
    cancel_steering(s);
    s->steering_accepted = 0u; s->steering_completed = 0u; s->steering_cancelled = 0u;
    return FE_ARRAY_OK;
}
fe_array_status fe_array_set_active_mask(fe_array *s, uint32_t mask) {
    uint32_t i;
    if (!valid(s)) return FE_ARRAY_ESTATE;
    if (!mask_ok(s->count, mask)) return FE_ARRAY_EINVAL;
    if (mask == s->mask) return FE_ARRAY_OK;
    cancel_steering(s);
    for (i = 0u; i < s->count; ++i)
        if (((s->mask ^ mask) & (1u << i)) != 0u)
            memset(s->history + i * FE_ARRAY_HISTORY, 0, FE_ARRAY_HISTORY * sizeof(float));
    s->mask = mask;
    return FE_ARRAY_OK;
}
fe_array_status fe_array_process(fe_array *s, const float *input, size_t ni, float *output, size_t no) {
    uint32_t i, active = 0u, taps;
    size_t t, frames, bytes;
    if (!valid(s)) return FE_ARRAY_ESTATE;
    if (!input || !output || ni == 0u || ni % s->count) return FE_ARRAY_EINVAL;
    frames = ni / s->count;
    if (frames > s->rate / 100u || no != frames || s->samples > UINT64_MAX - frames) return FE_ARRAY_EINVAL;
    bytes = fe_array_state_bytes(s->count);
    if (overlaps(input, ni * sizeof(float), output, no * sizeof(float)) ||
        overlaps(s, bytes, input, ni * sizeof(float)) ||
        overlaps(s, bytes, output, no * sizeof(float))) return FE_ARRAY_EINVAL;
    for (i = 0u; i < s->count; ++i) {
        if (!(s->mask & (1u << i))) continue;
        ++active;
        for (t = 0u; t < frames; ++t) {
            const float x = input[t * s->count + s->channel[i]];
            if (!isfinite(x) || fabsf(x) > 1.0f) return FE_ARRAY_EINVAL;
        }
    }
    taps = s->interpolation == FE_ARRAY_LINEAR ? 2u : 4u;
    for (t = 0u; t < frames; ++t) {
        float sum = 0.0f;
        for (i = 0u; i < s->count; ++i) {
            float value = 0.0f;
            float *h = s->history + i * FE_ARRAY_HISTORY;
            uint32_t k;
            if (!(s->mask & (1u << i))) { h[s->cursor] = 0.0f; continue; }
            h[s->cursor] = input[t * s->count + s->channel[i]];
            for (k = 0u; k < taps; ++k) {
                const uint32_t at = (s->cursor + FE_ARRAY_HISTORY - s->offset[i][k]) % FE_ARRAY_HISTORY;
                value += s->weight[i][k] * h[at];
            }
            sum += s->gain[i] * value;
        }
        output[t] = sum / (float)active;
        if (s->transition_total != 0u) {
            float next_sum = 0.0f, next;
            /* No second history and no cold-starting target beam. */
            for (i = 0u; i < s->count; ++i) {
                float value = 0.0f;
                const float *h = s->history + i * FE_ARRAY_HISTORY;
                uint32_t k;
                if (!(s->mask & (1u << i))) continue;
                for (k = 0u; k < taps; ++k) {
                    const uint32_t at = (s->cursor + FE_ARRAY_HISTORY - s->next_offset[i][k]) % FE_ARRAY_HISTORY;
                    value += s->next_weight[i][k] * h[at];
                }
                next_sum += s->gain[i] * value;
            }
            next = next_sum / (float)active;
            if (s->transition_done + 1u == s->transition_total) output[t] = next;
            else if (s->transition_done != 0u) {
                const float alpha = (float)s->transition_done / (float)(s->transition_total - 1u);
                output[t] = (1.0f - alpha) * output[t] + alpha * next;
            }
            ++s->transition_done;
            if (s->transition_done == s->transition_total) {
                memcpy(s->offset, s->next_offset, sizeof(s->offset));
                memcpy(s->weight, s->next_weight, sizeof(s->weight));
                memcpy(s->compensation, s->target_compensation, sizeof(s->compensation));
                memcpy(s->direction, s->target_direction, sizeof(s->direction));
                s->transition_total = 0u; s->transition_done = 0u;
                ++s->steering_completed;
            }
        }
        s->cursor = (s->cursor + 1u) % FE_ARRAY_HISTORY;
    }
    s->samples += frames;
    return FE_ARRAY_OK;
}
