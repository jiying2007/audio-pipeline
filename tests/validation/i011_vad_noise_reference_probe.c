#include "audio_pipeline/audio_modules.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !AP_HAVE_MODULE_NS
#error "I011 probe requires standalone NS module"
#endif

#define FRAME 160u
#define SCENARIOS 4u
#define FRAMES_PER_SCENARIO 320u
#define TOTAL_FRAMES (SCENARIOS * FRAMES_PER_SCENARIO)
#define FLOOR_EPS_DB 1.0e-6f

_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char ns_base_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char ns_low_mem[AP_MODULE_STATE_MAX_BYTES];

static float speech_proxy[TOTAL_FRAMES];
static float noise_proxy[TOTAL_FRAMES];
static uint32_t rng_state;

static float prng_signed(void) {
    rng_state = rng_state * 1664525u + 1013904223u;
    return ((float)((rng_state >> 8u) & 0x00ffffffu) / 8388607.5f) - 1.0f;
}

static float frame_rms_dbfs(const float *x) {
    double e = 1.0e-18;
    uint32_t i;
    for (i = 0u; i < FRAME; ++i) e += (double)x[i] * (double)x[i];
    e /= (double)FRAME;
    return (float)(10.0 * log10(e + 1.0e-18));
}

static int speech_active(uint32_t scenario, uint32_t frame) {
    if (scenario < 2u) return 0;
    if (scenario == 2u) return ((frame / 55u) % 2u) == 0u;
    return ((frame / 70u) % 3u) != 2u;
}

static void make_frame(uint32_t scenario, uint32_t frame, float *out) {
    uint32_t i;
    const int active = speech_active(scenario, frame);
    float noise_amp;
    float speech_amp;
    const double pi = 3.14159265358979323846;

    if (scenario == 0u) {
        noise_amp = 0.018f;
        speech_amp = 0.0f;
    } else if (scenario == 1u) {
        static const float levels[] = {0.006f, 0.012f, 0.024f, 0.048f, 0.080f, 0.032f};
        noise_amp = levels[(frame / 32u) % (sizeof(levels) / sizeof(levels[0]))];
        speech_amp = 0.0f;
    } else if (scenario == 2u) {
        noise_amp = 0.020f;
        speech_amp = active ? 0.075f : 0.0f;
    } else {
        noise_amp = 0.016f;
        speech_amp = active ? 0.032f : 0.0f;
    }

    for (i = 0u; i < FRAME; ++i) {
        const uint64_t n = (uint64_t)frame * FRAME + i;
        const float white = prng_signed();
        const float colored =
            0.55f * (float)sin(2.0 * pi * 83.0 * (double)n / 16000.0) +
            0.30f * (float)sin(2.0 * pi * 137.0 * (double)n / 16000.0);
        float speech = 0.0f;
        if (active) {
            speech =
                0.70f * (float)sin(2.0 * pi * 223.0 * (double)n / 16000.0) +
                0.30f * (float)sin(2.0 * pi * 487.0 * (double)n / 16000.0);
        }
        out[i] = noise_amp * (0.72f * white + 0.28f * colored) +
                 speech_amp * speech;
    }
}

static int cmp_float(const void *a, const void *b) {
    const float x = *(const float *)a;
    const float y = *(const float *)b;
    return (x > y) - (x < y);
}

static float quantile_sorted(const float *x, uint32_t n, float q) {
    uint32_t index;
    if (n == 0u) return 0.0f;
    if (q <= 0.0f) return x[0];
    if (q >= 1.0f) return x[n - 1u];
    index = (uint32_t)((float)(n - 1u) * q + 0.5f);
    if (index >= n) index = n - 1u;
    return x[index];
}

static double auc_score(const float *speech, uint32_t speech_n,
                        const float *noise, uint32_t noise_n) {
    double wins = 0.0;
    uint32_t i, j;
    if (speech_n == 0u || noise_n == 0u) return 0.0;
    for (i = 0u; i < speech_n; ++i) {
        for (j = 0u; j < noise_n; ++j) {
            const float d = speech[i] - noise[j];
            if (d > FLOOR_EPS_DB) wins += 1.0;
            else if (fabsf(d) <= FLOOR_EPS_DB) wins += 0.5;
        }
    }
    return wins / ((double)speech_n * (double)noise_n);
}

