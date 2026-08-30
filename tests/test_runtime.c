#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if defined(_MSC_VER)
#define AP_PIPE_ALIGN __declspec(align(AP_PIPELINE_STATE_ALIGNMENT))
#define AP_RT_ALIGN __declspec(align(AP_RUNTIME_STATE_ALIGNMENT))
#define AP_DIAG_ALIGN __declspec(align(AP_FLIGHT_RECORDER_STATE_ALIGNMENT))
#else
#define AP_PIPE_ALIGN _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
#define AP_RT_ALIGN _Alignas(AP_RUNTIME_STATE_ALIGNMENT)
#define AP_DIAG_ALIGN _Alignas(AP_FLIGHT_RECORDER_STATE_ALIGNMENT)
#endif

static AP_PIPE_ALIGN unsigned char pipeline_state[AP_PIPELINE_STATE_MAX_BYTES];
static AP_RT_ALIGN unsigned char runtime_state[AP_RUNTIME_STATE_MAX_BYTES];
static AP_RT_ALIGN unsigned char runtime_misaligned[
    AP_RUNTIME_STATE_MAX_BYTES + AP_RUNTIME_STATE_ALIGNMENT];
static AP_DIAG_ALIGN unsigned char recorder_state[32768];
static unsigned char dump_state[32768];

static void sleep_ms(unsigned ms) {
    struct timespec ts;
    ts.tv_sec = (time_t)(ms / 1000u);
    ts.tv_nsec = (long)(ms % 1000u) * 1000000L;
    (void)nanosleep(&ts, NULL);
}

static int wait_processed(ap_runtime_t *runtime, uint64_t target, unsigned timeout_ms) {
    unsigned i;
    for (i = 0u; i < timeout_ms; ++i) {
        ap_runtime_metrics_t m;
        ap_runtime_get_metrics(runtime, &m);
        if (m.processed_frames >= target) return 1;
        sleep_ms(1u);
    }
    return 0;
}

static ap_runtime_metrics_v3_t metrics_v3(ap_runtime_t *runtime) {
    ap_runtime_metrics_v3_t m;
    memset(&m, 0, sizeof(m));
    m.struct_size = sizeof(m);
    m.api_version = AP_RUNTIME_METRICS_V3_API_VERSION;
    assert(ap_runtime_get_metrics_v3(runtime, &m) == AP_OK);
    return m;
}

static ap_runtime_metrics_v2_t metrics_v2(ap_runtime_t *runtime) {
    ap_runtime_metrics_v2_t m;
    memset(&m, 0, sizeof(m));
    m.struct_size = sizeof(m);
    m.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    assert(ap_runtime_get_metrics_v2(runtime, &m) == AP_OK);
    return m;
}

static ap_metrics_t process_one(ap_runtime_t *runtime,
                                const int16_t *mic,
                                const int16_t *render,
                                int16_t *out) {
    ap_metrics_t pm;
    unsigned i;
    assert(ap_runtime_submit(runtime, mic, render) == AP_OK);
    for (i = 0u; i < 1000u; ++i) {
        if (ap_runtime_receive(runtime, out, &pm) == AP_OK) return pm;
        sleep_ms(1u);
    }
    assert(!"timed out waiting for runtime output");
    memset(&pm, 0, sizeof(pm));
    return pm;
}

static void test_runtime_init_contract(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_runtime_options_t opts = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    assert(rcfg.dsp_cpu == -1);
    assert(rcfg.dsp_priority == 0);
    assert(opts.struct_size == sizeof(opts));
    assert(opts.api_version == AP_RUNTIME_CONTROL_API_VERSION);
    assert(ap_runtime_state_alignment() == AP_RUNTIME_STATE_ALIGNMENT);
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    assert(ap_runtime_init(NULL, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_EINVAL);
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), NULL, &rcfg, &runtime) == AP_EINVAL);
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, NULL, &runtime) == AP_EINVAL);
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, NULL) == AP_EINVAL);
    assert(ap_runtime_init(runtime_state, ap_runtime_state_size() - 1u,
                           pipeline, &rcfg, &runtime) == AP_ENOMEM);
    assert(ap_runtime_init(runtime_misaligned + 1u, sizeof(runtime_misaligned) - 1u,
                           pipeline, &rcfg, &runtime) == AP_EINVAL);
    rcfg.recover_frames = 0u;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_EINVAL);
    rcfg = ap_runtime_config_default();
    opts.api_version = 0u;
    assert(ap_runtime_init_ex(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &opts, &runtime) == AP_EINVAL);
}

