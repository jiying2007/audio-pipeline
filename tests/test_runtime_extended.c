#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_runtime.h"
#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdlib.h>
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


static void test_direct_quality_degradation_event(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    ap_runtime_command_t command;
    ap_event_t event;
    ap_metrics_t pm;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};
    unsigned i;
    int saw_degraded = 0;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);
    assert(ap_runtime_start(runtime) == AP_OK);
    memset(&command, 0, sizeof(command));
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_SET_QUALITY;
    command.data.set_quality.quality = AP_QUALITY_SAFE;
    assert(ap_runtime_command(runtime, &command) == AP_OK);
    pm = process_one(runtime, mic, render, out);
    assert(pm.quality == AP_QUALITY_SAFE);
    for (i = 0u; i < 16u && ap_runtime_receive_event(runtime, &event) == AP_OK; ++i) {
        if (event.kind == AP_EVENT_QUALITY_DEGRADED &&
            event.arg0 == AP_QUALITY_FULL && event.arg1 == AP_QUALITY_SAFE)
            saw_degraded = 1;
    }
    assert(saw_degraded);
    ap_runtime_deinit(runtime);
}

static void test_bounded_memory_lock_path(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_runtime_metrics_t rm;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};

    options.lock_memory = 1u;
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    assert(ap_runtime_open(runtime_state, sizeof(runtime_state), pipeline,
                           &rcfg, &options, &runtime) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    (void)process_one(runtime, mic, render, out);
    rm = metrics(runtime);
    assert(rm.processed_frames == 1u);
    assert(rm.memory_lock_failures <= 1u);
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

/* The runtime command pre-validator and ap_pipeline_apply_tuning() share the
 * range helpers in src/ap_limits.h, so the two control-plane entry points must
 * return the same verdict for the same tuning value. Before the helpers existed
 * the two sites carried their own copies of the literals and only aec_mu was
 * pinned on the runtime side. The command queue holds two entries, so every
 * case runs against a freshly opened runtime. */
static void test_runtime_tuning_matches_pipeline(void) {
    static const struct {
        ap_tuning_mask_t mask;
        float aec_mu;
        float ns_floor;
        float agc_target_dbfs;
        float limiter_dbfs;
    } cases[] = {
        { AP_TUNING_NS_FLOOR, 0.22f, 0.01f, -20.0f, -2.0f },
        { AP_TUNING_NS_FLOOR, 0.22f, 0.12f, -20.0f, -2.0f },
        { AP_TUNING_AGC_TARGET, 0.22f, 0.12f, 0.0f, -2.0f },
        { AP_TUNING_AGC_TARGET, 0.22f, 0.12f, -20.0f, -2.0f },
        /* Individually valid AGC values can still violate the live pair when
         * only one field is updated. Runtime enqueue must reject exactly as the
         * pipeline boundary does. */
        { AP_TUNING_AGC_TARGET, 0.22f, 0.12f, -1.0f, -2.0f },
        { AP_TUNING_LIMITER, 0.22f, 0.12f, -20.0f, -20.0f },
        { AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER, 0.22f, 0.12f, -1.0f,
          -1.0f },
        { AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER, 0.22f, 0.12f, -20.0f,
          -2.0f },
        { AP_TUNING_LIMITER, 0.22f, 0.12f, -20.0f, 0.0f }
    };
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    unsigned i;
    unsigned rejected = 0u;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg,
                            &pipeline) == AP_OK);

    for (i = 0u; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        ap_tuning_t tuning;
        ap_runtime_command_t command;
        ap_runtime_t *runtime;
        ap_status_t pipeline_status;
        ap_status_t runtime_status;

        memset(&tuning, 0, sizeof(tuning));
        tuning.struct_size = sizeof(tuning);
        tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
        tuning.mask = cases[i].mask;
        tuning.aec_mu = cases[i].aec_mu;
        tuning.ns_floor = cases[i].ns_floor;
        tuning.agc_target_dbfs = cases[i].agc_target_dbfs;
        tuning.limiter_dbfs = cases[i].limiter_dbfs;

        /* apply_tuning() mutates the pipeline only on success, so its verdict
         * is taken first and the runtime verdict on an empty queue. */
        pipeline_status = ap_pipeline_apply_tuning(pipeline, &tuning);

        memset(&command, 0, sizeof(command));
        command.struct_size = sizeof(command);
        command.api_version = AP_RUNTIME_API_VERSION;
        command.kind = AP_RUNTIME_COMMAND_SET_TUNING;
        command.data.tuning = tuning;

        runtime = open_default(pipeline, &rcfg);
        runtime_status = ap_runtime_command(runtime, &command);
        ap_runtime_deinit(runtime);

        assert(runtime_status == pipeline_status);
        if (runtime_status != AP_OK) rejected++;
    }

    /* Fail-closed has to trigger, otherwise the loop proves nothing. */
    assert(rejected > 0u);
}

