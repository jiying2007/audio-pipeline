/* Offline, same-state observation only. Never installed or linked into the SDK. */
#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "activity/ap_activity.h"
#include "aec/ap_aec.h"
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

/* Include the exact production parser, event delivery and PCM/JSONL writer. */
#define main ap_d1_production_main
#include "../../../examples/process_pcm.c"
#undef main

enum { D1_FRAME = 160, D1_LANES = 7 };
enum { D1_AEC_INPUT, D1_REFERENCE, D1_ECHO, D1_AEC_RESIDUAL,
       D1_NS_INPUT, D1_NS_OUTPUT, D1_AGC_OUTPUT };

static const char *const d1_names[D1_LANES] = {
    "aec_input", "reference", "echo", "aec_residual",
    "ns_input", "ns_output", "agc_output"
};
static FILE *d1_lanes[D1_LANES], *d1_control, *d1_receipt;
static uint64_t d1_lane_frames[D1_LANES];
static uint64_t d1_activity_calls, d1_aec_calls, d1_ns_calls, d1_agc_calls, d1_res_calls;
static uint64_t d1_errors;
static const char *d1_first_error = "";
static int d1_directory_fd = -1, d1_aec_expected = -1;
static int d1_aec_present, d1_aec_enabled, d1_far, d1_dt;
static int d1_ns_mode, d1_frequency, d1_frequency_active;
static float d1_mic_energy, d1_reference_energy, d1_mu, d1_identity_error;
static float d1_ns_floor, d1_res_gain, d1_noise_rms, d1_speech_probability;
static ap_activity_state_t d1_activity_before, d1_activity_after;
static float d1_saved_mic[D1_FRAME], d1_saved_echo[D1_FRAME];
static float d1_saved_residual[D1_FRAME], d1_saved_ns[D1_FRAME];

static void d1_expect(int condition, const char *reason) {
    if (!condition) {
        if (!d1_errors) d1_first_error = reason;
        ++d1_errors;
    }
}

static void d1_finite(float value, const char *reason) {
    d1_expect(isfinite(value), reason);
}

static void d1_write_lane(unsigned which, const float *samples, uint32_t count) {
    uint32_t i;
    d1_expect(count == D1_FRAME && samples != NULL, "lane_geometry");
    if (count != D1_FRAME || !samples) return;
    for (i = 0u; i < count; ++i) d1_finite(samples[i], "lane_nonfinite");
    if (fwrite(samples, sizeof(float), count, d1_lanes[which]) != count)
        d1_expect(0, "lane_write");
    ++d1_lane_frames[which];
}

void ap_activity_process_d1_real(ap_activity_state_t *, float, float, ap_activity_result_t *);
void ap_activity_process(ap_activity_state_t *state, float mic_energy,
                         float reference_energy, ap_activity_result_t *result) {
    d1_expect(d1_activity_calls == d1_ns_calls && d1_ns_calls == d1_agc_calls,
              "activity_order");
    d1_aec_present = 0;
    d1_identity_error = 0.0f;
    d1_mic_energy = mic_energy;
    d1_reference_energy = reference_energy;
    d1_activity_before = *state;
    ap_activity_process_d1_real(state, mic_energy, reference_energy, result);
    d1_activity_after = *state;
    d1_far = result->far_end_active;
    d1_dt = result->double_talk_active;
    d1_finite(mic_energy, "activity_mic_energy");
    d1_finite(reference_energy, "activity_reference_energy");
    d1_finite(state->smoothed_mic_energy, "activity_smoothed_mic");
    d1_finite(state->smoothed_reference_energy, "activity_smoothed_reference");
    d1_finite(state->far_end_threshold, "activity_far_threshold");
    d1_finite(state->double_talk_ratio, "activity_dt_ratio");
    d1_expect((d1_far == 0 || d1_far == 1) && (d1_dt == 0 || d1_dt == 1),
              "activity_boolean");
    ++d1_activity_calls;
}

void ap_aec_backend_process_d1_real(ap_aec_state_t *, int, float, uint32_t,
    const float *, const float *, float *, float *, int, int, ap_aec_result_t *);
