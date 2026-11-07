/* D2 observes ordered gain views on one real AGC trajectory. No candidate DSP. */
#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "enhance/ap_enhance.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

enum { D2_FRAME = 160, D2_LANES = 4 };
static const char *const d2_lane_names[D2_LANES] = {
    "state_only", "gate_capped", "peak_capped", "replay_final"
};
static const char *const d2_difference_names[D2_LANES] = {
    "input_to_state_only", "state_to_gate", "gate_to_peak", "peak_to_final"
};
typedef struct d2_difference {
    int present;
    uint64_t frame;
    uint32_t sample, before_bits, after_bits;
} d2_difference_t;
typedef struct d2_mismatch {
    const char *kind;
    uint64_t frame;
    int sample;
    uint32_t actual_bits, expected_bits;
} d2_mismatch_t;

static FILE *d2_lanes[D2_LANES], *d2_csv, *d2_json;
static int d2_directory_fd = -1;
static uint64_t d2_input_frames, d2_frames, d2_calls, d2_resets, d2_errors;
static uint64_t d2_difference_counts[D2_LANES];
static uint64_t d2_target_gate_frames, d2_output_gate_frames, d2_peak_frames, d2_clamped_samples;
static d2_difference_t d2_first_differences[D2_LANES];
static d2_mismatch_t d2_first_mismatch;
static const char *d2_first_error = "";

static void d2_expect(int condition, const char *reason) {
    if (!condition) {
        if (!d2_errors) d2_first_error = reason;
        ++d2_errors;
    }
}

static uint32_t d2_bits(float value) {
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static int d2_match(float actual, float expected, const char *kind, int sample) {
    const uint32_t actual_bits = d2_bits(actual), expected_bits = d2_bits(expected);
    if (actual_bits == expected_bits) return 1;
    if (!d2_first_mismatch.kind) {
        d2_first_mismatch.kind = kind;
        d2_first_mismatch.frame = d2_frames;
        d2_first_mismatch.sample = sample;
        d2_first_mismatch.actual_bits = actual_bits;
        d2_first_mismatch.expected_bits = expected_bits;
    }
    d2_expect(0, kind);
    return 0;
}

static void d2_difference(unsigned which, uint32_t sample, float before, float after) {
    const uint32_t before_bits = d2_bits(before), after_bits = d2_bits(after);
    d2_difference_t *first = &d2_first_differences[which];
    if (before_bits == after_bits) return;
    ++d2_difference_counts[which];
    if (!first->present) {
        first->present = 1;
        first->frame = d2_frames;
        first->sample = sample;
        first->before_bits = before_bits;
        first->after_bits = after_bits;
    }
}

static float d2_clamp(float value, float low, float high) {
    return value < low ? low : (value > high ? high : value);
}

static uint32_t d2_u32le(const unsigned char *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8u) |
           ((uint32_t)bytes[2] << 16u) | ((uint32_t)bytes[3] << 24u);
}

