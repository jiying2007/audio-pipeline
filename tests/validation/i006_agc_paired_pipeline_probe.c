#include "audio_pipeline/audio_pipeline.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char state_with[AP_PIPELINE_STATE_MAX_BYTES];
    AP_ALIGN16 static unsigned char state_without[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[160];
    int16_t render[160];
    int16_t out_with[160];
    int16_t out_without[160];
    FILE *fm = NULL;
    FILE *fr = NULL;
    FILE *fw = NULL;
    FILE *fn = NULL;
    ap_config_t cfg_with = ap_config_default(AP_PROFILE_CALL);
    ap_config_t cfg_without;
    ap_pipeline_t *with_agc = NULL;
    ap_pipeline_t *without_agc = NULL;
    unsigned frame = 0u;
    uint32_t latency_with;
    uint32_t latency_without;

    if (argc != 5) {
        fprintf(stderr, "usage: %s MIC_PCM RENDER_PCM WITH_AGC_PCM WITHOUT_AGC_PCM\n", argv[0]);
        return 2;
    }
    cfg_with.io_sample_rate_hz = 16000u;
    cfg_with.internal_sample_rate_hz = 16000u;
    cfg_with.mic_channels = 1u;
    cfg_with.stages &= ~AP_STAGE_BF;
    cfg_without = cfg_with;
    cfg_without.stages &= ~AP_STAGE_AGC;
    if (ap_pipeline_validate_config(&cfg_with) != AP_OK ||
        ap_pipeline_validate_config(&cfg_without) != AP_OK)
        return 3;
    if (ap_pipeline_state_size() > sizeof(state_with) ||
        ap_pipeline_state_size() > sizeof(state_without) ||
        ap_pipeline_init(state_with, sizeof(state_with), &cfg_with, &with_agc) != AP_OK ||
        ap_pipeline_init(state_without, sizeof(state_without), &cfg_without, &without_agc) != AP_OK)
        return 3;
    latency_with = ap_pipeline_algorithmic_latency_ms(with_agc);
    latency_without = ap_pipeline_algorithmic_latency_ms(without_agc);
    if (latency_with != latency_without) {
        fprintf(stderr, "paired pipeline latency mismatch: %u != %u\n", latency_with, latency_without);
        return 3;
    }

    fm = fopen(argv[1], "rb");
    fr = fopen(argv[2], "rb");
    fw = fopen(argv[3], "wb");
    fn = fopen(argv[4], "wb");
    if (!fm || !fr || !fw || !fn) {
        if (fm) fclose(fm);
        if (fr) fclose(fr);
        if (fw) fclose(fw);
        if (fn) fclose(fn);
        return 2;
    }
    while (fread(mic, sizeof(mic[0]), 160u, fm) == 160u) {
        ap_metrics_t mw;
        ap_metrics_t mn;
        const size_t got = fread(render, sizeof(render[0]), 160u, fr);
        if (got < 160u) memset(render + got, 0, (160u - got) * sizeof(render[0]));
        if (ap_pipeline_push_render(with_agc, render, 160u) != AP_OK ||
            ap_pipeline_push_render(without_agc, render, 160u) != AP_OK ||
            ap_pipeline_process_capture(with_agc, mic, 160u, out_with) != AP_OK ||
            ap_pipeline_process_capture(without_agc, mic, 160u, out_without) != AP_OK) {
            fclose(fm); fclose(fr); fclose(fw); fclose(fn);
            return 4;
        }
        ap_pipeline_get_metrics(with_agc, &mw);
        ap_pipeline_get_metrics(without_agc, &mn);
        if (mw.far_end_active != mn.far_end_active ||
            mw.double_talk_active != mn.double_talk_active) {
            fprintf(stderr, "paired activity drift at frame %u\n", frame);
            fclose(fm); fclose(fr); fclose(fw); fclose(fn);
            return 4;
        }
        if (fwrite(out_with, sizeof(out_with[0]), 160u, fw) != 160u ||
            fwrite(out_without, sizeof(out_without[0]), 160u, fn) != 160u) {
            fclose(fm); fclose(fr); fclose(fw); fclose(fn);
            return 5;
        }
        printf("{\"frame\":%u,\"algorithmic_latency_ms\":%u,"
               "\"far_end_active\":%u,\"double_talk_active\":%u,"
               "\"with_output_rms_dbfs\":%.7g,\"without_output_rms_dbfs\":%.7g,"
               "\"with_vad_active\":%u,\"without_vad_active\":%u}\n",
               frame,
               latency_with,
               (unsigned)mw.far_end_active,
               (unsigned)mw.double_talk_active,
               (double)mw.output_rms_dbfs,
               (double)mn.output_rms_dbfs,
               (unsigned)mw.vad_active,
               (unsigned)mn.vad_active);
        frame++;
    }
    fclose(fm);
    fclose(fr);
    fclose(fw);
    fclose(fn);
    return 0;
}
