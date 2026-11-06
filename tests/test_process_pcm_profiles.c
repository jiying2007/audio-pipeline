/* Test the actual offline CLI against direct API processing and effective
 * configuration read-back. These are host integration contracts, not acoustic
 * quality or physical-target evidence. */
#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { CAPTURE, RENDER, OUTPUT, METRICS, STREAMS, TEST_FRAMES = 20 };
enum { PCM_CAPACITY = AP_MAX_IO_FRAME_SAMPLES * TEST_FRAMES,
       TEXT_CAPACITY = 16384 };
typedef struct run_result {
    int status;
    unsigned opens;
    unsigned inits;
    unsigned processed;
    ap_config_t initialized;
    ap_config_t effective;
    ap_tuning_t tuning;
    int16_t pcm[PCM_CAPACITY];
    size_t samples;
    char metrics[TEXT_CAPACITY];
    char printed[TEXT_CAPACITY];
} run_result_t;

static FILE *streams[STREAMS];
static unsigned closes[STREAMS];
static run_result_t *observed;
static FILE *profile_fopen(const char *path, const char *mode);
static int profile_fclose(FILE *stream);
static ap_status_t profile_init(void *storage, size_t size,
                                const ap_config_t *config,
                                ap_pipeline_t **pipeline);
static ap_status_t profile_process(ap_pipeline_t *pipeline, const int16_t *mic,
                                   size_t frames, int16_t *output);

#define main profile_cli_main
#define fopen profile_fopen
#define fclose profile_fclose
#define ap_pipeline_init profile_init
#define ap_pipeline_process_capture profile_process
#include "../examples/process_pcm.c"
#undef ap_pipeline_process_capture
#undef ap_pipeline_init
#undef fclose
#undef fopen
#undef main

static FILE *profile_fopen(const char *path, const char *mode) {
    static const char *names[] = {"capture", "render", "output", "metrics"};
    unsigned index;
    (void)mode;
    for (index = 0u; index < STREAMS; ++index)
        if (strcmp(path, names[index]) == 0) break;
    assert(index < STREAMS && streams[index] != NULL && closes[index] == 0u);
    observed->opens++;
    return streams[index];
}

static int profile_fclose(FILE *stream) {
    unsigned index;
    for (index = 0u; index < STREAMS; ++index)
        if (stream == streams[index]) break;
    assert(index < STREAMS && closes[index] == 0u);
    closes[index]++;
    /* Retain the ordinary temporary stream for inspection after the CLI
     * returns. Error/close-failure behavior is covered by the existing IO test. */
    return fflush(stream);
}

static ap_status_t profile_init(void *storage, size_t size,
                                const ap_config_t *config,
                                ap_pipeline_t **pipeline) {
    const ap_status_t status = ap_pipeline_init(storage, size, config, pipeline);
    observed->inits++;
    if (status == AP_OK)
        assert(ap_pipeline_get_config(*pipeline, &observed->initialized) == AP_OK);
    return status;
}

static ap_status_t profile_process(ap_pipeline_t *pipeline, const int16_t *mic,
                                   size_t frames, int16_t *output) {
    assert(ap_pipeline_get_config(pipeline, &observed->effective) == AP_OK);
    assert(ap_pipeline_get_tuning(pipeline, &observed->tuning) == AP_OK);
    observed->processed++;
    return ap_pipeline_process_capture(pipeline, mic, frames, output);
}

static void read_text(FILE *stream, char *text, size_t capacity) {
    size_t count;
    assert(fflush(stream) == 0 && fseek(stream, 0L, SEEK_SET) == 0);
    count = fread(text, 1u, capacity - 1u, stream);
    assert(!ferror(stream) && feof(stream));
    text[count] = '\0';
}