static float d2_f32le(const unsigned char *bytes) {
    const uint32_t bits = d2_u32le(bytes);
    float value;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

static FILE *d2_input(const char *path, uint64_t *bytes) {
    struct stat status;
    FILE *stream;
    const int fd = open(path, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) return NULL;
    if (fstat(fd, &status) || !S_ISREG(status.st_mode) || status.st_size < 0) {
        close(fd);
        return NULL;
    }
    *bytes = (uint64_t)status.st_size;
    stream = fdopen(fd, "rb");
    if (!stream) close(fd);
    return stream;
}

static FILE *d2_output(const char *name) {
    const int fd = openat(d2_directory_fd, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    FILE *stream;
    if (fd < 0) return NULL;
    stream = fdopen(fd, "wb");
    if (!stream) close(fd);
    return stream;
}

static int d2_open_outputs(const char *path) {
    DIR *scan;
    struct dirent *entry;
    unsigned i;
    int duplicate, nonempty = 0;
    d2_directory_fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (d2_directory_fd < 0) return 0;
    duplicate = dup(d2_directory_fd);
    if (duplicate < 0) return 0;
    scan = fdopendir(duplicate);
    if (!scan) { close(duplicate); return 0; }
    errno = 0;
    while ((entry = readdir(scan)) != NULL) {
        if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..")) nonempty = 1;
    }
    if (errno) nonempty = 1;
    if (closedir(scan)) nonempty = 1;
    if (nonempty) return 0;
    for (i = 0u; i < D2_LANES; ++i) {
        char name[64];
        const int length = snprintf(name, sizeof(name), "%s.f32le", d2_lane_names[i]);
        if (length < 0 || (size_t)length >= sizeof(name)) return 0;
        d2_lanes[i] = d2_output(name);
        if (!d2_lanes[i]) return 0;
    }
    d2_csv = d2_output("gain.csv");
    d2_json = d2_output("gain.json");
    if (!d2_csv || !d2_json) return 0;
    return fprintf(d2_csv,
        "frame,allow,reset,input_rms,input_peak,target_linear,limiter_linear,"
        "target_gain_raw,target_gain_bounded,target_gain,alpha,state_gain_before,"
        "state_gain_after,expected_state_gain_after,reference_gain_before,reference_gain_after,"
        "gate_cap_gain,peak_limit_gain,applied_gain,target_gate_cap_active,output_gate_cap_active,"
        "peak_cap_active,final_sample_clamp_count,state_gain_before_match,state_gain_after_match,"
        "formula_state_after_match,final_match,formula_final_match,state_only_peak,"
        "gate_capped_peak,peak_capped_peak,replay_final_peak\n") >= 0;
}

static void d2_close_outputs(void) {
    unsigned i;
    for (i = 0u; i < D2_LANES; ++i) {
        if (d2_lanes[i] && fclose(d2_lanes[i])) d2_expect(0, "lane_close");
        d2_lanes[i] = NULL;
    }
    if (d2_csv && fclose(d2_csv)) d2_expect(0, "csv_close");
    d2_csv = NULL;
}

static void d2_frame(ap_agc_state_t *state, const float *input, const float *reference,
                     uint32_t allow, uint32_t reset, float reference_before, float reference_after) {
    float views[D2_LANES][D2_FRAME], peaks[D2_LANES] = {0.0f};
    float energy = 1.0e-12f, peak = 0.0f, rms;
    float raw_target, bounded_target, target, alpha, predicted_after, gate_gain, applied_gain;
    float peak_limit_gain = 0.0f;
    const float before = state->gain;
    const float target_linear = state->target_linear, limit = state->limiter_linear;
    int before_match, after_match, formula_match, final_match = 1, formula_final_match = 1;
    int target_cap, output_cap, peak_cap = 0, failed;
    uint32_t clamped = 0u, i, lane;
    for (i = 0u; i < D2_FRAME; ++i) {
        const float amplitude = fabsf(input[i]);
        d2_expect(isfinite(input[i]) && isfinite(reference[i]), "nonfinite_input_or_reference");
        energy += input[i] * input[i];
        if (amplitude > peak) peak = amplitude;
    }
    d2_expect(isfinite(reference_before) && isfinite(reference_after) &&
              isfinite(before) && isfinite(target_linear) && isfinite(limit) &&
              isfinite(energy), "nonfinite_state_or_energy");
    before_match = d2_match(before, reference_before, "state_before_mismatch", -1);
    if (d2_errors) return;

    /* Observational arithmetic mirrors the original statement order only.
     * It is never fed back into the actual AGC state or control arguments. */
    rms = sqrtf(energy / (float)D2_FRAME);
    raw_target = target_linear / (rms + 1.0e-6f);
    bounded_target = d2_clamp(raw_target, 0.25f, 8.0f);
    target = bounded_target;
    target_cap = !allow && target > 1.0f;
    if (target_cap) target = 1.0f;
    alpha = target < before ? 0.25f : 0.015f;
    predicted_after = before;
    predicted_after += alpha * (target - predicted_after);
    d2_expect(isfinite(rms) && isfinite(raw_target) && isfinite(predicted_after),
              "nonfinite_reconstruction");
    if (d2_errors) return;

    memcpy(views[3], input, sizeof(views[3]));
    ap_agc_process_controlled(state, views[3], D2_FRAME, (int)allow);
    ++d2_calls;
    after_match = d2_match(state->gain, reference_after, "state_after_mismatch", -1);
    formula_match = d2_match(state->gain, predicted_after, "formula_state_mismatch", -1);
    d2_expect(d2_bits(state->target_linear) == d2_bits(target_linear) &&
              d2_bits(state->limiter_linear) == d2_bits(limit), "agc_configuration_changed");

    gate_gain = state->gain;
    output_cap = !allow && gate_gain > 1.0f;
    if (output_cap) gate_gain = 1.0f;
    applied_gain = gate_gain;
    if (peak > 1.0e-6f) peak_limit_gain = limit / peak;
    if (peak * applied_gain > limit && peak > 1.0e-6f) {
        applied_gain = limit / peak;
        peak_cap = 1;
    }
    for (i = 0u; i < D2_FRAME; ++i) {
        float reconstructed_final;
        views[0][i] = input[i] * state->gain;
        views[1][i] = input[i] * gate_gain;
        views[2][i] = input[i] * applied_gain;
        reconstructed_final = d2_clamp(views[2][i], -limit, limit);
        if (d2_bits(reconstructed_final) != d2_bits(views[2][i])) ++clamped;
        final_match &= d2_match(views[3][i], reference[i], "reference_final_mismatch", (int)i);
        formula_final_match &= d2_match(views[3][i], reconstructed_final,
                                        "formula_final_mismatch", (int)i);
        for (lane = 0u; lane < D2_LANES; ++lane) {
            const float amplitude = fabsf(views[lane][i]);
            d2_expect(isfinite(views[lane][i]), "nonfinite_view");
            if (amplitude > peaks[lane]) peaks[lane] = amplitude;
            d2_difference(lane, i, lane ? views[lane - 1u][i] : input[i], views[lane][i]);
        }
    }
    for (lane = 0u; lane < D2_LANES; ++lane)
        d2_expect(fwrite(views[lane], sizeof(float), D2_FRAME, d2_lanes[lane]) == D2_FRAME,
                  "lane_write");
    failed = fprintf(d2_csv,
        "%" PRIu64 ",%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,"
        "%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,",
        d2_frames, allow, reset, (double)rms, (double)peak, (double)target_linear,
        (double)limit, (double)raw_target, (double)bounded_target, (double)target,
        (double)alpha, (double)before, (double)state->gain, (double)predicted_after,
        (double)reference_before, (double)reference_after, (double)gate_gain) < 0;
    if (peak > 1.0e-6f) failed |= fprintf(d2_csv, "%.9g", (double)peak_limit_gain) < 0;
    failed |= fprintf(d2_csv, ",%.9g,%d,%d,%d,%u,%d,%d,%d,%d,%d,%.9g,%.9g,%.9g,%.9g\n",
        (double)applied_gain, target_cap, output_cap, peak_cap, clamped,
        before_match, after_match, formula_match, final_match, formula_final_match,
        (double)peaks[0], (double)peaks[1], (double)peaks[2], (double)peaks[3]) < 0;
    d2_expect(!failed, "csv_write");
    d2_target_gate_frames += (uint64_t)target_cap;
    d2_output_gate_frames += (uint64_t)output_cap;
    d2_peak_frames += (uint64_t)peak_cap;
    d2_clamped_samples += clamped;
    ++d2_frames;
}

static int d2_receipt(const char *profile, const ap_config_t *config) {
    const ap_build_info_t *info = ap_build_info();
    unsigned i;
    int failed = 0;
    const int valid = !d2_errors && d2_frames == d2_input_frames && d2_calls == d2_frames;
    if (!d2_json || !info || !info->source_revision) return 0;
    failed |= fprintf(d2_json,
        "{\n  \"schema_version\": 1,\n  \"experiment\": \"FE-DUALMIC-GAIN-D2\",\n"
        "  \"status\": \"%s\",\n  \"profile\": \"%s\",\n  \"source_revision\": \"%s\",\n"
        "  \"sample_format\": \"float32le\",\n  \"frame_samples\": 160,\n  \"offset_samples\": 160,\n"
        "  \"input_frames\": %" PRIu64 ",\n  \"frames\": %" PRIu64 ",\n"
        "  \"agc_calls\": %" PRIu64 ",\n  \"reset_count\": %" PRIu64 ",\n"
        "  \"target_dbfs\": %.9g,\n  \"limiter_dbfs\": %.9g,\n"
        "  \"error_count\": %" PRIu64 ",\n  \"first_error\": \"%s\",\n  \"first_mismatch\": ",
        valid ? "REPLAY_EXACT" : "MEASUREMENT_INVALID", profile, info->source_revision,
        d2_input_frames, d2_frames, d2_calls, d2_resets,
        (double)config->agc_target_dbfs, (double)config->limiter_dbfs, d2_errors, d2_first_error) < 0;
    if (d2_first_mismatch.kind) {
        const d2_mismatch_t *m = &d2_first_mismatch;
        failed |= fprintf(d2_json, "{\"kind\": \"%s\", \"frame\": %" PRIu64
            ", \"sample_in_frame\": ", m->kind, m->frame) < 0;
        if (m->sample < 0) failed |= fprintf(d2_json, "null, \"global_sample\": null") < 0;
        else failed |= fprintf(d2_json, "%d, \"global_sample\": %" PRIu64,
                                m->sample, m->frame * D2_FRAME + (uint32_t)m->sample) < 0;
        failed |= fprintf(d2_json, ", \"actual_bits\": \"0x%08" PRIx32
            "\", \"expected_bits\": \"0x%08" PRIx32 "\"}", m->actual_bits, m->expected_bits) < 0;
    } else failed |= fprintf(d2_json, "null") < 0;
    failed |= fprintf(d2_json, ",\n  \"first_differences\": {\n") < 0;
    for (i = 0u; i < D2_LANES; ++i) {
        const d2_difference_t *d = &d2_first_differences[i];
        failed |= fprintf(d2_json, "    \"%s\": ", d2_difference_names[i]) < 0;
        if (!d->present) failed |= fprintf(d2_json, "null") < 0;
        else failed |= fprintf(d2_json,
            "{\"frame\": %" PRIu64 ", \"sample_in_frame\": %u, \"global_sample\": %" PRIu64
            ", \"before_bits\": \"0x%08" PRIx32 "\", \"after_bits\": \"0x%08" PRIx32 "\"}",
            d->frame, d->sample, d->frame * D2_FRAME + d->sample,
            d->before_bits, d->after_bits) < 0;
        failed |= fprintf(d2_json, "%s\n", i + 1u == D2_LANES ? "" : ",") < 0;
    }
    failed |= fprintf(d2_json, "  },\n  \"difference_sample_counts\": {\n") < 0;
    for (i = 0u; i < D2_LANES; ++i)
        failed |= fprintf(d2_json, "    \"%s\": %" PRIu64 "%s\n", d2_difference_names[i],
                          d2_difference_counts[i], i + 1u == D2_LANES ? "" : ",") < 0;
    failed |= fprintf(d2_json,
        "  },\n  \"cap_counts\": {\"target_gate_frames\": %" PRIu64
        ", \"output_gate_frames\": %" PRIu64 ", \"peak_limit_frames\": %" PRIu64
        ", \"clamped_samples\": %" PRIu64 "},\n  \"lanes\": {\n",
        d2_target_gate_frames, d2_output_gate_frames, d2_peak_frames, d2_clamped_samples) < 0;
    for (i = 0u; i < D2_LANES; ++i)
        failed |= fprintf(d2_json,
            "    \"%s\": {\"file\": \"%s.f32le\", \"frames\": %" PRIu64
            ", \"samples\": %" PRIu64 ", \"bytes\": %" PRIu64 ", \"offset_samples\": 160}%s\n",
            d2_lane_names[i], d2_lane_names[i], d2_frames, d2_frames * D2_FRAME,
            d2_frames * D2_FRAME * sizeof(float), i + 1u == D2_LANES ? "" : ",") < 0;
    failed |= fprintf(d2_json, "  }\n}\n") < 0;
    if (fclose(d2_json)) failed = 1;
    d2_json = NULL;
    return !failed;
}

int main(int argc, char **argv) {
    ap_config_t config;
    ap_agc_state_t state;
    FILE *input = NULL, *reference = NULL, *control = NULL;
    uint64_t input_bytes = 0u, reference_bytes = 0u, control_bytes = 0u;
    uint16_t endian = 1u;
    int result = 2, outputs_open = 0;
    if (argc != 7 || strcmp(argv[1], "--profile") ||
        (strcmp(argv[2], "call") && strcmp(argv[2], "assistant"))) {
        fprintf(stderr, "usage: %s --profile call|assistant input.f32le reference-final.f32le control.bin empty-output-directory\n", argv[0]);
        return 2;
    }
    if (sizeof(float) != 4u || sizeof(uint32_t) != 4u || FLT_RADIX != 2 ||
        FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128 || FLT_EVAL_METHOD != 0 ||
        *(const unsigned char *)&endian != 1u) return 2;
    config = ap_config_default(strcmp(argv[2], "call") == 0 ? AP_PROFILE_CALL : AP_PROFILE_ASSISTANT);
    if (config.internal_sample_rate_hz != 16000u || !isfinite(config.agc_target_dbfs) ||
        !isfinite(config.limiter_dbfs)) return 2;
    input = d2_input(argv[3], &input_bytes);
    reference = d2_input(argv[4], &reference_bytes);
    control = d2_input(argv[5], &control_bytes);
    if (!input || !reference || !control || input_bytes == 0u || input_bytes % (D2_FRAME * 4u) ||
        reference_bytes != input_bytes || control_bytes != (input_bytes / (D2_FRAME * 4u)) * 16u)
        goto done;
    d2_input_frames = input_bytes / (D2_FRAME * 4u);
    if (!d2_open_outputs(argv[6])) goto done;
    outputs_open = 1;
    ap_agc_init(&state, config.agc_target_dbfs, config.limiter_dbfs);
    while (d2_frames < d2_input_frames && !d2_errors) {
        float samples[D2_FRAME], expected[D2_FRAME], before, after;
        unsigned char record[16];
        uint32_t allow, reset;
        if (fread(samples, sizeof(float), D2_FRAME, input) != D2_FRAME ||
            fread(expected, sizeof(float), D2_FRAME, reference) != D2_FRAME ||
            fread(record, 1u, sizeof(record), control) != sizeof(record)) {
            d2_expect(0, "truncated_frame");
            break;
        }
        allow = d2_u32le(record);
        reset = d2_u32le(record + 4u);
        before = d2_f32le(record + 8u);
        after = d2_f32le(record + 12u);
        d2_expect(allow <= 1u && reset <= 1u, "invalid_control_flag");
        if (d2_errors) break;
        if (reset) {
            ap_agc_init(&state, config.agc_target_dbfs, config.limiter_dbfs);
            ++d2_resets;
        }
        d2_frame(&state, samples, expected, allow, reset, before, after);
    }
    if (!d2_errors) {
        d2_expect(fgetc(input) == EOF && !ferror(input), "input_trailing_or_read_error");
        d2_expect(fgetc(reference) == EOF && !ferror(reference), "reference_trailing_or_read_error");
        d2_expect(fgetc(control) == EOF && !ferror(control), "control_trailing_or_read_error");
    }
    d2_expect(d2_frames == d2_input_frames && d2_calls == d2_frames, "incomplete_replay");
    result = d2_errors ? 12 : 0;
done:
    if (input && fclose(input)) d2_expect(0, "input_close");
    if (reference && fclose(reference)) d2_expect(0, "reference_close");
    if (control && fclose(control)) d2_expect(0, "control_close");
    d2_close_outputs();
    if (outputs_open) {
        if (d2_errors) result = 12;
        if (!d2_receipt(argv[2], &config)) result = 12;
    } else if (d2_json) {
        fclose(d2_json);
        d2_json = NULL;
    }
    if (d2_directory_fd >= 0 && close(d2_directory_fd) && result == 0) result = 12;
    if (result) fprintf(stderr, "D2 measurement failed: %s\n", *d2_first_error ? d2_first_error : "input_or_output_contract");
    return result;
}
