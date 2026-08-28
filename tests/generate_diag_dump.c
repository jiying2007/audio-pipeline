#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
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
unsigned char recorder_state[8192];
static unsigned char export_buffer[8192];

static void sleep_ms(unsigned ms) {
    struct timespec ts;
    ts.tv_sec = (time_t)(ms / 1000u);
    ts.tv_nsec = (long)(ms % 1000u) * 1000000L;
    (void)nanosleep(&ts, NULL);
}

int main(int argc, char **argv) {
    ap_config_t pipeline_config = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t runtime_config = ap_runtime_config_default();
    ap_flight_recorder_config_t recorder_config;
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_flight_recorder_t *recorder = NULL;
    int16_t mic[320];
    int16_t render[160];
    ap_runtime_metrics_t runtime_metrics;
    size_t need;
    size_t written = 0u;
    FILE *file;
    unsigned i;

    if (argc != 2) {
        fprintf(stderr, "usage: %s <output.apd>\n", argv[0]);
        return 2;
    }
    for (i = 0u; i < 160u; ++i) {
        render[i] = (int16_t)(((int)i * 97) % 5000 - 2500);
        mic[2u * i] = (int16_t)(render[i] / 2 + (int16_t)(i % 31u) * 10);
        mic[2u * i + 1u] = (int16_t)(render[i] / 3 - (int16_t)(i % 17u) * 7);
    }

    recorder_config = ap_flight_recorder_config_default(16000u, 2u);
    recorder_config.pre_roll_frames = 0u;
    recorder_config.post_roll_frames = 0u;
    recorder_config.trigger_severity = AP_EVENT_WARN;
    need = ap_flight_recorder_state_size(&recorder_config);
    assert(need > 0u && need <= sizeof(recorder_state));
    assert(ap_flight_recorder_init(recorder_state,
                                   sizeof(recorder_state),
                                   &recorder_config,
                                   &recorder) == AP_OK);
    assert(ap_pipeline_init(pipeline_state,
                            sizeof(pipeline_state),
                            &pipeline_config,
                            &pipeline) == AP_OK);
    assert(ap_runtime_init(runtime_state,
                           sizeof(runtime_state),
                           pipeline,
                           &runtime_config,
                           &runtime) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_OK);
    assert(ap_flight_recorder_trigger(recorder,
                                      AP_EVENT_DIAG_TRIGGERED,
                                      AP_EVENT_WARN) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    assert(ap_runtime_submit(runtime, mic, render) == AP_OK);
    for (i = 0u; i < 1000u; ++i) {
        ap_runtime_get_metrics(runtime, &runtime_metrics);
        if (runtime_metrics.processed_frames >= 1u) break;
        sleep_ms(1u);
    }
    assert(i < 1000u);
    assert(ap_flight_recorder_is_frozen(recorder));
    ap_runtime_deinit(runtime);

    assert(ap_flight_recorder_export_size(recorder) <= sizeof(export_buffer));
    assert(ap_flight_recorder_export(recorder,
                                     export_buffer,
                                     sizeof(export_buffer),
                                     &written) == AP_OK);
    file = fopen(argv[1], "wb");
    if (!file) {
        perror("fopen");
        return 2;
    }
    if (fwrite(export_buffer, 1u, written, file) != written) {
        fclose(file);
        return 3;
    }
    fclose(file);
    return 0;
}