static void run_cli(char **arguments, int argc, const int16_t *capture,
                    size_t capture_samples, const int16_t *render,
                    size_t render_samples, run_result_t *result) {
    FILE *printed = tmpfile();
    FILE *diagnostics = tmpfile();
    int saved_stdout;
    int saved_stderr;
    assert(printed != NULL && diagnostics != NULL);
    memset(result, 0, sizeof(*result));
    memset(closes, 0, sizeof(closes));
    observed = result;
    for (unsigned i = 0u; i < STREAMS; ++i) {
        streams[i] = tmpfile();
        assert(streams[i] != NULL);
    }
    assert(fwrite(capture, sizeof(int16_t), capture_samples, streams[CAPTURE]) == capture_samples);
    assert(fwrite(render, sizeof(int16_t), render_samples, streams[RENDER]) == render_samples);
    assert(fseek(streams[CAPTURE], 0L, SEEK_SET) == 0);
    assert(fseek(streams[RENDER], 0L, SEEK_SET) == 0);
    assert(fflush(stdout) == 0 && fflush(stderr) == 0);
    saved_stdout = dup(STDOUT_FILENO);
    saved_stderr = dup(STDERR_FILENO);
    assert(saved_stdout >= 0 && saved_stderr >= 0);
    assert(dup2(fileno(printed), STDOUT_FILENO) >= 0);
    assert(dup2(fileno(diagnostics), STDERR_FILENO) >= 0);
    result->status = profile_cli_main(argc, arguments);
    assert(fflush(stdout) == 0 && fflush(stderr) == 0);
    assert(dup2(saved_stdout, STDOUT_FILENO) >= 0);
    assert(dup2(saved_stderr, STDERR_FILENO) >= 0);
    assert(close(saved_stdout) == 0 && close(saved_stderr) == 0);
    read_text(printed, result->printed, sizeof(result->printed));
    read_text(streams[METRICS], result->metrics, sizeof(result->metrics));
    assert(fseek(streams[OUTPUT], 0L, SEEK_SET) == 0);
    result->samples = fread(result->pcm, sizeof(int16_t), PCM_CAPACITY, streams[OUTPUT]);
    assert(!ferror(streams[OUTPUT]));
    assert(fgetc(streams[OUTPUT]) == EOF);
    for (unsigned i = 0u; i < STREAMS; ++i) assert(fclose(streams[i]) == 0);
    assert(fclose(printed) == 0 && fclose(diagnostics) == 0);
}

static void assert_config(const ap_config_t *actual, const ap_config_t *expected) {
#define CHECK(field) assert(actual->field == expected->field)
    CHECK(io_sample_rate_hz); CHECK(internal_sample_rate_hz); CHECK(mic_channels);
    CHECK(mic_spacing_mm); CHECK(aec_filter_ms); CHECK(max_delay_ms); CHECK(initial_delay_ms);
    CHECK(aec_mu); CHECK(aec_adapt_stride); CHECK(ns_floor); CHECK(agc_target_dbfs);
    CHECK(limiter_dbfs); CHECK(resource_class); CHECK(stages);
    CHECK(enable_delay_tracking); CHECK(enable_clock_drift_compensation);
#undef CHECK
}

static void fill_input(int16_t *capture, int16_t *render, size_t samples) {
    /* Unequal channels, speech-scale variation and broadband reference exercise
     * real BF/AEC/NS/AGC state beyond startup. No acoustic score is inferred. */
    for (size_t n = 0u; n < samples; ++n) {
        const int reference = (int)((n * 7919u) % 12001u) - 6000;
        const int speech = (int)((n * 431u) % 8001u) - 4000;
        render[n] = (int16_t)reference;
        capture[2u * n] = (int16_t)(speech + reference / 3);
        capture[2u * n + 1u] = (int16_t)(speech + reference / 4);
    }
}

