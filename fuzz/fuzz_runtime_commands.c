#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#if defined(__GNUC__) || defined(__clang__)
#define AP_ALIGN(N) __attribute__((aligned(N)))
#else
#define AP_ALIGN(N)
#endif
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    static AP_ALIGN(AP_PIPELINE_STATE_ALIGNMENT) unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
    static AP_ALIGN(AP_RUNTIME_STATE_ALIGNMENT) unsigned char runtime_mem[AP_RUNTIME_STATE_MAX_BYTES];
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_runtime_command_t cmd;
    if (size < 4u) return 0;
    if (ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &pcfg, &pipeline) != AP_OK) return 0;
    if (ap_runtime_init(runtime_mem, sizeof(runtime_mem), pipeline, &rcfg, &runtime) != AP_OK) return 0;
    memset(&cmd, 0, sizeof(cmd));
    cmd.struct_size = sizeof(cmd);
    cmd.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    cmd.kind = 1u + (data[0] % 7u);
    if (cmd.kind == AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY) {
        cmd.data.discontinuity.flags = size > 1u ? data[1] : 0u;
        cmd.data.discontinuity.lost_frames = size > 3u ? ((uint32_t)data[2] << 8u) | data[3] : 0u;
    } else if (cmd.kind == AP_RUNTIME_COMMAND_SET_QUALITY) {
        cmd.data.set_quality.quality = (ap_quality_t)(size > 1u ? data[1] : 0u);
    } else if (cmd.kind == AP_RUNTIME_COMMAND_SET_TUNING) {
        cmd.data.tuning.struct_size = sizeof(cmd.data.tuning);
        cmd.data.tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
        cmd.data.tuning.mask = size > 1u ? data[1] : 0u;
        if (size >= 6u) memcpy(&cmd.data.tuning.aec_mu, data + 2u, 4u);
    }
    (void)ap_runtime_command(runtime, &cmd);
    ap_runtime_deinit(runtime);
    return 0;
}
