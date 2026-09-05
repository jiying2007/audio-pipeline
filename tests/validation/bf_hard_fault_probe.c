#include "frontend/ap_frontend.h"

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define AP_BF_PROBE_MAX_FRAME 480u

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s [--sample-rate HZ] [--spacing-mm MM] "
            "<stereo-s16le.pcm> <mono-out.pcm> <trace.jsonl>\n",
            argv0);
}

static int parse_u32(const char *text, uint32_t *value) {
    char *end = NULL;
    unsigned long parsed;
    errno = 0;
    parsed = strtoul(text, &end, 10);
    if (errno || !end || *end != '\0' || parsed > UINT32_MAX) return 0;
    *value = (uint32_t)parsed;
    return 1;
}

static int parse_float(const char *text, float *value) {
    char *end = NULL;
    float parsed;
    errno = 0;
    parsed = strtof(text, &end);
    if (errno || !end || *end != '\0' || !isfinite(parsed)) return 0;
    *value = parsed;
    return 1;
}

static int16_t float_to_s16(float value) {
    long rounded;
    if (!isfinite(value)) return 0;
    if (value > 32767.0f) value = 32767.0f;
    if (value < -32768.0f) value = -32768.0f;
    rounded = lroundf(value);
    if (rounded > 32767L) rounded = 32767L;
    if (rounded < -32768L) rounded = -32768L;
    return (int16_t)rounded;
}

int main(int argc, char **argv) {
    ap_beamformer_state_t state;
    int16_t input[AP_BF_PROBE_MAX_FRAME * 2u];
    int16_t output[AP_BF_PROBE_MAX_FRAME];
    float mic0[AP_BF_PROBE_MAX_FRAME];
    float mic1[AP_BF_PROBE_MAX_FRAME];
    float beam[AP_BF_PROBE_MAX_FRAME];
    uint32_t sample_rate = 16000u;
    float spacing_mm = 50.0f;
    uint32_t frame_samples;
    uint32_t frame_index = 0u;
    int arg = 1;
    const char *input_path;
    const char *output_path;
    const char *trace_path;
    FILE *fi;
    FILE *fo;
    FILE *ft;

    while (arg < argc && argv[arg][0] == '-') {
        if (strcmp(argv[arg], "--sample-rate") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &sample_rate)) {
                usage(argv[0]);
                return 2;
            }
        } else if (strcmp(argv[arg], "--spacing-mm") == 0) {
            if (++arg >= argc || !parse_float(argv[arg], &spacing_mm)) {
                usage(argv[0]);
                return 2;
            }
        } else {
            usage(argv[0]);
            return 2;
        }
        arg++;
    }

    if (argc - arg != 3 || sample_rate == 0u || sample_rate % 100u != 0u ||
        spacing_mm <= 0.0f) {
        usage(argv[0]);
        return 2;
    }
    frame_samples = sample_rate / 100u;
    if (frame_samples == 0u || frame_samples > AP_BF_PROBE_MAX_FRAME) {
        fprintf(stderr, "unsupported frame size: %u\n", frame_samples);
        return 2;
    }

    input_path = argv[arg++];
    output_path = argv[arg++];
    trace_path = argv[arg++];
    fi = fopen(input_path, "rb");
    fo = fopen(output_path, "wb");
    ft = fopen(trace_path, "wb");
    if (!fi || !fo || !ft) {
        perror("fopen");
        if (fi) fclose(fi);
        if (fo) fclose(fo);
        if (ft) fclose(ft);
        return 2;
    }

    ap_beamformer_init(&state, sample_rate, spacing_mm);
    while (fread(input, sizeof(int16_t) * 2u, frame_samples, fi) == frame_samples) {
        uint32_t i;
        for (i = 0u; i < frame_samples; ++i) {
            mic0[i] = (float)input[2u * i];
            mic1[i] = (float)input[2u * i + 1u];
        }

        ap_beamformer_process(&state, 1, mic0, mic1, beam, frame_samples);
        for (i = 0u; i < frame_samples; ++i) output[i] = float_to_s16(beam[i]);
        if (fwrite(output, sizeof(int16_t), frame_samples, fo) != frame_samples) {
            perror("fwrite");
            fclose(fi);
            fclose(fo);
            fclose(ft);
            return 5;
        }
        if (fprintf(ft,
                    "{\"frame\":%u,\"fallback_active\":%u,"
                    "\"fallback_strong_channel\":%u,"
                    "\"fallback_recovery_count\":%u,"
                    "\"fallback_gain\":%.9g,\"fallback_lag\":%d,"
                    "\"lag\":%d,\"score_updates\":%u}\n",
                    frame_index,
                    state.fallback_active,
                    state.fallback_strong_channel,
                    state.fallback_recovery_count,
                    (double)state.fallback_gain,
                    state.fallback_lag,
                    state.lag,
                    state.score_updates) < 0) {
            perror("fprintf");
            fclose(fi);
            fclose(fo);
            fclose(ft);
            return 5;
        }
        frame_index++;
    }

    if (ferror(fi)) {
        perror("fread");
        fclose(fi);
        fclose(fo);
        fclose(ft);
        return 5;
    }
    fclose(fi);
    if (fclose(fo) != 0 || fclose(ft) != 0) {
        perror("fclose");
        return 5;
    }
    if (frame_index == 0u) {
        fprintf(stderr, "empty input\n");
        return 2;
    }
    return 0;
}
