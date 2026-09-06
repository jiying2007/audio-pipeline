#include "frontend/ap_frontend.h"

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define AP_I007_RC_MAX_FRAME 480u

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s [--sample-rate HZ] [--spacing-mm MM] "
            "[--frontend bf-only|hpf-bf] <stereo-s16le.pcm> <trace.jsonl>\n",
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

static float roughness(const float *x, uint32_t n) {
    float energy = 1.0e-12f;
    float diff_energy = 1.0e-12f;
    uint32_t i;
    if (n == 0u) return 1.0f;
    energy += x[0] * x[0];
    for (i = 1u; i < n; ++i) {
        const float d = x[i] - x[i - 1u];
        energy += x[i] * x[i];
        diff_energy += d * d;
    }
    return diff_energy / energy;
}

static float best_smoothed_coherence(const ap_beamformer_state_t *s) {
    float best = -1.0e30f;
    int lag;
    for (lag = -s->max_lag; lag <= s->max_lag; ++lag) {
        const uint32_t index = (uint32_t)(lag + (int)AP_BF_HISTORY);
        if (s->lag_score[index] > best) best = s->lag_score[index];
    }
    return best;
}

int main(int argc, char **argv) {
    ap_beamformer_state_t state;
    ap_hpf_state_t hpf;
    int16_t input[AP_I007_RC_MAX_FRAME * 2u];
    float mic0[AP_I007_RC_MAX_FRAME];
    float mic1[AP_I007_RC_MAX_FRAME];
    float beam[AP_I007_RC_MAX_FRAME];
    uint32_t sample_rate = 16000u;
    float spacing_mm = 50.0f;
    uint32_t frame_samples;
    uint32_t frame_index = 0u;
    int use_hpf = 1;
    const char *frontend = "hpf-bf";
    int arg = 1;
    const char *input_path;
    const char *trace_path;
    FILE *fi;
    FILE *ft;

    while (arg < argc && argv[arg][0] == '-') {
        if (strcmp(argv[arg], "--sample-rate") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &sample_rate)) {
                usage(argv[0]); return 2;
            }
        } else if (strcmp(argv[arg], "--spacing-mm") == 0) {
            if (++arg >= argc || !parse_float(argv[arg], &spacing_mm)) {
                usage(argv[0]); return 2;
            }
        } else if (strcmp(argv[arg], "--frontend") == 0) {
            if (++arg >= argc) { usage(argv[0]); return 2; }
            frontend = argv[arg];
            if (strcmp(frontend, "bf-only") == 0) use_hpf = 0;
            else if (strcmp(frontend, "hpf-bf") == 0) use_hpf = 1;
            else { usage(argv[0]); return 2; }
        } else {
            usage(argv[0]); return 2;
        }
        arg++;
    }
    if (argc - arg != 2 || sample_rate == 0u || sample_rate % 100u != 0u || spacing_mm <= 0.0f) {
        usage(argv[0]); return 2;
    }
    frame_samples = sample_rate / 100u;
    if (frame_samples == 0u || frame_samples > AP_I007_RC_MAX_FRAME) return 2;
    input_path = argv[arg++];
    trace_path = argv[arg++];
    fi = fopen(input_path, "rb");
    ft = fopen(trace_path, "wb");
    if (!fi || !ft) {
        perror("fopen");
        if (fi) fclose(fi);
        if (ft) fclose(ft);
        return 2;
    }

    ap_beamformer_init(&state, sample_rate, spacing_mm);
    ap_hpf_init(&hpf, sample_rate, 2u);
    while (fread(input, sizeof(int16_t) * 2u, frame_samples, fi) == frame_samples) {
        double energy0 = 1.0e-12;
        double energy1 = 1.0e-12;
        float r0;
        float r1;
        float ratio;
        float coherence;
        uint32_t strong;
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
        }
        energy0 /= (double)frame_samples;
        energy1 /= (double)frame_samples;
        r0 = roughness(mic0, frame_samples);
        r1 = roughness(mic1, frame_samples);
        strong = energy0 >= energy1 ? 0u : 1u;
        ratio = sqrtf((float)(energy0 < energy1 ? energy0 / energy1 : energy1 / energy0));

        ap_beamformer_process(&state, 1, mic0, mic1, beam, frame_samples);
        coherence = best_smoothed_coherence(&state);

        if (fprintf(ft,
                    "{\"frame\":%u,\"frontend\":\"%s\","
                    "\"energy0\":%.9g,\"energy1\":%.9g,\"energy_ratio\":%.9g,"
                    "\"energy_strong_channel\":%u,\"roughness0\":%.9g,\"roughness1\":%.9g,"
                    "\"best_smoothed_coherence\":%.9g,\"fallback_active\":%u,"
                    "\"fallback_hard_fault\":%u,\"fallback_strong_channel\":%u,"
                    "\"lag\":%d,\"score_updates\":%u}\n",
                    frame_index, frontend, energy0, energy1, (double)ratio, strong,
                    (double)r0, (double)r1, (double)coherence,
                    state.fallback_active, state.fallback_hard_fault,
                    state.fallback_strong_channel, state.lag, state.score_updates) < 0) {
            perror("fprintf"); fclose(fi); fclose(ft); return 5;
        }
        frame_index++;
    }
    if (ferror(fi)) { perror("fread"); fclose(fi); fclose(ft); return 5; }
    if (fclose(fi) != 0 || fclose(ft) != 0) return 5;
    return frame_index ? 0 : 2;
}
