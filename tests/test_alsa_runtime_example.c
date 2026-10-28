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
enum io_scenario { IO_UNUSED, IO_CLEAN, IO_CAPTURE, IO_RENDER, IO_BOTH,
                   IO_INTERRUPT, IO_RECOVERY_FAILURE };
static enum io_scenario io_scenario;
static unsigned io_submitted;
static unsigned recovery_calls;
static unsigned io_frame;
static unsigned io_channels;
static int example_clock_gettime(clockid_t clock_id, struct timespec *value);
static ap_status_t example_receive(ap_runtime_t *runtime, int16_t *output,
                                   ap_metrics_t *metrics);
static ap_status_t example_submit(ap_runtime_t *runtime, const int16_t *mic,
                                  const int16_t *render,
                                  const ap_frame_metadata_t *metadata);
#define main alsa_example_main
#define clock_gettime example_clock_gettime
#define ap_runtime_receive example_receive
#define ap_runtime_submit_frame example_submit
#include "../examples/alsa_runtime_duplex.c"
#undef ap_runtime_submit_frame
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

/* A scripted transport drives the actual example recovery/submission path.
 * Zero actions mean a full requested transfer; negative actions are ALSA
 * errors. Each example invocation runs in its own CTest process. */
struct snd_pcm {
    unsigned channels;
    unsigned action_count;
    unsigned cursor;
    snd_pcm_sframes_t actions[3];
    snd_pcm_uframes_t requests[4];
};
static struct snd_pcm capture_pcm;
static struct snd_pcm playback_pcm;

