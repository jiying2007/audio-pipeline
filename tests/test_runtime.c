#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if defined(_MSC_VER)
#define AP_ALIGN(N) __declspec(align(N))
#else
#define AP_ALIGN(N) _Alignas(N)
#endif

static AP_ALIGN(AP_PIPELINE_STATE_ALIGNMENT)
unsigned char pipeline_state[AP_PIPELINE_STATE_MAX_BYTES];
static AP_ALIGN(AP_RUNTIME_STATE_ALIGNMENT)
unsigned char runtime_state[AP_RUNTIME_STATE_MAX_BYTES];
static AP_ALIGN(AP_FLIGHT_RECORDER_STATE_ALIGNMENT)
unsigned char recorder_state[16384];
static unsigned char dump_state[16384];

static void sleep_ms(unsigned ms) {
    struct timespec ts;
    ts.tv_sec = (time_t)(ms / 1000u);
    ts.tv_nsec = (long)(ms % 1000u) * 1000000L;
    (void)nanosleep(&ts, NULL);
}

static ap_runtime_metrics_t read_metrics(ap_runtime_t *runtime) {
    ap_runtime_metrics_t metrics;
    memset(&metrics, 0, sizeof(metrics));
    metrics.struct_size = sizeof(metrics);
    metrics.api_version = AP_RUNTIME_API_VERSION;
    assert(ap_runtime_read_metrics(runtime, &metrics) == AP_OK);
    return metrics;
}

static int wait_processed(ap_runtime_t *runtime, uint64_t count, unsigned timeout_ms) {
    unsigned i;
    for (i = 0u; i < timeout_ms; ++i) {
        if (read_metrics(runtime).processed_frames >= count) return 1;
        sleep_ms(1u);
    }
    return 0;
}

static ap_runtime_t *open_runtime(ap_pipeline_t *pipeline,
                                  ap_runtime_config_t *config) {
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_runtime_t *runtime = NULL;
    assert(options.struct_size == sizeof(options));
    assert(options.api_version == AP_RUNTIME_API_VERSION);
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           config, &options, &runtime) == AP_OK);
    assert(runtime != NULL);
    return runtime;
}

static void test_open_contract(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    unsigned char misaligned[AP_RUNTIME_STATE_MAX_BYTES + 1u];

    assert(ap_runtime_state_alignment() == AP_RUNTIME_STATE_ALIGNMENT);
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    assert(ap_runtime_open(NULL, sizeof(runtime_state), pipeline, &rcfg, &options, &runtime) == AP_EINVAL);
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), NULL, &rcfg, &options, &runtime) == AP_EINVAL);
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline, NULL, &options, &runtime) == AP_EINVAL);
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline, &rcfg, NULL, &runtime) == AP_EINVAL);
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &options, NULL) == AP_EINVAL);
    assert(ap_runtime_open(runtime_state, ap_runtime_state_size() - 1u,
                           pipeline, &rcfg, &options, &runtime) == AP_ENOMEM);
    assert(ap_runtime_open(misaligned + 1u, sizeof(misaligned) - 1u,
                           pipeline, &rcfg, &options, &runtime) == AP_EINVAL);
    rcfg.recover_frames = 0u;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_EINVAL);
    rcfg = ap_runtime_config_default();
    options.api_version = 0u;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_EINVAL);
}

static void test_submit_receive_metrics_and_backpressure(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};
    ap_runtime_metrics_t metrics;
    unsigned i;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    runtime = open_runtime(pipeline, &rcfg);
    for (i = 0u; i < AP_BUILD_RUNTIME_QUEUE_DEPTH; ++i)
        assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
    assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_EFULL);
    metrics = read_metrics(runtime);
    assert(metrics.submitted_frames == AP_BUILD_RUNTIME_QUEUE_DEPTH);
    assert(metrics.input_full_events == 1u);
    ap_runtime_deinit(runtime);

    runtime = open_runtime(pipeline, &rcfg);
    assert(ap_runtime_start(runtime) == AP_OK);
    assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
    for (i = 0u; i < 1000u; ++i) {
        ap_status_t status = ap_runtime_receive(runtime, out, NULL);
        if (status == AP_OK) break;
        assert(status == AP_EEMPTY);
        sleep_ms(1u);
    }
    assert(i < 1000u);
    metrics = read_metrics(runtime);
    assert(metrics.submitted_frames == 1u);
    assert(metrics.processed_frames == 1u);
    assert(metrics.failed_frames == 0u);
    assert(metrics.p99_dsp_us >= metrics.p50_dsp_us);
    ap_runtime_deinit(runtime);
}

