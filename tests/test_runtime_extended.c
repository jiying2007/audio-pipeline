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
unsigned char recorder_state[32768];
static AP_ALIGN(AP_FLIGHT_RECORDER_STATE_ALIGNMENT)
unsigned char recorder_misaligned[32768 + AP_FLIGHT_RECORDER_STATE_ALIGNMENT];
static unsigned char export_buffer[32768];

static void sleep_ms(unsigned ms) {
    struct timespec ts;
    ts.tv_sec = (time_t)(ms / 1000u);
    ts.tv_nsec = (long)(ms % 1000u) * 1000000L;
    (void)nanosleep(&ts, NULL);
}

static ap_runtime_metrics_t metrics(ap_runtime_t *runtime) {
    ap_runtime_metrics_t value;
    memset(&value, 0, sizeof(value));
    value.struct_size = sizeof(value);
    value.api_version = AP_RUNTIME_API_VERSION;
    assert(ap_runtime_read_metrics(runtime, &value) == AP_OK);
    return value;
}

static ap_runtime_t *open_default(ap_pipeline_t *pipeline,
                                  ap_runtime_config_t *config) {
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_runtime_t *runtime = NULL;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           config, &options, &runtime) == AP_OK);
    return runtime;
}

static int wait_processed(ap_runtime_t *runtime, uint64_t target) {
    unsigned i;
    for (i = 0u; i < 2000u; ++i) {
        if (metrics(runtime).processed_frames >= target) return 1;
        sleep_ms(1u);
    }
    return 0;
}

static ap_metrics_t process_one(ap_runtime_t *runtime,
                                const int16_t *mic,
                                const int16_t *render,
                                int16_t *output) {
    ap_metrics_t pipeline_metrics;
    unsigned i;
    assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
    for (i = 0u; i < 2000u; ++i) {
        ap_status_t status = ap_runtime_receive(runtime, output, &pipeline_metrics);
        if (status == AP_OK) return pipeline_metrics;
        assert(status == AP_EEMPTY);
        sleep_ms(1u);
    }
    assert(!"runtime output timeout");
    memset(&pipeline_metrics, 0, sizeof(pipeline_metrics));
    return pipeline_metrics;
}

static void test_open_start_and_argument_failures(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};
    ap_runtime_metrics_t rm;
    ap_runtime_critical_state_t critical;
    ap_event_t event;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);

    rcfg.dsp_cpu = -2;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_EINVAL);
    rcfg = ap_runtime_config_default();
    rcfg.dsp_cpu = 1000000;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_EINVAL);
    rcfg = ap_runtime_config_default();
    rcfg.dsp_priority = -1;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_EINVAL);
    rcfg.dsp_priority = 100;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_EINVAL);
    rcfg = ap_runtime_config_default();
    options.struct_size = 0u;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_EINVAL);

    options = ap_runtime_options_default();
    options.dsp_stack_bytes = 1u;
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_EINVAL);
    ap_runtime_deinit(runtime);

    options = ap_runtime_options_default();
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_OK);
    assert(ap_runtime_submit_frame(NULL, mic, NULL, NULL) == AP_EINVAL);
    assert(ap_runtime_submit_frame(runtime, NULL, NULL, NULL) == AP_EINVAL);
    assert(ap_runtime_receive(NULL, out, NULL) == AP_EINVAL);
    assert(ap_runtime_receive(runtime, NULL, NULL) == AP_EINVAL);
    assert(ap_runtime_receive(runtime, out, NULL) == AP_EEMPTY);
    assert(ap_runtime_receive_event(NULL, &event) == AP_EINVAL);
    assert(ap_runtime_receive_event(runtime, NULL) == AP_EINVAL);
    assert(ap_runtime_receive_event(runtime, &event) == AP_EEMPTY);

    memset(&rm, 0, sizeof(rm));
    rm.struct_size = sizeof(rm);
    rm.api_version = 0u;
    assert(ap_runtime_read_metrics(runtime, &rm) == AP_EINVAL);
    assert(ap_runtime_read_metrics(NULL, &rm) == AP_EINVAL);
    assert(ap_runtime_read_metrics(runtime, NULL) == AP_EINVAL);

    memset(&critical, 0, sizeof(critical));
    critical.struct_size = sizeof(critical);
    critical.api_version = 0u;
    assert(ap_runtime_get_critical_state(runtime, &critical) == AP_EINVAL);
    assert(ap_runtime_get_critical_state(NULL, &critical) == AP_EINVAL);
    assert(ap_runtime_get_critical_state(runtime, NULL) == AP_EINVAL);

    assert(ap_runtime_bind_current_thread(-1, 0) == 0);
    assert(ap_runtime_bind_current_thread(1000000, 0) == -1);
    ap_runtime_deinit(runtime);
}

