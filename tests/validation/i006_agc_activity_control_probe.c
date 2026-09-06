#include "audio_pipeline/audio_pipeline_build.h"
#include "activity/ap_activity.h"
#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>

#define I006_FRAME 160u
#define I006_FAR_THRESHOLD 1.0e-7f
#define I006_DT_RATIO 1.5f
#define I006_HANGOVER 3u

static float rms_dbfs(const float *x, size_t n) {
    double e = 1.0e-18;
    size_t i;
    for (i = 0u; i < n; ++i) e += (double)x[i] * (double)x[i];
    return (float)(10.0 * log10(e / (double)n + 1.0e-18));
}

static float peak_dbfs(const float *x, size_t n) {
    float peak = 1.0e-9f;
    size_t i;
    for (i = 0u; i < n; ++i) {
        const float a = fabsf(x[i]);
        if (a > peak) peak = a;
    }
    return 20.0f * log10f(peak);
}

int main(int argc, char **argv) {
#if !AP_BUILD_STAGE_AGC
    (void)argc;
    (void)argv;
    fputs("AGC module is not compiled\n", stderr);
    return 2;
#else
    FILE *fm;
    FILE *fr;
    int16_t mic_pcm[I006_FRAME];
    int16_t ref_pcm[I006_FRAME];
    float mic[I006_FRAME];
    ap_activity_state_t activity;
    ap_agc_state_t agc;
    unsigned frame = 0u;
    size_t i;

    if (argc != 3) {
        fprintf(stderr, "usage: %s MIC_PCM RENDER_PCM\n", argv[0]);
        return 2;
    }
    fm = fopen(argv[1], "rb");
    fr = fopen(argv[2], "rb");
    if (!fm || !fr) {
        if (fm) fclose(fm);
        if (fr) fclose(fr);
        return 2;
    }
    ap_activity_init(&activity, I006_FAR_THRESHOLD, I006_DT_RATIO, I006_HANGOVER);
    ap_agc_init(&agc, -20.0f, -2.0f);

    while (fread(mic_pcm, sizeof(mic_pcm[0]), I006_FRAME, fm) == I006_FRAME) {
        const size_t got = fread(ref_pcm, sizeof(ref_pcm[0]), I006_FRAME, fr);
        float mic_energy = 1.0e-12f;
        float ref_energy = 1.0e-12f;
        float input_rms;
        float input_peak;
        float output_rms;
        float output_peak;
        ap_activity_result_t result;
        int allow_gain;
        if (got < I006_FRAME) {
            for (i = got; i < I006_FRAME; ++i) ref_pcm[i] = 0;
        }
        for (i = 0u; i < I006_FRAME; ++i) {
            const float ref = (float)ref_pcm[i] / 32768.0f;
            mic[i] = (float)mic_pcm[i] / 32768.0f;
            mic_energy += mic[i] * mic[i];
            ref_energy += ref * ref;
        }
        mic_energy /= (float)I006_FRAME;
        ref_energy /= (float)I006_FRAME;
        input_rms = rms_dbfs(mic, I006_FRAME);
        input_peak = peak_dbfs(mic, I006_FRAME);
        ap_activity_process(&activity, mic_energy, ref_energy, &result);
        allow_gain = !(result.far_end_active && !result.double_talk_active);
        ap_agc_process_controlled(&agc, mic, I006_FRAME, allow_gain);
        output_rms = rms_dbfs(mic, I006_FRAME);
        output_peak = peak_dbfs(mic, I006_FRAME);
        printf("{\"frame\":%u,\"far_end_active\":%u,\"double_talk_active\":%u,"
               "\"allow_gain_increase\":%u,\"input_rms_dbfs\":%.7g,"
               "\"output_rms_dbfs\":%.7g,\"input_peak_dbfs\":%.7g,"
               "\"output_peak_dbfs\":%.7g,\"gain_db\":%.7g}\n",
               frame,
               (unsigned)result.far_end_active,
               (unsigned)result.double_talk_active,
               (unsigned)(allow_gain ? 1u : 0u),
               (double)input_rms,
               (double)output_rms,
               (double)input_peak,
               (double)output_peak,
               (double)(output_rms - input_rms));
        frame++;
    }
    fclose(fm);
    fclose(fr);
    return 0;
#endif
}
