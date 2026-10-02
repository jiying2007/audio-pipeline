#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

int main(void) {
    AP_ALIGN16 static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    const ap_build_info_t *info = ap_build_info();
    size_t pipeline_state = ap_pipeline_state_size();
    size_t runtime_state = ap_runtime_state_size();
    uint32_t latency_ms;
    uint32_t latency_frames;

    if (info == NULL) return 2;
    if (pipeline_state == 0u || pipeline_state > sizeof(pipeline_mem)) return 3;
    if (ap_pipeline_init(
            pipeline_mem, sizeof(pipeline_mem), &cfg, &pipeline) != AP_OK ||
        pipeline == NULL)
        return 4;

    latency_ms = ap_pipeline_algorithmic_latency_ms(pipeline);
    latency_frames = (latency_ms + 9u) / 10u;

    printf(
        "{\"schema_version\":1,"
        "\"version\":\"%s\","
        "\"source_revision\":\"%s\","
        "\"config_digest\":\"%s\","
        "\"target_triple\":\"%s\","
        "\"compiler_id\":\"%s\","
        "\"compiler_version\":\"%s\","
        "\"simd_backend\":\"%s\","
        "\"aec_backend\":\"%s\","
        "\"ns_estimator\":\"%s\","
        "\"module_mask\":%u,"
        "\"max_io_rate_hz\":%u,"
        "\"max_internal_rate_hz\":%u,"
        "\"max_mic_channels\":%u,"
        "\"max_delay_ms\":%u,"
        "\"max_aec_tail_ms\":%u,"
        "\"runtime_queue_depth\":%u,"
        "\"bf_direction_tracking\":%u,"
        "\"pipeline_state_bytes\":%zu,"
        "\"runtime_state_bytes\":%zu,"
        "\"pipeline_state_alignment\":%zu,"
        "\"runtime_state_alignment\":%zu,"
        "\"algorithmic_latency_ms\":%u,"
        "\"algorithmic_latency_frames\":%u}\n",
        info->version,
        info->source_revision,
        info->config_digest,
        info->target_triple,
        info->compiler_id,
        info->compiler_version,
        info->simd_backend,
        info->aec_backend ? info->aec_backend : "",
        info->ns_estimator ? info->ns_estimator : "",
        (unsigned)info->module_mask,
        info->max_io_rate_hz,
        info->max_internal_rate_hz,
        info->max_mic_channels,
        info->max_delay_ms,
        info->max_aec_tail_ms,
        info->runtime_queue_depth,
        (unsigned)info->bf_direction_tracking,
        pipeline_state,
        runtime_state,
        ap_pipeline_state_alignment(),
        ap_runtime_state_alignment(),
        latency_ms,
        latency_frames);
    return 0;
}
