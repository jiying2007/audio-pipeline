#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_types.h"
#include <stdio.h>

#if defined(_MSC_VER)
#define AP_ALIGN(N) __declspec(align(N))
#else
#define AP_ALIGN(N) _Alignas(N)
#endif

int main(void) {
    AP_ALIGN(AP_PIPELINE_STATE_ALIGNMENT)
    static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    ap_config_t config = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_pipeline_t *pipeline = NULL;
    const ap_build_info_t *info = ap_build_info();
    if (!info || ap_pipeline_state_size() > sizeof(state)) return 2;
    if (ap_pipeline_init(state, sizeof(state), &config, &pipeline) != AP_OK) return 3;
    printf("consumer version=%s state=%zu\n", info->version, ap_pipeline_state_size());
    return pipeline ? 0 : 4;
}