static void assert_direct(const run_result_t *result, ap_config_t config,
                          const int16_t *capture, const int16_t *render,
                          size_t render_samples, int capture_only, int override) {
    _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
    static unsigned char storage[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t expected[PCM_CAPACITY];
    int16_t padded[AP_MAX_IO_FRAME_SAMPLES];
    ap_pipeline_t *pipeline = NULL;
    const size_t frame = ap_pipeline_io_frame_samples(&config);
    unsigned trace_frames = 0u;
    int nonzero = 0;
    if (capture_only) {
        config.stages &= ~(AP_STAGE_SYNC | AP_STAGE_AEC | AP_STAGE_RES);
        config.enable_delay_tracking = 0u;
        config.enable_clock_drift_compensation = 0u;
    }
    assert_config(&result->initialized, &config);
    assert(ap_pipeline_init(storage, sizeof(storage), &config, &pipeline) == AP_OK);
    if (override) {
        ap_tuning_t tuning = {0};
        tuning.struct_size = sizeof(tuning);
        tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
        tuning.mask = AP_TUNING_NS_FLOOR;
        tuning.ns_floor = 0.25f;
        assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_OK);
        config.ns_floor = tuning.ns_floor;
    }
    assert_config(&result->effective, &config);
    assert(result->tuning.mask == (AP_TUNING_AEC_MU | AP_TUNING_NS_FLOOR |
                                   AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER));
    assert(result->tuning.aec_mu == config.aec_mu);
    assert(result->tuning.ns_floor == config.ns_floor);
    assert(result->tuning.agc_target_dbfs == config.agc_target_dbfs);
    assert(result->tuning.limiter_dbfs == config.limiter_dbfs);
    for (size_t i = 0u; i < TEST_FRAMES; ++i) {
        if (!capture_only) {
            size_t count = render_samples > i * frame ? render_samples - i * frame : 0u;
            if (count > frame) count = frame;
            memset(padded, 0, frame * sizeof(padded[0]));
            if (count) memcpy(padded, render + i * frame, count * sizeof(padded[0]));
            assert(ap_pipeline_push_render(pipeline, padded, frame) == AP_OK);
        }
        assert(ap_pipeline_process_capture(pipeline, capture + 2u * i * frame,
                                            frame, expected + i * frame) == AP_OK);
    }
    assert(result->status == 0 && result->inits == 1u && result->processed == TEST_FRAMES);
    assert(result->samples == TEST_FRAMES * frame);
    assert(memcmp(result->pcm, expected, result->samples * sizeof(int16_t)) == 0);
    for (size_t i = 0u; i < result->samples; ++i)
        if (expected[i] != 0) nonzero = 1;
    assert(nonzero);
    for (const char *line = result->metrics; *line;) {
        unsigned index = UINT32_MAX;
        assert(sscanf(line, "{\"frame\":%u", &index) == 1 && index == trace_frames);
        trace_frames++;
        line = strchr(line, '\n');
        assert(line != NULL);
        line++;
    }
    assert(trace_frames == TEST_FRAMES);
}

static void test_profiles(void) {
    static int16_t capture[PCM_CAPACITY * 2u];
    static int16_t render[PCM_CAPACITY];
    static run_result_t result, legacy, ordered;
    const uint32_t rates[] = {8000u, 16000u};
    const char *names[] = {"call", "assistant"};
    unsigned runs = 0u;
    for (unsigned p = 0u; p < 2u; ++p) {
        for (unsigned r = 0u; r < 2u; ++r) {
            ap_config_t config = ap_config_default((ap_profile_t)p);
            char rate[16];
            size_t samples;
            if (rates[r] > AP_BUILD_MAX_IO_RATE_HZ) continue;
            config.io_sample_rate_hz = rates[r];
            config.mic_channels = 2u;
            assert(config.aec_mu == (p ? 0.18f : 0.22f));
            assert(config.ns_floor == (p ? 0.18f : 0.12f));
            assert(config.agc_target_dbfs == (p ? -18.0f : -20.0f));
            assert(config.limiter_dbfs == -2.0f);
            assert(config.aec_filter_ms ==
                   ((p ? 80u : 96u) < AP_BUILD_MAX_AEC_TAIL_MS ?
                    (p ? 80u : 96u) : AP_BUILD_MAX_AEC_TAIL_MS));
            (void)snprintf(rate, sizeof(rate), "%u", rates[r]);
            samples = ap_pipeline_io_frame_samples(&config) * TEST_FRAMES;
            fill_input(capture, render, samples);
            for (unsigned mode = 0u; mode < 4u; ++mode) {
                const int capture_only = mode == 0u;
                const size_t render_samples = mode == 2u ? samples / 3u :
                                              (mode == 3u ? 0u : samples);
                for (int order = 0; order < 3; ++order) {
                    char *args[24];
                    int argc = 0;
                    args[argc++] = "profile-cli";
                    if (order == 1) { args[argc++] = "--ns-floor"; args[argc++] = "0.25"; }
                    args[argc++] = "--profile"; args[argc++] = (char *)names[p];
                    if (order == 2) { args[argc++] = "--ns-floor"; args[argc++] = "0.25"; }
                    args[argc++] = "--sample-rate"; args[argc++] = rate;
                    args[argc++] = "--mic-channels"; args[argc++] = "2";
                    args[argc++] = "--strict-capture-frames";
                    args[argc++] = "--metrics-jsonl"; args[argc++] = "metrics";
                    if (capture_only) args[argc++] = "--capture-only";
                    args[argc++] = "capture";
                    if (!capture_only) args[argc++] = "render";
                    args[argc++] = "output"; args[argc] = NULL;
                    run_cli(args, argc, capture, 2u * samples, render, render_samples, &result);
                    assert_direct(&result, config, capture, render, render_samples, capture_only, order != 0);
                    runs++;
                    if (order == 1) ordered = result;
                    if (order == 2) {
                        assert(ordered.samples == result.samples);
                        assert(memcmp(ordered.pcm, result.pcm, result.samples * sizeof(int16_t)) == 0);
                        assert(strcmp(ordered.metrics, result.metrics) == 0);
                    }
                    if (p == 0u && order == 0) {
                        /* Remove the explicit profile arguments, preserving the
                         * original legacy invocation exactly. */
                        memmove(args + 1, args + 3, (size_t)(argc - 2) * sizeof(args[0]));
                        run_cli(args, argc - 2, capture, 2u * samples, render, render_samples, &legacy);
                        assert_direct(&legacy, config, capture, render, render_samples, capture_only, 0);
                        assert(legacy.samples == result.samples);
                        assert(memcmp(legacy.pcm, result.pcm, result.samples * sizeof(int16_t)) == 0);
                        assert(strcmp(legacy.metrics, result.metrics) == 0);
                        runs++;
                    }
                }
            }
        }
    }
    printf("PCM_PROFILE_DIRECT_API_PASS runs=%u\n", runs);
}

