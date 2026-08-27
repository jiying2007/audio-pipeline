#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
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
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    uint32_t frames = 50000u;
    uint32_t rate = 16000u;
    int enable_res = 0;
    uint32_t frame_samples, f, i;
    uint64_t t0, t1;
    ap_metrics_t m;

    if (argc > 1) frames = (uint32_t)strtoul(argv[1], NULL, 10);
    if (argc > 2) rate = (uint32_t)strtoul(argv[2], NULL, 10);
    if (argc > 3) enable_res = atoi(argv[3]) != 0;
    if (frames == 0u) frames = 1u;
    if (rate != 8000u && rate != 16000u) {
        fprintf(stderr, "rate must be 8000 or 16000\n");
        return 2;
    }

    c.io_sample_rate_hz = rate;
    c.internal_sample_rate_hz = rate;
    c.mic_channels = 1u;
    c.max_delay_ms = 0u;
    c.initial_delay_ms = 0u;
    c.enable_hpf = 0u;
    c.enable_beamformer = 0u;
    c.enable_delay_tracking = 0u;
    c.enable_clock_drift_compensation = 0u;
    c.enable_aec = 0u;
    c.enable_residual_echo_suppression = (uint8_t)(enable_res ? 1u : 0u);
    c.enable_noise_suppression = 1u;
    c.enable_agc = 0u;
    c.enable_vad = 0u;

    if (ap_pipeline_init(state, sizeof(state), &c, &p) != AP_OK) {
        fprintf(stderr, "pipeline init failed\n");
        return 3;
    }
    frame_samples = rate / 100u;
    memset(mic, 0, sizeof(mic));
    memset(render, 0, sizeof(render));
    for (i = 0u; i < frame_samples; ++i) {
        const int32_t far = (int32_t)((i * 521u + 997u) % 12000u) - 6000;
        const int32_t near = (int32_t)((i * 197u + 313u) % 1200u) - 600;
        render[i] = (int16_t)far;
        mic[i] = (int16_t)near;
    }

    /* Warm the overlap/noise estimators before timing steady state. */
    for (f = 0u; f < 100u; ++f) {
        if (ap_pipeline_push_render(p, render, frame_samples) != AP_OK ||
            ap_pipeline_process_capture(p, mic, frame_samples, out) != AP_OK)
            return 4;
    }

    t0 = now_ns();
    for (f = 0u; f < frames; ++f) {
        if (ap_pipeline_push_render(p, render, frame_samples) != AP_OK ||
            ap_pipeline_process_capture(p, mic, frame_samples, out) != AP_OK)
            return 5;
    }
    t1 = now_ns();
    ap_pipeline_get_metrics(p, &m);

    {
        const double elapsed_s = (double)(t1 - t0) / 1.0e9;
        const double us_per_frame = (double)(t1 - t0) / 1000.0 / (double)frames;
        printf("rate=%u res=%d frames=%u elapsed_s=%.6f us_per_frame=%.3f processed=%llu freq_res=%u noise_dbfs=%.2f\n",
               rate, enable_res, frames, elapsed_s, us_per_frame,
               (unsigned long long)m.processed_frames,
               (unsigned)m.frequency_res_active, m.noise_rms_dbfs);
        if (m.processed_frames != (uint64_t)frames + 100u ||
            (enable_res && m.frequency_res_active == 0u) ||
            (!enable_res && m.frequency_res_active != 0u)) {
            fprintf(stderr, "NS benchmark correctness gate failed\n");
            return 6;
        }
    }
    return 0;
}
