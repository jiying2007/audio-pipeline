#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static AP_ALIGN16 unsigned char pipeline_state[AP_PIPELINE_STATE_MAX_BYTES];
static AP_ALIGN16 unsigned char runtime_state[AP_RUNTIME_STATE_MAX_BYTES];

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

int main(void) {
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
    rcfg.dsp_cpu = -1;
    rcfg.dsp_priority = 0;
    rcfg.overload_us = 9000u;
    rcfg.recover_frames = 20u;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);

    for (i = 0u; i < 8u; ++i)
        assert(ap_runtime_submit(runtime, mic, render) == AP_OK);
    assert(ap_runtime_submit(runtime, mic, render) == AP_EFULL);
    ap_runtime_get_metrics(runtime, &rm);
    assert(rm.submitted_frames == 8u);
    assert(rm.input_full_events == 1u);

    assert(ap_runtime_start(runtime) == AP_OK);
    assert(wait_processed(runtime, 8u, 1000u));

    for (i = 0u; i < 4u; ++i)
        assert(ap_runtime_submit(runtime, mic, render) == AP_OK);
    for (i = 0u; i < 1000u; ++i) {
        ap_runtime_get_metrics(runtime, &rm);
        if (rm.output_drop_events > 0u) break;
        sleep_ms(1u);
    }
    assert(rm.output_drop_events > 0u);

    while (ap_runtime_receive(runtime, out, &pm) == AP_OK) received++;
    assert(received == 8u);
    assert(pm.processed_frames == 8u);

    sleep_ms(10u);
    assert(ap_runtime_submit(runtime, mic, NULL) == AP_OK);
    assert(wait_processed(runtime, 9u, 1000u));
    for (i = 0u; i < 1000u; ++i) {
        if (ap_runtime_receive(runtime, out, &pm) == AP_OK) break;
        sleep_ms(1u);
    }
    assert(i < 1000u);
    assert(pm.processed_frames == 9u);

    ap_runtime_get_metrics(runtime, &rm);
    assert(rm.submitted_frames == 13u);
    assert(rm.processed_frames == 9u);
    assert(rm.input_full_events == 1u);
    assert(rm.output_drop_events >= 4u);
    assert(rm.max_dsp_us >= rm.last_dsp_us);

    ap_runtime_stop(runtime);
    ap_runtime_deinit(runtime);

    /* The same caller-owned storage can be initialized again after deinit. */
    runtime = NULL;
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    ap_runtime_deinit(runtime);

    puts("audio-pipeline runtime tests: OK");
    return 0;
}
