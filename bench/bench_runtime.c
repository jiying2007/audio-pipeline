#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define PI_F 3.14159265358979323846f
#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static uint64_t now_ns(void) {
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void sleep_until(uint64_t target_ns) {
    for (;;) {
        uint64_t n = now_ns();
        struct timespec ts;
        uint64_t left;
        if (n >= target_ns) return;
        left = target_ns - n;
        ts.tv_sec = (time_t)(left / 1000000000ull);
        ts.tv_nsec = (long)(left % 1000000000ull);
        (void)nanosleep(&ts, NULL);
    }
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
    AP_ALIGN16 static unsigned char runtime_mem[AP_RUNTIME_STATE_MAX_BYTES];
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_runtime_options_t ropts = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    int16_t mic[320], render[160], out[160];
    unsigned seconds = 5u, frames, f, i;
    uint32_t max_overruns = 0u;
    double min_full_ratio = 0.999;
    uint64_t full_frames = 0u, lite_frames = 0u, safe_frames = 0u;
    uint64_t received = 0u, start_ns;
    int rc = 1;

    if (argc > 1) seconds = (unsigned)strtoul(argv[1], NULL, 10);
    if (argc > 2) max_overruns = (uint32_t)strtoul(argv[2], NULL, 10);
    if (argc > 3) min_full_ratio = strtod(argv[3], NULL);
    if (argc > 4) rcfg.dsp_cpu = (int)strtol(argv[4], NULL, 10);
    if (!seconds) seconds = 1u;
    frames = seconds * 100u;
    rcfg.dsp_priority = 0;

    if (ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &cfg, &pipeline) != AP_OK ||
        ap_runtime_open(runtime_mem, sizeof(runtime_mem), pipeline, &rcfg, &ropts, &runtime) != AP_OK ||
        ap_runtime_start(runtime) != AP_OK) {
        fprintf(stderr, "runtime benchmark init failed\n");
        return 2;
    }

    start_ns = now_ns();
    for (f = 0u; f < frames; ++f) {
        ap_status_t s;
        const uint64_t target = start_ns + (uint64_t)f * 10000000ull;
        sleep_until(target);
        for (i = 0u; i < 160u; ++i) {
            const unsigned n = f * 160u + i;
            const float far = 0.16f * sinf(2.0f * PI_F * 731.0f * (float)n / 16000.0f);
            const float near = 0.07f * sinf(2.0f * PI_F * 223.0f * (float)n / 16000.0f);
            render[i] = (int16_t)(far * 32767.0f);
            mic[2u * i] = (int16_t)((near + 0.22f * far) * 32767.0f);
            mic[2u * i + 1u] = (int16_t)((near + 0.20f * far) * 32767.0f);
        }
        s = ap_runtime_submit_frame(runtime, mic, render, NULL);
        if (s != AP_OK) {
            fprintf(stderr, "submit failed at frame %u status=%d\n", f, (int)s);
            goto done;
        }
        for (;;) {
            ap_metrics_t pm;
            s = ap_runtime_receive(runtime, out, &pm);
            if (s != AP_OK) break;
            if (pm.quality == AP_QUALITY_FULL) full_frames++;
            else if (pm.quality == AP_QUALITY_LITE) lite_frames++;
            else safe_frames++;
            received++;
        }
        if (s != AP_EEMPTY) goto done;
    }

    while (received < frames) {
        ap_metrics_t pm;
        ap_status_t s = ap_runtime_receive(runtime, out, &pm);
        if (s == AP_OK) {
            if (pm.quality == AP_QUALITY_FULL) full_frames++;
            else if (pm.quality == AP_QUALITY_LITE) lite_frames++;
            else safe_frames++;
            received++;
        } else if (s == AP_EEMPTY) {
            struct timespec nap = {0, 100000};
            (void)nanosleep(&nap, NULL);
        } else {
            goto done;
        }
    }

    {
        ap_runtime_metrics_t rm;
        const double full_ratio = received ? (double)full_frames / (double)received : 0.0;
        memset(&rm, 0, sizeof(rm));
        rm.struct_size = sizeof(rm);
        rm.api_version = AP_RUNTIME_API_VERSION;
        if (ap_runtime_read_metrics(runtime, &rm) != AP_OK) goto done;
        printf("frames=%u received=%llu full=%llu lite=%llu safe=%llu full_ratio=%.6f input_full=%llu output_drop=%llu dsp_overruns=%llu last_dsp_us=%u max_dsp_us=%u quality=%d\n",
               frames, (unsigned long long)received,
               (unsigned long long)full_frames,
               (unsigned long long)lite_frames,
               (unsigned long long)safe_frames,
               full_ratio,
               (unsigned long long)rm.input_full_events,
               (unsigned long long)rm.output_drop_events,
               (unsigned long long)rm.dsp_overruns,
               rm.last_dsp_us, rm.max_dsp_us, (int)rm.quality);
        if (rm.input_full_events || rm.output_drop_events) {
            fprintf(stderr, "runtime queue gate failed\n");
            goto done;
        }
        if (rm.dsp_overruns > max_overruns) {
            fprintf(stderr, "runtime overrun gate failed: %llu > %u\n",
                    (unsigned long long)rm.dsp_overruns, max_overruns);
            goto done;
        }
        if (full_ratio < min_full_ratio) {
            fprintf(stderr, "FULL residence gate failed: %.6f < %.6f\n", full_ratio, min_full_ratio);
            goto done;
        }
    }
    rc = 0;

done:
    ap_runtime_stop(runtime);
    return rc;
}
