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
#else
#define AP_PIPE_ALIGN _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
#define AP_RT_ALIGN _Alignas(AP_RUNTIME_STATE_ALIGNMENT)
#endif

static AP_PIPE_ALIGN unsigned char pipeline_state[AP_PIPELINE_STATE_MAX_BYTES];
static AP_RT_ALIGN unsigned char runtime_state[AP_RUNTIME_STATE_MAX_BYTES];
static AP_RT_ALIGN unsigned char runtime_misaligned[
    AP_RUNTIME_STATE_MAX_BYTES + AP_RUNTIME_STATE_ALIGNMENT];

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
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    assert(rcfg.dsp_cpu == -1);
    assert(rcfg.dsp_priority == 0);
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
}

static void test_queue_and_lifecycle(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_runtime_metrics_t rm;
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

    for (i = 0u; i < 4u; ++i)
        assert(ap_runtime_submit(runtime, mic, render) == AP_OK);
    for (i = 0u; i < 1000u; ++i) {
        ap_runtime_get_metrics(runtime, &rm);
        if (rm.output_drop_events > 0u) break;
        sleep_ms(1u);
    }
    assert(rm.output_drop_events > 0u);

    while (ap_runtime_receive(runtime, out, &pm) == AP_OK) received++;
    assert(received == AP_BUILD_RUNTIME_QUEUE_DEPTH);
    assert(pm.processed_frames == AP_BUILD_RUNTIME_QUEUE_DEPTH);

    sleep_ms(10u);
    assert(ap_runtime_submit(runtime, mic, NULL) == AP_OK);
    assert(wait_processed(runtime, AP_BUILD_RUNTIME_QUEUE_DEPTH + 1u, 1000u));
    for (i = 0u; i < 1000u; ++i) {
        if (ap_runtime_receive(runtime, out, &pm) == AP_OK) break;
        sleep_ms(1u);
    }
    assert(i < 1000u);
    assert(pm.processed_frames == AP_BUILD_RUNTIME_QUEUE_DEPTH + 1u);

    ap_runtime_get_metrics(runtime, &rm);
    assert(rm.submitted_frames == AP_BUILD_RUNTIME_QUEUE_DEPTH + 5u);
    assert(rm.processed_frames == AP_BUILD_RUNTIME_QUEUE_DEPTH + 1u);
    assert(rm.input_full_events == 1u);
    /* Exact drop count is scheduler-dependent; bounded overflow visibility is not. */
    assert(rm.output_drop_events > 0u);
    assert(rm.max_dsp_us >= rm.last_dsp_us);

    ap_runtime_stop(runtime);
    ap_runtime_deinit(runtime);
    runtime = NULL;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
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
    test_quality_transitions();
    puts("audio-pipeline runtime tests: OK");
    return 0;
}