void ap_aec_backend_process(ap_aec_state_t *state, int enabled, float mu, uint32_t count,
    const float *mic, const float *reference, float *out, float *echo,
    int far, int dt, ap_aec_result_t *result) {
    uint32_t i;
    d1_expect(d1_activity_calls == d1_agc_calls + 1u &&
              d1_ns_calls == d1_agc_calls && !d1_aec_present, "aec_order");
    d1_expect(far == d1_far && dt == d1_dt && enabled == 1, "aec_control");
    d1_expect(count == D1_FRAME, "aec_geometry");
    if (count == D1_FRAME) memcpy(d1_saved_mic, mic, sizeof(d1_saved_mic));
    d1_write_lane(D1_AEC_INPUT, mic, count);
    d1_write_lane(D1_REFERENCE, reference, count);
    ap_aec_backend_process_d1_real(state, enabled, mu, count,
                                   mic, reference, out, echo, far, dt, result);
    if (count == D1_FRAME) {
        for (i = 0u; i < count; ++i) {
            const float error = fabsf(d1_saved_mic[i] - (out[i] + echo[i]));
            d1_finite(error, "aec_identity_nonfinite");
            if (error > d1_identity_error) d1_identity_error = error;
            d1_expect(error <= 1.0e-6f, "aec_identity");
        }
        memcpy(d1_saved_echo, echo, sizeof(d1_saved_echo));
        memcpy(d1_saved_residual, out, sizeof(d1_saved_residual));
    }
    d1_write_lane(D1_ECHO, echo, count);
    d1_write_lane(D1_AEC_RESIDUAL, out, count);
    d1_aec_present = 1;
    d1_aec_enabled = enabled;
    d1_mu = mu;
    d1_finite(mu, "aec_mu");
    ++d1_aec_calls;
}

void ap_ns_process_d1_real(ap_ns_state_t *, ap_enhance_mode_t, float,
    const float *, const float *, float *, uint32_t, int, int, int, ap_ns_result_t *);
void ap_ns_process(ap_ns_state_t *state, ap_enhance_mode_t mode, float floor_gain,
    const float *in, const float *echo, float *out, uint32_t count,
    int frequency, int far, int dt, ap_ns_result_t *result) {
    d1_expect(d1_activity_calls == d1_ns_calls + 1u && d1_ns_calls == d1_agc_calls,
              "ns_order");
    d1_expect(count == D1_FRAME && echo != NULL, "ns_geometry");
    d1_expect(far == d1_far && dt == d1_dt, "ns_activity_control");
    if (d1_aec_expected < 0) d1_aec_expected = d1_aec_present;
    d1_expect(d1_aec_expected == d1_aec_present, "aec_presence_changed");
    d1_expect(frequency == d1_aec_present, "frequency_path");
    if (count == D1_FRAME && d1_aec_present && echo) {
        d1_expect(memcmp(in, d1_saved_residual, sizeof(d1_saved_residual)) == 0,
                  "aec_to_ns_residual");
        d1_expect(memcmp(echo, d1_saved_echo, sizeof(d1_saved_echo)) == 0,
                  "aec_to_ns_echo");
    }
    d1_write_lane(D1_NS_INPUT, in, count);
    ap_ns_process_d1_real(state, mode, floor_gain, in, echo, out, count,
                          frequency, far, dt, result);
    if (count == D1_FRAME) memcpy(d1_saved_ns, out, sizeof(d1_saved_ns));
    d1_write_lane(D1_NS_OUTPUT, out, count);
    d1_ns_mode = (int)mode;
    d1_ns_floor = floor_gain;
    d1_frequency = frequency;
    d1_frequency_active = result->frequency_res_active;
    d1_res_gain = result->residual_echo_gain;
    d1_noise_rms = result->noise_rms_dbfs;
    d1_speech_probability = result->speech_probability;
    d1_expect(d1_frequency_active ==
              (frequency && echo && mode != AP_ENHANCE_SAFE && far && !dt),
              "frequency_active_control");
    d1_finite(floor_gain, "ns_floor");
    d1_finite(d1_res_gain, "ns_res_gain");
    d1_finite(d1_noise_rms, "ns_noise_rms");
    d1_finite(d1_speech_probability, "ns_speech_probability");
    ++d1_ns_calls;
}