static void test_runtime_tuning_projects_pending_commands(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    ap_runtime_command_t command;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg,
                            &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);

    /* First command is valid against the live default pair (-20, -2). It is
     * intentionally left queued so the second command must validate against
     * the projected state (-3, -2), not the worker-owned pipeline's old pair. */
    memset(&command, 0, sizeof(command));
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_SET_TUNING;
    command.data.tuning.struct_size = sizeof(command.data.tuning);
    command.data.tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    command.data.tuning.mask = AP_TUNING_AGC_TARGET;
    command.data.tuning.agc_target_dbfs = -3.0f;
    assert(ap_runtime_command(runtime, &command) == AP_OK);

    /* -4 dBFS is a valid limiter value in isolation and would also be valid
     * against the live pipeline's still-old -20 dBFS target. Against the
     * accepted pending target (-3 dBFS), however, it is invalid and must not
     * consume the second queue slot. */
    command.data.tuning.mask = AP_TUNING_LIMITER;
    command.data.tuning.limiter_dbfs = -4.0f;
    assert(ap_runtime_command(runtime, &command) == AP_EINVAL);

    /* A limiter that is valid against the projected target still fits in the
     * queue, proving the rejected command did not advance either queue state or
     * the producer-side projected pair. */
    command.data.tuning.limiter_dbfs = -2.0f;
    assert(ap_runtime_command(runtime, &command) == AP_OK);

    memset(&command, 0, sizeof(command));
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_RESET;
    assert(ap_runtime_command(runtime, &command) == AP_EFULL);

    ap_runtime_deinit(runtime);
}

/* Tuning applied straight to a pipeline the caller owns (before start or after
 * stop). The unused half of the pair is still filled so the helper cannot hide
 * an unintended zero. */
static ap_status_t apply_agc(ap_pipeline_t *pipeline, ap_tuning_mask_t mask,
                             float target, float limiter) {
    ap_tuning_t tuning;

    memset(&tuning, 0, sizeof(tuning));
    tuning.struct_size = sizeof(tuning);
    tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    tuning.mask = mask;
    tuning.agc_target_dbfs = target;
    tuning.limiter_dbfs = limiter;
    return ap_pipeline_apply_tuning(pipeline, &tuning);
}

/* One SET_TUNING command through the runtime control queue. */
static ap_status_t queue_agc(ap_runtime_t *runtime,
                             ap_runtime_command_t *command,
                             ap_tuning_mask_t mask, float target,
                             float limiter) {
    memset(command, 0, sizeof(*command));
    command->struct_size = sizeof(*command);
    command->api_version = AP_RUNTIME_API_VERSION;
    command->kind = AP_RUNTIME_COMMAND_SET_TUNING;
    command->data.tuning.struct_size = sizeof(command->data.tuning);
    command->data.tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    command->data.tuning.mask = mask;
    command->data.tuning.agc_target_dbfs = target;
    command->data.tuning.limiter_dbfs = limiter;
    return ap_runtime_command(runtime, command);
}

/* The projected AGC pair only tracks tuning that entered through the command
 * queue, so it went stale when the caller changed tuning directly on a pipeline
 * it owns (before start or after stop) and then legitimately rejected commands
 * against a pair the pipeline no longer had. The projection is now refreshed
 * from the pipeline whenever the worker is stopped and nothing is pending. */
