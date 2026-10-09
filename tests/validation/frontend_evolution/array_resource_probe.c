/*
 * FE08 component-only resource probe; NOT a DSP algorithm or acoustic evaluator.
 * Do not translate hosted/QEMU timings into SSC305 silicon CPU/p99 claims.
 */
#define _POSIX_C_SOURCE 200809L
#include "array_native.h"
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(__FAST_MATH__)
#error "Research resource probes require strict finite checks"
#endif

#define RESOURCE_FRAMES 2000u
#define RESOURCE_SAMPLES 160u
#define RESOURCE_STATE_LIMIT (16u * 1024u)
#define RESOURCE_PROFILE_COUNT 5u
#define RESOURCE_FNV_OFFSET UINT64_C(14695981039346656037)
#define RESOURCE_FNV_PRIME UINT64_C(1099511628211)

typedef struct {
    const char *name;
    uint32_t microphones;
    fe_array_interpolation interpolation;
} profile;
static const profile PROFILES[RESOURCE_PROFILE_COUNT] = {
    {"C1_LINEAR", 1u, FE_ARRAY_LINEAR},
    {"C2_LINEAR", 2u, FE_ARRAY_LINEAR},
    {"C2_FIR33", 2u, FE_ARRAY_FIR33_HANN},
    {"C4_FIR33", 4u, FE_ARRAY_FIR33_HANN},
    {"C4_SPATIAL33", 4u, FE_ARRAY_SPATIAL33}
};

static int compare_ns(const void *a, const void *b) {
    const uint64_t first = *(const uint64_t *)a;
    const uint64_t second = *(const uint64_t *)b;
    return (first > second) - (first < second);
}

static uint64_t fnv_update(uint64_t hash, const void *buffer, size_t n) {
    const unsigned char *data = (const unsigned char *)buffer;
    size_t i;
    for (i = 0u; i < n; ++i) {
        hash ^= data[i];
        hash *= RESOURCE_FNV_PRIME;
    }
    return hash;
}

static int timestamp_ns(uint64_t *out) {
    struct timespec ts;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts) != 0 || ts.tv_sec < 0 ||
        ts.tv_nsec < 0 || ts.tv_nsec >= 1000000000L) return 0;
    *out = (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
    return 1;
}

static void source_config(fe_array_config *cfg, const profile *p) {
    uint32_t i;
    memset(cfg, 0, sizeof(*cfg));
    cfg->sample_rate_hz = 16000u;
    cfg->mic_count = p->microphones;
    cfg->active_mask = (1u << p->microphones) - 1u;
    cfg->interpolation = p->interpolation;
    cfg->direction[1] = 1.0;
    for (i = 0u; i < p->microphones; ++i) {
        cfg->microphones[i].position_m[0] = 0.035 * (double)i;
        cfg->microphones[i].gain = 1.0;
        cfg->microphones[i].input_channel = i;
    }
}

