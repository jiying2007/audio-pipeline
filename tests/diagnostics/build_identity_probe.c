#include "audio_pipeline/audio_pipeline.h"
#include <inttypes.h>
#include <stdio.h>

static const char *safe_text(const char *value) {
    return value ? value : "";
}

int main(void) {
    const ap_build_info_t *info = ap_build_info();
    if (!info) return 2;
    if (info->struct_size < sizeof(*info) ||
        info->api_version != AP_BUILD_INFO_API_VERSION)
        return 3;

    printf("{\n");
    printf("  \"schema_version\": 1,\n");
    printf("  \"authority\": \"repository-internal-processor-build-info-only\",\n");
    printf("  \"version\": \"%s\",\n", safe_text(info->version));
    printf("  \"module_mask\": %" PRIu32 ",\n", (uint32_t)info->module_mask);
    printf("  \"aec_backend\": \"%s\",\n", safe_text(info->aec_backend));
    printf("  \"ns_estimator\": \"%s\",\n", safe_text(info->ns_estimator));
    printf("  \"simd_backend\": \"%s\",\n", safe_text(info->simd_backend));
    printf("  \"resampler_mode\": \"%s\",\n", safe_text(info->resampler_mode));
    printf("  \"source_revision\": \"%s\",\n", safe_text(info->source_revision));
    printf("  \"config_digest\": \"%s\",\n", safe_text(info->config_digest));
    printf("  \"compiler_id\": \"%s\",\n", safe_text(info->compiler_id));
    printf("  \"compiler_version\": \"%s\",\n", safe_text(info->compiler_version));
    printf("  \"target_triple\": \"%s\",\n", safe_text(info->target_triple));
    printf("  \"build_type\": \"%s\"\n", safe_text(info->build_type));
    printf("}\n");
    return 0;
}