int snd_pcm_open(snd_pcm_t **pcm, const char *name, int stream, int flags) {
    (void)name; (void)flags;
    if (io_scenario == IO_UNUSED) return -ENODEV;
    *pcm = stream == SND_PCM_STREAM_CAPTURE ? &capture_pcm : &playback_pcm;
    return 0;
}
int snd_pcm_close(snd_pcm_t *pcm) { (void)pcm; return 0; }
int snd_pcm_set_params(snd_pcm_t *pcm, int format, int access, unsigned channels,
                       unsigned rate, int resample, unsigned latency) {
    (void)format; (void)access; (void)rate; (void)resample; (void)latency;
    pcm->channels = channels;
    return 0;
}
const char *snd_strerror(int error) { (void)error; return "unit-test transport"; }
int snd_pcm_recover(snd_pcm_t *pcm, int error, int silent) {
    (void)pcm; (void)error; (void)silent;
    recovery_calls++;
    return io_scenario == IO_RECOVERY_FAILURE ? -EIO : 0;
}
static snd_pcm_sframes_t scripted_transfer(snd_pcm_t *pcm,
                                            snd_pcm_uframes_t frames) {
    const unsigned cursor = pcm->cursor++;
    const snd_pcm_sframes_t action = cursor < pcm->action_count ?
                                     pcm->actions[cursor] : 0;
    if (cursor < 4u) pcm->requests[cursor] = frames;
    if (action < 0) return action;
    assert((snd_pcm_uframes_t)action <= frames);
    return action ? action : (snd_pcm_sframes_t)frames;
}
snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *pcm, const void *data,
                                 snd_pcm_uframes_t frames) {
    (void)data;
    return scripted_transfer(pcm, frames);
}
snd_pcm_sframes_t snd_pcm_readi(snd_pcm_t *pcm, void *data,
                                snd_pcm_uframes_t frames) {
    const unsigned cursor = pcm->cursor;
    const snd_pcm_sframes_t count = scripted_transfer(pcm, frames);
    if (count > 0) {
        int16_t *samples = data;
        const int16_t value = cursor == 0u && pcm->action_count ? 111 : 222;
        for (size_t i = 0u; i < (size_t)count * pcm->channels; ++i)
            samples[i] = value;
    }
    return count;
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

static ap_status_t example_submit(ap_runtime_t *runtime, const int16_t *input,
                                  const int16_t *reference,
                                  const ap_frame_metadata_t *metadata) {
    const int capture_gap = io_scenario == IO_CAPTURE || io_scenario == IO_BOTH;
    const int render_gap = io_scenario == IO_RENDER || io_scenario == IO_BOTH;
    ap_runtime_metrics_t metrics;
    if (io_submitted == 0u) {
        uint32_t expected_flags = 0u;
        if (capture_gap) expected_flags |= AP_FRAME_CAPTURE_DISCONTINUITY | AP_FRAME_XRUN;
        if (render_gap) expected_flags |= AP_FRAME_RENDER_DISCONTINUITY | AP_FRAME_XRUN;
        assert((metadata ? metadata->flags : 0u) == expected_flags);
        if (expected_flags) {
            assert(metadata != NULL);
            assert(metadata->lost_capture_frames == 0u);
            assert(metadata->lost_render_frames == 0u);
        }
        for (unsigned i = 0u; i < io_frame * io_channels; ++i) {
            const int16_t expected = io_scenario == IO_INTERRUPT && i < 64u * io_channels ?
                                     111 : 222;
            assert(input[i] == expected);
        }
    } else {
        assert(metadata == NULL);
    }
    assert(ap_runtime_submit_frame(runtime, input, reference, metadata) == AP_OK);
    metrics = wait_processed(runtime, ++io_submitted);
    assert(metrics.stream_discontinuities == (uint64_t)(capture_gap || render_gap));
    assert(metrics.capture_gap_frames == (uint64_t)capture_gap);
    assert(metrics.render_gap_frames == (uint64_t)render_gap);
    return AP_OK;
}

static void test_io_recovery(const char *scenario) {
    char rate_text[16];
    char channels_text[16];
    char *args[] = {"alsa-unit", "capture", "playback", "-", "-", "1",
                    "-1", rate_text, channels_text, NULL};
    int result;
    const unsigned rate = AP_BUILD_MAX_IO_RATE_HZ < 16000u ?
                           AP_BUILD_MAX_IO_RATE_HZ : 16000u;
    io_frame = rate / 100u;
    io_channels = AP_BUILD_MAX_MIC_CHANNELS;
    (void)snprintf(rate_text, sizeof(rate_text), "%u", rate);
    (void)snprintf(channels_text, sizeof(channels_text), "%u", io_channels);
    if (strcmp(scenario, "clean") == 0) io_scenario = IO_CLEAN;
    else if (strcmp(scenario, "capture") == 0) io_scenario = IO_CAPTURE;
    else if (strcmp(scenario, "render") == 0) io_scenario = IO_RENDER;
    else if (strcmp(scenario, "both") == 0) io_scenario = IO_BOTH;
    else if (strcmp(scenario, "interrupt") == 0) io_scenario = IO_INTERRUPT;
    else if (strcmp(scenario, "recovery-failure") == 0) io_scenario = IO_RECOVERY_FAILURE;
    else assert(!"unknown unit I/O scenario");
    if (io_scenario == IO_CAPTURE || io_scenario == IO_BOTH ||
        io_scenario == IO_INTERRUPT || io_scenario == IO_RECOVERY_FAILURE) {
        capture_pcm.action_count = 3u;
        capture_pcm.actions[0] = 64;
        capture_pcm.actions[1] = io_scenario == IO_INTERRUPT ? -EINTR : -EPIPE;
    }
    if (io_scenario == IO_RENDER || io_scenario == IO_BOTH) {
        playback_pcm.action_count = 3u;
        playback_pcm.actions[0] = 64;
        playback_pcm.actions[1] = -ESTRPIPE;
    }
    result = alsa_example_main(9, args);
    if (io_scenario == IO_RECOVERY_FAILURE) {
        assert(result != 0 && io_submitted == 0u && recovery_calls == 1u);
        return;
    }
    assert(result == 0 && io_submitted == 100u);
    assert(recovery_calls == (io_scenario == IO_BOTH ? 2u :
                              io_scenario == IO_CLEAN ? 0u : 1u));
    if (io_scenario == IO_CAPTURE || io_scenario == IO_BOTH)
        assert(capture_pcm.requests[2] == io_frame);
    if (io_scenario == IO_RENDER || io_scenario == IO_BOTH)
        assert(playback_pcm.requests[2] == io_frame);
    if (io_scenario == IO_INTERRUPT)
        assert(capture_pcm.requests[2] == io_frame - 64u);
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

int main(int argc, char **argv) {
    if (argc == 3 && strcmp(argv[1], "--io") == 0) {
        test_io_recovery(argv[2]);
        puts("ALSA recovery unit contract: OK (no hardware authority)");
        return 0;
    }
    assert(argc == 1);
    test_complete_delivery();
    test_output_drop_terminates_drain();
    test_stalled_and_failed_completion();
    puts("audio-pipeline ALSA example unit contracts: OK (no hardware authority)");
    return 0;
}
