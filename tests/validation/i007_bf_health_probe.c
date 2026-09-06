#include "frontend/ap_frontend.h"

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define AP_I007_MAX_FRAME 480u

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s [--sample-rate HZ] [--spacing-mm MM] "
            "[--frontend bf-only|hpf-bf] "
            "<stereo-s16le.pcm> <mono-out.pcm> <ch0-out.pcm> <ch1-out.pcm> <trace.jsonl>\n",
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

static void close_files(FILE *fi, FILE *fo, FILE *f0, FILE *f1, FILE *ft) {
    if (fi) fclose(fi);
    if (fo) fclose(fo);
    if (f0) fclose(f0);
    if (f1) fclose(f1);
    if (ft) fclose(ft);
}

int main(int argc, char **argv) {
    ap_beamformer_state_t state;
    ap_hpf_state_t hpf;
    int16_t input[AP_I007_MAX_FRAME * 2u];
    int16_t output[AP_I007_MAX_FRAME];
    int16_t ch0_output[AP_I007_MAX_FRAME];
    int16_t ch1_output[AP_I007_MAX_FRAME];
    float mic0[AP_I007_MAX_FRAME];
    float mic1[AP_I007_MAX_FRAME];
    float beam[AP_I007_MAX_FRAME];
    uint32_t sample_rate = 16000u;
    float spacing_mm = 50.0f;
    uint32_t frame_samples;
    uint32_t frame_index = 0u;
    int use_hpf = 1;
    const char *frontend = "hpf-bf";
    int arg = 1;
    const char *input_path;
    const char *output_path;
    const char *ch0_path;
    const char *ch1_path;
    const char *trace_path;
    FILE *fi;
    FILE *fo;
    FILE *f0;
    FILE *f1;
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
        } else if (strcmp(argv[arg], "--frontend") == 0) {
            if (++arg >= argc) {
                usage(argv[0]);
                return 2;
            }
            frontend = argv[arg];
            if (strcmp(frontend, "bf-only") == 0) {
                use_hpf = 0;
            } else if (strcmp(frontend, "hpf-bf") == 0) {
                use_hpf = 1;
            } else {
                usage(argv[0]);
                return 2;
            }
        } else {
            usage(argv[0]);
            return 2;
        }
        arg++;
    }
    if (argc - arg != 5 || sample_rate == 0u || sample_rate % 100u != 0u || spacing_mm <= 0.0f) {
        usage(argv[0]);
        return 2;
    }
    frame_samples = sample_rate / 100u;
    if (frame_samples == 0u || frame_samples > AP_I007_MAX_FRAME) return 2;

    input_path = argv[arg++];
    output_path = argv[arg++];
    ch0_path = argv[arg++];
    ch1_path = argv[arg++];
    trace_path = argv[arg++];
    fi = fopen(input_path, "rb");
    fo = fopen(output_path, "wb");
    f0 = fopen(ch0_path, "wb");
    f1 = fopen(ch1_path, "wb");
    ft = fopen(trace_path, "wb");
    if (!fi || !fo || !f0 || !f1 || !ft) {
        perror("fopen");
        close_files(fi, fo, f0, f1, ft);
        return 2;
    }

    ap_beamformer_init(&state, sample_rate, spacing_mm);
    ap_hpf_init(&hpf, sample_rate, 2u);
    while (fread(input, sizeof(int16_t) * 2u, frame_samples, fi) == frame_samples) {
        double energy0 = 1.0e-12;
        double energy1 = 1.0e-12;
        uint32_t i;
        for (i = 0u; i < frame_samples; ++i) {
            mic0[i] = (float)input[2u * i];
            mic1[i] = (float)input[2u * i + 1u];
        }
        if (use_hpf) {
            ap_hpf_process(&hpf, mic0, frame_samples, 0u);
            ap_hpf_process(&hpf, mic1, frame_samples, 1u);
        }
        for (i = 0u; i < frame_samples; ++i) {
            energy0 += (double)mic0[i] * (double)mic0[i];
            energy1 += (double)mic1[i] * (double)mic1[i];
            ch0_output[i] = float_to_s16(mic0[i]);
            ch1_output[i] = float_to_s16(mic1[i]);
        }
        energy0 /= (double)frame_samples;
        energy1 /= (double)frame_samples;
        ap_beamformer_process(&state, 1, mic0, mic1, beam, frame_samples);
        for (i = 0u; i < frame_samples; ++i) output[i] = float_to_s16(beam[i]);
        if (fwrite(output, sizeof(int16_t), frame_samples, fo) != frame_samples ||
            fwrite(ch0_output, sizeof(int16_t), frame_samples, f0) != frame_samples ||
            fwrite(ch1_output, sizeof(int16_t), frame_samples, f1) != frame_samples) {
            perror("fwrite");
            close_files(fi, fo, f0, f1, ft);
            return 5;
        }
        if (fprintf(ft,
                    "{\"frame\":%u,\"frontend\":\"%s\","
                    "\"pre_bf_energy0\":%.9g,\"pre_bf_energy1\":%.9g,"
                    "\"fallback_active\":%u,\"fallback_hard_fault\":%u,"
                    "\"fallback_strong_channel\":%u,\"fallback_recovery_count\":%u,"
                    "\"fallback_gain\":%.9g,\"fallback_lag\":%d,"
                    "\"lag\":%d,\"score_updates\":%u}\n",
                    frame_index, frontend, energy0, energy1,
                    state.fallback_active, state.fallback_hard_fault,
                    state.fallback_strong_channel, state.fallback_recovery_count,
                    (double)state.fallback_gain, state.fallback_lag, state.lag,
                    state.score_updates) < 0) {
            perror("fprintf");
            close_files(fi, fo, f0, f1, ft);
            return 5;
        }
        frame_index++;
    }
    if (ferror(fi)) {
        perror("fread");
        close_files(fi, fo, f0, f1, ft);
        return 5;
    }
    if (fclose(fi) != 0 || fclose(fo) != 0 || fclose(f0) != 0 ||
        fclose(f1) != 0 || fclose(ft) != 0) return 5;
    return frame_index ? 0 : 2;
}
