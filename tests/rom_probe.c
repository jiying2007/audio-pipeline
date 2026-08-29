#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <stdint.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

/*
 * Link-only SKU ROM probe.
 *
 * Unlike consumer_smoke, this deliberately reaches pipeline init, render,
 * capture, metrics and control paths so --gc-sections retains the selected
 * DSP graph. Resource CI sizes the resulting ELF but does not execute it.
 * State/audio buffers live on the stack so the ROM metric is not polluted by
 * the public maximum state envelope in .bss.
 */
int main(void) {
    AP_ALIGN16 unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[AP_BUILD_IO_FRAME_MAX * AP_BUILD_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_BUILD_IO_FRAME_MAX] = {0};
    int16_t output[AP_BUILD_IO_FRAME_MAX] = {0};
    ap_config_t config = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = 0;
    ap_metrics_t metrics;
    ap_tuning_t tuning = {0};
    ap_status_t status;
    size_t frames;

    status = ap_pipeline_init(state, sizeof(state), &config, &pipeline);
    if (status != AP_OK || pipeline == 0) return (int)status;

    frames = ap_pipeline_frame_samples(pipeline);
    if (ap_pipeline_stages(pipeline) & AP_STAGE_SYNC) {
        status = ap_pipeline_push_render(pipeline, render, frames);
        if (status != AP_OK) return (int)status;
    }
    status = ap_pipeline_process_capture(pipeline, mic, frames, output);
    if (status != AP_OK) return (int)status;

    ap_pipeline_get_metrics(pipeline, &metrics);
    tuning.struct_size = sizeof(tuning);
    tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    tuning.mask = AP_TUNING_AEC_MU;
    tuning.aec_mu = config.aec_mu;
    (void)ap_pipeline_apply_tuning(pipeline, &tuning);
    (void)ap_pipeline_notify_stream_discontinuity(
        pipeline, AP_DISCONTINUITY_CAPTURE_GAP, 1u);
    (void)ap_pipeline_notify_echo_path_change(pipeline);

    return (int)((uint32_t)metrics.processed_frames ^
                 (uint32_t)output[0] ^
                 (uint32_t)ap_pipeline_algorithmic_latency_ms(pipeline));
}
