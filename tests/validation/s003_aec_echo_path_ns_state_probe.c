/* S003 candidate-zero echo-path NS internal-state observation probe.
 * Test-only: no shipping/public API surface is modified.
 */
#include "audio_pipeline/audio_pipeline.h"
#include "core/ap_pipeline_internal.h"

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !AP_BUILD_STAGE_NS
#error "S003 NS state probe requires NS"
#endif
#if !AP_BUILD_STAGE_RES
#error "S003 NS state probe requires RES/frequency-RES state"
#endif
#if !AP_BUILD_STAGE_AEC
#error "S003 NS state probe requires AEC"
#endif
#if !AP_BUILD_STAGE_SYNC
#error "S003 NS state probe requires SYNC"
#endif

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static float noise_before[AP_NS_BINS_MAX];
static float res_gain_before[AP_NS_BINS_MAX];
static float overlap_before[AP_INTERNAL_FRAME_MAX];

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

static void snapshot_before(const ap_pipeline_t *pipeline,
                            uint32_t bins,
                            uint32_t frame_samples) {
    const struct ap_pipeline *p = (const struct ap_pipeline *)pipeline;
    memcpy(noise_before,
           p->ns.noise_tracker.estimate,
           bins * sizeof(noise_before[0]));
    memcpy(res_gain_before,
           p->ns.residual_gain_bins,
           bins * sizeof(res_gain_before[0]));
    memcpy(overlap_before,
           p->ns.overlap,
           frame_samples * sizeof(overlap_before[0]));
}

static int emit_state(FILE *stream,
                      const ap_pipeline_t *pipeline,
                      uint32_t frame_index,
                      uint32_t algorithmic_latency_ms,
                      int echo_path_change_event,
                      uint32_t tracker_frame_before,
                      uint32_t bins,
                      uint32_t frame_samples) {
    const struct ap_pipeline *p = (const struct ap_pipeline *)pipeline;
    ap_metrics_t metrics;
    double noise_before_sum = 1.0e-30;
    double noise_after_sum = 1.0e-30;
    double noise_delta_sum = 0.0;
    double noise_abs_delta_sum = 0.0;
    double res_before_sum = 0.0;
    double res_after_sum = 0.0;
    double res_delta_sum = 0.0;
    double res_abs_delta_sum = 0.0;
    float res_min_after = 1.0f;
    float res_max_after = 0.0f;
    uint32_t k;

    ap_pipeline_get_metrics(pipeline, &metrics);

    for (k = 0u; k < bins; ++k) {
        const float nb = noise_before[k];
        const float na = p->ns.noise_tracker.estimate[k];
        const float rb = res_gain_before[k];
        const float ra = p->ns.residual_gain_bins[k];
        noise_before_sum += (double)nb;
        noise_after_sum += (double)na;
        noise_delta_sum += (double)na - (double)nb;
        noise_abs_delta_sum += fabs((double)na - (double)nb);
        res_before_sum += (double)rb;
        res_after_sum += (double)ra;
        res_delta_sum += (double)ra - (double)rb;
        res_abs_delta_sum += fabs((double)ra - (double)rb);
        if (ra < res_min_after) res_min_after = ra;
        if (ra > res_max_after) res_max_after = ra;
    }

    if (fprintf(
            stream,
            "{"
            "\"frame\":%u,"
            "\"algorithmic_latency_ms\":%u,"
            "\"echo_path_change_event\":%u,"
            "\"noise_tracker_frame_before\":%u,"
            "\"noise_tracker_frame_after\":%u,"
            "\"noise_tracker_frame_mod8_after\":%u,"
            "\"far_end_active\":%u,"
            "\"double_talk_active\":%u,"
            "\"aec_converged\":%u,"
            "\"erle_valid\":%u,"
            "\"erle_db\":%.9g,"
            "\"estimated_delay_ms\":%u,"
            "\"delay_error_samples\":%d,"
            "\"frequency_res_active\":%u,"
            "\"residual_echo_gain\":%.9g,"
            "\"noise_rms_dbfs\":%.9g,"
            "\"speech_probability\":%.9g,"
            "\"noise_estimate_mean_before\":%.9g,"
            "\"noise_estimate_mean_after\":%.9g,"
            "\"noise_estimate_signed_delta_mean\":%.9g,"
            "\"noise_estimate_abs_delta_mean\":%.9g,"
            "\"noise_estimate_abs_update_fraction_of_previous_sum\":%.9g,"
            "\"residual_gain_mean_before\":%.9g,"
            "\"residual_gain_mean_after\":%.9g,"
            "\"residual_gain_min_after\":%.9g,"
            "\"residual_gain_max_after\":%.9g,"
            "\"residual_gain_signed_delta_mean\":%.9g,"
            "\"residual_gain_abs_delta_mean\":%.9g,"
            "\"overlap_rms_before\":%.9g,"
            "\"overlap_rms_after\":%.9g,"
            "\"previous_rms_after\":%.9g"
            "}\n",
            frame_index,
            algorithmic_latency_ms,
            echo_path_change_event ? 1u : 0u,
            tracker_frame_before,
            p->ns.noise_tracker.frame,
            p->ns.noise_tracker.frame & 7u,
            (unsigned)metrics.far_end_active,
            (unsigned)metrics.double_talk_active,
            (unsigned)metrics.aec_converged,
            (unsigned)metrics.erle_valid,
            (double)metrics.erle_db,
            metrics.estimated_delay_ms,
            metrics.delay_error_samples,
            (unsigned)metrics.frequency_res_active,
            (double)metrics.residual_echo_gain,
            (double)p->ns.noise_rms_dbfs,
            (double)p->ns.speech_probability,
            noise_before_sum / (double)bins,
            noise_after_sum / (double)bins,
            noise_delta_sum / (double)bins,
            noise_abs_delta_sum / (double)bins,
            noise_abs_delta_sum / noise_before_sum,
            res_before_sum / (double)bins,
            res_after_sum / (double)bins,
            (double)res_min_after,
            (double)res_max_after,
            res_delta_sum / (double)bins,
            res_abs_delta_sum / (double)bins,
            (double)rms(overlap_before, frame_samples),
            (double)rms(p->ns.overlap, frame_samples),
            (double)rms(p->ns.previous, frame_samples)) < 0)
        return 0;
    return 1;
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
    cfg.stages = AP_STAGE_HPF | AP_STAGE_SYNC | AP_STAGE_AEC |
                 AP_STAGE_RES | AP_STAGE_NS;
    if (channels == 2u) cfg.stages |= AP_STAGE_BF;
    if (ap_pipeline_validate_config(&cfg) != AP_OK) {
        fprintf(stderr, "invalid NS state probe configuration\n");
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
        const uint32_t bins = p->ns.nfft / 2u + 1u;
        const uint32_t tracker_frame_before = p->ns.noise_tracker.frame;
        const int path_change = frame_index == echo_path_change_frame;
        size_t got;

        if (bins == 0u || bins > AP_NS_BINS_MAX) return 4;
        snapshot_before(pipeline, bins, internal_frame);

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
                        path_change, tracker_frame_before, bins, internal_frame))
            return 5;
        frame_index++;
    }

    fclose(fm);
    fclose(fr);
    fclose(fo);
    fclose(fs);
    return frame_index ? 0 : 6;
}