int main(int argc, char **argv) {
    ap_ns_module_t *ns_base = NULL;
    ap_ns_module_t *ns_low = NULL;
    const ap_module_ns_config_t base_cfg = {16000u, 0.12f};
    const ap_module_ns_config_t low_cfg = {16000u, 0.05f};
    uint32_t seed;
    uint32_t scenario, frame;
    uint32_t total_frames = 0u;
    uint32_t speech_n = 0u, noise_n = 0u;
    float max_noise_ref_delta_db = 0.0f;
    float max_proxy_delta_db = 0.0f;
    double speech_sum = 0.0, noise_sum = 0.0;
    float input[FRAME], out_base[FRAME], out_low[FRAME];

    if (argc != 2) {
        fprintf(stderr, "usage: %s <seed>\n", argv[0]);
        return 2;
    }
    seed = (uint32_t)strtoul(argv[1], NULL, 10);
    if (seed == 0u) return 2;
    rng_state = seed ^ 0x6a09e667u;

    if (ap_module_ns_init(ns_base_mem, sizeof(ns_base_mem), &base_cfg, &ns_base) != AP_OK)
        return 3;
    if (ap_module_ns_init(ns_low_mem, sizeof(ns_low_mem), &low_cfg, &ns_low) != AP_OK)
        return 4;

    for (scenario = 0u; scenario < SCENARIOS; ++scenario) {
        ap_module_ns_reset(ns_base);
        ap_module_ns_reset(ns_low);

        for (frame = 0u; frame < FRAMES_PER_SCENARIO; ++frame) {
            ap_module_ns_result_t rb, rl;
            const int labeled_speech = speech_active(scenario, frame);
            float pre_rms_dbfs;
            float proxy_base;
            float proxy_low;
            float d;

            make_frame(scenario, frame, input);
            if (ap_module_ns_process(ns_base, AP_QUALITY_FULL, input, NULL,
                                     out_base, FRAME, 0, 0, 0, &rb) != AP_OK)
                return 5;
            if (ap_module_ns_process(ns_low, AP_QUALITY_FULL, input, NULL,
                                     out_low, FRAME, 0, 0, 0, &rl) != AP_OK)
                return 6;

            if (!isfinite(rb.noise_rms_dbfs) || !isfinite(rl.noise_rms_dbfs))
                return 7;
            pre_rms_dbfs = frame_rms_dbfs(input);
            if (!isfinite(pre_rms_dbfs)) return 8;

            proxy_base = pre_rms_dbfs - rb.noise_rms_dbfs;
            proxy_low = pre_rms_dbfs - rl.noise_rms_dbfs;
            if (!isfinite(proxy_base) || !isfinite(proxy_low)) return 9;

            d = fabsf(rb.noise_rms_dbfs - rl.noise_rms_dbfs);
            if (d > max_noise_ref_delta_db) max_noise_ref_delta_db = d;
            d = fabsf(proxy_base - proxy_low);
            if (d > max_proxy_delta_db) max_proxy_delta_db = d;

            if (labeled_speech) {
                if (speech_n >= TOTAL_FRAMES) return 10;
                speech_proxy[speech_n++] = proxy_base;
                speech_sum += proxy_base;
            } else {
                if (noise_n >= TOTAL_FRAMES) return 11;
                noise_proxy[noise_n++] = proxy_base;
                noise_sum += proxy_base;
            }
            total_frames++;
        }
    }

    if (speech_n == 0u || noise_n == 0u || total_frames != TOTAL_FRAMES)
        return 12;

    qsort(speech_proxy, speech_n, sizeof(float), cmp_float);
    qsort(noise_proxy, noise_n, sizeof(float), cmp_float);

    {
        const double speech_mean = speech_sum / (double)speech_n;
        const double noise_mean = noise_sum / (double)noise_n;
        const float speech_p10 = quantile_sorted(speech_proxy, speech_n, 0.10f);
        const float noise_p90 = quantile_sorted(noise_proxy, noise_n, 0.90f);
        const double auc = auc_score(speech_proxy, speech_n, noise_proxy, noise_n);
        printf(
            "{\"schema_version\":1,\"seed\":%u,\"total_frames\":%u,"
            "\"speech_frames\":%u,\"noise_frames\":%u,"
            "\"max_noise_reference_delta_db\":%.9g,"
            "\"max_proxy_delta_db\":%.9g,"
            "\"speech_proxy_mean_db\":%.9g,"
            "\"noise_proxy_mean_db\":%.9g,"
            "\"mean_gap_db\":%.9g,"
            "\"speech_proxy_p10_db\":%.9g,"
            "\"noise_proxy_p90_db\":%.9g,"
            "\"tail_gap_db\":%.9g,"
            "\"proxy_auc\":%.12g}\n",
            seed, total_frames, speech_n, noise_n,
            (double)max_noise_ref_delta_db,
            (double)max_proxy_delta_db,
            speech_mean, noise_mean, speech_mean - noise_mean,
            (double)speech_p10, (double)noise_p90,
            (double)speech_p10 - (double)noise_p90,
            auc);
    }
    return 0;
}