static void test_queue_and_lifecycle(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_runtime_metrics_t rm;
    ap_runtime_metrics_v2_t rm2;
    ap_metrics_t pm;
    int16_t mic[320] = {0};
    int16_t render[160] = {0};
    int16_t out[160];
    unsigned i, received = 0u;

    assert(ap_pipeline_state_size() <= sizeof(pipeline_state));
    assert(ap_runtime_state_size() <= sizeof(runtime_state));
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    rcfg.overload_us = 9000u;
    rcfg.recover_frames = 20u;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);

    for (i = 0u; i < AP_BUILD_RUNTIME_QUEUE_DEPTH; ++i)
        assert(ap_runtime_submit(runtime, mic, render) == AP_OK);
    assert(ap_runtime_submit(runtime, mic, render) == AP_EFULL);
    ap_runtime_get_metrics(runtime, &rm);
    assert(rm.submitted_frames == AP_BUILD_RUNTIME_QUEUE_DEPTH);
    assert(rm.input_full_events == 1u);

    assert(ap_runtime_start(runtime) == AP_OK);
    assert(wait_processed(runtime, AP_BUILD_RUNTIME_QUEUE_DEPTH, 1000u));

    /* Keep the output queue full and submit more capture. The DSP timeline must
     * continue even though publication cannot keep up. */
    for (i = 0u; i < 4u; ++i)
        assert(ap_runtime_submit(runtime, mic, render) == AP_OK);
    assert(wait_processed(runtime, AP_BUILD_RUNTIME_QUEUE_DEPTH + 4u, 1000u));

    ap_runtime_get_metrics(runtime, &rm);
    assert(rm.submitted_frames == AP_BUILD_RUNTIME_QUEUE_DEPTH + 4u);
    assert(rm.processed_frames == rm.submitted_frames);
    assert(rm.input_full_events == 1u);
    assert(rm.output_drop_events == 4u);
    assert(rm.max_dsp_us >= rm.last_dsp_us);

    rm2 = metrics_v2(runtime);
    assert(rm2.input_queue_high_water == AP_BUILD_RUNTIME_QUEUE_DEPTH);
    assert(rm2.output_queue_high_water == AP_BUILD_RUNTIME_QUEUE_DEPTH);
    assert(rm2.p99_dsp_us >= rm2.p50_dsp_us);

    while (ap_runtime_receive(runtime, out, &pm) == AP_OK) received++;
    assert(received == AP_BUILD_RUNTIME_QUEUE_DEPTH);

    ap_runtime_stop(runtime);
    ap_runtime_deinit(runtime);

    runtime = NULL;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    (void)process_one(runtime, mic, NULL, out);
    ap_runtime_get_metrics(runtime, &rm);
    assert(rm.submitted_frames == 1u);
    assert(rm.processed_frames == 1u);
    assert(rm.input_full_events == 0u);
    assert(rm.output_drop_events == 0u);
    ap_runtime_deinit(runtime);
}

