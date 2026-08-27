#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_modules.h"
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
#if !AP_HAVE_MODULE_NS
    (void)argc; (void)argv;
    return 2;
#else
    AP_ALIGN16 static unsigned char memory[AP_MODULE_STATE_MAX_BYTES];
    ap_ns_module_t *ns = NULL;
    ap_module_ns_config_t cfg;
    ap_module_ns_result_t result;
    float input[160], predicted_echo[160], output[160];
    uint32_t frames = 50000u;
    uint32_t rate = 16000u;
    int enable_res = 0;
    uint32_t frame_samples, f, i;
    uint64_t t0, t1;

    if (argc > 1) frames = (uint32_t)strtoul(argv[1], NULL, 10);
    if (argc > 2) rate = (uint32_t)strtoul(argv[2], NULL, 10);
    if (argc > 3) enable_res = atoi(argv[3]) != 0;
    if (frames == 0u) frames = 1u;
    if (rate != 8000u && rate != 16000u) return 2;
#if !AP_HAVE_MODULE_RES
    if (enable_res) return 2;
#endif

    frame_samples = rate / 100u;
    cfg.sample_rate_hz = rate;
    cfg.floor_gain = 0.12f;
    if (ap_module_ns_state_size() > sizeof(memory) ||
        ap_module_ns_init(memory, sizeof(memory), &cfg, &ns) != AP_OK)
        return 3;

    for (i = 0u; i < frame_samples; ++i) {
        input[i] = ((float)((int32_t)((i * 197u + 313u) % 1200u) - 600)) / 32768.0f;
        predicted_echo[i] = 0.0f;
    }

    for (f = 0u; f < 100u; ++f) {
        if (ap_module_ns_process(ns, AP_QUALITY_FULL, input, predicted_echo,
                                 output, frame_samples, enable_res,
                                 enable_res, 0, &result) != AP_OK)
            return 4;
    }

    t0 = now_ns();
    for (f = 0u; f < frames; ++f) {
        if (ap_module_ns_process(ns, AP_QUALITY_FULL, input, predicted_echo,
                                 output, frame_samples, enable_res,
                                 enable_res, 0, &result) != AP_OK)
            return 5;
    }
    t1 = now_ns();

    printf("rate=%u res=%d frames=%u elapsed_s=%.6f us_per_frame=%.3f freq_res=%u noise_dbfs=%.2f\n",
           rate, enable_res, frames, (double)(t1 - t0) / 1.0e9,
           (double)(t1 - t0) / 1000.0 / (double)frames,
           (unsigned)result.frequency_res_active, result.noise_rms_dbfs);
    if ((enable_res && result.frequency_res_active == 0u) ||
        (!enable_res && result.frequency_res_active != 0u))
        return 6;
    return 0;
#endif
}
