/* D7 read-only taps. This file is never installed or linked into the SDK. */
#define _POSIX_C_SOURCE 200809L
#include "frontend/ap_frontend.h"
#include <stddef.h>
/* Build-time copy renames only D1's final main, not its production CLI include. */
#include "dualmic_stages_d1.c"

enum { D7_LANES = 5, D7_RECORD = 472 };
static const char *const d7_names[D7_LANES] = {
    "hpf_input_l", "hpf_input_r", "hpf_output_l", "hpf_output_r", "bf_output"
};
static FILE *d7_lanes[D7_LANES], *d7_trace, *d7_receipt;
static int d7_fd = -1, d7_self_test;
static uint64_t d7_hpf_calls, d7_bf_calls, d7_errors;
static const char *d7_first_error = "";
static uint32_t d7_order;
static ap_hpf_state_t d7_hpf_before[2], d7_hpf_after[2];
static float d7_hpf_output[2][D1_FRAME];
static ap_beamformer_state_t d7_bf_before, d7_bf_after;

_Static_assert(sizeof(float) == 4, "D7 float size");
_Static_assert(sizeof(uint32_t) == 4 && sizeof(int) == 4, "D7 integer size");
_Static_assert(sizeof(ap_hpf_state_t) == 24, "D7 HPF state size");
_Static_assert(sizeof(ap_beamformer_state_t) == 180, "D7 BF state size");
_Static_assert(offsetof(ap_hpf_state_t, r) == 0, "D7 r offset");
_Static_assert(offsetof(ap_hpf_state_t, x) == 4, "D7 x offset");
_Static_assert(offsetof(ap_hpf_state_t, y) == 12, "D7 y offset");
_Static_assert(offsetof(ap_hpf_state_t, channels) == 20, "D7 channels offset");
_Static_assert(offsetof(ap_beamformer_state_t, history) == 0, "D7 history offset");
_Static_assert(offsetof(ap_beamformer_state_t, lag_score) == 64, "D7 lag_score offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_gain) == 132, "D7 fallback_gain offset");
_Static_assert(offsetof(ap_beamformer_state_t, lag) == 136, "D7 lag offset");
_Static_assert(offsetof(ap_beamformer_state_t, max_lag) == 140, "D7 max_lag offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_lag) == 144, "D7 fallback_lag offset");
_Static_assert(offsetof(ap_beamformer_state_t, counter) == 148, "D7 counter offset");
_Static_assert(offsetof(ap_beamformer_state_t, score_updates) == 152, "D7 score_updates offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_active) == 156, "D7 fallback_active offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_strong_channel) == 160, "D7 fallback_strong_channel offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_recovery_count) == 164, "D7 fallback_recovery_count offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_hard_fault) == 168, "D7 fallback_hard_fault offset");
_Static_assert(offsetof(ap_beamformer_state_t, fallback_hard_arm_count) == 172, "D7 fallback_hard_arm_count offset");
_Static_assert(offsetof(ap_beamformer_state_t, fixed_health_counter) == 176, "D7 fixed_health_counter offset");

