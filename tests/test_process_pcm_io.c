/* Deterministic stdio-failure tests of the actual offline processor.
 * These are host engineering tests, never acoustic, DUT or HIL evidence. */
#define _GNU_SOURCE
#include "audio_pipeline/audio_pipeline.h"
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { CAPTURE_FILE, RENDER_FILE, OUTPUT_FILE, METRICS_FILE, FILE_COUNT };
enum { VALID_CONTROL_FRAMES = 12 };
typedef struct io_cookie {
    const unsigned char *input;
    size_t input_size;
    size_t position;
    unsigned char output[16384];
    size_t output_size;
    int read_error;
    int write_error;
    int close_error;
    int unbuffered;
    unsigned reads;
    unsigned writes;
    unsigned closes;
    char buffer[4096];
} io_cookie_t;

static io_cookie_t cookies[FILE_COUNT];
static FILE *opened[FILE_COUNT];
static unsigned open_calls;
static int open_error = -1;
static FILE *test_fopen(const char *path, const char *mode);
static int test_fclose(FILE *stream);

#ifndef AP_PROCESS_PCM_SOURCE
#define AP_PROCESS_PCM_SOURCE "../examples/process_pcm.c"
#endif
#define main process_pcm_example_main
#define fopen test_fopen
#define fclose test_fclose
#include AP_PROCESS_PCM_SOURCE
#undef fclose
#undef fopen
#undef main

static ssize_t cookie_read(void *opaque, char *destination, size_t size) {
    io_cookie_t *cookie = opaque;
    size_t available = cookie->input_size - cookie->position;
    cookie->reads++;
    if (available == 0u && cookie->read_error) {
        errno = EIO;
        return -1;
    }
    if (size > available) size = available;
    if (size != 0u) memcpy(destination, cookie->input + cookie->position, size);
    cookie->position += size;
    return (ssize_t)size;
}

static ssize_t cookie_write(void *opaque, const char *source, size_t size) {
    io_cookie_t *cookie = opaque;
    cookie->writes++;
    if (cookie->write_error) {
        errno = ENOSPC;
        return -1;
    }
    assert(size <= sizeof(cookie->output) - cookie->output_size);
    memcpy(cookie->output + cookie->output_size, source, size);
    cookie->output_size += size;
    return (ssize_t)size;
}

static int cookie_close(void *opaque) {
    io_cookie_t *cookie = opaque;
    cookie->closes++;
    if (cookie->close_error) {
        errno = EIO;
        return -1;
    }
    return 0;
}

static FILE *test_fopen(const char *path, const char *mode) {
    static const char *names[] = {
        "unit-capture", "unit-render", "unit-output", "unit-metrics"
    };
    unsigned index;
    cookie_io_functions_t functions = {0};
    for (index = 0u; index < FILE_COUNT; ++index)
        if (strcmp(path, names[index]) == 0) break;
    assert(index < FILE_COUNT);
    open_calls++;
    if ((int)index == open_error) {
        errno = EACCES;
        return NULL;
    }
    assert(opened[index] == NULL);
    functions.read = index < OUTPUT_FILE ? cookie_read : NULL;
    functions.write = index >= OUTPUT_FILE ? cookie_write : NULL;
    functions.close = cookie_close;
    opened[index] = fopencookie(&cookies[index], mode, functions);
    assert(opened[index] != NULL);
    assert(setvbuf(opened[index], cookies[index].buffer,
                   cookies[index].unbuffered ? _IONBF : _IOFBF,
                   sizeof(cookies[index].buffer)) == 0);
    return opened[index];
}

static int test_fclose(FILE *stream) {
    unsigned index;
    for (index = 0u; index < FILE_COUNT; ++index)
        if (opened[index] == stream) break;
    assert(index < FILE_COUNT);
    opened[index] = NULL;
    return fclose(stream);
}