static void test_print_and_rejection(void) {
    static run_result_t result;
    const int16_t empty = 0;
    const char *names[] = {"call", "assistant"};
    for (unsigned p = 0u; p < 2u; ++p) {
        ap_config_t config = ap_config_default((ap_profile_t)p);
        char expected[256];
        char *args[] = {"profile-cli", "--print-default-tuning", "--profile", (char *)names[p], NULL};
        (void)snprintf(expected, sizeof(expected),
            "{\"aec_mu\":%.9g,\"ns_floor\":%.9g,\"agc_target_dbfs\":%.9g,\"limiter_dbfs\":%.9g}\n",
            (double)config.aec_mu, (double)config.ns_floor,
            (double)config.agc_target_dbfs, (double)config.limiter_dbfs);
        run_cli(args, 4, &empty, 0u, &empty, 0u, &result);
        assert(result.status == 0 && result.opens == 0u && result.inits == 0u);
        assert(strcmp(result.printed, expected) == 0);
        if (p == 0u) {
            run_cli(args, 2, &empty, 0u, &empty, 0u, &result);
            assert(result.status == 0 && strcmp(result.printed, expected) == 0);
        }
    }
    {
        char *missing[] = {"profile-cli", "--profile", NULL};
        char *invalid[] = {"profile-cli", "--profile", "voice", "--capture-only", "capture", "output", NULL};
        run_cli(missing, 2, &empty, 0u, &empty, 0u, &result);
        assert(result.status != 0 && result.opens == 0u && result.inits == 0u);
        run_cli(invalid, 6, &empty, 0u, &empty, 0u, &result);
        assert(result.status != 0 && result.opens == 0u && result.inits == 0u);
    }
    puts("PCM_PROFILE_PRINT_AND_REJECTION_PASS");
}

static void test_profile_partial_frame_rejection(void) {
    static run_result_t result;
    int16_t capture[480] = {0};
    const int16_t empty = 0;
    const char *names[] = {"call", "assistant"};
    for (unsigned p = 0u; p < 2u; ++p) {
        char *args[] = {"profile-cli", "--profile", (char *)names[p],
                        "--sample-rate", "8000", "--mic-channels", "2",
                        "--strict-capture-frames", "--capture-only", "capture", "output", NULL};
        /* One complete 8k dual-mic frame plus one half frame; processing the
         * valid prefix is permitted, reporting success is not. */
        run_cli(args, 11, capture, 240u, &empty, 0u, &result);
        assert(result.status != 0 && result.processed == 1u && result.samples == 80u);
        run_cli(args, 11, capture, 161u, &empty, 0u, &result);
        assert(result.status != 0 && result.processed == 1u && result.samples == 80u);
    }
    puts("PCM_PROFILE_PARTIAL_FRAME_REJECTION_PASS");
}

int main(void) {
    test_profiles();
    test_print_and_rejection();
    test_profile_partial_frame_rejection();
    return 0;
}