static int run_one(const profile *p, int functional_only, int first_row) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char state[RESOURCE_STATE_LIMIT];
    float input[RESOURCE_SAMPLES * FE_ARRAY_MAX_MICS];
    float output[RESOURCE_SAMPLES];
    float spatial[FE_ARRAY_MAX_MICS * 33u] = {0.0f};
    uint64_t samples_ns[RESOURCE_FRAMES];
    uint64_t elapsed = 0u, checksum = RESOURCE_FNV_OFFSET, output_hash = RESOURCE_FNV_OFFSET;
    size_t need = fe_array_state_bytes_for_mode(p->microphones, p->interpolation);
    uint32_t frame, mic, n;
    double sum_squares = 0.0, peak = 0.0;
    fe_array_config cfg;
    fe_array *array = NULL;

    if (need == 0u || need > sizeof(state)) return 2;
    source_config(&cfg, p);
    for (mic = 0u; mic < p->microphones; ++mic)
        spatial[mic * 33u + 16u] = 1.0f / (float)p->microphones;

    if (p->interpolation == FE_ARRAY_SPATIAL33) {
        if (fe_array_init_spatial33(state, need, &cfg, spatial,
                                    p->microphones * 33u, &array) != FE_ARRAY_OK) return 3;
    } else if (fe_array_init(state, need, &cfg, &array) != FE_ARRAY_OK) return 3;

    for (frame = 0u; frame < RESOURCE_FRAMES; ++frame) {
        uint64_t begin = 0u, end = 0u;
        for (n = 0u; n < RESOURCE_SAMPLES; ++n)
            for (mic = 0u; mic < p->microphones; ++mic) {
                const uint32_t tick = frame * RESOURCE_SAMPLES + n;
                const int32_t value = (int32_t)((tick * 31u + mic * 17u) % 511u) - 255;
                input[(size_t)n * p->microphones + mic] = (float)value / 512.0f;
            }
        checksum = fnv_update(checksum, input, (size_t)RESOURCE_SAMPLES * p->microphones * sizeof(float));
        if (!functional_only && !timestamp_ns(&begin)) return 4;
        if (fe_array_process(array, input, (size_t)RESOURCE_SAMPLES * p->microphones,
                             output, RESOURCE_SAMPLES) != FE_ARRAY_OK) return 5;
        if (!functional_only) {
            if (!timestamp_ns(&end) || end < begin) return 6;
            samples_ns[frame] = end - begin;
            elapsed += samples_ns[frame];
        }
        output_hash = fnv_update(output_hash, output, sizeof(output));
        for (n = 0u; n < RESOURCE_SAMPLES; ++n) {
            const double v = (double)output[n], absolute = fabs(v);
            if (!isfinite(v) || absolute > 2.0) return 7;
            sum_squares += v*v;
            if (absolute > peak) peak = absolute;
        }
    }
    if (fe_array_get_info(array, &(fe_array_info){0}) != FE_ARRAY_OK ||
        !isfinite(sum_squares) || !(sum_squares > 0.0) || !(peak > 0.0)) return 8;
    printf("%s{\"name\":\"%s\",\"mic_count\":%u,\"mode\":%u,"
           "\"state_bytes\":%zu,\"frames\":%u,"
           "\"input_fnv64\":\"%016" PRIx64 "\","
           "\"output_fnv64\":\"%016" PRIx64 "\","
           "\"output_energy\":%.12g,\"peak_abs\":%.9g,",
           first_row ? "" : ",", p->name, p->microphones, (unsigned)p->interpolation,
           need, RESOURCE_FRAMES, checksum, output_hash, sum_squares, peak);
    if (functional_only) {
        printf("\"timing\":null}");
    } else {
        double total_audio_seconds = (double)RESOURCE_FRAMES * 0.010;
        const uint32_t p50 = (RESOURCE_FRAMES - 1u) / 2u;
        const uint32_t p95 = ((RESOURCE_FRAMES * 95u + 99u) / 100u) - 1u;
        const uint32_t p99 = ((RESOURCE_FRAMES * 99u + 99u) / 100u) - 1u;
        qsort(samples_ns, RESOURCE_FRAMES, sizeof(samples_ns[0]), compare_ns);
        if (!elapsed) return 9;
        printf("\"timing\":{\"clock\":\"CLOCK_THREAD_CPUTIME_ID\","
               "\"cpu_ms_per_audio_second\":%.9g,"
               "\"frame_p50_ns\":%" PRIu64 ",\"frame_p95_ns\":%" PRIu64 ","
               "\"frame_p99_ns\":%" PRIu64 ",\"frame_max_ns\":%" PRIu64 "}}",
               ((double)elapsed / 1e6) / total_audio_seconds,
               samples_ns[p50], samples_ns[p95], samples_ns[p99],
               samples_ns[RESOURCE_FRAMES - 1u]);
    }
    return 0;
}

int main(int argc, char **argv) {
    int functional_only = 0;
    uint32_t i;
    if (argc == 2 && strcmp(argv[1], "--functional") == 0) functional_only = 1;
    else if (argc != 1) return 2;
    printf("{\"schema_version\":1,\"scope\":\"FE08_ARRAY_COMPONENT_ONLY\","
           "\"shipping_authority\":false,\"profiles\":[");
    for (i = 0u; i < RESOURCE_PROFILE_COUNT; ++i)
        if (run_one(&PROFILES[i], functional_only, i == 0u) != 0) return 10;
    printf("],\"profile_count\":%u,\"timing_is_hosted_only\":%s}\n",
           RESOURCE_PROFILE_COUNT, functional_only ? "false" : "true");
    return 0;
}