static void verify_valid_output(const ap_config_t *configuration,
                                const int16_t *capture, const int16_t *reference,
                                size_t reference_samples, size_t frames,
                                int capture_only) {
    _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
    static unsigned char storage[AP_PIPELINE_STATE_MAX_BYTES];
    ap_config_t config = *configuration;
    ap_pipeline_t *pipeline = NULL;
    int16_t expected[AP_MAX_IO_FRAME_SAMPLES * VALID_CONTROL_FRAMES];
    int16_t padded[AP_MAX_IO_FRAME_SAMPLES];
    const size_t frame = ap_pipeline_io_frame_samples(&config);
    if (capture_only) {
        config.stages &= ~(AP_STAGE_SYNC | AP_STAGE_AEC | AP_STAGE_RES);
        config.enable_delay_tracking = 0u;
        config.enable_clock_drift_compensation = 0u;
    }
    assert(frames <= VALID_CONTROL_FRAMES);
    assert(ap_pipeline_init(storage, sizeof(storage), &config, &pipeline) == AP_OK);
    for (size_t index = 0u; index < frames; ++index) {
        if (!capture_only) {
            size_t count = reference_samples > index * frame ?
                           reference_samples - index * frame : 0u;
            if (count > frame) count = frame;
            memset(padded, 0, frame * sizeof(padded[0]));
            if (count != 0u)
                memcpy(padded, reference + index * frame, count * sizeof(padded[0]));
            assert(ap_pipeline_push_render(pipeline, padded, frame) == AP_OK);
        }
        assert(ap_pipeline_process_capture(
            pipeline, capture + index * frame * config.mic_channels, frame,
            expected + index * frame) == AP_OK);
    }
    assert(cookies[OUTPUT_FILE].output_size == frames * frame * sizeof(int16_t));
    assert(memcmp(cookies[OUTPUT_FILE].output, expected,
                  cookies[OUTPUT_FILE].output_size) == 0);
    if (frames != 0u) {
        int nonzero = 0;
        for (size_t index = 0u; index < frames * frame; ++index)
            if (expected[index] != 0) { nonzero = 1; break; }
        assert(nonzero);
    }
    {
        size_t lines = 0u;
        for (size_t index = 0u; index < cookies[METRICS_FILE].output_size; ++index)
            if (cookies[METRICS_FILE].output[index] == '\n') lines++;
        assert(lines == frames);
        if (frames != 0u) {
            assert(cookies[METRICS_FILE].output_size < sizeof(cookies[METRICS_FILE].output));
            cookies[METRICS_FILE].output[cookies[METRICS_FILE].output_size] = 0;
            assert(strstr((const char *)cookies[METRICS_FILE].output, "\"frame\":0,") != NULL);
        }
    }
}

static int invoke_processor(int argc, char **argv, char *diagnostics, size_t capacity) {
    FILE *record = tmpfile();
    const int saved_stderr = dup(STDERR_FILENO);
    int status;
    size_t count;
    assert(record != NULL && saved_stderr >= 0 && capacity > 1u);
    assert(fflush(stderr) == 0);
    assert(dup2(fileno(record), STDERR_FILENO) >= 0);
    status = process_pcm_example_main(argc, argv);
    assert(fflush(stderr) == 0);
    assert(dup2(saved_stderr, STDERR_FILENO) >= 0);
    assert(close(saved_stderr) == 0);
    rewind(record);
    count = fread(diagnostics, 1u, capacity - 1u, record);
    assert(!ferror(record) && feof(record));
    diagnostics[count] = '\0';
    assert(fclose(record) == 0);
    return status;
}

