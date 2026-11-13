/* D8 read-only observation and engineering controls, never linked into the SDK.
 * The generated D1 helper has only the two definition renames in the input lock.
 * This file never synthesizes an observed state or changes a DSP control.
 * All scientific I/O is additionally contained by the D8 parent's write budget.
 */
#define _POSIX_C_SOURCE 200809L
#include "frontend/ap_frontend.h"
#include <stddef.h>
#include "dualmic_stages_d1.c"

enum { D8_LANES = 5, D8_RECORD = 472, D8_AGC_RECORD = 24,
       D8_MAX_FRAMES = 629, D8_RECEIPT_MAX = 4096 };
static const char *const d8_names[D8_LANES] = {
    "hpf_input_l", "hpf_input_r", "hpf_output_l", "hpf_output_r", "bf_output"
};
typedef struct d8_sink {
    FILE *file;
    uint64_t bytes, limit;
} d8_sink;
static d8_sink d8_lanes[D8_LANES], d8_trace, d8_agc_trace, d8_receipt;
static int d8_fd = -1, d8_self_test, d8_memory_writes;
static uint64_t d8_hpf_calls, d8_bf_calls, d8_agc_calls, d8_errors;
static uint32_t d8_expected_frames, d8_order;
static const char *d8_first_error = "";
static ap_hpf_state_t d8_hpf_before[2], d8_hpf_after[2];
static float d8_hpf_output[2][D1_FRAME];
static ap_beamformer_state_t d8_bf_before, d8_bf_after;
static ap_agc_state_t d8_agc_before, d8_agc_after;
_Static_assert(sizeof(float) == 4, "D8 float size");
_Static_assert(sizeof(uint32_t) == 4 && sizeof(int) == 4, "D8 integer size");
_Static_assert(sizeof(ap_hpf_state_t) == 24, "D8 HPF state size");
_Static_assert(sizeof(ap_beamformer_state_t) == 180, "D8 BF state size");
_Static_assert(offsetof(ap_hpf_state_t, r) == 0, "D8 r offset");
_Static_assert(offsetof(ap_hpf_state_t, x) == 4, "D8 x offset");
_Static_assert(offsetof(ap_hpf_state_t, y) == 12, "D8 y offset");
_Static_assert(offsetof(ap_hpf_state_t, channels) == 20, "D8 channels offset");
_Static_assert(offsetof(ap_beamformer_state_t, history) == 0, "D8 history offset");
_Static_assert(offsetof(ap_beamformer_state_t, lag_score) == 64, "D8 lag_score offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_gain) == 132, "D8 fallback_gain offset");
_Static_assert(offsetof(ap_beamformer_state_t, lag) == 136, "D8 lag offset");
_Static_assert(offsetof(ap_beamformer_state_t, max_lag) == 140, "D8 max_lag offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_lag) == 144, "D8 fallback_lag offset");
_Static_assert(offsetof(ap_beamformer_state_t, counter) == 148, "D8 counter offset");
_Static_assert(offsetof(ap_beamformer_state_t, score_updates) == 152, "D8 score_updates offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_active) == 156, "D8 fallback_active offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_strong_channel) == 160, "D8 fallback_strong_channel offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_recovery_count) == 164, "D8 fallback_recovery_count offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_hard_fault) == 168, "D8 fallback_hard_fault offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_hard_arm_count) == 172, "D8 fallback_hard_arm_count offset");
_Static_assert(offsetof(ap_beamformer_state_t, fixed_health_counter) == 176, "D8 fixed_health_counter offset");


_Static_assert(sizeof(ap_agc_state_t) == 12, "D8 AGC state size");
_Static_assert(offsetof(ap_agc_state_t, gain) == 0, "D8 AGC gain offset");
_Static_assert(offsetof(ap_agc_state_t, target_linear) == 4, "D8 AGC target offset");
_Static_assert(offsetof(ap_agc_state_t, limiter_linear) == 8, "D8 AGC limiter offset");
_Static_assert(AP_BF_HISTORY == 8 && AP_BF_LAG_SCORE_COUNT == 17, "D8 BF arrays");
_Static_assert(16 + 4 * 24 + 2 * 180 == D8_RECORD, "D8 complete record");

static void d8_expect(int condition, const char *reason) {
    if (!condition) {
        if (!d8_errors) d8_first_error = reason;
        ++d8_errors;
    }
}
static void d8_finite(const float *values, uint32_t n) {
    uint32_t i;
    for (i = 0u; i < n; ++i) d8_expect(isfinite(values[i]), "nonfinite");
}
static int d8_room(uint64_t frame) {
    const int valid = d8_expected_frames > 0u &&
        d8_expected_frames <= D8_MAX_FRAMES && frame < d8_expected_frames;
    d8_expect(valid, "maximum_frames");
    return valid;
}
/* Reserve against the complete requested write before touching the stream.
 * Partial/error writes remain in place and their actual prefix is counted. */
static void d8_write(d8_sink *sink, const void *data, size_t bytes) {
    size_t written;
    if (d8_self_test && !d8_memory_writes) return;
    if (!sink->file) { d8_expect(0, "write"); return; }
    if (sink->bytes > sink->limit || bytes > sink->limit - sink->bytes) {
        d8_expect(0, "write_limit");
        return;
    }
    written = fwrite(data, 1u, bytes, sink->file);
    sink->bytes += written;
    d8_expect(written == bytes, "write");
}
static void d8_lane(unsigned lane, const float *values, uint32_t n) {
    d8_finite(values, n);
    d8_write(&d8_lanes[lane], values, (size_t)n * sizeof(float));
}
static void d8_check_hpf(const ap_hpf_state_t *state) {
    d8_finite(&state->r, 1u);
    d8_finite(state->x, 2u);
    d8_finite(state->y, 2u);
    d8_expect(state->channels == 2u, "hpf_channels");
}
static void d8_check_bf(const ap_beamformer_state_t *state) {
    d8_finite(state->history[0], AP_BF_HISTORY);
    d8_finite(state->history[1], AP_BF_HISTORY);
    d8_finite(state->lag_score, AP_BF_LAG_SCORE_COUNT);
    d8_finite(&state->fallback_gain, 1u);
    d8_expect(state->max_lag == 3 && state->lag >= -3 && state->lag <= 3 &&
              state->fallback_lag >= -3 && state->fallback_lag <= 3, "bf_lag_geometry");
    d8_expect(state->fallback_active <= 1u && state->fallback_hard_fault <= 1u &&
              state->fallback_strong_channel <= 1u, "bf_route_geometry");
}
static void d8_check_agc(const ap_agc_state_t *state) {
    d8_finite(&state->gain, 1u);
    d8_finite(&state->target_linear, 1u);
    d8_finite(&state->limiter_linear, 1u);
}
void ap_hpf_process_d8_real(ap_hpf_state_t *, float *, uint32_t, uint32_t);
void ap_hpf_process(ap_hpf_state_t *state, float *values, uint32_t n, uint32_t channel) {
    d8_expect(state && values && n == D1_FRAME && channel < 2u, "hpf_geometry");
    if (!state || !values || n != D1_FRAME || channel >= 2u) return;
    if (!d8_room(d8_bf_calls)) return;
    d8_expect(d8_order == channel, "hpf_channel_order");
    if (!d8_self_test)
        d8_expect(d8_bf_calls == d8_agc_calls && d8_agc_calls == d1_agc_calls &&
                  d1_agc_calls == d1_activity_calls, "upstream_before_activity");
    d8_hpf_before[channel] = *state;
    if (channel == 1u)
        d8_expect(memcmp(state, &d8_hpf_after[0], sizeof(*state)) == 0,
                  "hpf_interchannel_state");
    d8_check_hpf(state);
    d8_lane(channel, values, n);
    ap_hpf_process_d8_real(state, values, n, channel);
    d8_hpf_after[channel] = *state;
    d8_check_hpf(state);
    memcpy(d8_hpf_output[channel], values, sizeof(d8_hpf_output[channel]));
    d8_lane(channel + 2u, values, n);
    ++d8_hpf_calls;
    ++d8_order;
}
void ap_beamformer_process_d8_real(ap_beamformer_state_t *, int, float *, float *, float *, uint32_t);
void ap_beamformer_process(ap_beamformer_state_t *state, int track_direction,
                          float *left, float *right, float *out, uint32_t n) {
    uint32_t header[4];
    unsigned char record[D8_RECORD];
    const int32_t tracking = (int32_t)track_direction;
    d8_expect(state && left && right && out && n == D1_FRAME, "bf_geometry");
    if (!state || !left || !right || !out || n != D1_FRAME) return;
    /* Engineering can test this guard; no tracking-off DSP run is admitted. */
    d8_expect(track_direction == 1, "track_direction");
    if (track_direction != 1 || !d8_room(d8_bf_calls)) return;
    d8_expect(d8_order == 2u && d8_hpf_calls == 2u * (d8_bf_calls + 1u), "bf_order");
    if (!d8_self_test)
        d8_expect(d1_activity_calls == d8_bf_calls && d1_ns_calls == d8_bf_calls &&
                  d1_agc_calls == d8_bf_calls && d8_agc_calls == d8_bf_calls,
                  "bf_before_activity");
    d8_expect(memcmp(left, d8_hpf_output[0], sizeof(d8_hpf_output[0])) == 0 &&
              memcmp(right, d8_hpf_output[1], sizeof(d8_hpf_output[1])) == 0, "hpf_to_bf");
    d8_bf_before = *state;
    d8_check_bf(state);
    header[0] = (uint32_t)d8_bf_calls;
    memcpy(&header[1], &tracking, sizeof(tracking));
    header[2] = (out == left ? 1u : 0u) | (out == right ? 2u : 0u);
    header[3] = n;
    ap_beamformer_process_d8_real(state, track_direction, left, right, out, n);
    d8_bf_after = *state;
    d8_check_bf(state);
    d8_lane(4u, out, n);
    memcpy(record, header, 16u);
    memcpy(record + 16u, &d8_hpf_before[0], 24u);
    memcpy(record + 40u, &d8_hpf_after[0], 24u);
    memcpy(record + 64u, &d8_hpf_before[1], 24u);
    memcpy(record + 88u, &d8_hpf_after[1], 24u);
    memcpy(record + 112u, &d8_bf_before, 180u);
    memcpy(record + 292u, &d8_bf_after, 180u);
    d8_write(&d8_trace, record, sizeof(record));
    ++d8_bf_calls;
    d8_order = 0u;
}
void ap_agc_process_controlled(ap_agc_state_t *state, float *samples,
                               uint32_t n, int allow) {
    unsigned char record[D8_AGC_RECORD];
    uint64_t calls_before;
    d8_expect(state && samples && n == D1_FRAME && (allow == 0 || allow == 1),
              "agc_geometry");
    if (!state || !samples || n != D1_FRAME || (allow != 0 && allow != 1)) return;
    if (!d8_room(d8_agc_calls)) return;
    d8_expect(d8_bf_calls == d8_agc_calls + 1u && d8_order == 0u &&
              d1_agc_calls == d8_agc_calls, "agc_wrapper_order");
    d8_agc_before = *state;
    d8_check_agc(state);
    d8_finite(samples, n);
    calls_before = d1_agc_calls;
    /* Exactly one call; body, control and all seven D1 lanes are unchanged. */
    ap_d8_d1_agc_process_controlled(state, samples, n, allow);
    d8_agc_after = *state;
    d8_check_agc(state);
    d8_finite(samples, n);
    d8_expect(d1_agc_calls == calls_before + 1u, "agc_wrapper_count");
    memcpy(record, &d8_agc_before, 12u);
    memcpy(record + 12u, &d8_agc_after, 12u);
    d8_write(&d8_agc_trace, record, sizeof(record));
    ++d8_agc_calls;
}
static int d8_parse_frames(const char *text, uint32_t *frames) {
    uint32_t value = 0u;
    const unsigned char *p = (const unsigned char *)text;
    if (!p || *p < '1' || *p > '9') return 0;
    for (; *p; ++p) {
        if (*p < '0' || *p > '9' || value > D8_MAX_FRAMES / 10u) return 0;
        value = value * 10u + (uint32_t)(*p - '0');
        if (value > D8_MAX_FRAMES) return 0;
    }
    *frames = value;
    return 1;
}
static int d8_open_file(d8_sink *sink, const char *name, uint64_t limit) {
    struct stat st;
    int fd = openat(d8_fd, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (fd < 0) return 0;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size != 0 || st.st_nlink != 1) {
        close(fd);
        return 0;
    }
    sink->file = fdopen(fd, "wb");
    if (!sink->file) { close(fd); return 0; }
    sink->bytes = 0u;
    sink->limit = limit;
    return 1;
}
static int d8_layout(void) {
    const uint16_t endian = 1u;
    return sizeof(float) == 4u && sizeof(int) == 4u && FLT_RADIX == 2 &&
           FLT_MANT_DIG == 24 && FLT_MAX_EXP == 128 &&
           *(const unsigned char *)&endian == 1u &&
           sizeof(ap_agc_state_t) == 12u && offsetof(ap_agc_state_t, gain) == 0u &&
           offsetof(ap_agc_state_t, target_linear) == 4u &&
           offsetof(ap_agc_state_t, limiter_linear) == 8u &&
           AP_BF_HISTORY == 8u && AP_BF_LAG_SCORE_COUNT == 17u &&
           sizeof(ap_hpf_state_t) == 24u && sizeof(ap_beamformer_state_t) == 180u
           && offsetof(ap_hpf_state_t, r) == 0u
           && offsetof(ap_hpf_state_t, x) == 4u
           && offsetof(ap_hpf_state_t, y) == 12u
           && offsetof(ap_hpf_state_t, channels) == 20u
           && offsetof(ap_beamformer_state_t, history) == 0u
           && offsetof(ap_beamformer_state_t, lag_score) == 64u
           && offsetof(ap_beamformer_state_t, fallback_gain) == 132u
           && offsetof(ap_beamformer_state_t, lag) == 136u
           && offsetof(ap_beamformer_state_t, max_lag) == 140u
           && offsetof(ap_beamformer_state_t, fallback_lag) == 144u
           && offsetof(ap_beamformer_state_t, counter) == 148u
           && offsetof(ap_beamformer_state_t, score_updates) == 152u
           && offsetof(ap_beamformer_state_t, fallback_active) == 156u
           && offsetof(ap_beamformer_state_t, fallback_strong_channel) == 160u
           && offsetof(ap_beamformer_state_t, fallback_recovery_count) == 164u
           && offsetof(ap_beamformer_state_t, fallback_hard_fault) == 168u
           && offsetof(ap_beamformer_state_t, fallback_hard_arm_count) == 172u
           && offsetof(ap_beamformer_state_t, fixed_health_counter) == 176u;
}

static int d8_open(const char *directory) {
    unsigned i;
    DIR *scan;
    struct dirent *entry;
    int duplicate, empty = 1;
    if (!directory || !*directory || !d8_layout()) return 0;
    d8_fd = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (d8_fd < 0) return 0;
    duplicate = dup(d8_fd);
    if (duplicate < 0) return 0;
    scan = fdopendir(duplicate);
    if (!scan) { close(duplicate); return 0; }
    errno = 0;
    while ((entry = readdir(scan)) != NULL)
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) empty = 0;
    if (errno) empty = 0;
    if (closedir(scan)) empty = 0;
    if (!empty) return 0;
    for (i = 0u; i < D8_LANES; ++i) {
        char name[64];
        const int count = snprintf(name, sizeof(name), "%s.f32le", d8_names[i]);
        if (count < 0 || (size_t)count >= sizeof(name) ||
            !d8_open_file(&d8_lanes[i], name, (uint64_t)d8_expected_frames * D1_FRAME * 4u))
            return 0;
    }
    return d8_open_file(&d8_trace, "state.bin", (uint64_t)d8_expected_frames * D8_RECORD) &&
           d8_open_file(&d8_agc_trace, "agc-state.bin",
                        (uint64_t)d8_expected_frames * D8_AGC_RECORD) &&
           d8_open_file(&d8_receipt, "observer.json", D8_RECEIPT_MAX);
}
static void d8_close_sink(d8_sink *sink) {
    if (sink->file && fclose(sink->file)) d8_expect(0, "close");
    sink->file = NULL;
}
static void d8_close(void) {
    unsigned i;
    for (i = 0u; i < D8_LANES; ++i) d8_close_sink(&d8_lanes[i]);
    d8_close_sink(&d8_trace);
    d8_close_sink(&d8_agc_trace);
}
static void d8_lengths(void) {
    unsigned i;
    for (i = 0u; i < D8_LANES; ++i)
        d8_expect(d8_lanes[i].bytes == (uint64_t)d8_expected_frames * D1_FRAME * 4u,
                  "lane_bytes");
    d8_expect(d8_trace.bytes == (uint64_t)d8_expected_frames * D8_RECORD, "state_bytes");
    d8_expect(d8_agc_trace.bytes == (uint64_t)d8_expected_frames * D8_AGC_RECORD,
              "agc_state_bytes");
}
static int d8_write_receipt(int cli_result) {
    char text[D8_RECEIPT_MAX];
    const int count = snprintf(text, sizeof(text),
        "{\n \"schema_version\":1, \"experiment\":\"FE-DUALMIC-BROADSIDE-OUTPUT-D8\",\n"
        " \"status\":\"%s\", \"source_revision\":\"%s\",\n"
        " \"frames\":%" PRIu64 ", \"expected_frames\":%u, \"maximum_frames\":%u,\n"
        " \"hpf_calls\":%" PRIu64 ", \"bf_calls\":%" PRIu64 ", \"agc_calls\":%" PRIu64 ",\n"
        " \"cli_exit_code\":%d, \"observer_error_count\":%" PRIu64 ", \"first_error\":\"%s\",\n"
        " \"layout_checked\":true, \"hpf_state_bytes\":24, \"bf_state_bytes\":180,\n"
        " \"agc_state_bytes\":12, \"hpf_state_offsets\":[0,4,12,20],\n"
        " \"bf_state_offsets\":[0,64,132,136,140,144,148,152,156,160,164,168,172,176],\n"
        " \"agc_state_offsets\":[0,4,8], \"record_bytes\":472, \"agc_record_bytes\":24,\n"
        " \"record_offsets\":[0,4,8,12,16,40,64,88,112,292], \"agc_record_offsets\":[0,12],\n"
        " \"lane_bytes\":[%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "],\n"
        " \"state_bytes\":%" PRIu64 ", \"agc_trace_bytes\":%" PRIu64 ",\n"
        " \"track_direction_required\":1, \"offset_samples\":0, \"sample_format\":\"float32le\",\n"
        " \"d8_file_write_caps_checked\":true, \"receipt_cap_bytes\":4096,\n"
        " \"unobserved_downstream_state_claimed\":false\n}\n",
        cli_result == 0 && d8_errors == 0u ? "OBSERVED" : "INVALID",
        AP_BUILD_SOURCE_REVISION, d8_bf_calls, d8_expected_frames, (unsigned)D8_MAX_FRAMES,
        d8_hpf_calls, d8_bf_calls, d8_agc_calls, cli_result, d8_errors, d8_first_error,
        d8_lanes[0].bytes, d8_lanes[1].bytes, d8_lanes[2].bytes,
        d8_lanes[3].bytes, d8_lanes[4].bytes, d8_trace.bytes, d8_agc_trace.bytes);
    if (count < 0 || (size_t)count >= sizeof(text)) {
        d8_expect(0, "receipt_limit");
        d8_close_sink(&d8_receipt);
        return 0;
    }
    d8_write(&d8_receipt, text, (size_t)count);
    d8_close_sink(&d8_receipt);
    return d8_errors == 0u;
}
/* Independent output-only equation. The after-state supplies the actual route,
 * while every delayed sample comes from the untouched input or before-history.
 * The arm controls only this expected equation, never the observed DSP. */