static void test_memory_lock_lifecycle(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_runtime_options_t opts = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_runtime_metrics_v2_t rm2;

    opts.lock_memory = 1u;
    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    assert(ap_runtime_init_ex(runtime_state, sizeof(runtime_state), pipeline,
                              &rcfg, &opts, &runtime) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    ap_runtime_stop(runtime);
    rm2 = metrics_v2(runtime);
    assert(rm2.memory_lock_failures <= 1u);
    ap_runtime_deinit(runtime);
}

static void test_metadata_commands_and_events(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_frame_metadata_t meta;
    ap_runtime_command_t cmd;
    ap_runtime_metrics_v2_t rm2;
    ap_metrics_t pm;
    ap_event_t event;
    int16_t mic[320] = {0};
    int16_t render[160] = {0};
    int16_t out[160];
    unsigned i;
    int saw_discontinuity = 0;
    int saw_direct_degradation = 0;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    rcfg.recover_frames = 100u;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);

    memset(&meta, 0, sizeof(meta));
    meta.struct_size = sizeof(meta);
    meta.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    meta.flags = AP_FRAME_CAPTURE_TIMESTAMP_VALID | AP_FRAME_RENDER_TIMESTAMP_VALID |
                 AP_FRAME_CAPTURE_DISCONTINUITY;
    meta.stream_sequence = 42u;
    meta.capture_timestamp_ns = 100000000ull;
    meta.render_timestamp_ns = 60000000ull;
    meta.lost_capture_frames = 3u;
    assert(ap_runtime_submit_ex(runtime, mic, render, &meta) == AP_OK);
    for (i = 0u; i < 1000u; ++i) {
        if (ap_runtime_receive(runtime, out, &pm) == AP_OK) break;
        sleep_ms(1u);
    }
    assert(i < 1000u);
    rm2 = metrics_v2(runtime);
    assert(rm2.stream_discontinuities >= 1u);
    assert(rm2.capture_gap_frames >= 3u);
    assert(rm2.timestamp_frames >= 1u);

    while (ap_runtime_receive_event(runtime, &event) == AP_OK) {
        if (event.kind == AP_EVENT_STREAM_DISCONTINUITY) saw_discontinuity = 1;
    }
    assert(saw_discontinuity);

    memset(&cmd, 0, sizeof(cmd));
    cmd.struct_size = sizeof(cmd);
    cmd.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    cmd.kind = 0x7fffffffu;
    assert(ap_runtime_command(runtime, &cmd) == AP_EINVAL);
    cmd.kind = AP_RUNTIME_COMMAND_SET_QUALITY;
    cmd.data.set_quality.quality = (ap_quality_t)99;
    assert(ap_runtime_command(runtime, &cmd) == AP_EINVAL);
    cmd.kind = AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY;
    cmd.data.discontinuity.flags = 1u << 31;
    assert(ap_runtime_command(runtime, &cmd) == AP_EINVAL);

    memset(&cmd, 0, sizeof(cmd));
    cmd.struct_size = sizeof(cmd);
    cmd.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    cmd.kind = AP_RUNTIME_COMMAND_SET_QUALITY;
    cmd.data.set_quality.quality = AP_QUALITY_SAFE;
    assert(ap_runtime_command(runtime, &cmd) == AP_OK);
    pm = process_one(runtime, mic, render, out);
    assert(pm.quality == AP_QUALITY_SAFE);
    while (ap_runtime_receive_event(runtime, &event) == AP_OK) {
        if (event.kind == AP_EVENT_QUALITY_DEGRADED &&
            event.arg0 == AP_QUALITY_FULL && event.arg1 == AP_QUALITY_SAFE)
            saw_direct_degradation = 1;
    }
    assert(saw_direct_degradation);

    memset(&cmd, 0, sizeof(cmd));
    cmd.struct_size = sizeof(cmd);
    cmd.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    cmd.kind = AP_RUNTIME_COMMAND_SET_TUNING;
    cmd.data.tuning.struct_size = sizeof(cmd.data.tuning);
    cmd.data.tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    cmd.data.tuning.mask = AP_TUNING_AEC_MU | AP_TUNING_NS_FLOOR;
    cmd.data.tuning.aec_mu = 0.15f;
    cmd.data.tuning.ns_floor = 0.20f;
    assert(ap_runtime_command(runtime, &cmd) == AP_OK);
    (void)process_one(runtime, mic, render, out);

    ap_runtime_deinit(runtime);
}


static void test_recorder_configuration_contract(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_flight_recorder_config_t dcfg = ap_flight_recorder_config_default(16000u, 2u);
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_flight_recorder_t *recorder = NULL;

    assert(dcfg.record_mask == AP_DIAG_RECORD_METRICS);
    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    assert(ap_flight_recorder_state_size(&dcfg) > 0u);
    dcfg.frame_samples++;
    assert(ap_flight_recorder_state_size(&dcfg) == 0u);
    dcfg = ap_flight_recorder_config_default(11025u, 2u);
    assert(ap_flight_recorder_state_size(&dcfg) == 0u);
    dcfg = ap_flight_recorder_config_default(16000u, 2u);
    dcfg.pre_roll_frames = UINT32_MAX;
    dcfg.post_roll_frames = UINT32_MAX;
    assert(ap_flight_recorder_state_size(&dcfg) == 0u);

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    dcfg = ap_flight_recorder_config_default(8000u, 2u);
    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &dcfg, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_EINVAL);
    dcfg = ap_flight_recorder_config_default(16000u, 1u);
    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &dcfg, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_EINVAL);
    dcfg = ap_flight_recorder_config_default(16000u, 2u);
    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &dcfg, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_OK);
    ap_runtime_deinit(runtime);
}

