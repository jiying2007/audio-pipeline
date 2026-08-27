#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "ap_limits.h"
#include <stdint.h>

typedef struct ap_vad_module_impl {
    ap_vad_state_t state;
} ap_vad_module_impl_t;

static int ap_module_vad_aligned(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

size_t ap_module_vad_state_size(void) { return sizeof(ap_vad_module_impl_t); }

ap_status_t ap_module_vad_init(void *memory, size_t memory_size,
                               ap_vad_module_t **out) {
    ap_vad_module_impl_t *m;
    if (!memory || !out || !ap_module_vad_aligned(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_vad_module_impl_t)) return AP_ENOMEM;
    m = (ap_vad_module_impl_t *)memory;
    ap_vad_init(&m->state);
    *out = (ap_vad_module_t *)m;
    return AP_OK;
}

ap_status_t ap_module_vad_process(ap_vad_module_t *module,
                                  const float *samples, size_t frame_samples,
                                  float upstream_speech_probability,
                                  int use_upstream_probability,
                                  ap_module_vad_result_t *result) {
    ap_vad_module_impl_t *m = (ap_vad_module_impl_t *)module;
    ap_vad_result_t internal;
    if (!m || !samples || !result || frame_samples == 0u ||
        frame_samples > AP_INTERNAL_FRAME_MAX ||
        upstream_speech_probability < 0.0f || upstream_speech_probability > 1.0f)
        return AP_EINVAL;
    ap_vad_process(&m->state, samples, (uint32_t)frame_samples,
                   upstream_speech_probability, use_upstream_probability,
                   &internal);
    result->probability = internal.probability;
    result->active = internal.active;
    return AP_OK;
}
