#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "ap_limits.h"
#include <stdint.h>

static int ap_module_res_aligned(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

static ap_enhance_mode_t ap_module_res_mode(ap_quality_t q) {
    if (q == AP_QUALITY_FULL) return AP_ENHANCE_FULL;
    if (q == AP_QUALITY_LITE) return AP_ENHANCE_LITE;
    return AP_ENHANCE_SAFE;
}

size_t ap_module_res_state_size(void) { return sizeof(ap_res_state_t); }

ap_status_t ap_module_res_init(void *memory, size_t memory_size,
                               ap_res_module_t **out) {
    if (!memory || !out || !ap_module_res_aligned(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_res_state_t)) return AP_ENOMEM;
    ap_res_init((ap_res_state_t *)memory);
    *out = (ap_res_module_t *)memory;
    return AP_OK;
}

ap_status_t ap_module_res_process(ap_res_module_t *module,
                                  ap_quality_t quality,
                                  float *samples, size_t frame_samples,
                                  float echo_energy,
                                  float residual_energy,
                                  int far_end_active,
                                  int double_talk_active,
                                  float *applied_gain) {
    if (!module || !samples || !applied_gain || frame_samples == 0u ||
        frame_samples > AP_INTERNAL_FRAME_MAX ||
        quality < AP_QUALITY_SAFE || quality > AP_QUALITY_FULL)
        return AP_EINVAL;
    *applied_gain = ap_res_process((ap_res_state_t *)module,
                                   ap_module_res_mode(quality), samples,
                                   (uint32_t)frame_samples,
                                   echo_energy, residual_energy,
                                   far_end_active, double_talk_active);
    return AP_OK;
}
