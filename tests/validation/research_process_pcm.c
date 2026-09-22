#include "audio_pipeline/audio_pipeline.h"
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static int parse_u32(const char *text, uint32_t *value) {
    char *end = NULL;
    unsigned long parsed;
    errno = 0;
    parsed = strtoul(text, &end, 10);
    if (errno || !end || *end != '\0' || parsed > 0xfffffffful) return 0;
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

static int env_u32(const char *name, uint32_t *value) {
    const char *text = getenv(name);
    return !text || !*text ? 1 : parse_u32(text, value);
}

static int env_float(const char *name, float *value) {
    const char *text = getenv(name);
    return !text || !*text ? 1 : parse_float(text, value);
}

static int valid_capture_profile(const char *profile) {
    return strcmp(profile, "default") == 0 ||
           strcmp(profile, "ns-isolated") == 0 ||
           strcmp(profile, "vad-isolated") == 0 ||
           strcmp(profile, "agc-isolated") == 0 ||
           strcmp(profile, "bf-isolated") == 0;
}

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s [--sample-rate HZ] [--mic-channels 1|2] "
            "[--capture-only] [--capture-profile default|ns-isolated|vad-isolated|agc-isolated|bf-isolated] "
            "[--metrics-jsonl FILE] <mic.pcm> [render.pcm] <out.pcm>\n"
            "research-only environment overrides: AP_RESEARCH_MIC_SPACING_MM, "
            "AP_RESEARCH_AEC_FILTER_MS, AP_RESEARCH_MAX_DELAY_MS, "
            "AP_RESEARCH_INITIAL_DELAY_MS\n",
            argv0);
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    uint32_t sample_rate = cfg.io_sample_rate_hz;
    uint32_t channels = cfg.mic_channels;
    int capture_only = 0;
    const char *capture_profile = "default";
    const char *metrics_path = NULL;
    const char *mic_path;
    const char *render_path = NULL;
    const char *out_path;
    FILE *fm = NULL, *fr = NULL, *fo = NULL, *fmetrics = NULL;
    int16_t *mic = NULL, *render = NULL, *out = NULL;
    size_t frame;
    uint32_t frame_index = 0u;
    int arg = 1;

    while (arg < argc && argv[arg][0] == '-') {
        if (strcmp(argv[arg], "--sample-rate") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &sample_rate)) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[arg], "--mic-channels") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &channels)) { usage(argv[0]); return 2; }
        } else if (strcmp(argv[arg], "--capture-only") == 0) {
            capture_only = 1;
        } else if (strcmp(argv[arg], "--capture-profile") == 0) {
            if (++arg >= argc || !valid_capture_profile(argv[arg])) { usage(argv[0]); return 2; }
            capture_profile = argv[arg];
        } else if (strcmp(argv[arg], "--metrics-jsonl") == 0) {
            if (++arg >= argc) { usage(argv[0]); return 2; }
            metrics_path = argv[arg];
        } else {
            usage(argv[0]); return 2;
        }
        arg++;
    }

    if ((!capture_only && argc - arg != 3) || (capture_only && argc - arg != 2)) {
        usage(argv[0]); return 2;
    }
    mic_path = argv[arg++];
    if (!capture_only) render_path = argv[arg++];
    out_path = argv[arg++];

    cfg.io_sample_rate_hz = sample_rate;
    cfg.mic_channels = channels;
    if (!env_float("AP_RESEARCH_MIC_SPACING_MM", &cfg.mic_spacing_mm) ||
        !env_u32("AP_RESEARCH_AEC_FILTER_MS", &cfg.aec_filter_ms) ||
        !env_u32("AP_RESEARCH_MAX_DELAY_MS", &cfg.max_delay_ms) ||
        !env_u32("AP_RESEARCH_INITIAL_DELAY_MS", &cfg.initial_delay_ms)) {
        fprintf(stderr, "invalid research environment override\n");
        return 2;
    }
    if (channels == 1u) cfg.stages &= ~AP_STAGE_BF;
    if (capture_only) {
        cfg.stages &= ~(AP_STAGE_SYNC | AP_STAGE_AEC | AP_STAGE_RES);
        cfg.enable_delay_tracking = 0u;
        cfg.enable_clock_drift_compensation = 0u;
        if (strcmp(capture_profile, "ns-isolated") == 0)
            cfg.stages = AP_STAGE_NS | AP_STAGE_VAD;
        else if (strcmp(capture_profile, "vad-isolated") == 0)
            cfg.stages = AP_STAGE_VAD;
        else if (strcmp(capture_profile, "agc-isolated") == 0)
            cfg.stages = AP_STAGE_AGC;
        else if (strcmp(capture_profile, "bf-isolated") == 0)
            cfg.stages = AP_STAGE_BF;
    }
    if (ap_pipeline_validate_config(&cfg) != AP_OK) {
        fprintf(stderr, "invalid research processor configuration\n");
        return 2;
    }
    frame = ap_pipeline_io_frame_samples(&cfg);
    if (!frame) return 2;

    mic = (int16_t *)calloc(frame * channels, sizeof(*mic));
    render = (int16_t *)calloc(frame, sizeof(*render));
    out = (int16_t *)calloc(frame, sizeof(*out));
    if (!mic || !render || !out) return 3;

    fm = fopen(mic_path, "rb");
    if (!capture_only) fr = fopen(render_path, "rb");
    fo = fopen(out_path, "wb");
    if (metrics_path) fmetrics = fopen(metrics_path, "wb");
    if (!fm || (!capture_only && !fr) || !fo || (metrics_path && !fmetrics)) {
        perror("fopen"); return 3;
    }
    if (ap_pipeline_state_size() > sizeof(state) ||
        ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) != AP_OK) return 3;

    while (fread(mic, sizeof(int16_t) * channels, frame, fm) == frame) {
        ap_metrics_t metrics;
        if (!capture_only) {
            size_t got = fread(render, sizeof(int16_t), frame, fr);
            if (got < frame) memset(render + got, 0, (frame - got) * sizeof(*render));
            if (ap_pipeline_push_render(pipeline, render, frame) != AP_OK) return 4;
        }
        if (ap_pipeline_process_capture(pipeline, mic, frame, out) != AP_OK) return 4;
        if (fwrite(out, sizeof(int16_t), frame, fo) != frame) return 5;
        if (fmetrics) {
            ap_pipeline_get_metrics(pipeline, &metrics);
            if (fprintf(fmetrics,
                        "{\"frame\":%u,\"algorithmic_latency_ms\":%u,"
                        "\"vad_probability\":%.7g,\"vad_active\":%u,"
                        "\"erle_db\":%.7g,\"erle_valid\":%u,"
                        "\"estimated_delay_ms\":%u,\"active_aec_taps\":%u,"
                        "\"active_aec_partitions\":%u}\n",
                        frame_index, ap_pipeline_algorithmic_latency_ms(pipeline),
                        (double)metrics.vad_probability, (unsigned)metrics.vad_active,
                        (double)metrics.erle_db, (unsigned)metrics.erle_valid,
                        metrics.estimated_delay_ms, metrics.active_aec_taps,
                        metrics.active_aec_partitions) < 0) return 5;
        }
        frame_index++;
    }

    fclose(fm);
    if (fr) fclose(fr);
    fclose(fo);
    if (fmetrics) fclose(fmetrics);
    free(mic); free(render); free(out);
    return 0;
}