static void test_runtime_tuning_resyncs_caller_owned_pipeline(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime;
    ap_runtime_command_t command;
    ap_tuning_t tuning;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg,
                            &pipeline) == AP_OK);

    /* Phase 1: caller-owned tuning after open must refresh admission. -1.4 dBFS
     * is valid against the directly applied -1.2 dBFS limiter but not against
     * the -2 dBFS limiter the runtime recorded at open. */
    runtime = open_default(pipeline, &rcfg);
    assert(apply_agc(pipeline, AP_TUNING_LIMITER, -20.0f, -1.2f) == AP_OK);
    assert(queue_agc(runtime, &command, AP_TUNING_AGC_TARGET, -1.4f,
                     0.0f) == AP_OK);
    assert(queue_agc(runtime, &command, AP_TUNING_AGC_TARGET, -1.1f,
                     0.0f) == AP_EINVAL);
    assert(ap_runtime_start(runtime) == AP_OK);
    (void)process_one(runtime, mic, render, out);
    ap_runtime_stop(runtime);
    ap_runtime_deinit(runtime);

    memset(&tuning, 0, sizeof(tuning));
    assert(ap_pipeline_get_tuning(pipeline, &tuning) == AP_OK);
    assert(tuning.agc_target_dbfs == -1.4f);
    assert(tuning.limiter_dbfs == -1.2f);

    /* Phase 2: a stopped runtime must rebuild from the caller-owned pipeline
     * and then replay pending commands. The queued target -3 does not own the
     * limiter field; after the caller changes that field to -1.2, a second
     * target -1.4 is valid against the state the worker will actually reach.
     * A stale (-3,-2) projection would falsely reject it. */
    pcfg = ap_config_default(AP_PROFILE_CALL);
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg,
                            &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);
    assert(queue_agc(runtime, &command, AP_TUNING_AGC_TARGET, -3.0f,
                     0.0f) == AP_OK);
    assert(apply_agc(pipeline, AP_TUNING_LIMITER, -20.0f, -1.2f) == AP_OK);
    assert(queue_agc(runtime, &command, AP_TUNING_AGC_TARGET, -1.4f,
                     0.0f) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    (void)process_one(runtime, mic, render, out);
    ap_runtime_stop(runtime);
    ap_runtime_deinit(runtime);

    memset(&tuning, 0, sizeof(tuning));
    assert(ap_pipeline_get_tuning(pipeline, &tuning) == AP_OK);
    assert(tuning.agc_target_dbfs == -1.4f);
    assert(tuning.limiter_dbfs == -1.2f);

    /* Phase 3: direct caller tuning can also make an already accepted pending
     * sequence invalid. Limiter -4 is accepted against the default target -20;
     * changing the live target to -3 while stopped means applying that pending
     * limiter would create (-3,-4), which is invalid. Do not enqueue more work
     * or start the worker until the caller repairs the live pair. */
    pcfg = ap_config_default(AP_PROFILE_CALL);
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg,
                            &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);
    assert(queue_agc(runtime, &command, AP_TUNING_LIMITER, 0.0f,
                     -4.0f) == AP_OK);
    assert(apply_agc(pipeline, AP_TUNING_AGC_TARGET, -3.0f, -2.0f) == AP_OK);
    assert(queue_agc(runtime, &command, AP_TUNING_AGC_TARGET, -20.0f,
                     0.0f) == AP_ESTATE);
    assert(ap_runtime_start(runtime) == AP_ESTATE);

    assert(apply_agc(pipeline, AP_TUNING_AGC_TARGET, -20.0f, -2.0f) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    (void)process_one(runtime, mic, render, out);
    ap_runtime_stop(runtime);
    ap_runtime_deinit(runtime);

    memset(&tuning, 0, sizeof(tuning));
    assert(ap_pipeline_get_tuning(pipeline, &tuning) == AP_OK);
    assert(tuning.agc_target_dbfs == -20.0f);
    assert(tuning.limiter_dbfs == -4.0f);

    /* Phase 4: a direct change after open but before start must be captured at
     * hand-off so commands submitted while running never need to inspect the
     * worker-owned pipeline. */
    pcfg = ap_config_default(AP_PROFILE_CALL);
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg,
                            &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);
    assert(apply_agc(pipeline, AP_TUNING_LIMITER, -20.0f, -1.05f) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    assert(queue_agc(runtime, &command, AP_TUNING_AGC_TARGET, -1.1f,
                     0.0f) == AP_OK);
    (void)process_one(runtime, mic, render, out);
    ap_runtime_stop(runtime);
    ap_runtime_deinit(runtime);

    memset(&tuning, 0, sizeof(tuning));
    assert(ap_pipeline_get_tuning(pipeline, &tuning) == AP_OK);
    assert(tuning.agc_target_dbfs == -1.1f);
    assert(tuning.limiter_dbfs == -1.05f);

    /* Phase 5: the same runtime can hand ownership back on stop. A direct
     * caller change after stop must be captured by the next start before a
     * running-state command is validated only against the producer shadow. */
    pcfg = ap_config_default(AP_PROFILE_CALL);
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg,
                            &pipeline) == AP_OK);
    runtime = open_default(pipeline, &rcfg);
    assert(ap_runtime_start(runtime) == AP_OK);
    (void)process_one(runtime, mic, render, out);
    ap_runtime_stop(runtime);
    assert(apply_agc(pipeline, AP_TUNING_LIMITER, -20.0f, -1.05f) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    assert(queue_agc(runtime, &command, AP_TUNING_AGC_TARGET, -1.1f,
                     0.0f) == AP_OK);
    (void)process_one(runtime, mic, render, out);
    ap_runtime_stop(runtime);
    ap_runtime_deinit(runtime);

    memset(&tuning, 0, sizeof(tuning));
    assert(ap_pipeline_get_tuning(pipeline, &tuning) == AP_OK);
    assert(tuning.agc_target_dbfs == -1.1f);
    assert(tuning.limiter_dbfs == -1.05f);
}


