/* S003 candidate-zero echo-path standalone RES state probe.
 * Test-only: reads internal state without changing shipping/public API.
 */
#include "audio_pipeline/audio_pipeline.h"
#include "core/ap_pipeline_internal.h"

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !AP_BUILD_STAGE_RES
#error "S003 RES state probe requires RES"
#endif
#if !AP_BUILD_STAGE_AEC
#error "S003 RES state probe requires AEC"
#endif
#if !AP_BUILD_STAGE_SYNC
#error "S003 RES state probe requires SYNC"
#endif

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s [--sample-rate HZ] [--mic-channels 1|2] "
            "--state-jsonl FILE --echo-path-change-frame N "
            "<mic.pcm> <render.pcm> <out.pcm>\n",
            argv0);
}

static int parse_u32(const char *text, uint32_t *value) {
    char *end = NULL;
    unsigned long parsed;
    errno = 0;
    parsed = strtoul(text, &end, 10);
    if (errno || !end || *end != '\0' || parsed > 0xfffffffful) return 0;
    *value = (uint32_t)parsed;
    return 1;
}

static float rms(const float *values, uint32_t count) {
    double energy = 1.0e-30;
    uint32_t i;
    for (i = 0u; i < count; ++i) {
        const double x = values[i];
        energy += x * x;
    }
    return (float)sqrt(energy / (double)(count ? count : 1u));
}