static float d8_past(const ap_beamformer_state_t *before,
                     const float *input, unsigned channel, int index) {
    return index >= 0 ? input[index] : before->history[channel][(int)AP_BF_HISTORY + index];
}
static void d8_equation(const ap_beamformer_state_t *before,
                        const ap_beamformer_state_t *after, int candidate,
                        const float *left, const float *right, float *out) {
    uint32_t i;
    const int lag = candidate ? 0 : (after->fallback_active ? after->fallback_lag : after->lag);
    for (i = 0u; i < D1_FRAME; ++i) {
        const float x = lag < 0 ? d8_past(before, left, 0u, (int)i + lag) : left[i];
        const float y = lag > 0 ? d8_past(before, right, 1u, (int)i - lag) : right[i];
        if (!after->fallback_active) out[i] = 0.5f * (x + y);
        else {
            const float strong = after->fallback_strong_channel == 0u ? x : y;
            const float weak = after->fallback_strong_channel == 0u ? y : x;
            out[i] = after->fallback_hard_fault ? strong :
                after->fallback_gain * (0.75f * strong + 0.25f * weak);
        }
    }
}
static float d8_clip(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}
static void d8_agc_equation(ap_agc_state_t *state, float *samples, int allow) {
    uint32_t i;
    float energy = 1.0e-12f, peak = 0.0f, target, alpha, gain;
    const float limit = state->limiter_linear;
    for (i = 0u; i < D1_FRAME; ++i) {
        const float magnitude = fabsf(samples[i]);
        energy += samples[i] * samples[i];
        if (magnitude > peak) peak = magnitude;
    }
    target = d8_clip(state->target_linear /
        (sqrtf(energy / (float)D1_FRAME) + 1.0e-6f), 0.25f, 8.0f);
    if (!allow && target > 1.0f) target = 1.0f;
    alpha = target < state->gain ? 0.25f : 0.015f;
    state->gain += alpha * (target - state->gain);
    gain = state->gain;
    if (!allow && gain > 1.0f) gain = 1.0f;
    if (peak * gain > limit && peak > 1.0e-6f) gain = limit / peak;
    for (i = 0u; i < D1_FRAME; ++i)
        samples[i] = d8_clip(samples[i] * gain, -limit, limit);
}
static void d8_reset_counts(void) {
    d8_hpf_calls = d8_bf_calls = d8_agc_calls = 0u;
    d8_order = 0u;
    d8_expected_frames = D8_MAX_FRAMES;
}
static int d8_expected_error(const char *reason, uint64_t count) {
    const int matched = d8_errors == count && strcmp(d8_first_error, reason) == 0;
    d8_errors = 0u;
    d8_first_error = "";
    return matched;
}