static void test_flight_recorder(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_flight_recorder_config_t dcfg = ap_flight_recorder_config_default(16000u, 2u);
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_flight_recorder_t *recorder = NULL;
    ap_frame_metadata_t meta;
    int16_t mic[320] = {0};
    int16_t render[160] = {0};
    size_t need, written = 0u;

    dcfg.pre_roll_frames = 2u;
    dcfg.post_roll_frames = 1u;
    dcfg.record_mask = AP_DIAG_RECORD_ALL;
    dcfg.trigger_severity = AP_EVENT_WARN;
    need = ap_flight_recorder_state_size(&dcfg);
    assert(need > 0u && need <= sizeof(recorder_state));
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &dcfg, &recorder) == AP_OK);

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);

    memset(&meta, 0, sizeof(meta));
    meta.struct_size = sizeof(meta);
    meta.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    meta.flags = AP_FRAME_CAPTURE_DISCONTINUITY;
    meta.lost_capture_frames = 1u;
    assert(ap_runtime_submit_ex(runtime, mic, render, &meta) == AP_OK);
    assert(ap_runtime_submit(runtime, mic, render) == AP_OK);
    assert(wait_processed(runtime, 2u, 1000u));
    assert(ap_flight_recorder_is_frozen(recorder));
    assert(ap_flight_recorder_export_size(recorder) <= sizeof(dump_state));
    assert(ap_flight_recorder_export(recorder, dump_state, sizeof(dump_state), &written) == AP_OK);
    assert(written == ap_flight_recorder_export_size(recorder));
    assert(written > 128u);

    ap_runtime_deinit(runtime);
}

static void test_recorder_trigger_survives_event_queue_full(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_flight_recorder_config_t dcfg = ap_flight_recorder_config_default(16000u, 2u);
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_flight_recorder_t *recorder = NULL;
    ap_runtime_metrics_v2_t rm2;
    int16_t mic[320] = {0};
    size_t need;

    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    dcfg.record_mask = AP_DIAG_RECORD_METRICS;
    dcfg.trigger_severity = AP_EVENT_ERROR;
    need = ap_flight_recorder_state_size(&dcfg);
    assert(need > 0u && need <= sizeof(recorder_state));
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &dcfg, &recorder) == AP_OK);

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    rcfg.overload_us = 0u;
    rcfg.recover_frames = 100u;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);

    /* RUNTIME_STARTED occupies the first event slot and RENDER_MISSING occupies
     * the second. The following ERROR deadline event must still trigger the
     * recorder even though delivery through the event ring is now full. */
    assert(ap_runtime_submit(runtime, mic, NULL) == AP_OK);
    assert(wait_processed(runtime, 1u, 1000u));
    rm2 = metrics_v2(runtime);
    assert(rm2.event_drop_events >= 1u);
    assert(ap_flight_recorder_is_frozen(recorder));
    {
        ap_runtime_critical_state_t critical;
        ap_runtime_metrics_v3_t rm3 = metrics_v3(runtime);
        memset(&critical, 0, sizeof(critical));
        critical.struct_size = sizeof(critical);
        critical.api_version = AP_RUNTIME_CRITICAL_STATE_API_VERSION;
        assert(ap_runtime_get_critical_state(runtime, &critical) == AP_OK);
        assert(critical.total_events >= 1u);
        assert(critical.severity >= AP_EVENT_ERROR);
        assert(rm3.critical_events >= 1u);
        assert(rm3.failed_frames == 0u);
    }

    ap_runtime_deinit(runtime);
}

static void test_quality_transitions(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_metrics_t pm;
    int16_t mic[320] = {0};
    int16_t render[160] = {0};
    int16_t out[160];
    unsigned i;

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    rcfg.overload_us = 0u;
    rcfg.recover_frames = 2u;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);

    for (i = 0u; i < 3u; ++i) pm = process_one(runtime, mic, render, out);
    assert(pm.quality == AP_QUALITY_LITE);
    for (i = 0u; i < 3u; ++i) pm = process_one(runtime, mic, render, out);
    assert(pm.quality == AP_QUALITY_SAFE);

    ap_runtime_deinit(runtime);
    runtime = NULL;
    rcfg.overload_us = UINT32_MAX;
    rcfg.recover_frames = 2u;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    for (i = 0u; i < 2u; ++i) pm = process_one(runtime, mic, render, out);
    assert(pm.quality == AP_QUALITY_LITE);
    for (i = 0u; i < 2u; ++i) pm = process_one(runtime, mic, render, out);
    assert(pm.quality == AP_QUALITY_FULL);
    ap_runtime_deinit(runtime);
}

int main(void) {
    test_runtime_init_contract();
    test_queue_and_lifecycle();
    test_memory_lock_lifecycle();
    test_metadata_commands_and_events();
    test_recorder_configuration_contract();
    test_flight_recorder();
    test_recorder_trigger_survives_event_queue_full();
    test_quality_transitions();
    puts("audio-pipeline runtime tests: OK");
    return 0;
}