static int emit_state(FILE *stream,
                      const ap_pipeline_t *pipeline,
                      uint32_t frame_index,
                      uint32_t algorithmic_latency_ms,
                      int echo_path_change_event,
                      float gain_before,
                      uint32_t frame_samples) {
    const struct ap_pipeline *p = (const struct ap_pipeline *)pipeline;
    ap_metrics_t metrics;
    const float gain_after = p->res.gain;
    const float post_res_rms = rms(p->aec_out, frame_samples);
    const float pre_res_rms_recovered =
        gain_after > 1.0e-12f ? post_res_rms / gain_after : 0.0f;
    const float echo_estimate_rms = rms(p->echo_estimate, frame_samples);

    ap_pipeline_get_metrics(pipeline, &metrics);

    return fprintf(
        stream,
        "{"
        "\"frame\":%u,"
        "\"algorithmic_latency_ms\":%u,"
        "\"echo_path_change_event\":%u,"
        "\"far_end_active\":%u,"
        "\"double_talk_active\":%u,"
        "\"aec_converged\":%u,"
        "\"erle_valid\":%u,"
        "\"erle_db\":%.9g,"
        "\"estimated_delay_ms\":%u,"
        "\"delay_error_samples\":%d,"
        "\"res_gain_before\":%.9g,"
        "\"res_gain_after\":%.9g,"
        "\"res_gain_delta\":%.9g,"
        "\"post_res_rms\":%.9g,"
        "\"pre_res_rms_recovered\":%.9g,"
        "\"echo_estimate_rms\":%.9g"
        "}\n",
        frame_index,
        algorithmic_latency_ms,
        echo_path_change_event ? 1u : 0u,
        (unsigned)metrics.far_end_active,
        (unsigned)metrics.double_talk_active,
        (unsigned)metrics.aec_converged,
        (unsigned)metrics.erle_valid,
        (double)metrics.erle_db,
        metrics.estimated_delay_ms,
        metrics.delay_error_samples,
        (double)gain_before,
        (double)gain_after,
        (double)(gain_after - gain_before),
        (double)post_res_rms,
        (double)pre_res_rms_recovered,
        (double)echo_estimate_rms) >= 0;
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    FILE *fm = NULL;
    FILE *fr = NULL;
    FILE *fo = NULL;
    FILE *fs = NULL;
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    uint32_t sample_rate = cfg.io_sample_rate_hz;
    uint32_t channels = cfg.mic_channels;
    uint32_t echo_path_change_frame = UINT32_MAX;
    const char *state_path = NULL;
    const char *mic_path;
    const char *render_path;
    const char *out_path;
    uint32_t frame_index = 0u;
    uint32_t algorithmic_latency_ms;
    uint32_t internal_frame;
    int arg = 1;
    size_t frame;

    while (arg < argc && argv[arg][0] == '-') {
        if (strcmp(argv[arg], "--sample-rate") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &sample_rate)) {
                usage(argv[0]); return 2;
            }
        } else if (strcmp(argv[arg], "--mic-channels") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &channels)) {
                usage(argv[0]); return 2;
            }
        } else if (strcmp(argv[arg], "--state-jsonl") == 0) {
            if (++arg >= argc) { usage(argv[0]); return 2; }
            state_path = argv[arg];
        } else if (strcmp(argv[arg], "--echo-path-change-frame") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &echo_path_change_frame)) {
                usage(argv[0]); return 2;
            }
        } else {
            usage(argv[0]); return 2;
        }
        arg++;
    }

    if (!state_path || echo_path_change_frame == UINT32_MAX ||
        channels < 1u || channels > AP_MAX_MIC_CHANNELS ||
        sample_rate == 0u || sample_rate % 100u != 0u ||
        argc - arg != 3) {
        usage(argv[0]); return 2;
    }

    mic_path = argv[arg++];
    render_path = argv[arg++];
    out_path = argv[arg++];

    cfg.io_sample_rate_hz = sample_rate;
    cfg.mic_channels = channels;
    cfg.stages = AP_STAGE_HPF | AP_STAGE_SYNC | AP_STAGE_AEC | AP_STAGE_RES;
    if (channels == 2u) cfg.stages |= AP_STAGE_BF;
    if (ap_pipeline_validate_config(&cfg) != AP_OK) {
        fprintf(stderr, "invalid RES state probe configuration\n");
        return 2;
    }

    frame = ap_pipeline_io_frame_samples(&cfg);
    internal_frame = (uint32_t)ap_pipeline_internal_frame_samples(&cfg);
    if (!frame || frame > AP_MAX_IO_FRAME_SAMPLES ||
        !internal_frame || internal_frame > AP_INTERNAL_FRAME_MAX)
        return 2;

    fm = fopen(mic_path, "rb");
    fr = fopen(render_path, "rb");
    fo = fopen(out_path, "wb");
    fs = fopen(state_path, "wb");
    if (!fm || !fr || !fo || !fs) {
        perror("fopen");
        if (fm) fclose(fm);
        if (fr) fclose(fr);
        if (fo) fclose(fo);
        if (fs) fclose(fs);
        return 2;
    }

    if (ap_pipeline_state_size() > sizeof(state) ||
        ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) != AP_OK)
        return 3;
    algorithmic_latency_ms = ap_pipeline_algorithmic_latency_ms(pipeline);

    while (fread(mic, sizeof(int16_t) * channels, frame, fm) == frame) {
        struct ap_pipeline *p = (struct ap_pipeline *)pipeline;
        const float gain_before = p->res.gain;
        const int path_change = frame_index == echo_path_change_frame;
        size_t got;

        if (path_change && ap_pipeline_notify_echo_path_change(pipeline) != AP_OK)
            return 4;

        got = fread(render, sizeof(int16_t), frame, fr);
        if (got < frame)
            memset(render + got, 0, (frame - got) * sizeof(int16_t));
        if (ap_pipeline_push_render(pipeline, render, frame) != AP_OK)
            return 4;
        if (ap_pipeline_process_capture(pipeline, mic, frame, out) != AP_OK)
            return 4;
        if (fwrite(out, sizeof(int16_t), frame, fo) != frame)
            return 5;
        if (!emit_state(fs, pipeline, frame_index, algorithmic_latency_ms,
                        path_change, gain_before, internal_frame))
            return 5;
        frame_index++;
    }

    fclose(fm);
    fclose(fr);
    fclose(fo);
    fclose(fs);
    return frame_index ? 0 : 6;
}
