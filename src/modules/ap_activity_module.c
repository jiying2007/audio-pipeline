#include "audio_pipeline/audio_modules.h"
#include "activity/ap_activity.h"
#include "ap_numeric.h"
#include <stdint.h>

typedef struct ap_activity_module_impl { ap_activity_state_t state; } ap_activity_module_impl_t;

static int aligned16(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

size_t ap_module_activity_state_size(void) { return sizeof(ap_activity_module_impl_t); }

ap_status_t ap_module_activity_init(void *memory, size_t memory_size,
                                    const ap_module_activity_config_t *config,
                                    ap_activity_module_t **out) {
    ap_activity_module_impl_t *m;
    if (!memory || !config || !out || !aligned16(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(*m)) return AP_ENOMEM;
    if (!isfinite(config->far_end_threshold) ||
        !isfinite(config->double_talk_ratio) ||
        !(config->far_end_threshold > 0.0f) ||
        !(config->double_talk_ratio >= 1.0f) ||
        config->hangover_frames > 100u)
        return AP_EINVAL;
    m = (ap_activity_module_impl_t *)memory;
    ap_activity_init(&m->state, config->far_end_threshold,
                     config->double_talk_ratio, config->hangover_frames);
    *out = (ap_activity_module_t *)m;
    return AP_OK;
}

void ap_module_activity_reset(ap_activity_module_t *module) {
    ap_activity_module_impl_t *m = (ap_activity_module_impl_t *)module;
    if (m) ap_activity_reset(&m->state);
}

ap_status_t ap_module_activity_process(ap_activity_module_t *module,
                                       float mic_energy,
                                       float reference_energy,
                                       ap_module_activity_result_t *result) {
    ap_activity_module_impl_t *m = (ap_activity_module_impl_t *)module;
    ap_activity_result_t r;
    if (!m || !result || !isfinite(mic_energy) ||
        !isfinite(reference_energy) || mic_energy < 0.0f ||
        reference_energy < 0.0f)
        return AP_EINVAL;
    ap_activity_process(&m->state, mic_energy, reference_energy, &r);
    result->far_end_active = r.far_end_active;
    result->double_talk_active = r.double_talk_active;
    return AP_OK;
}
