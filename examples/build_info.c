#include "audio_pipeline/audio_types.h"
#include <stdio.h>

int main(void) {
    const ap_build_info_t *info = ap_build_info();
    if (info == NULL) return 2;

    printf("version=%s\n", info->version);
    printf("module_mask=%u\n", (unsigned)info->module_mask);
    printf("aec_backend=%s\n", info->aec_backend ? info->aec_backend : "");
    printf("ns_estimator=%s\n", info->ns_estimator ? info->ns_estimator : "");
    printf("simd_backend=%s\n", info->simd_backend ? info->simd_backend : "");
    printf("resampler_mode=%s\n", info->resampler_mode ? info->resampler_mode : "");
    printf("fast_math=%u\n", (unsigned)info->fast_math);
    printf("source_revision=%s\n", info->source_revision);
    printf("compiler_id=%s\n", info->compiler_id);
    printf("compiler_version=%s\n", info->compiler_version);
    printf("target_triple=%s\n", info->target_triple);
    printf("build_type=%s\n", info->build_type);
    printf("config_digest=%s\n", info->config_digest);
    return 0;
}