static unsigned d8_engineering_bf(int candidate) {
    unsigned alias, route, strong, iteration, channel, i, checks = 0u;
    int lag, fallback;
    for (alias = 0u; alias < 4u; ++alias)
    for (route = 0u; route < 3u; ++route)
    for (strong = 0u; strong < 2u; ++strong)
    for (lag = -3; lag <= 3; ++lag)
    for (fallback = -3; fallback <= 3; ++fallback) {
        ap_hpf_state_t h, reference_h;
        ap_beamformer_state_t b, reference_b;
        d8_reset_counts();
        ap_hpf_init(&h, 16000u, 2u);
        ap_beamformer_init(&b, 16000u, 35.0f);
        b.lag = lag;
        b.fallback_lag = fallback;
        b.fallback_active = route != 0u;
        b.fallback_hard_fault = route == 2u;
        b.fallback_strong_channel = strong;
        b.fallback_gain = 0.8f;
        b.counter = 0u;
        b.fixed_health_counter = 3u;
        for (channel = 0u; channel < 2u; ++channel)
            for (i = 0u; i < AP_BF_HISTORY; ++i)
                b.history[channel][i] = (float)((int)(channel * 8u + i) - 7) / 64.0f;
        for (iteration = 0u; iteration < 9u; ++iteration) {
            float input[2][D1_FRAME], real_input[2][D1_FRAME], saved[2][D1_FRAME];
            float output[D1_FRAME], real_output[D1_FRAME], equation[D1_FRAME];
            float *observed, *expected;
            /* Includes two actual score-update cadences and a real reset. */
            if (iteration == 5u) {
                ap_hpf_init(&h, 16000u, 2u);
                ap_beamformer_init(&b, 16000u, 35.0f);
            }
            reference_h = h;
            reference_b = b;
            for (channel = 0u; channel < 2u; ++channel)
                for (i = 0u; i < D1_FRAME; ++i)
                    input[channel][i] = (float)((int)((i * 17u + iteration * 11u +
                        (alias == 3u ? 0u : channel * 3u)) % 113u) - 56) / 128.0f;
            memcpy(real_input, input, sizeof(input));
            for (channel = 0u; channel < 2u; ++channel) {
                ap_hpf_process(&h, input[channel], D1_FRAME, channel);
                ap_hpf_process_d8_real(&reference_h, real_input[channel], D1_FRAME, channel);
            }
            d8_expect(memcmp(&h, &reference_h, sizeof(h)) == 0 &&
                      memcmp(input, real_input, sizeof(input)) == 0, "engineering_hpf");
            memcpy(saved[0], input[0], sizeof(saved[0]));
            memcpy(saved[1], input[alias == 3u ? 0u : 1u], sizeof(saved[1]));
            observed = alias == 0u ? output : input[alias == 3u ? 0u : alias - 1u];
            expected = alias == 0u ? real_output : real_input[alias == 3u ? 0u : alias - 1u];
            ap_beamformer_process(&b, 1, input[0],
                                  input[alias == 3u ? 0u : 1u], observed, D1_FRAME);
            d8_expect(memcmp(&d8_bf_before, &reference_b, sizeof(b)) == 0,
                      "engineering_before_continuity");
            ap_beamformer_process_d8_real(&reference_b, 1, real_input[0],
                                          real_input[alias == 3u ? 0u : 1u],
                                          expected, D1_FRAME);
            d8_expect(memcmp(&b, &reference_b, sizeof(b)) == 0 &&
                      memcmp(observed, expected, sizeof(output)) == 0, "engineering_bf");
            d8_equation(&d8_bf_before, &b, candidate, saved[0], saved[1], equation);
            d8_expect(memcmp(observed, equation, sizeof(equation)) == 0,
                      "engineering_output_equation");
            for (channel = 0u; channel < 2u; ++channel)
                d8_expect(memcmp(b.history[channel], saved[channel] + D1_FRAME - AP_BF_HISTORY,
                          AP_BF_HISTORY * sizeof(float)) == 0, "engineering_history");
            d8_expect(b.fixed_health_counter == 3u, "engineering_full_tracking");
            ++checks;
        }
    }
    return checks;
}
/* POSIX memory streams exercise the unchanged D1 writer without creating
 * unaccounted temporary files. Extra byte holds fmemopen's NUL terminator.
 * No state record or output is replaced with the independently computed value. */
