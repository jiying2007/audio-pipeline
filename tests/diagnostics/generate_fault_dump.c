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

static int select_fault(const char *name, ap_frame_metadata_t *metadata) {
    if (strcmp(name, "capture-gap") == 0) {
        metadata->flags |= AP_FRAME_CAPTURE_DISCONTINUITY;
        metadata->lost_capture_frames = 3u;
        return 1;
    }
    if (strcmp(name, "render-gap") == 0) {
        metadata->flags |= AP_FRAME_RENDER_DISCONTINUITY;
        metadata->lost_render_frames = 2u;
        return 1;
    }
    if (strcmp(name, "clock-reset") == 0) {
        metadata->flags |= AP_FRAME_CLOCK_RESET;
        return 1;
    }
    if (strcmp(name, "xrun") == 0) {
        metadata->flags |= AP_FRAME_XRUN;
        return 1;
    }
    if (strcmp(name, "codec-reopen") == 0) {
        metadata->flags |= AP_FRAME_CODEC_REOPEN;
        return 1;
    }
    return 0;
}

int main(int argc, char **argv) {
    ap_config_t pipeline_config = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t runtime_config = ap_runtime_config_default();
    ap_runtime_options_t runtime_options = ap_runtime_options_default();
    ap_flight_recorder_config_t recorder_config;
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_flight_recorder_t *recorder = NULL;
    ap_frame_metadata_t metadata;
    int16_t mic[320];
    int16_t render[160];
    size_t need;
    size_t written = 0u;
    FILE *file;
    unsigned i;

    if (argc != 3) {
        fprintf(stderr,
                "usage: %s <capture-gap|render-gap|clock-reset|xrun|codec-reopen> <output.apd>\n",
                argv[0]);
        return 2;
    }

    memset(&metadata, 0, sizeof(metadata));
    metadata.struct_size = sizeof(metadata);
    metadata.api_version = AP_RUNTIME_API_VERSION;
    metadata.flags = AP_FRAME_CAPTURE_TIMESTAMP_VALID |
                     AP_FRAME_RENDER_TIMESTAMP_VALID;
    metadata.stream_sequence = 42u;
    metadata.capture_timestamp_ns = 1000000000ull;
    metadata.render_timestamp_ns = 960000000ull;
    if (!select_fault(argv[1], &metadata)) {
        fprintf(stderr, "unknown fault case: %s\n", argv[1]);
        return 2;
    }

    for (i = 0u; i < 160u; ++i) {
        render[i] = (int16_t)(((int)i * 97) % 5000 - 2500);
        mic[2u * i] =
            (int16_t)(render[i] / 2 + (int16_t)(i % 31u) * 10);
        mic[2u * i + 1u] =
            (int16_t)(render[i] / 3 - (int16_t)(i % 17u) * 7);
    }

    recorder_config = ap_flight_recorder_config_default(16000u, 2u);
    recorder_config.record_mask = AP_DIAG_RECORD_ALL;
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
    assert(ap_runtime_open(runtime_state,
                           sizeof(runtime_state),
                           pipeline,
                           &runtime_config,
                           &runtime_options,
                           &runtime) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_OK);
    assert(ap_runtime_start(runtime) == AP_OK);
    assert(ap_runtime_submit_frame(runtime, mic, render, &metadata) == AP_OK);

    for (i = 0u; i < 1000u; ++i) {
        if (ap_flight_recorder_is_frozen(recorder)) break;
        sleep_ms(1u);
    }
    assert(i < 1000u);
    ap_runtime_deinit(runtime);

    assert(ap_flight_recorder_export_size(recorder) <= sizeof(export_buffer));
    assert(ap_flight_recorder_export(recorder,
                                     export_buffer,
                                     sizeof(export_buffer),
                                     &written) == AP_OK);
    assert(written > 0u);

    file = fopen(argv[2], "wb");
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
