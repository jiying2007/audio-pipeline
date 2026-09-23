#include "audio_pipeline/audio_modules.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if !AP_HAVE_MODULE_NS
#error "I011 probe requires standalone NS module"
#endif

#define FRAME 160u
#define BASE_FLOOR 0.12f
#define STRESS_FLOOR 0.05f

_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char ns_base_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char ns_stress_mem[AP_MODULE_STATE_MAX_BYTES];

static float frame_rms_dbfs(const float *x) {
    double energy = 1.0e-18;
    uint32_t i;
    for (i = 0u; i < FRAME; ++i)
        energy += (double)x[i] * (double)x[i];
    energy /= (double)FRAME;
    return 10.0f * log10f((float)energy);
}

static uint32_t next_pow2(uint32_t x) {
    uint32_t p = 1u;
    while (p < x) p <<= 1u;
    return p;
}

int main(int argc, char **argv) {
    ap_ns_module_t *base = NULL;
    ap_ns_module_t *stress = NULL;
    const ap_module_ns_config_t base_cfg = {16000u, BASE_FLOOR};
    const ap_module_ns_config_t stress_cfg = {16000u, STRESS_FLOOR};
    FILE *input_file;
    int16_t raw[FRAME];
    float input[FRAME];
    float out_base[FRAME];
    float out_stress[FRAME];
    uint32_t frame_index = 0u;
    const uint32_t nfft = next_pow2(FRAME * 2u);
    const uint32_t bins = nfft / 2u + 1u;
    const float scale_offset_db =
        10.0f * log10f(2.0f * (float)bins * (float)nfft / (float)FRAME);

    if (argc != 2) {
        fprintf(stderr, "usage: %s <raw-s16-mono-pcm>\n", argv[0]);
        return 2;
    }
    if (nfft != 512u || bins != 257u) return 3;
    if (ap_module_ns_init(ns_base_mem, sizeof(ns_base_mem), &base_cfg, &base) != AP_OK)
        return 4;
    if (ap_module_ns_init(ns_stress_mem, sizeof(ns_stress_mem), &stress_cfg, &stress) != AP_OK)
        return 5;

    input_file = fopen(argv[1], "rb");
    if (!input_file) {
        perror("fopen");
        return 6;
    }

    for (;;) {
        const size_t got = fread(raw, sizeof(raw[0]), FRAME, input_file);
        uint32_t i;
        ap_module_ns_result_t rb;
        ap_module_ns_result_t rs;
        if (got == 0u) break;
        if (got != FRAME) {
            fprintf(stderr, "partial input frame: %zu\n", got);
            fclose(input_file);
            return 7;
        }
        for (i = 0u; i < FRAME; ++i)
            input[i] = (float)raw[i] / 32768.0f;

        if (ap_module_ns_process(base, AP_QUALITY_FULL, input, NULL,
                                 out_base, FRAME, 0, 0, 0, &rb) != AP_OK) {
            fclose(input_file);
            return 8;
        }
        if (ap_module_ns_process(stress, AP_QUALITY_FULL, input, NULL,
                                 out_stress, FRAME, 0, 0, 0, &rs) != AP_OK) {
            fclose(input_file);
            return 9;
        }

        printf(
            "{\"frame\":%u,\"input_rms_dbfs\":%.9g,"
            "\"legacy_base_noise_dbfs\":%.9g,\"legacy_stress_noise_dbfs\":%.9g,"
            "\"calibrated_base_noise_dbfs\":%.9g,\"calibrated_stress_noise_dbfs\":%.9g,"
            "\"base_speech_probability\":%.9g,\"stress_speech_probability\":%.9g,"
            "\"scale_offset_db\":%.9g,\"nfft\":%u,\"bins\":%u}\n",
            frame_index,
            (double)frame_rms_dbfs(input),
            (double)rb.noise_rms_dbfs,
            (double)rs.noise_rms_dbfs,
            (double)(rb.noise_rms_dbfs + scale_offset_db),
            (double)(rs.noise_rms_dbfs + scale_offset_db),
            (double)rb.speech_probability,
            (double)rs.speech_probability,
            (double)scale_offset_db,
            nfft,
            bins);
        frame_index++;
    }

    fclose(input_file);
    if (frame_index == 0u) return 10;
    return 0;
}