static void d7_expect(int condition, const char *reason) {
    if (!condition) {
        if (!d7_errors) d7_first_error = reason;
        ++d7_errors;
    }
}
static void d7_finite(const float *values, uint32_t n) {
    uint32_t i;
    for (i = 0u; i < n; ++i) d7_expect(isfinite(values[i]), "nonfinite");
}
static void d7_write(FILE *stream, const void *data, size_t bytes) {
    if (!d7_self_test)
        d7_expect(stream != NULL && fwrite(data, 1u, bytes, stream) == bytes, "write");
}
static void d7_lane(unsigned lane, const float *values, uint32_t n) {
    d7_finite(values, n);
    d7_write(d7_lanes[lane], values, n * sizeof(float));
}
static void d7_check_hpf(const ap_hpf_state_t *state) {
    d7_finite(&state->r, 1u);
    d7_finite(state->x, 2u);
    d7_finite(state->y, 2u);
    d7_expect(state->channels == 2u, "hpf_channels");
}
static void d7_check_bf(const ap_beamformer_state_t *state) {
    d7_finite(state->history[0], AP_BF_HISTORY);
    d7_finite(state->history[1], AP_BF_HISTORY);
    d7_finite(state->lag_score, AP_BF_LAG_SCORE_COUNT);
    d7_finite(&state->fallback_gain, 1u);
}
void ap_hpf_process_d7_real(ap_hpf_state_t *, float *, uint32_t, uint32_t);
void ap_hpf_process(ap_hpf_state_t *state, float *values, uint32_t n, uint32_t channel) {
    d7_expect(state != NULL && values != NULL && n == D1_FRAME && channel < 2u, "hpf_geometry");
    if (!state || !values || n != D1_FRAME || channel >= 2u) return;
    d7_expect(d7_order == channel, "hpf_channel_order");
    if (!d7_self_test)
        d7_expect(d7_bf_calls == d1_agc_calls && d1_agc_calls == d1_activity_calls,
                  "upstream_before_activity");
    d7_hpf_before[channel] = *state;
    d7_check_hpf(state);
    d7_lane(channel, values, n);
    ap_hpf_process_d7_real(state, values, n, channel);
    d7_hpf_after[channel] = *state;
    d7_check_hpf(state);
    memcpy(d7_hpf_output[channel], values, sizeof(d7_hpf_output[channel]));
    d7_lane(channel + 2u, values, n);
    ++d7_hpf_calls;
    ++d7_order;
}
void ap_beamformer_process_d7_real(ap_beamformer_state_t *, int, float *, float *, float *, uint32_t);
void ap_beamformer_process(ap_beamformer_state_t *state, int track_direction,
                          float *left, float *right, float *out, uint32_t n) {
    uint32_t header[4];
    int32_t tracking = (int32_t)track_direction;
    d7_expect(state && left && right && out && n == D1_FRAME, "bf_geometry");
    if (!state || !left || !right || !out || n != D1_FRAME) return;
    d7_expect(d7_order == 2u && d7_hpf_calls == 2u * (d7_bf_calls + 1u), "bf_order");
    if (!d7_self_test)
        d7_expect(d1_activity_calls == d7_bf_calls && d1_ns_calls == d7_bf_calls &&
                  d1_agc_calls == d7_bf_calls, "bf_before_activity");
    d7_expect(memcmp(left, d7_hpf_output[0], sizeof(d7_hpf_output[0])) == 0 &&
              memcmp(right, d7_hpf_output[1], sizeof(d7_hpf_output[1])) == 0, "hpf_to_bf");
    d7_expect(track_direction == 0 || track_direction == 1, "track_direction");
    d7_bf_before = *state;
    d7_check_bf(state);
    header[0] = (uint32_t)d7_bf_calls;
    memcpy(&header[1], &tracking, sizeof(tracking));
    header[2] = (out == left ? 1u : 0u) | (out == right ? 2u : 0u);
    header[3] = n;
    ap_beamformer_process_d7_real(state, track_direction, left, right, out, n);
    d7_bf_after = *state;
    d7_check_bf(state);
    d7_lane(4u, out, n);
    d7_write(d7_trace, header, sizeof(header));
    d7_write(d7_trace, &d7_hpf_before[0], sizeof(ap_hpf_state_t));
    d7_write(d7_trace, &d7_hpf_after[0], sizeof(ap_hpf_state_t));
    d7_write(d7_trace, &d7_hpf_before[1], sizeof(ap_hpf_state_t));
    d7_write(d7_trace, &d7_hpf_after[1], sizeof(ap_hpf_state_t));
    d7_write(d7_trace, &d7_bf_before, sizeof(ap_beamformer_state_t));
    d7_write(d7_trace, &d7_bf_after, sizeof(ap_beamformer_state_t));
    ++d7_bf_calls;
    d7_order = 0u;
}
static FILE *d7_open_file(const char *name) {
    int fd = openat(d7_fd, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    FILE *stream;
    if (fd < 0) return NULL;
    stream = fdopen(fd, "wb");
    if (!stream) close(fd);
    return stream;
}
static int d7_layout(void) {
    const uint16_t endian = 1u;
    return sizeof(float) == 4u && sizeof(int) == 4u && FLT_RADIX == 2 &&
           FLT_MANT_DIG == 24 && FLT_MAX_EXP == 128 &&
           *(const unsigned char *)&endian == 1u &&
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
static int d7_open(const char *directory) {
    unsigned i;
    DIR *scan;
    struct dirent *entry;
    int duplicate, empty = 1;
    if (!directory || !*directory || !d7_layout()) return 0;
    d7_fd = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (d7_fd < 0) return 0;
    duplicate = dup(d7_fd);
    if (duplicate < 0) return 0;
    scan = fdopendir(duplicate);
    if (!scan) { close(duplicate); return 0; }
    errno = 0;
    while ((entry = readdir(scan)) != NULL)
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) empty = 0;
    if (errno) empty = 0;
    if (closedir(scan)) empty = 0;
    if (!empty) return 0;
    for (i = 0u; i < D7_LANES; ++i) {
        char name[64];
        int count = snprintf(name, sizeof(name), "%s.f32le", d7_names[i]);
        if (count < 0 || (size_t)count >= sizeof(name)) return 0;
        d7_lanes[i] = d7_open_file(name);
        if (!d7_lanes[i]) return 0;
    }
    d7_trace = d7_open_file("state.bin");
    d7_receipt = d7_open_file("observer.json");
    return d7_trace != NULL && d7_receipt != NULL;
}
static void d7_close(void) {
    unsigned i;
    for (i = 0u; i < D7_LANES; ++i) {
        if (d7_lanes[i] && fclose(d7_lanes[i])) d7_expect(0, "lane_close");
        d7_lanes[i] = NULL;
    }
    if (d7_trace && fclose(d7_trace)) d7_expect(0, "trace_close");
    d7_trace = NULL;
}
static int d7_write_receipt(int cli_result) {
    int failed;
    if (!d7_receipt) return 0;
    failed = fprintf(d7_receipt,
        "{\n \"experiment\": \"FE-DUALMIC-UPSTREAM-D7\", \"status\": \"%s\",\n"
        " \"source_revision\": \"%s\", \"frames\": %" PRIu64 ",\n"
        " \"hpf_calls\": %" PRIu64 ", \"bf_calls\": %" PRIu64 ",\n"
        " \"cli_exit_code\": %d, \"observer_error_count\": %" PRIu64 ", \"first_error\": \"%s\",\n"
        " \"layout_checked\": true, \"hpf_state_bytes\": %zu, \"bf_state_bytes\": %zu,\n"
        " \"hpf_state_offsets\": [%zu,%zu,%zu,%zu],\n"
        " \"bf_state_offsets\": [%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu,%zu],\n"
        " \"record_bytes\": %u, \"offset_samples\": 0, \"sample_format\": \"float32le\"\n}\n",
        cli_result == 0 && d7_errors == 0u ? "OBSERVED" : "INVALID",
        AP_BUILD_SOURCE_REVISION, d7_bf_calls, d7_hpf_calls, d7_bf_calls,
        cli_result, d7_errors, d7_first_error, sizeof(ap_hpf_state_t),
        sizeof(ap_beamformer_state_t),
        offsetof(ap_hpf_state_t, r),
        offsetof(ap_hpf_state_t, x),
        offsetof(ap_hpf_state_t, y),
        offsetof(ap_hpf_state_t, channels),
        offsetof(ap_beamformer_state_t, history),
        offsetof(ap_beamformer_state_t, lag_score),
        offsetof(ap_beamformer_state_t, fallback_gain),
        offsetof(ap_beamformer_state_t, lag),
        offsetof(ap_beamformer_state_t, max_lag),
        offsetof(ap_beamformer_state_t, fallback_lag),
        offsetof(ap_beamformer_state_t, counter),
        offsetof(ap_beamformer_state_t, score_updates),
        offsetof(ap_beamformer_state_t, fallback_active),
        offsetof(ap_beamformer_state_t, fallback_strong_channel),
        offsetof(ap_beamformer_state_t, fallback_recovery_count),
        offsetof(ap_beamformer_state_t, fallback_hard_fault),
        offsetof(ap_beamformer_state_t, fallback_hard_arm_count),
        offsetof(ap_beamformer_state_t, fixed_health_counter),
        (unsigned)D7_RECORD) < 0;
    if (fclose(d7_receipt)) failed = 1;
    d7_receipt = NULL;
    return !failed;
}
static int d7_expected_error(const char *reason, uint64_t count) {
    const int matched = d7_errors == count && strcmp(d7_first_error, reason) == 0;
    d7_errors = 0u;
    d7_first_error = "";
    return matched;
}
static int d7_engineering_errors(void) {
    float bad = NAN, values[D1_FRAME] = {0.0f};
    ap_hpf_state_t h;
    FILE *full;
    char buffer[64];
    d7_finite(&bad, 1u);
    if (!d7_expected_error("nonfinite", 1u)) return 0;
    ap_hpf_process(NULL, values, D1_FRAME, 0u);
    if (!d7_expected_error("hpf_geometry", 1u)) return 0;
    ap_beamformer_process(NULL, 1, values, values, values, D1_FRAME);
    if (!d7_expected_error("bf_geometry", 1u)) return 0;
    ap_hpf_init(&h, 16000u, 2u);
    d7_order = 0u;
    ap_hpf_process(&h, values, D1_FRAME, 1u);
    if (!d7_expected_error("hpf_channel_order", 1u)) return 0;
    d7_expect(0, "first");
    d7_expect(0, "second");
    if (!d7_expected_error("first", 2u)) return 0;
    d7_self_test = 0;
    d7_write(NULL, values, sizeof(values));
    if (!d7_expected_error("write", 1u)) return 0;
    full = fopen("/dev/full", "wb");
    if (!full || setvbuf(full, NULL, _IONBF, 0u)) return 0;
    d7_write(full, values, sizeof(values));
    if (!d7_expected_error("write", 1u)) { fclose(full); return 0; }
    if (fclose(full)) return 0;
    full = fopen("/dev/full", "wb");
    if (!full || setvbuf(full, buffer, _IOFBF, sizeof(buffer))) return 0;
    if (fputc('x', full) == EOF) { fclose(full); return 0; }
    d7_lanes[0] = full;
    d7_close();
    if (!d7_expected_error("lane_close", 1u)) return 0;
    d7_self_test = 1;
    return 1;
}
/* Engineering only: wrapper and real function receive byte-identical seeded
 * states. This is not the original-archive neutrality proof or quality data. */
static int d7_engineering(void) {
    unsigned mode, alias, route, iteration, channel, i, checks = 0u;
    int lag;
    d7_self_test = 1;
    d7_expect(d7_layout(), "layout");
    for (mode = 0u; mode < 2u; ++mode)
    for (alias = 0u; alias < 4u; ++alias)
    for (route = 0u; route < 3u; ++route)
    for (lag = -3; lag <= 3; ++lag) {
        ap_hpf_state_t h, reference_h;
        ap_beamformer_state_t b, reference_b;
        ap_hpf_init(&h, 16000u, 2u);
        ap_beamformer_init(&b, 16000u, 35.0f);
        b.lag = lag;
        b.fallback_lag = -lag;
        b.fallback_active = route != 0u;
        b.fallback_hard_fault = route == 2u;
        b.fallback_strong_channel = alias & 1u;
        b.fallback_gain = 0.8f;
        for (iteration = 0u; iteration < 5u; ++iteration) {
            float input[2][D1_FRAME], real_input[2][D1_FRAME];
            float output[D1_FRAME], real_output[D1_FRAME];
            float *observed, *expected;
            if (iteration == 3u) {
                ap_hpf_init(&h, 16000u, 2u);
                ap_beamformer_init(&b, 16000u, 35.0f);
            }
            reference_h = h;
            reference_b = b;
            for (channel = 0u; channel < 2u; ++channel)
                for (i = 0u; i < D1_FRAME; ++i)
                    input[channel][i] = (float)((int)((i * 17u + iteration * 11u + (alias == 3u ? 0u : channel * 3u)) % 113u) - 56) / 128.0f;
            memcpy(real_input, input, sizeof(input));
            for (channel = 0u; channel < 2u; ++channel) {
                ap_hpf_process(&h, input[channel], D1_FRAME, channel);
                ap_hpf_process_d7_real(&reference_h, real_input[channel], D1_FRAME, channel);
            }
            d7_expect(memcmp(&h, &reference_h, sizeof(h)) == 0 &&
                      memcmp(input, real_input, sizeof(input)) == 0, "engineering_hpf");
            observed = alias == 0u ? output : input[alias == 3u ? 0u : alias - 1u];
            expected = alias == 0u ? real_output : real_input[alias == 3u ? 0u : alias - 1u];
            ap_beamformer_process(&b, (int)mode, input[0], input[alias == 3u ? 0u : 1u], observed, D1_FRAME);
            ap_beamformer_process_d7_real(&reference_b, (int)mode, real_input[0], real_input[alias == 3u ? 0u : 1u], expected, D1_FRAME);
            d7_expect(memcmp(&b, &reference_b, sizeof(b)) == 0 &&
                      memcmp(observed, expected, sizeof(output)) == 0, "engineering_bf");
            ++checks;
        }
    }
    if (d7_errors) {
        fprintf(stderr, "D7 engineering failure: %s\n", d7_first_error);
        return 12;
    }
    if (!d7_engineering_errors()) {
        fprintf(stderr, "D7 engineering negative failed\n");
        return 12;
    }
    printf("{\"status\":\"PASS\",\"comparisons\":%u,\"layout_checked\":true,\"negative_checks\":8}\n", checks);
    return 0;
}
int main(int argc, char **argv) {
    int result;
    if (argc == 2 && strcmp(argv[1], "--d7-self-test") == 0) return d7_engineering();
    if (!d7_open(getenv("AP_D7_STAGE_DIR"))) {
        fprintf(stderr, "D7 requires a new empty real AP_D7_STAGE_DIR and the pinned ABI\n");
        d7_close();
        if (d7_receipt) fclose(d7_receipt);
        if (d7_fd >= 0) close(d7_fd);
        return 2;
    }
    result = ap_d7_d1_main(argc, argv);
    d7_expect(d7_bf_calls == d1_agc_calls && d7_bf_calls > 0u &&
              d7_hpf_calls == 2u * d7_bf_calls && d7_order == 0u, "final_call_balance");
    d7_close();
    if (!d7_write_receipt(result) || d7_errors) result = 12;
    if (close(d7_fd) && result == 0) result = 12;
    return result;
}
