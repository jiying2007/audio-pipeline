#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define PI_F 3.14159265358979323846f
#define HIST_BIN_US 10u
#define HIST_MAX_US 20000u
#define HIST_BINS (HIST_MAX_US / HIST_BIN_US + 2u)
#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static uint32_t histogram[HIST_BINS];

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void hist_add(uint32_t us) {
    uint32_t bin = us / HIST_BIN_US;
    if (bin >= HIST_BINS) bin = HIST_BINS - 1u;
    histogram[bin]++;
}

static uint32_t hist_percentile(uint32_t frames, uint32_t num, uint32_t den) {
    uint64_t need = ((uint64_t)frames * num + den - 1u) / den;
    uint64_t seen = 0u;
    uint32_t i;
    for (i = 0u; i < HIST_BINS; ++i) {
        seen += histogram[i];
        if (seen >= need) {
            if (i == HIST_BINS - 1u) return HIST_MAX_US + HIST_BIN_US;
            return i * HIST_BIN_US + HIST_BIN_US - 1u;
        }
    }
    return 0u;
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    int16_t mic[320], render[160], out[160];
    unsigned seconds = 30u, frames, f, i;
    double rtf_limit = 0.0;
    uint32_t p99_limit_us = 0u;
    uint64_t total_t0, total_t1;
    uint32_t max_us = 0u;
    uint32_t deadline_misses = 0u;
    ap_metrics_t m;
    if (argc > 1) seconds = (unsigned)strtoul(argv[1], NULL, 10);
    if (argc > 2) rtf_limit = strtod(argv[2], NULL);
    if (argc > 3) p99_limit_us = (uint32_t)strtoul(argv[3], NULL, 10);
    if (!seconds) seconds = 1u;
    if (ap_pipeline_init(state, sizeof(state), &c, &p) != AP_OK) return 2;
    frames = seconds * 100u;
    memset(histogram, 0, sizeof(histogram));
    total_t0 = now_ns();
    for (f = 0; f < frames; ++f) {
        uint64_t t0, t1;
        uint32_t frame_us;
        for (i = 0; i < 160u; ++i) {
            const unsigned s = f * 160u + i;
            const float far = 0.18f * sinf(2.0f * PI_F * 733.0f * (float)s / 16000.0f);
            const float near = 0.08f * sinf(2.0f * PI_F * 211.0f * (float)s / 16000.0f);
            const float noise = (float)((int)(s * 1103515245u + 12345u) & 0xffff) / 65535.0f - 0.5f;
            render[i] = (int16_t)(far * 32767.0f);
            mic[2u * i] = (int16_t)((near + 0.20f * far + 0.02f * noise) * 32767.0f);
            mic[2u * i + 1u] = (int16_t)((near + 0.18f * far + 0.02f * noise) * 32767.0f);
        }
        t0 = now_ns();
        (void)ap_pipeline_push_render(p, render, 160u);
        if (ap_pipeline_process_capture(p, mic, 160u, out) != AP_OK) return 3;
        t1 = now_ns();
        frame_us = (uint32_t)((t1 - t0 + 999ull) / 1000ull);
        hist_add(frame_us);
        if (frame_us > max_us) max_us = frame_us;
        if (frame_us > 10000u) deadline_misses++;
    }
    total_t1 = now_ns();
    ap_pipeline_get_metrics(p, &m);
    {
        const double elapsed_s = (double)(total_t1 - total_t0) / 1.0e9;
        const double audio_s = (double)seconds;
        const double rtf = elapsed_s / audio_s;
        const double us_frame_avg = (double)(total_t1 - total_t0) / 1000.0 / frames;
        const uint32_t p50 = hist_percentile(frames, 50u, 100u);
        const uint32_t p95 = hist_percentile(frames, 95u, 100u);
        const uint32_t p99 = hist_percentile(frames, 99u, 100u);
        printf("frames=%u audio_s=%u elapsed_s=%.6f avg_us=%.2f p50_us=%u p95_us=%u p99_us=%u max_us=%u deadline_misses=%u rtf=%.5f state_bytes=%zu aec_backend=%d aec_block=%u aec_partitions=%u aec_taps=%u erle_db=%.2f delay_ms=%u delay_error=%d drift_ppm=%.2f slips=%llu delay_jumps=%llu aec_resets=%llu res_gain=%.3f freq_res=%u quality=%d\n",
               frames, seconds, elapsed_s, us_frame_avg, p50, p95, p99, max_us,
               deadline_misses, rtf, ap_pipeline_state_size(), (int)m.aec_backend,
               m.aec_block_samples, m.active_aec_partitions, m.active_aec_taps,
               m.erle_db, m.estimated_delay_ms, (int)m.delay_error_samples,
               m.estimated_drift_ppm,
               (unsigned long long)m.reference_sample_slips,
               (unsigned long long)m.delay_jumps,
               (unsigned long long)m.aec_resets,
               m.residual_echo_gain, (unsigned)m.frequency_res_active,
               (int)m.quality);
        if (rtf_limit > 0.0 && rtf > rtf_limit) {
            fprintf(stderr, "RTF gate failed: %.5f > %.5f\n", rtf, rtf_limit);
            return 4;
        }
        if (p99_limit_us > 0u && p99 > p99_limit_us) {
            fprintf(stderr, "p99 gate failed: %u us > %u us\n", p99, p99_limit_us);
            return 5;
        }
        if (deadline_misses != 0u && p99_limit_us > 0u) {
            fprintf(stderr, "10 ms deadline misses: %u\n", deadline_misses);
            return 6;
        }
    }
    return 0;
}