static void d1_write_control(int allow, float before, float after) {
    int failed = 0;
    failed |= fprintf(d1_control,
        "%" PRIu64 ",%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,"
        "%u,%u,%u,%u,%u,%d,%d,%d",
        d1_agc_calls, (double)d1_mic_energy, (double)d1_reference_energy,
        (double)d1_activity_before.smoothed_mic_energy,
        (double)d1_activity_before.smoothed_reference_energy,
        (double)d1_activity_after.smoothed_mic_energy,
        (double)d1_activity_after.smoothed_reference_energy,
        (double)d1_activity_after.far_end_threshold,
        (double)d1_activity_after.double_talk_ratio,
        d1_activity_after.hangover_frames,
        d1_activity_before.far_end_hangover, d1_activity_after.far_end_hangover,
        d1_activity_before.double_talk_hangover, d1_activity_after.double_talk_hangover,
        d1_far, d1_dt, d1_aec_present) < 0;
    if (d1_aec_present)
        failed |= fprintf(d1_control, ",%d,%.9g,%d,%.9g", d1_aec_enabled,
                          (double)d1_mu, d1_far && !d1_dt,
                          (double)d1_identity_error) < 0;
    else
        failed |= fprintf(d1_control, ",,,%d,", d1_far && !d1_dt) < 0;
    failed |= fprintf(d1_control, ",%d,%.9g,%d,%d,%.9g,%.9g,%.9g,%d,%.9g,%.9g\n",
        d1_ns_mode, (double)d1_ns_floor, d1_frequency, d1_frequency_active,
        (double)d1_res_gain, (double)d1_noise_rms, (double)d1_speech_probability,
        allow, (double)before, (double)after) < 0;
    d1_expect(!failed, "control_write");
}

void ap_agc_process_controlled_d1_real(ap_agc_state_t *, float *, uint32_t, int);
void ap_agc_process_controlled(ap_agc_state_t *state, float *samples,
                               uint32_t count, int allow) {
    const float before = state->gain;
    d1_expect(d1_activity_calls == d1_agc_calls + 1u && d1_ns_calls == d1_agc_calls + 1u,
              "agc_order");
    d1_expect(count == D1_FRAME, "agc_geometry");
    if (count == D1_FRAME)
        d1_expect(memcmp(samples, d1_saved_ns, sizeof(d1_saved_ns)) == 0, "ns_to_agc");
    d1_expect(allow == !(d1_far && !d1_dt), "agc_control");
    ap_agc_process_controlled_d1_real(state, samples, count, allow);
    d1_write_lane(D1_AGC_OUTPUT, samples, count);
    d1_finite(before, "agc_gain_before");
    d1_finite(state->gain, "agc_gain_after");
    d1_write_control(allow, before, state->gain);
    ++d1_agc_calls;
}

float ap_res_process_d1_real(ap_res_state_t *, ap_enhance_mode_t, float *,
    uint32_t, float, float, int, int);
float ap_res_process(ap_res_state_t *state, ap_enhance_mode_t mode, float *samples,
    uint32_t count, float echo_energy, float residual_energy, int far, int dt) {
    ++d1_res_calls;
    d1_expect(0, "unexpected_standalone_res");
    return ap_res_process_d1_real(state, mode, samples, count,
                                echo_energy, residual_energy, far, dt);
}