static void test_command_validation_and_queue_pressure(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    ap_runtime_command_t command;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);

    memset(&command, 0, sizeof(command));
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_RESET;
    assert(ap_runtime_command(NULL, &command) == AP_EINVAL);
    assert(ap_runtime_command(runtime, NULL) == AP_EINVAL);
    command.struct_size = 0u;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);
    command.struct_size = sizeof(command);
    command.api_version = 0u;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = 999u;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);

    command.kind = AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY;
    command.data.discontinuity.flags = 0u;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);
    command.data.discontinuity.flags = 1u << 31;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);

    command.kind = AP_RUNTIME_COMMAND_SET_QUALITY;
    command.data.set_quality.quality = (ap_quality_t)99;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);

    command.kind = AP_RUNTIME_COMMAND_SET_TUNING;
    memset(&command.data.tuning, 0, sizeof(command.data.tuning));
    command.data.tuning.struct_size = sizeof(command.data.tuning);
    command.data.tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    command.data.tuning.mask = AP_TUNING_AEC_MU;
    command.data.tuning.aec_mu = 0.0f;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);
    command.data.tuning.aec_mu = 0.15f;
    assert(ap_runtime_command(runtime, &command) == AP_OK);

    memset(&command, 0, sizeof(command));
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_RESET;
    assert(ap_runtime_command(runtime, &command) == AP_OK);
    assert(ap_runtime_command(runtime, &command) == AP_EFULL);
    assert(metrics(runtime).command_full_events == 1u);

    assert(ap_runtime_start(runtime) == AP_OK);
    (void)process_one(runtime, mic, render, out);
    ap_runtime_deinit(runtime);
}

static void test_metadata_event_drop_and_output_backpressure(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    ap_frame_metadata_t metadata;
    ap_runtime_metrics_t rm;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};
    unsigned i;

    rcfg.overload_us = 0u;
    rcfg.recover_frames = 100u;
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);
    assert(ap_runtime_start(runtime) == AP_OK);

    memset(&metadata, 0, sizeof(metadata));
    metadata.struct_size = sizeof(metadata);
    metadata.api_version = 0u;
    assert(ap_runtime_submit_frame(runtime, mic, render, &metadata) == AP_EINVAL);
    metadata.api_version = AP_RUNTIME_API_VERSION;
    metadata.flags = AP_FRAME_CAPTURE_TIMESTAMP_VALID | AP_FRAME_RENDER_TIMESTAMP_VALID |
                     AP_FRAME_CAPTURE_DISCONTINUITY | AP_FRAME_RENDER_DISCONTINUITY |
                     AP_FRAME_CLOCK_RESET | AP_FRAME_XRUN | AP_FRAME_CODEC_REOPEN;
    metadata.stream_sequence = 100u;
    metadata.capture_timestamp_ns = 100000000ull;
    metadata.render_timestamp_ns = 60000000ull;
    metadata.lost_capture_frames = 2u;
    metadata.lost_render_frames = 5u;
    assert(ap_runtime_submit_frame(runtime, mic, render, &metadata) == AP_OK);
    assert(wait_processed(runtime, 1u));

    for (i = 1u; i < AP_BUILD_RUNTIME_QUEUE_DEPTH; ++i)
        assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
    assert(wait_processed(runtime, AP_BUILD_RUNTIME_QUEUE_DEPTH));

    for (i = 0u; i < 4u; ++i) {
        assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
        assert(wait_processed(runtime, AP_BUILD_RUNTIME_QUEUE_DEPTH + i + 1u));
    }

    rm = metrics(runtime);
    assert(rm.capture_gap_frames >= 5u);
    assert(rm.render_gap_frames >= 5u);
    assert(rm.timestamp_frames >= 1u);
    assert(rm.output_drop_events >= 4u);
    assert(rm.event_drop_events >= 1u);
    assert(rm.critical_events >= 1u);

    while (ap_runtime_receive(runtime, out, NULL) == AP_OK) {
    }
    ap_runtime_deinit(runtime);
}