static int run_scenario(const char *scenario, int legacy, int strict_frames) {
    ap_config_t config = ap_config_default(AP_PROFILE_CALL);
    const size_t frame = ap_pipeline_io_frame_samples(&config);
    const size_t capture_frame_bytes = frame * config.mic_channels * sizeof(int16_t);
    int16_t capture[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS * (VALID_CONTROL_FRAMES + 1)];
    int16_t reference[AP_MAX_IO_FRAME_SAMPLES * VALID_CONTROL_FRAMES];
    char *arguments[16];
    int argument_count = 0;
    int capture_only = 1;
    int expect_success = 0;
    int invalid_tuning = 0;
    int legacy_failure_control = 0;
    int compatibility_tail = 0;
    char diagnostics[1024];
    size_t valid_frames = 2u;
    int status;
    for (unsigned index = 0u; index < FILE_COUNT; ++index)
        assert(opened[index] == NULL);
    memset(cookies, 0, sizeof(cookies));
    open_calls = 0u;
    open_error = -1;
    for (size_t index = 0u; index < sizeof(capture) / sizeof(capture[0]); ++index)
        capture[index] = (int16_t)(((int)(index % 89u) - 44) * 173);
    for (size_t index = 0u; index < sizeof(reference) / sizeof(reference[0]); ++index)
        reference[index] = (int16_t)(((int)(index % 53u) - 26) * 127);
    cookies[CAPTURE_FILE].input = (const unsigned char *)capture;
    cookies[CAPTURE_FILE].input_size = capture_frame_bytes * 2u;
    cookies[RENDER_FILE].input = (const unsigned char *)reference;
    cookies[RENDER_FILE].input_size = frame * sizeof(int16_t) * 2u;

    if (strcmp(scenario, "clean-capture") == 0) expect_success = 1;
    else if (strcmp(scenario, "clean-duplex") == 0) {
        capture_only = 0; expect_success = 1;
    } else if (strcmp(scenario, "render-short") == 0) {
        capture_only = 0; expect_success = 1;
        cookies[RENDER_FILE].input_size = (frame + 13u) * sizeof(int16_t);
    } else if (strcmp(scenario, "render-empty") == 0) {
        capture_only = 0; expect_success = 1;
        cookies[RENDER_FILE].input_size = 0u;
    } else if (strcmp(scenario, "capture-empty") == 0) {
        expect_success = 1; valid_frames = 0u;
        cookies[CAPTURE_FILE].input_size = 0u;
    } else if (strcmp(scenario, "capture-odd") == 0) {
        cookies[CAPTURE_FILE].input_size = capture_frame_bytes + 1u;
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "capture-partial-frame") == 0) {
        cookies[CAPTURE_FILE].input_size = capture_frame_bytes + capture_frame_bytes / 2u;
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "capture-partial-channel") == 0) {
        cookies[CAPTURE_FILE].input_size = capture_frame_bytes + sizeof(int16_t);
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "render-odd") == 0) {
        capture_only = 0;
        cookies[RENDER_FILE].input_size = frame * sizeof(int16_t) + 1u;
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "capture-read-error") == 0) {
        cookies[CAPTURE_FILE].input_size = capture_frame_bytes;
        cookies[CAPTURE_FILE].read_error = 1;
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "render-read-error") == 0) {
        capture_only = 0;
        cookies[RENDER_FILE].input_size = 13u * sizeof(int16_t);
        cookies[RENDER_FILE].read_error = 1;
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "output-write-error") == 0) {
        cookies[OUTPUT_FILE].write_error = 1;
        cookies[OUTPUT_FILE].unbuffered = 1;
    } else if (strcmp(scenario, "output-close-error") == 0) {
        cookies[OUTPUT_FILE].write_error = 1;
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "metrics-write-error") == 0) {
        cookies[METRICS_FILE].write_error = 1;
        cookies[METRICS_FILE].unbuffered = 1;
    } else if (strcmp(scenario, "metrics-close-error") == 0) {
        cookies[METRICS_FILE].write_error = 1;
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "input-close-error") == 0) {
        cookies[CAPTURE_FILE].close_error = 1;
        legacy_failure_control = 1;
    } else if (strcmp(scenario, "capture-open-error") == 0) open_error = CAPTURE_FILE;
    else if (strcmp(scenario, "render-open-error") == 0) {
        capture_only = 0; open_error = RENDER_FILE;
    } else if (strcmp(scenario, "output-open-error") == 0) open_error = OUTPUT_FILE;
    else if (strcmp(scenario, "metrics-open-error") == 0) open_error = METRICS_FILE;
    else if (strcmp(scenario, "invalid-tuning") == 0) invalid_tuning = 1;
    else { fprintf(stderr, "unknown scenario: %s\n", scenario); return 2; }

    compatibility_tail = !legacy && !strict_frames &&
                         strcmp(scenario, "capture-partial-frame") == 0;
    if (compatibility_tail) expect_success = 1;

    /* Reach beyond the default 40 ms SYNC reference delay and NS startup.
     * Keep failure/predecessor controls at their original lengths. */
    if (expect_success && valid_frames != 0u) {
        valid_frames = VALID_CONTROL_FRAMES;
        cookies[CAPTURE_FILE].input_size = capture_frame_bytes * valid_frames;
        if (strcmp(scenario, "clean-duplex") == 0)
            cookies[RENDER_FILE].input_size = frame * sizeof(int16_t) * valid_frames;
    }

    if (compatibility_tail)
        cookies[CAPTURE_FILE].input_size += capture_frame_bytes / 2u;

    arguments[argument_count++] = "process-pcm-stdio-unit";
    if (capture_only) arguments[argument_count++] = "--capture-only";
    if (strict_frames) arguments[argument_count++] = "--strict-capture-frames";
    if (invalid_tuning) {
        arguments[argument_count++] = "--ns-floor";
        arguments[argument_count++] = "2";
    }
    arguments[argument_count++] = "--metrics-jsonl";
    arguments[argument_count++] = "unit-metrics";
    arguments[argument_count++] = "unit-capture";
    if (!capture_only) arguments[argument_count++] = "unit-render";
    arguments[argument_count++] = "unit-output";
    arguments[argument_count] = NULL;
    status = invoke_processor(argument_count, arguments, diagnostics, sizeof(diagnostics));

    if (legacy) {
        assert(legacy_failure_control);
        /* Eight errors and one silent whole-channel EOF tail in v2.3.60. */
        assert(status == 0);
        for (unsigned index = 0u; index < FILE_COUNT; ++index)
            if (opened[index]) (void)test_fclose(opened[index]);
        printf("%s %s\n", strcmp(scenario, "capture-partial-frame") == 0 ?
               "LEGACY_CAPTURE_TAIL_DISCARD_REPRODUCED" :
               "LEGACY_FALSE_SUCCESS_REPRODUCED", scenario);
        return 0;
    }
    assert(expect_success ? status == 0 : status != 0);
    if (compatibility_tail) {
        char expected[256];
        const int length = snprintf(expected, sizeof(expected),
            "capture tail ignored: %zu samples per channel "
            "(%u channels); use --strict-capture-frames to reject\n",
            frame / 2u, (unsigned)config.mic_channels);
        assert(length > 0 && (size_t)length < sizeof(expected));
        assert(strcmp(diagnostics, expected) == 0);
    } else {
        assert(strstr(diagnostics, "capture tail ignored:") == NULL);
    }
    for (unsigned index = 0u; index < FILE_COUNT; ++index) {
        assert(opened[index] == NULL);
        assert(cookies[index].closes <= 1u);
    }
    if (invalid_tuning) assert(open_calls == 0u);
    if (open_error == CAPTURE_FILE) {
        assert(cookies[OUTPUT_FILE].closes == 0u);
        assert(cookies[METRICS_FILE].closes == 0u);
    }
    if (expect_success)
        verify_valid_output(&config, capture, reference,
                            cookies[RENDER_FILE].input_size / sizeof(int16_t),
                            valid_frames, capture_only);
    printf("PCM_IO_CONTRACT_PASS %s mode=%s status=%d opens=%u\n",
           scenario, strict_frames ? "strict" : "default", status, open_calls);
    return 0;
}

int main(int argc, char **argv) {
    if (argc == 3 && strcmp(argv[1], "--legacy-detection") == 0)
        return run_scenario(argv[2], 1, 0);
    assert(argc == 2);
    assert(run_scenario(argv[1], 0, 0) == 0);
    assert(run_scenario(argv[1], 0, 1) == 0);
    return 0;
}