static unsigned d8_engineering_agc(void) {
    static const float gains[] = {0.25f, 1.0f, 4.0f, 8.0f};
    unsigned allow, profile, seed, i, checks = 0u;
    for (allow = 0u; allow < 2u; ++allow)
    for (profile = 0u; profile < 4u; ++profile)
    for (seed = 0u; seed < sizeof(gains) / sizeof(gains[0]); ++seed) {
        ap_agc_state_t state, before, reference, equation_state;
        float values[D1_FRAME], real_values[D1_FRAME], equation[D1_FRAME];
        unsigned char lane[D1_FRAME * 4u + 1u], record[D8_AGC_RECORD + 1u];
        char control[2048];
        memset(lane, 0, sizeof(lane));
        memset(record, 0, sizeof(record));
        memset(control, 0, sizeof(control));
        ap_agc_init(&state, -18.0f, -2.0f);
        state.gain = gains[seed];
        before = reference = equation_state = state;
        for (i = 0u; i < D1_FRAME; ++i) {
            const float v = (float)((int)((i * 19u) % 59u) - 29) / 32.0f;
            values[i] = profile == 0u ? 0.0f : (profile == 1u ? v * 0.001f :
                       (profile == 2u ? v : (i == 37u ? 10.0f : v * 0.1f)));
        }
        memcpy(real_values, values, sizeof(values));
        memcpy(equation, values, sizeof(values));
        memcpy(d1_saved_ns, values, sizeof(values));
        d8_reset_counts();
        d8_bf_calls = 1u;
        d8_hpf_calls = 2u;
        d1_activity_calls = d1_ns_calls = 1u;
        d1_agc_calls = d1_errors = 0u;
        d1_first_error = "";
        d1_far = !allow;
        d1_dt = 0;
        d1_lane_frames[D1_AGC_OUTPUT] = 0u;
        d1_lanes[D1_AGC_OUTPUT] = fmemopen(lane, sizeof(lane), "w+b");
        d1_control = fmemopen(control, sizeof(control), "w+b");
        d8_agc_trace.file = fmemopen(record, sizeof(record), "w+b");
        d8_agc_trace.bytes = 0u;
        d8_agc_trace.limit = D8_AGC_RECORD;
        if (!d1_lanes[D1_AGC_OUTPUT] || !d1_control || !d8_agc_trace.file) {
            if (d1_lanes[D1_AGC_OUTPUT]) fclose(d1_lanes[D1_AGC_OUTPUT]);
            if (d1_control) fclose(d1_control);
            d1_lanes[D1_AGC_OUTPUT] = d1_control = NULL;
            d8_close_sink(&d8_agc_trace);
            d8_expect(0, "engineering_memory_stream");
            return checks;
        }
        d8_memory_writes = 1;
        ap_agc_process_controlled(&state, values, D1_FRAME, (int)allow);
        d8_memory_writes = 0;
        ap_agc_process_controlled_d1_real(&reference, real_values, D1_FRAME, (int)allow);
        d8_agc_equation(&equation_state, equation, (int)allow);
        d8_expect(fflush(d1_lanes[D1_AGC_OUTPUT]) == 0 &&
                  fflush(d1_control) == 0 && fflush(d8_agc_trace.file) == 0,
                  "engineering_agc_flush");
        d8_expect(memcmp(&state, &reference, sizeof(state)) == 0 &&
                  memcmp(values, real_values, sizeof(values)) == 0, "engineering_agc_neutrality");
        d8_expect(memcmp(&state, &equation_state, sizeof(state)) == 0 &&
                  memcmp(values, equation, sizeof(values)) == 0, "engineering_agc_equation");
        d8_expect(memcmp(record, &before, 12u) == 0 &&
                  memcmp(record + 12u, &state, 12u) == 0 &&
                  memcmp(lane, values, sizeof(values)) == 0, "engineering_agc_actual_record");
        d8_expect(d1_errors == 0u && d8_agc_calls == 1u && d1_agc_calls == 1u &&
                  d1_lane_frames[D1_AGC_OUTPUT] == 1u &&
                  d8_agc_trace.bytes == D8_AGC_RECORD &&
                  ftell(d1_lanes[D1_AGC_OUTPUT]) == (long)sizeof(values) &&
                  ftell(d1_control) > 0L && ftell(d1_control) < 1024L,
                  "engineering_agc_counts");
        d8_expect(fclose(d1_lanes[D1_AGC_OUTPUT]) == 0, "engineering_lane_close");
        d8_expect(fclose(d1_control) == 0, "engineering_control_close");
        d1_lanes[D1_AGC_OUTPUT] = d1_control = NULL;
        d8_close_sink(&d8_agc_trace);
        ++checks;
    }
    return checks;
}

