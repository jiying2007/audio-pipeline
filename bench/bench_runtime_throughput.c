#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static uint64_t now_ns(void) {
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
    AP_ALIGN16 static unsigned char runtime_mem[AP_RUNTIME_STATE_MAX_BYTES];
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    uint32_t frames = 10000u;
    uint32_t f, i;
    int minimal = 0;
    uint64_t t0, t1;

    if (argc > 1) frames = (uint32_t)strtoul(argv[1], NULL, 10);
    if (argc > 2) {
        if (strcmp(argv[2], "minimal") == 0) minimal = 1;
        else if (strcmp(argv[2], "full") != 0) {
            fprintf(stderr, "mode must be minimal or full\n");
            return 2;
        }
    }
    if (frames == 0u) frames = 1u;

    if (minimal) {
        pcfg.mic_channels = 1u;
        pcfg.initial_delay_ms = 0u;
        pcfg.enable_hpf = 0u;
        pcfg.enable_beamformer = 0u;
        pcfg.enable_delay_tracking = 0u;
        pcfg.enable_clock_drift_compensation = 0u;
        pcfg.enable_aec = 0u;
        pcfg.enable_residual_echo_suppression = 0u;
        pcfg.enable_noise_suppression = 0u;
        pcfg.enable_agc = 0u;
        pcfg.enable_vad = 0u;
    }

    memset(mic, 0, sizeof(mic));
    memset(render, 0, sizeof(render));
    for (i = 0u; i < pcfg.io_sample_rate_hz / 100u; ++i) {
        const int16_t far = (int16_t)((int)(i % 31u) * 211 - 3165);
        render[i] = far;
        mic[i * pcfg.mic_channels] = (int16_t)(far / 5);
        if (pcfg.mic_channels == 2u)
            mic[i * 2u + 1u] = (int16_t)(far / 6);
    }

    rcfg.dsp_cpu = -1;
    rcfg.dsp_priority = 0;
    rcfg.overload_us = UINT32_MAX;
    rcfg.recover_frames = UINT32_MAX;
    if (ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &pcfg, &pipeline) != AP_OK ||
        ap_runtime_init(runtime_mem, sizeof(runtime_mem), pipeline, &rcfg, &runtime) != AP_OK ||
        ap_runtime_start(runtime) != AP_OK) {
        fprintf(stderr, "runtime throughput init failed\n");
        return 3;
    }

    t0 = now_ns();
    for (f = 0u; f < frames; ++f) {
        ap_status_t s = ap_runtime_submit(runtime, mic, render);
        if (s != AP_OK) {
            fprintf(stderr, "submit failed frame=%u status=%d\n", f, (int)s);
            ap_runtime_deinit(runtime);
            return 4;
        }
        do {
            s = ap_runtime_receive(runtime, out, NULL);
        } while (s == AP_EEMPTY);
        if (s != AP_OK) {
            fprintf(stderr, "receive failed frame=%u status=%d\n", f, (int)s);
            ap_runtime_deinit(runtime);
            return 5;
        }
    }
    t1 = now_ns();

    {
        ap_runtime_metrics_t rm;
        const double elapsed_s = (double)(t1 - t0) / 1.0e9;
        const double us_per_frame = (double)(t1 - t0) / 1000.0 / (double)frames;
        ap_runtime_get_metrics(runtime, &rm);
        printf("mode=%s frames=%u elapsed_s=%.6f us_per_frame=%.3f processed=%llu input_full=%llu output_drop=%llu dsp_overruns=%llu quality=%d\n",
               minimal ? "minimal" : "full", frames, elapsed_s, us_per_frame,
               (unsigned long long)rm.processed_frames,
               (unsigned long long)rm.input_full_events,
               (unsigned long long)rm.output_drop_events,
               (unsigned long long)rm.dsp_overruns,
               (int)rm.quality);
        if (rm.processed_frames != frames || rm.input_full_events != 0u ||
            rm.output_drop_events != 0u || rm.dsp_overruns != 0u) {
            fprintf(stderr, "runtime throughput correctness gate failed\n");
            ap_runtime_deinit(runtime);
            return 6;
        }
    }

    ap_runtime_deinit(runtime);
    return 0;
}
