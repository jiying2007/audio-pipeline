#define _GNU_SOURCE
#include "audio_pipeline/audio_runtime.h"
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <unistd.h>

static _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
unsigned char pipeline_memory[AP_PIPELINE_STATE_MAX_BYTES];
static _Alignas(AP_RUNTIME_STATE_ALIGNMENT)
unsigned char runtime_memory[AP_RUNTIME_STATE_MAX_BYTES];
static int inject_failure;
static unsigned create_calls;
static int inject_create_failure;

int __real_pthread_attr_init(pthread_attr_t *attr);
int __real_pthread_create(pthread_t *thread, const pthread_attr_t *attr,
                          void *(*start)(void *), void *arg);
int __wrap_pthread_attr_init(pthread_attr_t *attr) {
    if (inject_failure) { inject_failure = 0; return ENOMEM; }
    return __real_pthread_attr_init(attr);
}
int __wrap_pthread_create(pthread_t *thread, const pthread_attr_t *attr,
                          void *(*start)(void *), void *arg) {
    ++create_calls;
    if (inject_create_failure) { inject_create_failure = 0; return EAGAIN; }
    return __real_pthread_create(thread, attr, start, arg);
}

static int check(ap_profile_t profile, size_t stack_bytes) {
    ap_config_t pcfg = ap_config_default(profile);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_status_t status;
    unsigned before;
    int failed = 0;
    options.dsp_stack_bytes = stack_bytes;
    if (ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory), &pcfg, &pipeline) != AP_OK ||
        ap_runtime_open(runtime_memory, sizeof(runtime_memory), pipeline,
                        &rcfg, &options, &runtime) != AP_OK) return 1;
    before = create_calls;
    inject_failure = 1;
    status = ap_runtime_start(runtime);
    /* Baseline may actually start a default-stack worker. Join before reporting. */
    if (status == AP_OK) ap_runtime_stop(runtime);
    printf("profile=%d stack=%zu injected_status=%d create_calls=%u\n",
           (int)profile, stack_bytes, (int)status, create_calls - before);
    if (status != AP_ESTATE || create_calls != before || inject_failure) failed = 1;
    /* A failure must leave STOPPED, not strand the lifecycle in RUNNING. */
    before = create_calls;
    status = ap_runtime_start(runtime);
    if (status != AP_OK || create_calls != before + 1u) failed = 1;
    if (status == AP_OK) {
        if (ap_runtime_start(runtime) != AP_ESTATE) failed = 1;
        ap_runtime_stop(runtime);
    }
    ap_runtime_deinit(runtime);
    return failed;
}
/* A resource-denied create must not consume queued input or strand RUNNING.
 * This is deterministic link-wrap injection, not natural system exhaustion. */
static int check_create_failure(ap_profile_t profile, size_t stack_bytes) {
    ap_config_t pcfg = ap_config_default(profile);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    int16_t mic[AP_BUILD_IO_FRAME_MAX * AP_BUILD_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_BUILD_IO_FRAME_MAX] = {0};
    int16_t output[AP_BUILD_IO_FRAME_MAX] = {0};
    ap_status_t status;
    unsigned before, tries;
    int failed = 0;
    options.dsp_stack_bytes = stack_bytes;
    if (ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory), &pcfg, &pipeline) != AP_OK ||
        ap_runtime_open(runtime_memory, sizeof(runtime_memory), pipeline,
                        &rcfg, &options, &runtime) != AP_OK) return 1;
    if (ap_runtime_submit_frame(runtime, mic, render, NULL) != AP_OK) failed = 1;
    before = create_calls;
    inject_create_failure = 1;
    status = ap_runtime_start(runtime);
    if (status == AP_OK) ap_runtime_stop(runtime);
    printf("create profile=%d stack=%zu injected_status=%d create_calls=%u\n",
           (int)profile, stack_bytes, (int)status, create_calls - before);
    if (status != AP_ESTATE || create_calls != before + 1u || inject_create_failure)
        failed = 1;
    if (ap_runtime_receive(runtime, output, NULL) != AP_EEMPTY) failed = 1;
    before = create_calls;
    status = ap_runtime_start(runtime);
    if (status != AP_OK || create_calls != before + 1u) failed = 1;
    if (status == AP_OK) {
        if (ap_runtime_start(runtime) != AP_ESTATE || create_calls != before + 1u) failed = 1;
        for (tries = 0; tries < 1000u; ++tries) {
            status = ap_runtime_receive(runtime, output, NULL);
            if (status != AP_EEMPTY) break;
            usleep(1000);
        }
        if (status != AP_OK) failed = 1;
        if (ap_runtime_receive(runtime, output, NULL) != AP_EEMPTY) failed = 1;
        ap_runtime_stop(runtime);
        if (ap_runtime_receive(runtime, output, NULL) != AP_EEMPTY) failed = 1;
    }
    ap_runtime_deinit(runtime);
    return failed;
}

int main(void) {
    int failed = 0;
    failed += check(AP_PROFILE_CALL, 256u * 1024u);
    failed += check(AP_PROFILE_ASSISTANT, 256u * 1024u);
    failed += check(AP_PROFILE_CALL, 0u);
    failed += check(AP_PROFILE_ASSISTANT, 0u);
    printf("attribute-init fault cases=4 failures=%d\n", failed);
    failed += check_create_failure(AP_PROFILE_CALL, 256u * 1024u);
    failed += check_create_failure(AP_PROFILE_ASSISTANT, 256u * 1024u);
    failed += check_create_failure(AP_PROFILE_CALL, 0u);
    failed += check_create_failure(AP_PROFILE_ASSISTANT, 0u);
    printf("all fault cases=8 failures=%d\n", failed);
    return failed ? 1 : 0;
}
