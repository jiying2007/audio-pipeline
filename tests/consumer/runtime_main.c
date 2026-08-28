#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <stdio.h>

#if defined(_MSC_VER)
#define AP_ALIGN(N) __declspec(align(N))
#else
#define AP_ALIGN(N) _Alignas(N)
#endif

int main(void) {
    AP_ALIGN(AP_PIPELINE_STATE_ALIGNMENT)
    static unsigned char pipeline_state[AP_PIPELINE_STATE_MAX_BYTES];
    AP_ALIGN(AP_RUNTIME_STATE_ALIGNMENT)
    static unsigned char runtime_state[AP_RUNTIME_STATE_MAX_BYTES];
    ap_config_t pipeline_config = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_runtime_config_t runtime_config = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    if (ap_pipeline_init(pipeline_state, sizeof(pipeline_state),
                         &pipeline_config, &pipeline) != AP_OK)
        return 2;
    if (ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline,
                        &runtime_config, &runtime) != AP_OK)
        return 3;
    printf("runtime consumer state=%zu\n", ap_runtime_state_size());
    ap_runtime_deinit(runtime);
    return 0;
}
