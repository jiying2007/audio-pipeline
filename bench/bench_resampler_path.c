#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static AP_ALIGN16 unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];

static uint64_t now_ns(void) {
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static ap_config_t resampler_only_config(uint32_t io_rate, uint32_t internal_rate) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    c.io_sample_rate_hz = io_rate;
    c.internal_sample_rate_hz = internal_rate;
    c.mic_channels = 1u;
    c.enable_hpf = 0u;
    c.enable_beamformer = 0u;
    c.enable_delay_tracking = 0u;
    c.enable_clock_drift_compensation = 0u;
    c.enable_aec = 0u;
    c.enable_residual_echo_suppression = 0u;
    c.enable_noise_suppression = 0u;
    c.enable_agc = 0u;
    c.enable_vad = 0u;
    return c;
}

int main(int argc, char **argv) {
    uint32_t io_rate = 48000u;
    uint32_t internal_rate = 16000u;
    uint32_t frames = 100000u;
    ap_config_t cfg;
    ap_pipeline_t *pipeline = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    uint32_t io_frames, frame, i;
    uint64_t t0, t1;
    volatile int64_t checksum = 0;

    if (argc > 1) io_rate = (uint32_t)strtoul(argv[1], NULL, 10);
    if (argc > 2) internal_rate = (uint32_t)strtoul(argv[2], NULL, 10);
    if (argc > 3) frames = (uint32_t)strtoul(argv[3], NULL, 10);
    if (!frames) frames = 1u;

    cfg = resampler_only_config(io_rate, internal_rate);
    io_frames = io_rate / 100u;
    if (!io_frames || io_frames > AP_MAX_IO_FRAME_SAMPLES) return 2;
    if (ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) != AP_OK) return 3;

    for (i = 0u; i < io_frames; ++i)
        mic[i] = (int16_t)((int32_t)((i * 1103u + 7919u) % 40001u) - 20000);

    /* Warm caches and pipeline state before timing. */
    for (frame = 0u; frame < 200u; ++frame) {
        mic[frame % io_frames] ^= (int16_t)(frame * 17u);
        if (ap_pipeline_process_capture(pipeline, mic, io_frames, out) != AP_OK) return 4;
        checksum += out[(frame * 13u) % io_frames];
    }

    t0 = now_ns();
    for (frame = 0u; frame < frames; ++frame) {
        const uint32_t pos = frame % io_frames;
        mic[pos] = (int16_t)(mic[pos] + (int16_t)((frame & 31u) - 15u));
        if (ap_pipeline_process_capture(pipeline, mic, io_frames, out) != AP_OK) return 5;
        checksum += out[(frame * 29u) % io_frames];
    }
    t1 = now_ns();

    printf("resampler_path io=%u internal=%u frames=%u us_per_frame=%.6f checksum=%lld\n",
           io_rate, internal_rate, frames,
           (double)(t1 - t0) / 1000.0 / (double)frames,
           (long long)checksum);
    return 0;
}
