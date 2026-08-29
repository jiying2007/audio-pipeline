#include "audio_pipeline/audio_types.h"
#include <stdio.h>

int main(void) {
    const ap_build_info_t *base = ap_build_info();
    const ap_build_info_v2_t *v2 = ap_build_info_v2_get();
    if (base == NULL || v2 == NULL) return 2;

    printf("version=%s\n", base->version);
    printf("module_mask=%u\n", (unsigned)base->module_mask);
    printf("aec_backend=%s\n", base->aec_backend ? base->aec_backend : "");
    printf("ns_estimator=%s\n", base->ns_estimator ? base->ns_estimator : "");
    printf("simd_backend=%s\n", base->simd_backend ? base->simd_backend : "");
    printf("resampler_mode=%s\n", base->resampler_mode ? base->resampler_mode : "");
    printf("fast_math=%u\n", (unsigned)base->fast_math);
    printf("source_revision=%s\n", v2->source_revision);
    printf("compiler_id=%s\n", v2->compiler_id);
    printf("compiler_version=%s\n", v2->compiler_version);
    printf("target_triple=%s\n", v2->target_triple);
    printf("build_type=%s\n", v2->build_type);
    printf("config_digest=%s\n", v2->config_digest);
    return 0;
}
