/* Test the real example and real SDK with a unit-only ALSA transport and
 * controlled clock/error boundaries. This is not DUT, acoustic or HIL evidence.
 */
#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_runtime.h"
#include <alsa/asoundlib.h>
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

static uint64_t clock_step_ns;
static uint64_t clock_now_ns;
static ap_status_t receive_error;
static int example_clock_gettime(clockid_t clock_id, struct timespec *value);
static ap_status_t example_receive(ap_runtime_t *runtime, int16_t *output,
                                   ap_metrics_t *metrics);
#define main alsa_example_main
#define clock_gettime example_clock_gettime
#define ap_runtime_receive example_receive
#include "../examples/alsa_runtime_duplex.c"
#undef ap_runtime_receive
#undef clock_gettime
#undef main

static int example_clock_gettime(clockid_t clock_id, struct timespec *value) {
    if (!clock_step_ns) return clock_gettime(clock_id, value);
    assert(clock_id == CLOCK_MONOTONIC);
    value->tv_sec = (time_t)(clock_now_ns / UINT64_C(1000000000));
    value->tv_nsec = (long)(clock_now_ns % UINT64_C(1000000000));
    clock_now_ns += clock_step_ns;
    return 0;
}

static ap_status_t example_receive(ap_runtime_t *runtime, int16_t *output,
                                   ap_metrics_t *metrics) {
    if (receive_error != AP_OK) return receive_error;
    return ap_runtime_receive(runtime, output, metrics);
}

/* These declarations resolve the real example's optional device entry point.
 * The completion tests below use the real SDK without opening a device. */
int snd_pcm_open(snd_pcm_t **pcm, const char *name, int stream, int flags) {
    (void)pcm; (void)name; (void)stream; (void)flags; return -ENODEV;
}
int snd_pcm_close(snd_pcm_t *pcm) { (void)pcm; return 0; }
int snd_pcm_set_params(snd_pcm_t *pcm, int format, int access, unsigned channels,
                       unsigned rate, int resample, unsigned latency) {
    (void)pcm; (void)format; (void)access; (void)channels; (void)rate;
    (void)resample; (void)latency; return -ENODEV;
}
const char *snd_strerror(int error) { (void)error; return "unit-test transport"; }
int snd_pcm_recover(snd_pcm_t *pcm, int error, int silent) {
    (void)pcm; (void)error; (void)silent; return -ENODEV;
}
snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *pcm, const void *data,
                                 snd_pcm_uframes_t frames) {
    (void)pcm; (void)data; (void)frames; return -ENODEV;
}
snd_pcm_sframes_t snd_pcm_readi(snd_pcm_t *pcm, void *data,
                                snd_pcm_uframes_t frames) {
    (void)pcm; (void)data; (void)frames; return -ENODEV;
}
int snd_pcm_drop(snd_pcm_t *pcm) { (void)pcm; return 0; }
int snd_pcm_prepare(snd_pcm_t *pcm) { (void)pcm; return 0; }

static _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
unsigned char pipeline_memory[AP_PIPELINE_STATE_MAX_BYTES];
static _Alignas(AP_RUNTIME_STATE_ALIGNMENT)
unsigned char runtime_memory[AP_RUNTIME_STATE_MAX_BYTES];
static int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
static int16_t render[AP_MAX_IO_FRAME_SAMPLES];
static int16_t output[AP_MAX_IO_FRAME_SAMPLES];

static ap_runtime_t *open_runtime(void) {
    ap_config_t pipeline_config = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t config = ap_runtime_config_default();
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    assert(ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory),
                            &pipeline_config, &pipeline) == AP_OK);
    assert(ap_runtime_open(runtime_memory, sizeof(runtime_memory), pipeline,
                           &config, &options, &runtime) == AP_OK);
    return runtime;
}

static ap_runtime_metrics_t wait_processed(ap_runtime_t *runtime, unsigned count) {
    ap_runtime_metrics_t metrics = {0};
    const struct timespec pause = {0, 1000000};
    metrics.struct_size = sizeof(metrics);
    metrics.api_version = AP_RUNTIME_API_VERSION;
    for (unsigned i = 0u; i < 2000u; ++i) {
        assert(ap_runtime_read_metrics(runtime, &metrics) == AP_OK);
        if (metrics.processed_frames >= count) return metrics;
        (void)nanosleep(&pause, NULL);
    }
    assert(!"runtime processing timeout");
    return metrics;
}

static void test_complete_delivery(void) {
    ap_runtime_t *runtime = open_runtime();
    unsigned received = 0u;
    assert(ap_runtime_start(runtime) == AP_OK);
    assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
    (void)wait_processed(runtime, 1u);
    ap_runtime_stop(runtime);
    assert(drain_runtime(runtime, NULL, output, 160u, 1u, &received) == DRAIN_OK);
    assert(received == 1u);
    ap_runtime_deinit(runtime);
}

static void test_output_drop_terminates_drain(void) {
    ap_runtime_t *runtime = open_runtime();
    unsigned received = 0u;
    assert(ap_runtime_start(runtime) == AP_OK);
    for (unsigned i = 0u; i < AP_BUILD_RUNTIME_QUEUE_DEPTH + 1u; ++i) {
        assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
        (void)wait_processed(runtime, i + 1u);
    }
    ap_runtime_stop(runtime);
    assert(wait_processed(runtime, AP_BUILD_RUNTIME_QUEUE_DEPTH + 1u).output_drop_events == 1u);
    assert(drain_runtime(runtime, NULL, output, 160u,
                          AP_BUILD_RUNTIME_QUEUE_DEPTH + 1u, &received) == DRAIN_ERROR);
    assert(received == AP_BUILD_RUNTIME_QUEUE_DEPTH);
    ap_runtime_deinit(runtime);
}

static void test_stalled_and_failed_completion(void) {
    ap_runtime_t *runtime = open_runtime();
    unsigned received = 0u;
    /* Accepted while stopped: no worker can produce this completion. Advance
     * only the example's clock, preserving the fixed production deadline. */
    assert(ap_runtime_submit_frame(runtime, mic, render, NULL) == AP_OK);
    clock_now_ns = 0u;
    clock_step_ns = UINT64_C(1000000000);
    assert(drain_runtime(runtime, NULL, output, 160u, 1u, &received) == DRAIN_TIMEOUT);
    assert(received == 0u && clock_now_ns == UINT64_C(3000000000));
    clock_step_ns = 0u;
    receive_error = AP_ESTATE;
    assert(drain_runtime(runtime, NULL, output, 160u, 1u, &received) == DRAIN_ERROR);
    assert(received == 0u);
    receive_error = AP_OK;
    ap_runtime_deinit(runtime);
}

int main(void) {
    test_complete_delivery();
    test_output_drop_terminates_drain();
    test_stalled_and_failed_completion();
    puts("audio-pipeline ALSA example unit contracts: OK (no hardware authority)");
    return 0;
}
