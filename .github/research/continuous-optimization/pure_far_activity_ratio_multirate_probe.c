#include "audio_pipeline/audio_pipeline.h"
#include "core/ap_pipeline_internal.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_RESEARCH_ALIGN16 __declspec(align(16))
#else
#define AP_RESEARCH_ALIGN16 _Alignas(16)
#endif

static float recover_smoothed_input(float previous, float current) {
    float alpha;
    if (previous <= 0.0f) return current;
    alpha = current > previous ? 0.35f : 0.08f;
    return previous + (current - previous) / alpha;
}

static double relative_error(double a, double b) {
    double denom = fmax(fmax(fabs(a), fabs(b)), 1.0e-20);
    return fabs(a - b) / denom;
}

static int fail(const char *message) {
    fprintf(stderr, "%s\n", message);
    return 2;
}

static int supported_rate(unsigned long rate) {
    return rate == 8000ul || rate == 16000ul || rate == 24000ul ||
           rate == 32000ul || rate == 48000ul;
}

int main(int argc, char **argv) {
#if !AP_BUILD_ACTIVITY || !AP_BUILD_STAGE_SYNC || !AP_BUILD_STAGE_AEC
    (void)argc;
    (void)argv;
    return fail("research probe requires ACTIVITY+SYNC+AEC in the unchanged baseline build");
#else
    AP_RESEARCH_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    FILE *fm = NULL;
    FILE *fr = NULL;
    FILE *fo = NULL;
    size_t frame;
    uint32_t frame_index = 0u;
    float previous_smoothed_mic = 0.0f;
    float previous_smoothed_reference = 0.0f;
    char *rate_end = NULL;
    unsigned long rate;

    if (argc != 5) {
        fprintf(stderr, "usage: %s <sample-rate-hz> <mic.pcm> <render.pcm> <trace.jsonl>\n", argv[0]);
        return 2;
    }

    rate = strtoul(argv[1], &rate_end, 10);
    if (!rate_end || *rate_end != '\0' || !supported_rate(rate))
        return fail("unsupported research probe sample rate");

    cfg.io_sample_rate_hz = (uint32_t)rate;
    cfg.mic_channels = 1u;
    cfg.stages &= ~AP_STAGE_BF;
    if (ap_pipeline_validate_config(&cfg) != AP_OK)
        return fail("unchanged baseline config rejected");
    frame = ap_pipeline_io_frame_samples(&cfg);
    if (frame == 0u || frame > AP_MAX_IO_FRAME_SAMPLES)
        return fail("unexpected frame geometry");
    if (ap_pipeline_state_size() > sizeof(state) ||
        ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) != AP_OK)
        return fail("pipeline init failed");

    fm = fopen(argv[2], "rb");
    fr = fopen(argv[3], "rb");
    fo = fopen(argv[4], "wb");
    if (!fm || !fr || !fo) {
        perror("fopen");
        if (fm) fclose(fm);
        if (fr) fclose(fr);
        if (fo) fclose(fo);
        return 2;
    }

    while (fread(mic, sizeof(int16_t), frame, fm) == frame) {
        ap_metrics_t metrics;
        ap_activity_state_t *activity;
        float current_smoothed_mic;
        float current_smoothed_reference;
        float recovered_mic_energy;
        float recovered_reference_energy;
        float direct_reference_energy = 1.0e-12f;
        float metric_mic_energy;
        float smoothed_ratio;
        float instant_ratio;
        float dt_ratio;
        int dt_on_evidence;
        int dt_hold_evidence;
        int expected_public_dtd;
        uint32_t i;
        size_t got = fread(render, sizeof(int16_t), frame, fr);

        if (got < frame)
            memset(render + got, 0, (frame - got) * sizeof(int16_t));
        if (ap_pipeline_push_render(pipeline, render, frame) != AP_OK)
            return fail("push render failed");
        if (ap_pipeline_process_capture(pipeline, mic, frame, out) != AP_OK)
            return fail("process capture failed");
        ap_pipeline_get_metrics(pipeline, &metrics);

        activity = &pipeline->activity;
        current_smoothed_mic = activity->smoothed_mic_energy;
        current_smoothed_reference = activity->smoothed_reference_energy;
        recovered_mic_energy = recover_smoothed_input(previous_smoothed_mic,
                                                       current_smoothed_mic);
        recovered_reference_energy = recover_smoothed_input(previous_smoothed_reference,
                                                             current_smoothed_reference);
        for (i = 0u; i < pipeline->internal_frame; ++i)
            direct_reference_energy += pipeline->reference[i] * pipeline->reference[i];
        direct_reference_energy /= pipeline->internal_frame;
        metric_mic_energy = powf(10.0f, metrics.input_rms_dbfs / 10.0f) - 1.0e-18f;
        if (metric_mic_energy < 0.0f) metric_mic_energy = 0.0f;

        smoothed_ratio = current_smoothed_mic /
                         (current_smoothed_reference + 1.0e-12f);
        instant_ratio = recovered_mic_energy /
                        (recovered_reference_energy + 1.0e-12f);
        dt_ratio = activity->double_talk_ratio;
        dt_on_evidence = metrics.far_end_active &&
                         smoothed_ratio > dt_ratio &&
                         instant_ratio > 0.90f * dt_ratio;
        dt_hold_evidence = metrics.far_end_active &&
                           instant_ratio > 0.72f * dt_ratio;
        expected_public_dtd = metrics.far_end_active &&
                              activity->double_talk_hangover > 0u;
        if ((int)metrics.double_talk_active != expected_public_dtd)
            return fail("public DTD does not match unchanged internal hangover state");

        if (fprintf(fo,
                    "{\"frame\":%u,"
                    "\"far_end_active\":%u,\"double_talk_active\":%u,"
                    "\"aec_converged\":%u,\"estimated_delay_ms\":%u,"
                    "\"delay_error_samples\":%d,"
                    "\"far_end_threshold\":%.9g,\"double_talk_ratio\":%.9g,"
                    "\"hangover_frames\":%u,\"far_end_hangover\":%u,"
                    "\"double_talk_hangover\":%u,"
                    "\"smoothed_mic_energy\":%.9g,"
                    "\"smoothed_reference_energy\":%.9g,"
                    "\"recovered_mic_energy\":%.9g,"
                    "\"recovered_reference_energy\":%.9g,"
                    "\"direct_reference_energy\":%.9g,"
                    "\"metric_mic_energy\":%.9g,"
                    "\"smoothed_ratio\":%.9g,\"instant_ratio\":%.9g,"
                    "\"dt_on_evidence\":%d,\"dt_hold_evidence\":%d,"
                    "\"mic_recovery_relative_error\":%.9g,"
                    "\"reference_recovery_relative_error\":%.9g}\n",
                    frame_index,
                    (unsigned)metrics.far_end_active,
                    (unsigned)metrics.double_talk_active,
                    (unsigned)metrics.aec_converged,
                    metrics.estimated_delay_ms,
                    metrics.delay_error_samples,
                    (double)activity->far_end_threshold,
                    (double)activity->double_talk_ratio,
                    activity->hangover_frames,
                    activity->far_end_hangover,
                    activity->double_talk_hangover,
                    (double)current_smoothed_mic,
                    (double)current_smoothed_reference,
                    (double)recovered_mic_energy,
                    (double)recovered_reference_energy,
                    (double)direct_reference_energy,
                    (double)metric_mic_energy,
                    (double)smoothed_ratio,
                    (double)instant_ratio,
                    dt_on_evidence,
                    dt_hold_evidence,
                    relative_error(recovered_mic_energy, metric_mic_energy),
                    relative_error(recovered_reference_energy, direct_reference_energy)) < 0)
            return fail("trace write failed");

        previous_smoothed_mic = current_smoothed_mic;
        previous_smoothed_reference = current_smoothed_reference;
        frame_index++;
    }

    fclose(fm);
    fclose(fr);
    fclose(fo);
    return 0;
#endif
}
