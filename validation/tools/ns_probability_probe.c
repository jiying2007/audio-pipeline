#include "audio_pipeline/audio_modules.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

#define RATE 16000u
#define FRAME (RATE / 100u)

static void usage(const char *argv0) {
    fprintf(stderr, "usage: %s <mono-s16le.pcm> <trace.jsonl>\n", argv0);
}

int main(int argc, char **argv) {
#if AP_HAVE_MODULE_NS
    AP_ALIGN16 static unsigned char state[AP_MODULE_STATE_MAX_BYTES];
    int16_t pcm[FRAME];
    float input[FRAME];
    float output[FRAME];
    ap_ns_module_t *ns = NULL;
    ap_module_ns_config_t config = {RATE, 0.12f};
    FILE *in = NULL;
    FILE *trace = NULL;
    uint32_t frame_index = 0u;
    size_t i;

    if (argc != 3) {
        usage(argv[0]);
        return 2;
    }
    in = fopen(argv[1], "rb");
    trace = fopen(argv[2], "wb");
    if (!in || !trace) {
        perror("fopen");
        if (in) fclose(in);
        if (trace) fclose(trace);
        return 2;
    }
    if (ap_module_ns_state_size() > sizeof(state) ||
        ap_module_ns_init(state, sizeof(state), &config, &ns) != AP_OK) {
        fprintf(stderr, "failed to initialize NS module\n");
        fclose(in);
        fclose(trace);
        return 3;
    }

    while (fread(pcm, sizeof(int16_t), FRAME, in) == FRAME) {
        ap_module_ns_result_t result;
        for (i = 0u; i < FRAME; ++i) input[i] = (float)pcm[i] / 32768.0f;
        if (ap_module_ns_process(ns, AP_QUALITY_FULL, input, NULL, output, FRAME,
                                 0, 0, 0, &result) != AP_OK) {
            fclose(in);
            fclose(trace);
            return 4;
        }
        if (fprintf(trace,
                    "{\"frame\":%u,\"ns_speech_probability\":%.7g,\"ns_noise_rms_dbfs\":%.7g}\n",
                    frame_index,
                    (double)result.speech_probability,
                    (double)result.noise_rms_dbfs) < 0) {
            fclose(in);
            fclose(trace);
            return 5;
        }
        frame_index++;
    }
    fclose(in);
    fclose(trace);
    return 0;
#else
    (void)argc;
    (void)argv;
    fputs("NS module is not compiled\n", stderr);
    return 3;
#endif
}