/* Opt-in accelerated engineering endurance. No wall-clock soak or target timing
 * claim: the ordinary CTest invocation stays short and retains all contracts. */
static uint64_t engineering_now_ns(void) {
    struct timespec ts;
    assert(clock_gettime(CLOCK_MONOTONIC, &ts) == 0);
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}

static void engineering_receive(ap_runtime_t *runtime, int16_t *output) {
    const uint64_t deadline = engineering_now_ns() + UINT64_C(5000000000);
    unsigned spins = 0u;
    for (;;) {
        ap_status_t status = ap_runtime_receive(runtime, output, NULL);
        if (status == AP_OK) return;
        assert(status == AP_EEMPTY);
        if ((++spins & 255u) == 0u) {
            assert(engineering_now_ns() < deadline);
            (void)sched_yield();
        }
    }
}

static int engineering_count(const char *text, uint32_t *value) {
    char *end = NULL;
    unsigned long parsed;
    errno = 0;
    if (!text[0] || text[0] < '0' || text[0] > '9') return 0;
    parsed = strtoul(text, &end, 10);
    if (errno || !end || *end || parsed > 10000000ul) return 0;
    *value = (uint32_t)parsed;
    return *value > 0u;
}

static void test_engineering_endurance(uint32_t frames, uint32_t cycles) {
    const uint32_t per_cycle = frames / cycles;
    const uint64_t started = engineering_now_ns();
    uint64_t first_hash = 0u;
    uint64_t metadata_faults = 0u, missing_render = 0u, path_commands = 0u;
    uint32_t cycle;
    assert(per_cycle >= 1024u);
    for (cycle = 0u; cycle < cycles; ++cycle) {
        ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
        ap_runtime_config_t rcfg = ap_runtime_config_default();
        ap_pipeline_t *pipeline = NULL;
        ap_runtime_t *runtime;
        uint64_t hash = UINT64_C(14695981039346656037);
        uint64_t last_processed = 0u;
        int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
        int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
        int16_t output[AP_MAX_IO_FRAME_SAMPLES];
        uint32_t frame, i;
        /* Reuse the existing saturation, metadata, event/backpressure and
         * reset contracts rather than introducing alternate fault semantics. */
        test_command_validation_and_queue_pressure();
        test_metadata_event_drop_and_output_backpressure();
        assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg,
                                &pipeline) == AP_OK);
        rcfg.overload_us = UINT32_MAX; /* host scheduling is not DSP policy */
        rcfg.recover_frames = UINT32_MAX;
        runtime = open_default(pipeline, &rcfg);
        /* Deterministic input saturation before worker ownership. */
        for (i = 0u; i < AP_BUILD_RUNTIME_QUEUE_DEPTH; ++i)
            assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
        assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_EFULL);
        assert(metrics(runtime).input_full_events == 1u);
        ap_runtime_deinit(runtime);
        runtime = open_default(pipeline, &rcfg);
        assert(ap_runtime_start(runtime) == AP_OK);
        for (frame = 0u; frame < per_cycle; ++frame) {
            ap_frame_metadata_t md;
            const int no_render = frame % 997u == 0u;
            const uint32_t samples = pcfg.io_sample_rate_hz / 100u;
            memset(&md, 0, sizeof(md));
            md.struct_size = sizeof(md);
            md.api_version = AP_RUNTIME_API_VERSION;
            md.stream_sequence = frame;
            md.flags = AP_FRAME_CAPTURE_TIMESTAMP_VALID | AP_FRAME_RENDER_TIMESTAMP_VALID;
            md.capture_timestamp_ns = UINT64_C(1000000000) +
                                      (uint64_t)frame * UINT64_C(10000000);
            md.render_timestamp_ns = md.capture_timestamp_ns - UINT64_C(40000000);
            if (frame % 1021u == 0u) {
                md.flags |= AP_FRAME_CAPTURE_DISCONTINUITY | AP_FRAME_RENDER_DISCONTINUITY |
                            AP_FRAME_CLOCK_RESET | AP_FRAME_XRUN | AP_FRAME_CODEC_REOPEN;
                md.lost_capture_frames = 2u;
                md.lost_render_frames = 3u;
                md.capture_timestamp_ns += UINT64_C(200000000);
                md.render_timestamp_ns += UINT64_C(200000000);
                metadata_faults++;
            }
            if (frame % 4093u == 0u) {
                ap_runtime_command_t cmd;
                memset(&cmd, 0, sizeof(cmd));
                cmd.struct_size = sizeof(cmd);
                cmd.api_version = AP_RUNTIME_API_VERSION;
                cmd.kind = AP_RUNTIME_COMMAND_ECHO_PATH_CHANGE;
                assert(ap_runtime_command(runtime, &cmd) == AP_OK);
                path_commands++;
            }
            for (i = 0u; i < samples; ++i) {
                const uint32_t x = (frame * samples + i) * 1664525u + 1013904223u;
                const int32_t noise = (int32_t)(x >> 16u) - 32768;
                uint32_t ch;
                render[i] = (int16_t)(noise / 8);
                for (ch = 0u; ch < pcfg.mic_channels; ++ch)
                    mic[i * pcfg.mic_channels + ch] = (int16_t)(noise / (12 + (int32_t)ch));
            }
            assert(ap_runtime_submit_frame(runtime, mic, no_render ? NULL : render, &md) == AP_OK);
            if (no_render) missing_render++;
            engineering_receive(runtime, output);
            for (i = 0u; i < samples; ++i) {
                const uint16_t sample = (uint16_t)output[i];
                hash = (hash ^ (uint8_t)sample) * UINT64_C(1099511628211);
                hash = (hash ^ (uint8_t)(sample >> 8u)) * UINT64_C(1099511628211);
            }
            if (frame % 1024u == 0u) {
                const ap_runtime_metrics_t rm = metrics(runtime);
                assert(rm.processed_frames >= last_processed);
                assert(rm.failed_frames == 0u);
                last_processed = rm.processed_frames;
            }
        }
        {
            const ap_runtime_metrics_t rm = metrics(runtime);
            assert(rm.submitted_frames == per_cycle);
            assert(rm.processed_frames == per_cycle);
            assert(rm.failed_frames == 0u);
            assert(rm.input_full_events == 0u && rm.output_drop_events == 0u);
            assert(rm.capture_gap_frames >= 2u && rm.render_gap_frames >= 3u);
            assert(rm.timestamp_frames == per_cycle);
        }
        ap_runtime_stop(runtime);
        ap_runtime_deinit(runtime);
        if (cycle == 0u) first_hash = hash;
        else assert(hash == first_hash);
    }
    printf("{\"schema_version\":1,\"status\":\"PASS\","
           "\"authority\":\"host-engineering-not-product-soak\","
           "\"source_revision\":\"%s\",\"config_digest\":\"%s\","
           "\"frames\":%u,\"cycles\":%u,\"frames_per_cycle\":%u,"
           "\"processed_audio_seconds\":%.2f,\"host_wall_seconds\":%.6f,"
           "\"metadata_faults\":%" PRIu64 ",\"missing_render_frames\":%" PRIu64 ","
           "\"echo_path_commands\":%" PRIu64 ",\"fault_contract_cycles\":%u,"
           "\"repeated_output_fnv1a64\":\"%016" PRIx64 "\","
           "\"product_certification_authority\":false}\n",
           ap_build_info()->source_revision, ap_build_info()->config_digest,
           frames, cycles, per_cycle, (double)frames / 100.0,
           (double)(engineering_now_ns() - started) / 1.0e9,
           metadata_faults, missing_render, path_commands, cycles, first_hash);
}

int main(int argc, char **argv) {
    if (argc != 1) {
        uint32_t frames, cycles;
        if (argc != 4 || strcmp(argv[1], "--endurance") != 0 ||
            !engineering_count(argv[2], &frames) ||
            !engineering_count(argv[3], &cycles) || cycles > 128u ||
            frames % cycles != 0u || frames / cycles < 1024u) return 2;
        test_engineering_endurance(frames, cycles);
        return 0;
    }

    test_open_start_and_argument_failures();
    test_runtime_tuning_matches_pipeline();
    test_runtime_tuning_projects_pending_commands();
    test_runtime_tuning_resyncs_caller_owned_pipeline();
    test_command_validation_and_queue_pressure();
    test_metadata_event_drop_and_output_backpressure();
    test_automatic_quality_degrade_and_recovery();
    test_direct_quality_degradation_event();
    test_bounded_memory_lock_path();
    test_recorder_validation_record_and_export();
    test_recorder_attach_geometry();
    puts("audio-pipeline v2 extended runtime contracts: OK");
    return 0;
}
