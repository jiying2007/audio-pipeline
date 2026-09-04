#include "audio_pipeline/audio_modules.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static float rms_dbfs(const float *x, size_t n) {
    double energy = 1.0e-18;
    size_t i;
    for (i = 0; i < n; ++i) energy += (double)x[i] * (double)x[i];
    return (float)(10.0 * log10(energy / (double)n + 1.0e-18));
}

static float peak_dbfs(const float *x, size_t n) {
    float peak = 1.0e-9f;
    size_t i;
    for (i = 0; i < n; ++i) {
        const float value = fabsf(x[i]);
        if (value > peak) peak = value;
    }
    return 20.0f * log10f(peak);
}

int main(int argc, char **argv) {
#if !AP_HAVE_MODULE_AGC
    (void)argc;
    (void)argv;
    fputs("AGC module is not compiled\n", stderr);
    return 2;
#else
    AP_ALIGN16 static unsigned char state[AP_MODULE_STATE_MAX_BYTES];
    int16_t pcm[AP_BUILD_MAX_INTERNAL_RATE_HZ / 100u];
    float samples[AP_BUILD_MAX_INTERNAL_RATE_HZ / 100u];
    ap_agc_module_t *agc = NULL;
    ap_module_agc_config_t cfg;
    FILE *input;
    const size_t frame = 160u;
    unsigned frame_index = 0u;
    size_t i;

    if (argc != 4) {
        fprintf(stderr, "usage: %s TARGET_DBFS LIMITER_DBFS INPUT_PCM\n", argv[0]);
        return 2;
    }
    cfg.target_dbfs = strtof(argv[1], NULL);
    cfg.limiter_dbfs = strtof(argv[2], NULL);
    if (!isfinite(cfg.target_dbfs) || !isfinite(cfg.limiter_dbfs)) return 2;
    if (ap_module_agc_state_size() > sizeof(state) ||
        ap_module_agc_init(state, sizeof(state), &cfg, &agc) != AP_OK) {
        fputs("AGC init failed\n", stderr);
        return 3;
    }
    input = fopen(argv[3], "rb");
    if (!input) {
        perror("fopen");
        return 2;
    }
    while (fread(pcm, sizeof(pcm[0]), frame, input) == frame) {
        float input_rms;
        float input_peak;
        float output_rms;
        float output_peak;
        for (i = 0u; i < frame; ++i) samples[i] = (float)pcm[i] / 32768.0f;
        input_rms = rms_dbfs(samples, frame);
        input_peak = peak_dbfs(samples, frame);
        if (ap_module_agc_process(agc, samples, frame) != AP_OK) {
            fclose(input);
            return 4;
        }
        output_rms = rms_dbfs(samples, frame);
        output_peak = peak_dbfs(samples, frame);
        printf("{\"frame\":%u,\"input_rms_dbfs\":%.7g,\"output_rms_dbfs\":%.7g,"
               "\"input_peak_dbfs\":%.7g,\"output_peak_dbfs\":%.7g,"
               "\"gain_db\":%.7g}\n",
               frame_index,
               (double)input_rms,
               (double)output_rms,
               (double)input_peak,
               (double)output_peak,
               (double)(output_rms - input_rms));
        frame_index++;
    }
    fclose(input);
    return 0;
#endif
}
