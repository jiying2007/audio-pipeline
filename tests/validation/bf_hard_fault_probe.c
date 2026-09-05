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
            "[--frontend bf-only|hpf-bf] "
            "[--oracle-channel 0|1 --oracle-out FILE] "
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

static float frame_roughness(const float *x, uint32_t n) {
    float energy = 1.0e-12f;
    float diff_energy = 1.0e-12f;
    uint32_t i;
    if (n == 0u) return 1.0f;
    energy += x[0] * x[0];
    for (i = 1u; i < n; ++i) {
        const float delta = x[i] - x[i - 1u];
        energy += x[i] * x[i];
        diff_energy += delta * delta;
    }
    return diff_energy / energy;
}

int main(int argc, char **argv) {
    ap_beamformer_state_t state;
    ap_hpf_state_t hpf;
    int16_t input[AP_BF_PROBE_MAX_FRAME * 2u];
    int16_t output[AP_BF_PROBE_MAX_FRAME];
    int16_t oracle_output[AP_BF_PROBE_MAX_FRAME];
    float mic0[AP_BF_PROBE_MAX_FRAME];
    float mic1[AP_BF_PROBE_MAX_FRAME];
    float beam[AP_BF_PROBE_MAX_FRAME];
    uint32_t sample_rate = 16000u;
    float spacing_mm = 50.0f;
    uint32_t frame_samples;
    uint32_t frame_index = 0u;
    uint32_t oracle_channel = 0u;
    int oracle_channel_set = 0;
    int use_hpf = 1;
    const char *frontend = "hpf-bf";
    const char *oracle_path = NULL;
    int arg = 1;
    const char *input_path;
    const char *output_path;
    const char *trace_path;
    FILE *fi;
    FILE *fo;
    FILE *ft;
    FILE *foracle = NULL;

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
        } else if (strcmp(argv[arg], "--oracle-channel") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &oracle_channel) || oracle_channel > 1u) {
                usage(argv[0]);
                return 2;
            }
            oracle_channel_set = 1;
        } else if (strcmp(argv[arg], "--oracle-out") == 0) {
            if (++arg >= argc) {
                usage(argv[0]);
                return 2;
            }
            oracle_path = argv[arg];
        } else {
            usage(argv[0]);
            return 2;
        }
        arg++;
    }

    if (argc - arg != 3 || sample_rate == 0u || sample_rate % 100u != 0u ||
        spacing_mm <= 0.0f || oracle_channel_set != (oracle_path != NULL)) {
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
    if (oracle_path) foracle = fopen(oracle_path, "wb");
    if (!fi || !fo || !ft || (oracle_path && !foracle)) {
        perror("fopen");
        if (fi) fclose(fi);
        if (fo) fclose(fo);
        if (ft) fclose(ft);
        if (foracle) fclose(foracle);
        return 2;
    }

    ap_beamformer_init(&state, sample_rate, spacing_mm);
    ap_hpf_init(&hpf, sample_rate, 2u);
    while (fread(input, sizeof(int16_t) * 2u, frame_samples, fi) == frame_samples) {
        double energy0 = 1.0e-12;
        double energy1 = 1.0e-12;
        double amplitude_ratio;
        float roughness0;
        float roughness1;
        uint32_t i;
        for (i = 0u; i < frame_samples; ++i) {
            mic0[i] = (float)input[2u * i];
            mic1[i] = (float)input[2u * i + 1u];
        }
        if (use_hpf) {
            ap_hpf_process(&hpf, mic0, frame_samples, 0u);
            ap_hpf_process(&hpf, mic1, frame_samples, 1u);
        }
        roughness0 = frame_roughness(mic0, frame_samples);
        roughness1 = frame_roughness(mic1, frame_samples);
        for (i = 0u; i < frame_samples; ++i) {
            energy0 += (double)mic0[i] * (double)mic0[i];
            energy1 += (double)mic1[i] * (double)mic1[i];
            if (foracle) {
                const float oracle = oracle_channel == 0u ? mic0[i] : mic1[i];
                oracle_output[i] = float_to_s16(oracle);
            }
        }
        energy0 /= (double)frame_samples;
        energy1 /= (double)frame_samples;
        amplitude_ratio = sqrt(fmin(energy0, energy1) / fmax(fmax(energy0, energy1), 1.0e-24));
        if (foracle && fwrite(oracle_output, sizeof(int16_t), frame_samples, foracle) != frame_samples) {
            perror("fwrite oracle");
            fclose(fi);
            fclose(fo);
            fclose(ft);
            fclose(foracle);
            return 5;
        }

        ap_beamformer_process(&state, 1, mic0, mic1, beam, frame_samples);
        for (i = 0u; i < frame_samples; ++i) output[i] = float_to_s16(beam[i]);
        if (fwrite(output, sizeof(int16_t), frame_samples, fo) != frame_samples) {
            perror("fwrite");
            fclose(fi);
            fclose(fo);
            fclose(ft);
            if (foracle) fclose(foracle);
            return 5;
        }
        if (fprintf(ft,
                    "{\"frame\":%u,\"frontend\":\"%s\","
                    "\"pre_bf_energy0\":%.9g,\"pre_bf_energy1\":%.9g,"
                    "\"pre_bf_amplitude_ratio\":%.9g,"
                    "\"pre_bf_roughness0\":%.9g,\"pre_bf_roughness1\":%.9g,"
                    "\"fallback_active\":%u,\"fallback_hard_fault\":%u,"
                    "\"fallback_strong_channel\":%u,"
                    "\"fallback_recovery_count\":%u,"
                    "\"fallback_gain\":%.9g,\"fallback_lag\":%d,"
                    "\"lag\":%d,\"score_updates\":%u}\n",
                    frame_index,
                    frontend,
                    energy0,
                    energy1,
                    amplitude_ratio,
                    (double)roughness0,
                    (double)roughness1,
                    state.fallback_active,
                    state.fallback_hard_fault,
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
            if (foracle) fclose(foracle);
            return 5;
        }
        frame_index++;
    }

    if (ferror(fi)) {
        perror("fread");
        fclose(fi);
        fclose(fo);
        fclose(ft);
        if (foracle) fclose(foracle);
        return 5;
    }
    fclose(fi);
    if (fclose(fo) != 0 || fclose(ft) != 0 || (foracle && fclose(foracle) != 0)) {
        perror("fclose");
        return 5;
    }
    if (frame_index == 0u) {
        fprintf(stderr, "empty input\n");
        return 2;
    }
    return 0;
}
