#include "audio_pipeline/audio_pipeline_build.h"
#define AP_BUILD_STAGE_HPF AP_HAVE_MODULE_HPF
#define AP_BUILD_STAGE_BF AP_HAVE_MODULE_BF
#define AP_BUILD_STAGE_SYNC AP_HAVE_MODULE_SYNC
#define AP_BUILD_ACTIVITY AP_HAVE_MODULE_ACTIVITY
#define AP_BUILD_STAGE_AEC AP_HAVE_MODULE_AEC
#define AP_BUILD_STAGE_RES AP_HAVE_MODULE_RES
#define AP_BUILD_STAGE_NS AP_HAVE_MODULE_NS
#define AP_BUILD_STAGE_AGC AP_HAVE_MODULE_AGC
#define AP_BUILD_STAGE_VAD AP_HAVE_MODULE_VAD
#include "core/ap_pipeline_internal.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define FRAME 160u
#define DT_RATIO 1.5f
#define DT_INSTANT_ON (0.90f * DT_RATIO)
#define DT_INSTANT_HOLD (0.72f * DT_RATIO)

#if defined(_MSC_VER)
#define ALIGN16 __declspec(align(16))
#else
#define ALIGN16 _Alignas(16)
#endif

static float energy_i16(const int16_t *x, size_t n) {
    double e = 1.0e-12;
    size_t i;
    for (i = 0u; i < n; ++i) {
        const double v = (double)x[i] / 32768.0;
        e += v * v;
    }
    return (float)(e / (double)n);
}

static float rms_dbfs_i16(const int16_t *x, size_t n) {
    return 10.0f * log10f(energy_i16(x, n) + 1.0e-18f);
}

int main(int argc, char **argv) {
#if !(AP_HAVE_PIPELINE && AP_HAVE_MODULE_ACTIVITY && AP_HAVE_MODULE_AGC && AP_HAVE_MODULE_NS)
    (void)argc;
    (void)argv;
    fputs("required pipeline/activity/NS/AGC modules are not compiled\n", stderr);
    return 2;
#else
    ALIGN16 static unsigned char on_state[AP_PIPELINE_STATE_MAX_BYTES];
    ALIGN16 static unsigned char off_state[AP_PIPELINE_STATE_MAX_BYTES];
    ap_pipeline_t *on = NULL;
    ap_pipeline_t *off = NULL;
    ap_config_t on_cfg = ap_config_default(AP_PROFILE_CALL);
    ap_config_t off_cfg;
    int16_t mic[FRAME];
    int16_t render[FRAME];
    int16_t on_out[FRAME];
    int16_t off_out[FRAME];
    FILE *fm;
    FILE *fr;
    unsigned frame = 0u;

    if (argc != 3) {
        fprintf(stderr, "usage: %s MIC_PCM RENDER_PCM\n", argv[0]);
        return 2;
    }
    on_cfg.mic_channels = 1u;
    on_cfg.stages &= ~AP_STAGE_BF;
    off_cfg = on_cfg;
    off_cfg.stages &= ~AP_STAGE_AGC;
    if (ap_pipeline_validate_config(&on_cfg) != AP_OK ||
        ap_pipeline_validate_config(&off_cfg) != AP_OK)
        return 3;
    if (ap_pipeline_init(on_state, sizeof(on_state), &on_cfg, &on) != AP_OK ||
        ap_pipeline_init(off_state, sizeof(off_state), &off_cfg, &off) != AP_OK)
        return 3;

    fm = fopen(argv[1], "rb");
    fr = fopen(argv[2], "rb");
    if (!fm || !fr) {
        if (fm) fclose(fm);
        if (fr) fclose(fr);
        return 2;
    }

    while (fread(mic, sizeof(mic[0]), FRAME, fm) == FRAME) {
        ap_metrics_t mon, mof;
        size_t got = fread(render, sizeof(render[0]), FRAME, fr);
        float input_mic_energy;
        float input_ref_energy;
        float input_ratio;
        float smoothed_ratio;
        float gain_linear;
        float gain_db;
        if (got < FRAME)
            memset(render + got, 0, (FRAME - got) * sizeof(render[0]));

        input_mic_energy = energy_i16(mic, FRAME);
        input_ref_energy = energy_i16(render, FRAME);
        input_ratio = input_mic_energy / (input_ref_energy + 1.0e-12f);

        if (ap_pipeline_push_render(on, render, FRAME) != AP_OK ||
            ap_pipeline_push_render(off, render, FRAME) != AP_OK)
            return 4;
        if (ap_pipeline_process_capture(on, mic, FRAME, on_out) != AP_OK ||
            ap_pipeline_process_capture(off, mic, FRAME, off_out) != AP_OK)
            return 4;
        ap_pipeline_get_metrics(on, &mon);
        ap_pipeline_get_metrics(off, &mof);
        if (mon.far_end_active != mof.far_end_active ||
            mon.double_talk_active != mof.double_talk_active)
            return 5;

        smoothed_ratio = on->activity.smoothed_mic_energy /
                         (on->activity.smoothed_reference_energy + 1.0e-12f);
        gain_linear = on->agc.gain;
        gain_db = 20.0f * log10f(gain_linear + 1.0e-12f);
        printf("{\"frame\":%u,\"far_end_active\":%u,\"double_talk_active\":%u,"
               "\"agc_gain_linear\":%.9g,\"agc_gain_db\":%.9g,"
               "\"ns_speech_probability\":%.9g,"
               "\"smoothed_mic_energy\":%.9g,\"smoothed_reference_energy\":%.9g,"
               "\"smoothed_ratio\":%.9g,\"input_ratio_proxy\":%.9g,"
               "\"smoothed_gate\":%u,\"instant_on_proxy_gate\":%u,\"instant_hold_proxy_gate\":%u,"
               "\"with_agc_output_rms_dbfs\":%.9g,\"without_agc_output_rms_dbfs\":%.9g}\n",
               frame,
               (unsigned)mon.far_end_active,
               (unsigned)mon.double_talk_active,
               (double)gain_linear,
               (double)gain_db,
               (double)on->ns.speech_probability,
               (double)on->activity.smoothed_mic_energy,
               (double)on->activity.smoothed_reference_energy,
               (double)smoothed_ratio,
               (double)input_ratio,
               (unsigned)(smoothed_ratio > DT_RATIO),
               (unsigned)(input_ratio > DT_INSTANT_ON),
               (unsigned)(input_ratio > DT_INSTANT_HOLD),
               (double)rms_dbfs_i16(on_out, FRAME),
               (double)rms_dbfs_i16(off_out, FRAME));
        frame++;
    }
    fclose(fm);
    fclose(fr);
    return 0;
#endif
}
