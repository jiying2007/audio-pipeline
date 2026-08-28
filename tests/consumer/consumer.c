#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <stdio.h>

int main(void) {
    ap_config_t config = ap_config_default(AP_PROFILE_ASSISTANT);
    const ap_build_info_t *info = ap_build_info();
    if (!info || info->version_major != AP_VERSION_MAJOR) return 2;
    if (ap_pipeline_validate_config(&config) != AP_OK) return 3;
    printf("audio-pipeline %u.%u.%u modules=0x%08x state=%zu\n",
           info->version_major, info->version_minor, info->version_patch,
           (unsigned)info->module_mask, ap_pipeline_state_size());
    return 0;
}
