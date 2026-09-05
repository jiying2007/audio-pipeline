#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define AP_PROBE_RATE_HZ 16000u
#define AP_PROBE_FRAME_SAMPLES 160u
#define AP_PROBE_NS_FLOOR 0.12f

static float s16_to_f32(int16_t value) {
    return (float)value * (1.0f / 32768.0f);
}

int main(int argc, char **argv) {
    FILE *input;
    FILE *output;
    int16_t pcm[AP_PROBE_FRAME_SAMPLES];
    float raw[AP_PROBE_FRAME_SAMPLES];
    float ns_out[AP_PROBE_FRAME_SAMPLES];
    ap_ns_state_t ns;
    ap_vad_state_t raw_vad;
    ap_vad_state_t ns_local_vad;
    ap_vad_state_t fused_vad;
    uint32_t frame_index = 0u;

    if (argc != 3) {
        fprintf(stderr, "usage: %s <mono-s16le-16k.pcm> <trace.jsonl>\n", argv[0]);
        return 2;
    }
    input = fopen(argv[1], "rb");
    output = fopen(argv[2], "wb");
    if (!input || !output) {
        perror("fopen");
        if (input) fclose(input);
        if (output) fclose(output);
        return 2;
    }

    ap_ns_init(&ns, AP_PROBE_FRAME_SAMPLES);
    ap_vad_init(&raw_vad);
    ap_vad_init(&ns_local_vad);
    ap_vad_init(&fused_vad);

    while (fread(pcm, sizeof(int16_t), AP_PROBE_FRAME_SAMPLES, input) == AP_PROBE_FRAME_SAMPLES) {
        ap_ns_result_t ns_result;
        ap_vad_result_t raw_result;
        ap_vad_result_t ns_local_result;
        ap_vad_result_t fused_result;
        uint32_t i;

        for (i = 0u; i < AP_PROBE_FRAME_SAMPLES; ++i)
            raw[i] = s16_to_f32(pcm[i]);

        ap_ns_process(&ns,
                      AP_ENHANCE_FULL,
                      AP_PROBE_NS_FLOOR,
                      raw,
                      NULL,
                      ns_out,
                      AP_PROBE_FRAME_SAMPLES,
                      0,
                      0,
                      0,
                      &ns_result);

        ap_vad_process(&raw_vad,
                       raw,
                       AP_PROBE_FRAME_SAMPLES,
                       0.0f,
                       0,
                       &raw_result);
        ap_vad_process(&ns_local_vad,
                       ns_out,
                       AP_PROBE_FRAME_SAMPLES,
                       0.0f,
                       0,
                       &ns_local_result);
        ap_vad_process(&fused_vad,
                       ns_out,
                       AP_PROBE_FRAME_SAMPLES,
                       ns_result.speech_probability,
                       1,
                       &fused_result);

        if (fprintf(output,
                    "{\"frame\":%u,"
                    "\"ns_speech_probability\":%.9g,"
                    "\"raw_probability\":%.9g,\"raw_active\":%u,\"raw_noise_rms\":%.9g,\"raw_hangover\":%u,"
                    "\"ns_local_probability\":%.9g,\"ns_local_active\":%u,\"ns_local_noise_rms\":%.9g,\"ns_local_hangover\":%u,"
                    "\"fused_probability\":%.9g,\"fused_active\":%u,\"fused_noise_rms\":%.9g,\"fused_hangover\":%u}\n",
                    frame_index,
                    (double)ns_result.speech_probability,
                    (double)raw_result.probability,
                    (unsigned)raw_result.active,
                    (double)raw_vad.noise_rms,
                    raw_vad.hangover,
                    (double)ns_local_result.probability,
                    (unsigned)ns_local_result.active,
                    (double)ns_local_vad.noise_rms,
                    ns_local_vad.hangover,
                    (double)fused_result.probability,
                    (unsigned)fused_result.active,
                    (double)fused_vad.noise_rms,
                    fused_vad.hangover) < 0) {
            fclose(input);
            fclose(output);
            return 3;
        }
        frame_index++;
    }

    if (ferror(input)) {
        perror("fread");
        fclose(input);
        fclose(output);
        return 3;
    }
    fclose(input);
    fclose(output);
    if (frame_index == 0u) return 4;
    return 0;
}