static FILE *d1_open_file(const char *name) {
    const int fd = openat(d1_directory_fd, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    FILE *stream;
    if (fd < 0) return NULL;
    stream = fdopen(fd, "wb");
    if (!stream) close(fd);
    return stream;
}

static int d1_open(const char *directory) {
    DIR *scan;
    struct dirent *entry;
    uint16_t endian = 1u;
    unsigned i;
    int duplicate, nonempty = 0;
    if (!directory || !*directory || sizeof(float) != 4u || FLT_RADIX != 2 ||
        FLT_MANT_DIG != 24 || FLT_MAX_EXP != 128 ||
        *(const unsigned char *)&endian != 1u) return 0;
    d1_directory_fd = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (d1_directory_fd < 0) return 0;
    duplicate = dup(d1_directory_fd);
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
    for (i = 0u; i < D1_LANES; ++i) {
        char name[64];
        const int written = snprintf(name, sizeof(name), "%s.f32le", d1_names[i]);
        if (written < 0 || (size_t)written >= sizeof(name)) return 0;
        d1_lanes[i] = d1_open_file(name);
        if (!d1_lanes[i]) return 0;
    }
    d1_control = d1_open_file("control.csv");
    d1_receipt = d1_open_file("observer.json");
    if (!d1_control || !d1_receipt) return 0;
    return fprintf(d1_control,
        "frame,mic_energy,reference_energy,smoothed_mic_before,smoothed_reference_before,"
        "smoothed_mic_after,smoothed_reference_after,far_threshold,double_talk_ratio,"
        "hangover_frames,far_hangover_before,far_hangover_after,dt_hangover_before,"
        "dt_hangover_after,far,dt,aec_present,aec_enabled,aec_mu,gate_eligible,"
        "aec_identity_max_abs_error,ns_mode,ns_floor,frequency_enabled,frequency_active,"
        "res_gain,noise_rms_dbfs,speech_probability,agc_allow,gain_before,gain_after\n") >= 0;
}

static void d1_close_traces(void) {
    unsigned i;
    for (i = 0u; i < D1_LANES; ++i) {
        if (d1_lanes[i] && fclose(d1_lanes[i])) d1_expect(0, "lane_close");
        d1_lanes[i] = NULL;
    }
    if (d1_control && fclose(d1_control)) d1_expect(0, "control_close");
    d1_control = NULL;
}

static int d1_write_receipt(int cli_result) {
    unsigned i;
    int failed = 0;
    const int valid = cli_result == 0 && d1_errors == 0u;
    if (!d1_receipt) return 0;
    failed |= fprintf(d1_receipt,
        "{\n  \"schema_version\": 1,\n  \"experiment\": \"FE-DUALMIC-STAGES-D1\",\n"
        "  \"status\": \"%s\",\n  \"source_revision\": \"%s\",\n"
        "  \"transformed_measurement_copy\": true,\n  \"frame_samples\": 160,\n"
        "  \"sample_format\": \"float32le\",\n  \"frames\": %" PRIu64 ",\n"
        "  \"capture_only\": %s,\n  \"cli_exit_code\": %d,\n"
        "  \"observer_error_count\": %" PRIu64 ",\n  \"first_error\": \"%s\",\n"
        "  \"calls\": {\"activity\": %" PRIu64 ", \"aec\": %" PRIu64
        ", \"ns\": %" PRIu64 ", \"agc\": %" PRIu64 ", \"res\": %" PRIu64 "},\n"
        "  \"gate_eligible_is_actual_adaptation_count\": false,\n  \"lanes\": {\n",
        valid ? "OBSERVED" : "INVALID", AP_BUILD_SOURCE_REVISION, d1_agc_calls,
        d1_aec_expected == 0 ? "true" : "false", cli_result, d1_errors, d1_first_error,
        d1_activity_calls, d1_aec_calls, d1_ns_calls, d1_agc_calls, d1_res_calls) < 0;
    for (i = 0u; i < D1_LANES; ++i) {
        const uint64_t frames = d1_lane_frames[i];
        failed |= fprintf(d1_receipt,
            "    \"%s\": {\"file\": \"%s.f32le\", \"present\": %s, "
            "\"frames\": %" PRIu64 ", \"samples\": %" PRIu64
            ", \"bytes\": %" PRIu64 ", \"offset_samples\": %u}%s\n",
            d1_names[i], d1_names[i], frames ? "true" : "false", frames,
            frames * D1_FRAME, frames * D1_FRAME * sizeof(float),
            i == D1_NS_OUTPUT || i == D1_AGC_OUTPUT ? D1_FRAME : 0u,
            i + 1u == D1_LANES ? "" : ",") < 0;
    }
    failed |= fprintf(d1_receipt, "  }\n}\n") < 0;
    if (fclose(d1_receipt)) failed = 1;
    d1_receipt = NULL;
    return !failed;
}

int main(int argc, char **argv) {
    int cli_result, result;
    unsigned i;
    if (!d1_open(getenv("AP_D1_STAGE_DIR"))) {
        fprintf(stderr, "D1 requires AP_D1_STAGE_DIR to be an existing empty real directory\n");
        d1_close_traces();
        if (d1_receipt) fclose(d1_receipt);
        if (d1_directory_fd >= 0) close(d1_directory_fd);
        return 2;
    }
    cli_result = ap_d1_production_main(argc, argv);
    d1_expect(d1_activity_calls == d1_ns_calls && d1_ns_calls == d1_agc_calls,
              "final_call_balance");
    d1_expect(d1_agc_calls > 0u, "no_observed_frames");
    d1_expect(d1_res_calls == 0u, "final_standalone_res");
    d1_expect(d1_aec_calls == (d1_aec_expected == 1 ? d1_agc_calls : 0u),
              "final_aec_balance");
    for (i = 0u; i < D1_LANES; ++i)
        d1_expect(d1_lane_frames[i] == (i < D1_NS_INPUT ? d1_aec_calls : d1_agc_calls),
                  "final_lane_balance");
    d1_close_traces();
    result = cli_result ? cli_result : (d1_errors ? 12 : 0);
    if (!d1_write_receipt(cli_result)) result = 12;
    if (close(d1_directory_fd) && result == 0) result = 12;
    return result;
}
