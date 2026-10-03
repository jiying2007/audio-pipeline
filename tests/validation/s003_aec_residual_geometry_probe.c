/* S003 candidate-zero AEC residual-geometry probe.
 * Test-only: observes existing frame buffers after prefix-aec processing.
 * It never inspects AEC weights/taps and does not modify shipping/public API.
 */
#include "audio_pipeline/audio_pipeline.h"
#include "core/ap_pipeline_internal.h"

#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !AP_BUILD_STAGE_AEC
#error "S003 residual-geometry probe requires AEC"
#endif
#if !AP_BUILD_STAGE_SYNC
#error "S003 residual-geometry probe requires SYNC"
#endif

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

#define S003_NORM_EPS 1.0e-12

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s --sample-rate HZ --mic-channels 1|2 "
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

static int emit_geometry(FILE *stream,
                         const ap_pipeline_t *pipeline,
                         uint32_t frame_index,
                         int echo_path_change_event,
                         uint32_t frame_samples) {
    const struct ap_pipeline *p = (const struct ap_pipeline *)pipeline;
    ap_metrics_t metrics;
    double subtraction_input_energy = 0.0;
    double estimate_energy = 0.0;
    double cross = 0.0;
    double residual_energy = 0.0;
    double reconstructed;
    double identity_abs_error;
    double identity_rel_error;
    double q = 0.0;
    double rho = 0.0;
    double normalized_reconstructed = 0.0;
    double normalized_observed = 0.0;
    double normalized_abs_error = 0.0;
    double normalized_rel_error = 0.0;
    int normalized_valid = 0;
    uint32_t i;

    ap_pipeline_get_metrics(pipeline, &metrics);
    for (i = 0u; i < frame_samples; ++i) {
        const double e = p->echo_estimate[i];
        const double r = p->aec_out[i];
        /*
         * pipeline->mono aliases pipeline->processed and is overwritten with
         * aec_out before ap_pipeline_process_capture() returns. Reconstruct
         * the exact subtraction input from the two live AEC outputs instead:
         *     r = m - e  =>  m = r + e.
         */
        const double m = r + e;
        subtraction_input_energy += m * m;
        estimate_energy += e * e;
        cross += m * e;
        residual_energy += r * r;
    }
    subtraction_input_energy /= (double)frame_samples;
    estimate_energy /= (double)frame_samples;
    cross /= (double)frame_samples;
    residual_energy /= (double)frame_samples;

    reconstructed = subtraction_input_energy + estimate_energy - 2.0 * cross;
    identity_abs_error = fabs(reconstructed - residual_energy);
    identity_rel_error = identity_abs_error /
        fmax(subtraction_input_energy + estimate_energy + 2.0 * fabs(cross),
             S003_NORM_EPS);

    if (subtraction_input_energy > S003_NORM_EPS && estimate_energy > S003_NORM_EPS) {
        q = estimate_energy / subtraction_input_energy;
        rho = cross / sqrt(subtraction_input_energy * estimate_energy);
        normalized_observed = residual_energy / subtraction_input_energy;
        normalized_reconstructed =
            1.0 + q - 2.0 * rho * sqrt(q);
        normalized_abs_error =
            fabs(normalized_reconstructed - normalized_observed);
        normalized_rel_error = normalized_abs_error /
            fmax(1.0 + q + 2.0 * fabs(rho) * sqrt(q), S003_NORM_EPS);
        normalized_valid = 1;
    }

    return fprintf(
        stream,
        "{"
        "\"frame\":%u,"
        "\"echo_path_change_event\":%u,"
        "\"far_end_active\":%u,"
        "\"double_talk_active\":%u,"
        "\"aec_converged\":%u,"
        "\"erle_valid\":%u,"
        "\"erle_db\":%.17g,"
        "\"estimated_delay_ms\":%u,"
        "\"delay_error_samples\":%d,"
        "\"subtraction_input_energy\":%.17g,"
        "\"echo_estimate_energy\":%.17g,"
        "\"cross_energy\":%.17g,"
        "\"residual_energy\":%.17g,"
        "\"identity_reconstructed_residual_energy\":%.17g,"
        "\"identity_abs_error\":%.17g,"
        "\"identity_rel_error\":%.17g,"
        "\"normalized_valid\":%u,"
        "\"q_estimate_to_input_power_ratio\":%.17g,"
        "\"rho_input_estimate_similarity\":%.17g,"
        "\"normalized_residual_observed\":%.17g,"
        "\"normalized_residual_reconstructed\":%.17g,"
        "\"normalized_abs_error\":%.17g,"
        "\"normalized_rel_error\":%.17g"
        "}\n",
        frame_index,
        echo_path_change_event ? 1u : 0u,
        (unsigned)metrics.far_end_active,
        (unsigned)metrics.double_talk_active,
        (unsigned)metrics.aec_converged,
        (unsigned)metrics.erle_valid,
        (double)metrics.erle_db,
        metrics.estimated_delay_ms,
        metrics.delay_error_samples,
        subtraction_input_energy,
        estimate_energy,
        cross,
        residual_energy,
        reconstructed,
        identity_abs_error,
        identity_rel_error,
        normalized_valid ? 1u : 0u,
        q,
        rho,
        normalized_observed,
        normalized_reconstructed,
        normalized_abs_error,
        normalized_rel_error) >= 0;
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    FILE *fm = NULL, *fr = NULL, *fo = NULL, *fs = NULL;
    uint32_t sample_rate = cfg.io_sample_rate_hz;
    uint32_t channels = cfg.mic_channels;
    uint32_t echo_path_change_frame = UINT32_MAX;
    const char *state_path = NULL;
    const char *mic_path, *render_path, *out_path;
    uint32_t frame_index = 0u;
    uint32_t internal_frame;
    size_t frame;
    int arg = 1;

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
    {
        const ap_stage_mask_t front =
            AP_STAGE_HPF | (channels == 2u ? AP_STAGE_BF : 0u);
        cfg.stages = front | AP_STAGE_SYNC | AP_STAGE_AEC;
    }
    if (ap_pipeline_validate_config(&cfg) != AP_OK) return 2;
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

    while (fread(mic, sizeof(int16_t) * channels, frame, fm) == frame) {
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
        if (!emit_geometry(fs, pipeline, frame_index, path_change, internal_frame))
            return 5;
        frame_index++;
    }

    fclose(fm); fclose(fr); fclose(fo); fclose(fs);
    return frame_index ? 0 : 6;
}