static unsigned d8_engineering_records(void) {
    unsigned alias, channel, i, checks = 0u;
    for (alias = 0u; alias < 4u; ++alias) {
        unsigned char lane[D8_LANES][D1_FRAME * 4u + 1u], record[D8_RECORD + 1u];
        float input[2][D1_FRAME], raw[2][D1_FRAME], filtered[2][D1_FRAME], output[D1_FRAME];
        float *out;
        uint32_t header[4];
        ap_hpf_state_t h;
        ap_beamformer_state_t b;
        memset(lane, 0, sizeof(lane));
        memset(record, 0, sizeof(record));
        d8_reset_counts();
        d8_expected_frames = 1u;
        ap_hpf_init(&h, 16000u, 2u);
        ap_beamformer_init(&b, 16000u, 35.0f);
        b.lag = -1;
        b.fallback_lag = 2;
        b.fallback_active = 1u;
        b.fallback_strong_channel = 1u;
        b.fallback_gain = 0.8f;
        for (channel = 0u; channel < 2u; ++channel)
            for (i = 0u; i < D1_FRAME; ++i)
                input[channel][i] = (float)((int)((i * 13u +
                    (alias == 3u ? 0u : channel * 7u)) % 47u) - 23) / 64.0f;
        memcpy(raw, input, sizeof(input));
        for (i = 0u; i < D8_LANES; ++i) {
            d8_lanes[i].file = fmemopen(lane[i], sizeof(lane[i]), "w+b");
            d8_lanes[i].bytes = 0u;
            d8_lanes[i].limit = sizeof(lane[i]) - 1u;
            if (!d8_lanes[i].file) {
                d8_expect(0, "engineering_memory_stream");
                d8_close();
                return checks;
            }
        }
        d8_trace.file = fmemopen(record, sizeof(record), "w+b");
        d8_trace.bytes = 0u;
        d8_trace.limit = D8_RECORD;
        if (!d8_trace.file) {
            d8_expect(0, "engineering_memory_stream");
            d8_close();
            return checks;
        }
        d8_memory_writes = 1;
        ap_hpf_process(&h, input[0], D1_FRAME, 0u);
        ap_hpf_process(&h, input[1], D1_FRAME, 1u);
        memcpy(filtered, input, sizeof(filtered));
        out = alias == 0u ? output : input[alias == 3u ? 0u : alias - 1u];
        ap_beamformer_process(&b, 1, input[0], input[alias == 3u ? 0u : 1u], out, D1_FRAME);
        d8_memory_writes = 0;
        for (i = 0u; i < D8_LANES; ++i)
            d8_expect(fflush(d8_lanes[i].file) == 0 && d8_lanes[i].bytes == 640u,
                      "engineering_lane_record_bytes");
        d8_expect(fflush(d8_trace.file) == 0 && d8_trace.bytes == D8_RECORD,
                  "engineering_trace_record_bytes");
        memcpy(header, record, sizeof(header));
        d8_expect(header[0] == 0u && header[1] == 1u && header[2] == alias &&
                  header[3] == D1_FRAME, "engineering_record_header");
        d8_expect(memcmp(record + 16u, &d8_hpf_before[0], 24u) == 0 &&
                  memcmp(record + 40u, &d8_hpf_after[0], 24u) == 0 &&
                  memcmp(record + 64u, &d8_hpf_before[1], 24u) == 0 &&
                  memcmp(record + 88u, &d8_hpf_after[1], 24u) == 0 &&
                  memcmp(record + 112u, &d8_bf_before, 180u) == 0 &&
                  memcmp(record + 292u, &d8_bf_after, 180u) == 0,
                  "engineering_record_offsets");
        d8_expect(memcmp(lane[0], raw[0], 640u) == 0 &&
                  memcmp(lane[1], raw[1], 640u) == 0 &&
                  memcmp(lane[2], filtered[0], 640u) == 0 &&
                  memcmp(lane[3], filtered[1], 640u) == 0 &&
                  memcmp(lane[4], out, 640u) == 0, "engineering_lane_records");
        d8_close();
        ++checks;
    }
    return checks;
}
static unsigned d8_engineering_errors(void) {
    unsigned checks = 0u;
    float bad = NAN, values[D1_FRAME] = {0.0f};
    ap_hpf_state_t h, saved_h;
    ap_beamformer_state_t b, saved_b;
    d8_sink sink = {NULL, 0u, 1024u};
    char buffer[64], memory[10];
    uint32_t parsed = 0u;
    d8_reset_counts();
    d8_finite(&bad, 1u);
    if (!d8_expected_error("nonfinite", 1u)) return 0u;
    ++checks;
    bad = INFINITY;
    d8_finite(&bad, 1u);
    if (!d8_expected_error("nonfinite", 1u)) return 0u;
    ++checks;
    ap_hpf_process(NULL, values, D1_FRAME, 0u);
    if (!d8_expected_error("hpf_geometry", 1u)) return 0u;
    ++checks;
    ap_beamformer_process(NULL, 1, values, values, values, D1_FRAME);
    if (!d8_expected_error("bf_geometry", 1u)) return 0u;
    ++checks;
    ap_agc_process_controlled(NULL, values, D1_FRAME, 1);
    if (!d8_expected_error("agc_geometry", 1u)) return 0u;
    ++checks;
    ap_hpf_init(&h, 16000u, 2u);
    d8_order = 1u;
    ap_hpf_process(&h, values, D1_FRAME, 0u);
    if (!d8_expected_error("hpf_channel_order", 1u)) return 0u;
    ++checks;
    ap_beamformer_init(&b, 16000u, 35.0f);
    memset(d8_hpf_output, 0, sizeof(d8_hpf_output));
    d8_hpf_calls = 2u;
    d8_order = 1u;
    ap_beamformer_process(&b, 1, values, values, values, D1_FRAME);
    if (!d8_expected_error("bf_order", 1u)) return 0u;
    ++checks;
    saved_b = b;
    d8_reset_counts();
    ap_beamformer_process(&b, 0, values, values, values, D1_FRAME);
    if (!d8_expected_error("track_direction", 1u) ||
        memcmp(&b, &saved_b, sizeof(b)) || d8_bf_calls != 0u) return 0u;
    ++checks;
    saved_h = h;
    d8_bf_calls = D8_MAX_FRAMES;
    ap_hpf_process(&h, values, D1_FRAME, 0u);
    if (!d8_expected_error("maximum_frames", 1u) ||
        memcmp(&h, &saved_h, sizeof(h))) return 0u;
    ++checks;
    if (!d8_room(D8_MAX_FRAMES - 1u) || d8_room(D8_MAX_FRAMES) ||
        !d8_expected_error("maximum_frames", 1u)) return 0u;
    ++checks;
    d8_expect(0, "first");
    d8_expect(0, "second");
    if (!d8_expected_error("first", 2u)) return 0u;
    ++checks;
    d8_memory_writes = 1;
    d8_write(&sink, values, sizeof(values));
    if (!d8_expected_error("write", 1u)) return 0u;
    ++checks;
    sink.file = fopen("/dev/full", "wb");
    if (!sink.file || setvbuf(sink.file, NULL, _IONBF, 0u)) return 0u;
    d8_write(&sink, values, sizeof(values));
    if (!d8_expected_error("write", 1u)) { fclose(sink.file); return 0u; }
    d8_close_sink(&sink);
    if (d8_errors) return 0u;
    ++checks;
    sink.file = fopen("/dev/full", "wb");
    if (!sink.file || setvbuf(sink.file, buffer, _IOFBF, sizeof(buffer))) return 0u;
    if (fputc('x', sink.file) == EOF) { fclose(sink.file); return 0u; }
    d8_close_sink(&sink);
    if (!d8_expected_error("close", 1u)) return 0u;
    ++checks;
    memset(memory, 0, sizeof(memory));
    sink.file = fmemopen(memory, sizeof(memory), "w+b");
    sink.limit = 8u;
    sink.bytes = 0u;
    if (!sink.file) return 0u;
    d8_write(&sink, values, 9u);
    if (!d8_expected_error("write_limit", 1u) || sink.bytes || ftell(sink.file) != 0L) {
        fclose(sink.file); return 0u;
    }
    ++checks;
    d8_write(&sink, values, 8u);
    if (d8_errors || sink.bytes != 8u || ftell(sink.file) != 8L) {
        fclose(sink.file); return 0u;
    }
    d8_write(&sink, values, 1u);
    if (!d8_expected_error("write_limit", 1u) || sink.bytes != 8u) {
        fclose(sink.file); return 0u;
    }
    d8_close_sink(&sink);
    if (d8_errors) return 0u;
    ++checks;
    d8_memory_writes = 0;
    /* O_EXCL must reject an existing target before opening or writing it. */
    d8_fd = AT_FDCWD;
    errno = 0;
    if (d8_open_file(&sink, "/dev/null", 1u)) { d8_close_sink(&sink); return 0u; }
    d8_fd = -1;
    if (errno != EEXIST) return 0u;
    ++checks;
    if (!d8_parse_frames("1", &parsed) || parsed != 1u ||
        !d8_parse_frames("629", &parsed) || parsed != 629u ||
        d8_parse_frames(NULL, &parsed) || d8_parse_frames("", &parsed) ||
        d8_parse_frames("0", &parsed) || d8_parse_frames("01", &parsed) ||
        d8_parse_frames("+1", &parsed) || d8_parse_frames("-1", &parsed) ||
        d8_parse_frames(" 1", &parsed) || d8_parse_frames("1 ", &parsed) ||
        d8_parse_frames("630", &parsed) || d8_parse_frames("1x", &parsed) ||
        d8_parse_frames("99999999999999999999999999999", &parsed)) return 0u;
    ++checks;
    ap_hpf_init(&h, 16000u, 1u);
    d8_check_hpf(&h);
    if (!d8_expected_error("hpf_channels", 1u)) return 0u;
    ++checks;
    ap_beamformer_init(&b, 16000u, 35.0f);
    b.lag = 4;
    d8_check_bf(&b);
    if (!d8_expected_error("bf_lag_geometry", 1u)) return 0u;
    ++checks;
    b.lag = 0;
    b.fallback_active = 2u;
    d8_check_bf(&b);
    if (!d8_expected_error("bf_route_geometry", 1u)) return 0u;
    ++checks;
    return checks;
}
static int d8_engineering(int candidate) {
    unsigned bf, agc, records, negatives;
    d8_self_test = 1;
    d8_reset_counts();
    d8_expect(d8_layout(), "layout");
    bf = d8_engineering_bf(candidate);
    agc = d8_engineering_agc();
    records = d8_engineering_records();
    if (d8_errors) {
        fprintf(stderr, "D8 engineering failure: %s\n", d8_first_error);
        return 12;
    }
    negatives = d8_engineering_errors();
    if (!negatives || d8_errors) {
        fprintf(stderr, "D8 engineering negative failed\n");
        return 12;
    }
    if (printf("{\"status\":\"PASS\",\"arm\":\"%s\",\"comparisons\":%u,"
           "\"equation_comparisons\":%u,\"equation_samples\":%u,"
           "\"agc_comparisons\":%u,\"record_comparisons\":%u,"
           "\"layout_checked\":true,\"negative_checks\":%u}\n",
           candidate ? "candidate" : "baseline", bf, bf, bf * D1_FRAME, agc, records, negatives) < 0 ||
        fflush(stdout)) return 12;
    return 0;
}
int main(int argc, char **argv) {
    int result;
    if (argc >= 2 && strcmp(argv[1], "--d8-self-test") == 0) {
        if (argc == 3 && strcmp(argv[2], "baseline") == 0) return d8_engineering(0);
        if (argc == 3 && strcmp(argv[2], "candidate") == 0) return d8_engineering(1);
        fprintf(stderr, "usage: --d8-self-test baseline|candidate\n");
        return 2;
    }
    if (!d8_parse_frames(getenv("AP_D8_EXPECTED_FRAMES"), &d8_expected_frames) ||
        !d8_open(getenv("AP_D8_STAGE_DIR"))) {
        fprintf(stderr, "D8 requires empty real AP_D8_STAGE_DIR, AP_D8_EXPECTED_FRAMES=1..629 and pinned ABI\n");
        d8_close();
        d8_close_sink(&d8_receipt);
        if (d8_fd >= 0) close(d8_fd);
        return 2;
    }
    result = ap_d8_d1_main(argc, argv);
    d8_expect(d8_bf_calls == d8_expected_frames && d8_bf_calls == d8_agc_calls &&
              d8_agc_calls == d1_agc_calls && d8_bf_calls > 0u &&
              d8_hpf_calls == 2u * d8_bf_calls && d8_order == 0u, "final_call_balance");
    d8_lengths();
    d8_close();
    if (close(d8_fd)) d8_expect(0, "directory_close");
    d8_fd = -1;
    if (!d8_write_receipt(result) || d8_errors) result = 12;
    return result;
}
