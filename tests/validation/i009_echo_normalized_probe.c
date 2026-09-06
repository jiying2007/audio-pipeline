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
#if AP_HAVE_MODULE_AEC
#define AP_BUILD_AEC_MDF 1
#endif
#if AP_HAVE_MODULE_NS
#define AP_BUILD_NS_EMA 1
#endif
#include "core/ap_pipeline_internal.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define FRAME 160u

#if defined(_MSC_VER)
#define ALIGN16 __declspec(align(16))
#else
#define ALIGN16 _Alignas(16)
#endif

static float energy_f32(const float *x, uint32_t n) {
    double energy = 1.0e-12;
    uint32_t i;
    for (i = 0u; i < n; ++i) energy += (double)x[i] * (double)x[i];
    return (float)(energy / (double)(n ? n : 1u));
}

static float smooth_energy(float old_value, float value) {
    const float alpha = value > old_value ? 0.35f : 0.08f;
    if (old_value <= 0.0f) return value;
    return old_value + alpha * (value - old_value);
}

static float recover_input_energy(float old_smoothed, float new_smoothed) {
    float alpha;
    if (old_smoothed <= 0.0f) return new_smoothed;
    alpha = new_smoothed > old_smoothed ? 0.35f : 0.08f;
    return old_smoothed + (new_smoothed - old_smoothed) / alpha;
}

int main(int argc, char **argv) {
#if !(AP_HAVE_PIPELINE && AP_HAVE_MODULE_ACTIVITY && AP_HAVE_MODULE_AEC)
    (void)argc;
    (void)argv;
    fputs("required pipeline/activity/AEC modules are not compiled\n", stderr);
    return 2;
#else
    ALIGN16 static unsigned char state_memory[AP_PIPELINE_STATE_MAX_BYTES];
    ap_pipeline_t *pipeline = NULL;
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    int16_t mic[FRAME];
    int16_t render[FRAME];
    int16_t output[FRAME];
    FILE *fm;
    FILE *fr;
    unsigned frame = 0u;
    float smoothed_echo_energy = 0.0f;

    if (argc != 3) {
        fprintf(stderr, "usage: %s MIC_PCM RENDER_PCM\n", argv[0]);
        return 2;
    }
    cfg.mic_channels = 1u;
    cfg.stages &= ~AP_STAGE_BF;
    if (ap_pipeline_validate_config(&cfg) != AP_OK) return 3;
    if (ap_pipeline_init(state_memory, sizeof(state_memory), &cfg, &pipeline) != AP_OK)
        return 3;

    fm = fopen(argv[1], "rb");
    fr = fopen(argv[2], "rb");
    if (!fm || !fr) {
        if (fm) fclose(fm);
        if (fr) fclose(fr);
        return 2;
    }

    while (fread(mic, sizeof(mic[0]), FRAME, fm) == FRAME) {
        ap_metrics_t metrics;
        const float old_smoothed_mic = pipeline->activity.smoothed_mic_energy;
        const float old_smoothed_ref = pipeline->activity.smoothed_reference_energy;
        const float previous_echo_energy = energy_f32(pipeline->echo_estimate, pipeline->internal_frame);
        const unsigned previous_aec_converged = (unsigned)pipeline->metrics.aec_converged;
        const unsigned previous_aec_convergence_frames = pipeline->metrics.aec_convergence_frames;
        size_t got = fread(render, sizeof(render[0]), FRAME, fr);
        float mic_energy;
        float reference_energy;
        float current_echo_energy;
        float raw_smoothed_ratio;
        float raw_instant_ratio;
        float echo_smoothed_ratio;
        float echo_instant_ratio;
        if (got < FRAME)
            memset(render + got, 0, (FRAME - got) * sizeof(render[0]));

        smoothed_echo_energy = smooth_energy(smoothed_echo_energy, previous_echo_energy);
        if (ap_pipeline_push_render(pipeline, render, FRAME) != AP_OK) return 4;
        if (ap_pipeline_process_capture(pipeline, mic, FRAME, output) != AP_OK) return 4;
        ap_pipeline_get_metrics(pipeline, &metrics);

        mic_energy = recover_input_energy(old_smoothed_mic, pipeline->activity.smoothed_mic_energy);
        reference_energy = recover_input_energy(old_smoothed_ref, pipeline->activity.smoothed_reference_energy);
        current_echo_energy = energy_f32(pipeline->echo_estimate, pipeline->internal_frame);
        raw_smoothed_ratio = pipeline->activity.smoothed_mic_energy /
                             (pipeline->activity.smoothed_reference_energy + 1.0e-12f);
        raw_instant_ratio = mic_energy / (reference_energy + 1.0e-12f);
        echo_smoothed_ratio = pipeline->activity.smoothed_mic_energy /
                              (smoothed_echo_energy + 1.0e-12f);
        echo_instant_ratio = mic_energy / (previous_echo_energy + 1.0e-12f);

        printf("{\"frame\":%u,\"far_end_active\":%u,\"double_talk_active\":%u,"
               "\"previous_aec_converged\":%u,\"previous_aec_convergence_frames\":%u,"
               "\"mic_energy\":%.9g,\"reference_energy\":%.9g,"
               "\"previous_echo_energy\":%.9g,\"current_echo_energy\":%.9g,"
               "\"smoothed_mic_energy\":%.9g,\"smoothed_reference_energy\":%.9g,"
               "\"smoothed_echo_energy\":%.9g,\"raw_smoothed_ratio\":%.9g,"
               "\"raw_instant_ratio\":%.9g,\"echo_smoothed_ratio\":%.9g,"
               "\"echo_instant_ratio\":%.9g}\n",
               frame,
               (unsigned)metrics.far_end_active,
               (unsigned)metrics.double_talk_active,
               previous_aec_converged,
               previous_aec_convergence_frames,
               (double)mic_energy,
               (double)reference_energy,
               (double)previous_echo_energy,
               (double)current_echo_energy,
               (double)pipeline->activity.smoothed_mic_energy,
               (double)pipeline->activity.smoothed_reference_energy,
               (double)smoothed_echo_energy,
               (double)raw_smoothed_ratio,
               (double)raw_instant_ratio,
               (double)echo_smoothed_ratio,
               (double)echo_instant_ratio);
        frame++;
    }
    fclose(fm);
    fclose(fr);
    return 0;
#endif
}