static void test_metadata_command_and_critical_latch(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};
    ap_frame_metadata_t metadata;
    ap_runtime_command_t command;
    ap_runtime_critical_state_t critical;
    ap_runtime_metrics_t metrics;
    unsigned i;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    rcfg.overload_us = 0u;
    runtime = open_runtime(pipeline, &rcfg);
    assert(ap_runtime_start(runtime) == AP_OK);

    memset(&metadata, 0, sizeof(metadata));
    metadata.struct_size = sizeof(metadata);
    metadata.api_version = AP_RUNTIME_API_VERSION;
    metadata.flags = AP_FRAME_CAPTURE_DISCONTINUITY |
                     AP_FRAME_CAPTURE_TIMESTAMP_VALID |
                     AP_FRAME_RENDER_TIMESTAMP_VALID;
    metadata.stream_sequence = 42u;
    metadata.capture_timestamp_ns = 100000000ull;
    metadata.render_timestamp_ns = 60000000ull;
    metadata.lost_capture_frames = 3u;
    assert(ap_runtime_submit_frame(runtime, mic, render, &metadata) == AP_OK);

    memset(&command, 0, sizeof(command));
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_ECHO_PATH_CHANGE;
    assert(ap_runtime_command(runtime, &command) == AP_OK);
    command.kind = 999u;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);

    for (i = 0u; i < 1000u; ++i) {
        ap_status_t status = ap_runtime_receive(runtime, out, NULL);
        if (status == AP_OK) break;
        assert(status == AP_EEMPTY);
        sleep_ms(1u);
    }
    assert(i < 1000u);
    metrics = read_metrics(runtime);
    assert(metrics.stream_discontinuities >= 1u);
    assert(metrics.capture_gap_frames >= 3u);
    assert(metrics.timestamp_frames >= 1u);
    assert(metrics.dsp_overruns >= 1u);

    memset(&critical, 0, sizeof(critical));
    critical.struct_size = sizeof(critical);
    critical.api_version = AP_RUNTIME_API_VERSION;
    assert(ap_runtime_get_critical_state(runtime, &critical) == AP_OK);
    assert(critical.total_events >= 1u);
    assert(critical.severity >= AP_EVENT_ERROR);
    ap_runtime_deinit(runtime);
}

static void test_flight_recorder_contract(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_flight_recorder_config_t dcfg = ap_flight_recorder_config_default(16000u, 2u);
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    ap_flight_recorder_t *recorder = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    size_t need;
    size_t written = 0u;

    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    dcfg.record_mask = AP_DIAG_RECORD_METRICS;
    need = ap_flight_recorder_state_size(&dcfg);
    assert(need > 0u && need <= sizeof(recorder_state));
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state),
                                   &dcfg, &recorder) == AP_OK);
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    runtime = open_runtime(pipeline, &rcfg);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_OK);
    assert(ap_flight_recorder_trigger(recorder, AP_EVENT_DIAG_TRIGGERED,
                                      AP_EVENT_ERROR) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
    assert(wait_processed(runtime, 1u, 1000u));
    assert(ap_flight_recorder_is_frozen(recorder));
    assert(ap_flight_recorder_export_size(recorder) <= sizeof(dump_state));
    assert(ap_flight_recorder_export(recorder, dump_state, sizeof(dump_state),
                                     &written) == AP_OK);
    assert(written > 0u);
    ap_runtime_deinit(runtime);
}

int main(void) {
    test_open_contract();
    test_submit_receive_metrics_and_backpressure();
    test_metadata_command_and_critical_latch();
    test_flight_recorder_contract();
    puts("audio-pipeline v2 runtime contracts: OK");
    return 0;
}
