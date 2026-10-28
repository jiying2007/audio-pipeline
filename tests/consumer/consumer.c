#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    ap_config_t config = ap_config_default(AP_PROFILE_ASSISTANT);
    const ap_build_info_t *info = ap_build_info();
    if (!info || info->version_major != AP_VERSION_MAJOR) return 2;
    if (ap_pipeline_validate_config(&config) != AP_OK) return 3;
    if (argc > 2) return 4;
    if (argc == 2 && (!info->source_revision ||
                     strcmp(info->source_revision, argv[1]) != 0)) {
        fprintf(stderr, "installed SDK source revision does not match %s\n", argv[1]);
        return 4;
    }
    printf("audio-pipeline %u.%u.%u modules=0x%08x state=%zu source_revision=%s\n",
           info->version_major, info->version_minor, info->version_patch,
           (unsigned)info->module_mask, ap_pipeline_state_size(), info->source_revision);
    return 0;
}
