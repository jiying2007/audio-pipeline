#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "ap_limits.h"
#include <stdint.h>

typedef struct ap_agc_module_impl {
    ap_agc_state_t state;
} ap_agc_module_impl_t;

static int ap_module_agc_aligned(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

size_t ap_module_agc_state_size(void) { return sizeof(ap_agc_module_impl_t); }

ap_status_t ap_module_agc_init(void *memory, size_t memory_size,
                               const ap_module_agc_config_t *config,
                               ap_agc_module_t **out) {
    ap_agc_module_impl_t *m;
    if (!memory || !config || !out || !ap_module_agc_aligned(memory))
        return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_agc_module_impl_t)) return AP_ENOMEM;
    if (config->target_dbfs > -1.0f || config->target_dbfs < -60.0f ||
        config->limiter_dbfs > -0.1f || config->limiter_dbfs < -20.0f)
        return AP_EINVAL;
    m = (ap_agc_module_impl_t *)memory;
    ap_agc_init(&m->state, config->target_dbfs, config->limiter_dbfs);
    *out = (ap_agc_module_t *)m;
    return AP_OK;
}

ap_status_t ap_module_agc_process(ap_agc_module_t *module,
                                  float *samples, size_t frame_samples) {
    ap_agc_module_impl_t *m = (ap_agc_module_impl_t *)module;
    if (!m || !samples || frame_samples == 0u ||
        frame_samples > AP_INTERNAL_FRAME_MAX) return AP_EINVAL;
    ap_agc_process(&m->state, samples, (uint32_t)frame_samples);
    return AP_OK;
}