static void test_automatic_quality_degrade_and_recovery(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    ap_metrics_t pm;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};
    unsigned i;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    rcfg.overload_us = 0u;
    rcfg.recover_frames = 2u;
    runtime = open_default(pipeline, &rcfg);
    assert(ap_runtime_start(runtime) == AP_OK);
    for (i = 0u; i < 6u; ++i) pm = process_one(runtime, mic, render, out);
    assert(pm.quality == AP_QUALITY_SAFE);
    assert(metrics(runtime).dsp_overruns >= 6u);
    ap_runtime_deinit(runtime);

    rcfg.overload_us = UINT32_MAX;
    rcfg.recover_frames = 2u;
    runtime = open_default(pipeline, &rcfg);
    assert(ap_runtime_start(runtime) == AP_OK);
    for (i = 0u; i < 4u; ++i) pm = process_one(runtime, mic, render, out);
    assert(pm.quality == AP_QUALITY_FULL);
    ap_runtime_deinit(runtime);
}

static void test_recorder_validation_record_and_export(void) {
    ap_flight_recorder_config_t config = ap_flight_recorder_config_default(16000u, 2u);
    ap_flight_recorder_t *recorder = NULL;
    ap_diag_frame_t frame;
    ap_metrics_t pm;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t output[AP_MAX_IO_FRAME_SAMPLES] = {0};
    size_t need;
    size_t written = 0u;

    assert(ap_flight_recorder_state_alignment() == AP_FLIGHT_RECORDER_STATE_ALIGNMENT);
    assert(ap_flight_recorder_state_size(NULL) == 0u);
    config.api_version = 0u;
    assert(ap_flight_recorder_state_size(&config) == 0u);
    config = ap_flight_recorder_config_default(11025u, 2u);
    assert(ap_flight_recorder_state_size(&config) == 0u);
    config = ap_flight_recorder_config_default(16000u, 0u);
    assert(ap_flight_recorder_state_size(&config) == 0u);
    config = ap_flight_recorder_config_default(16000u, 3u);
    assert(ap_flight_recorder_state_size(&config) == 0u);
    config = ap_flight_recorder_config_default(16000u, 2u);
    config.frame_samples++;
    assert(ap_flight_recorder_state_size(&config) == 0u);
    config = ap_flight_recorder_config_default(16000u, 2u);
    config.record_mask = 1u << 31;
    assert(ap_flight_recorder_state_size(&config) == 0u);
    config = ap_flight_recorder_config_default(16000u, 2u);
    config.pre_roll_frames = UINT32_MAX;
    config.post_roll_frames = UINT32_MAX;
    assert(ap_flight_recorder_state_size(&config) == 0u);

    config = ap_flight_recorder_config_default(16000u, 2u);
    config.pre_roll_frames = 1u;
    config.post_roll_frames = 0u;
    config.record_mask = AP_DIAG_RECORD_ALL;
    config.trigger_severity = AP_EVENT_ERROR;
    need = ap_flight_recorder_state_size(&config);
    assert(need > 0u && need <= sizeof(recorder_state));
    assert(ap_flight_recorder_init(NULL, sizeof(recorder_state), &config, &recorder) == AP_EINVAL);
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), NULL, &recorder) == AP_EINVAL);
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &config, NULL) == AP_EINVAL);
    assert(ap_flight_recorder_init(recorder_state, need - 1u, &config, &recorder) == AP_ENOMEM);
    assert(ap_flight_recorder_init(recorder_misaligned + 1u,
                                   sizeof(recorder_misaligned) - 1u,
                                   &config, &recorder) == AP_EINVAL);
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state),
                                   &config, &recorder) == AP_OK);

    assert(!ap_flight_recorder_is_frozen(NULL));
    assert(ap_flight_recorder_export_size(NULL) == 0u);
    assert(ap_flight_recorder_export_size(recorder) == 0u);
    assert(ap_flight_recorder_export(recorder, export_buffer,
                                     sizeof(export_buffer), &written) == AP_ESTATE);
    assert(ap_flight_recorder_trigger(NULL, AP_EVENT_DIAG_TRIGGERED,
                                      AP_EVENT_ERROR) == AP_EINVAL);
    assert(ap_flight_recorder_trigger(recorder, AP_EVENT_DIAG_TRIGGERED,
                                      AP_EVENT_WARN) == AP_OK);

    memset(&frame, 0, sizeof(frame));
    frame.struct_size = sizeof(frame);
    frame.api_version = AP_DIAG_API_VERSION;
    frame.frame_sequence = 7u;
    frame.capture_timestamp_ns = 11u;
    frame.render_timestamp_ns = 9u;
    frame.metadata_flags = AP_FRAME_CAPTURE_TIMESTAMP_VALID;
    frame.trigger_event = AP_EVENT_DIAG_TRIGGERED;
    frame.mic_interleaved = mic;
    frame.render = render;
    frame.output = output;
    frame.metrics = &pm;
    memset(&pm, 0, sizeof(pm));
    assert(ap_flight_recorder_record(NULL, &frame) == AP_EINVAL);
    assert(ap_flight_recorder_record(recorder, NULL) == AP_EINVAL);
    frame.api_version = 0u;
    assert(ap_flight_recorder_record(recorder, &frame) == AP_EINVAL);
    frame.api_version = AP_DIAG_API_VERSION;
    assert(ap_flight_recorder_record(recorder, &frame) == AP_OK);
    assert(!ap_flight_recorder_is_frozen(recorder));

    assert(ap_flight_recorder_trigger(recorder, AP_EVENT_PIPELINE_ERROR,
                                      AP_EVENT_ERROR) == AP_OK);
    assert(ap_flight_recorder_trigger(recorder, AP_EVENT_PIPELINE_ERROR,
                                      AP_EVENT_FATAL) == AP_OK);
    assert(ap_flight_recorder_record(recorder, &frame) == AP_OK);
    assert(ap_flight_recorder_is_frozen(recorder));
    assert(ap_flight_recorder_record(recorder, &frame) == AP_ESTATE);

    need = ap_flight_recorder_export_size(recorder);
    assert(need > 0u && need <= sizeof(export_buffer));
    assert(ap_flight_recorder_export(NULL, export_buffer,
                                     sizeof(export_buffer), &written) == AP_EINVAL);
    assert(ap_flight_recorder_export(recorder, NULL,
                                     sizeof(export_buffer), &written) == AP_EINVAL);
    assert(ap_flight_recorder_export(recorder, export_buffer,
                                     sizeof(export_buffer), NULL) == AP_EINVAL);
    assert(ap_flight_recorder_export(recorder, export_buffer,
                                     need - 1u, &written) == AP_ENOMEM);
    assert(ap_flight_recorder_export(recorder, export_buffer,
                                     sizeof(export_buffer), &written) == AP_OK);
    assert(written == need);

    ap_flight_recorder_reset(NULL);
    ap_flight_recorder_reset(recorder);
    assert(!ap_flight_recorder_is_frozen(recorder));
}

static void test_recorder_attach_geometry(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    ap_flight_recorder_config_t config;
    ap_flight_recorder_t *recorder = NULL;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);
    assert(ap_runtime_attach_flight_recorder(NULL, NULL) == AP_EINVAL);

    config = ap_flight_recorder_config_default(8000u, 2u);
    config.pre_roll_frames = 1u;
    config.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state),
                                   &config, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_EINVAL);

    config = ap_flight_recorder_config_default(16000u, 1u);
    config.pre_roll_frames = 1u;
    config.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state),
                                   &config, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_EINVAL);

    config = ap_flight_recorder_config_default(16000u, 2u);
    config.pre_roll_frames = 1u;
    config.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state),
                                   &config, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, NULL) == AP_ESTATE);
    ap_runtime_deinit(runtime);
}

int main(void) {
    test_open_start_and_argument_failures();
    test_command_validation_and_queue_pressure();
    test_metadata_event_drop_and_output_backpressure();
    test_automatic_quality_degrade_and_recovery();
    test_recorder_validation_record_and_export();
    test_recorder_attach_geometry();
    puts("audio-pipeline v2 extended runtime contracts: OK");
    return 0;
}
