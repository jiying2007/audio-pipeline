#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_modules.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static uint64_t now_ns(void) {
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

int main(int argc, char **argv) {
#if !AP_HAVE_MODULE_RESAMPLER
    (void)argc; (void)argv;
    return 2;
#else
    uint32_t io_rate = 48000u;
    uint32_t internal_rate = 16000u;
    uint32_t frames = 100000u;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    float internal[160];
    uint32_t io_frames, internal_frames, frame, i;
    uint64_t t0, t1;
    volatile int64_t checksum = 0;

    if (argc > 1) io_rate = (uint32_t)strtoul(argv[1], NULL, 10);
    if (argc > 2) internal_rate = (uint32_t)strtoul(argv[2], NULL, 10);
    if (argc > 3) frames = (uint32_t)strtoul(argv[3], NULL, 10);
    if (!frames) frames = 1u;
    io_frames = io_rate / 100u;
    internal_frames = internal_rate / 100u;
    if (!io_frames || io_frames > AP_MAX_IO_FRAME_SAMPLES ||
        (internal_rate != 8000u && internal_rate != 16000u)) return 2;

    for (i = 0u; i < io_frames; ++i)
        mic[i] = (int16_t)((int32_t)((i * 1103u + 7919u) % 40001u) - 20000);

    for (frame = 0u; frame < 200u; ++frame) {
        mic[frame % io_frames] ^= (int16_t)(frame * 17u);
        if (ap_module_resampler_input_s16(mic, io_frames, 1u, 0u,
                                          internal, internal_frames) != AP_OK ||
            ap_module_resampler_output_s16(internal, internal_frames,
                                           out, io_frames) != AP_OK)
            return 3;
        checksum += out[(frame * 13u) % io_frames];
    }

    t0 = now_ns();
    for (frame = 0u; frame < frames; ++frame) {
        const uint32_t pos = frame % io_frames;
        mic[pos] = (int16_t)(mic[pos] + (int16_t)((frame & 31u) - 15u));
        if (ap_module_resampler_input_s16(mic, io_frames, 1u, 0u,
                                          internal, internal_frames) != AP_OK ||
            ap_module_resampler_output_s16(internal, internal_frames,
                                           out, io_frames) != AP_OK)
            return 4;
        checksum += out[(frame * 29u) % io_frames];
    }
    t1 = now_ns();

    printf("resampler_path io=%u internal=%u frames=%u us_per_frame=%.6f checksum=%lld\n",
           io_rate, internal_rate, frames,
           (double)(t1 - t0) / 1000.0 / (double)frames,
           (long long)checksum);
    return 0;
#endif
}
