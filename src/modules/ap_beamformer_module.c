#include "audio_pipeline/audio_modules.h"
#include "frontend/ap_frontend.h"
#include "ap_numeric.h"
#include <stdint.h>

typedef struct ap_beamformer_module_impl {
    ap_beamformer_state_t state;
    uint32_t rate;
    float spacing;
} ap_beamformer_module_impl_t;

static int aligned16(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}
size_t ap_module_beamformer_state_size(void) { return sizeof(ap_beamformer_module_impl_t); }
ap_status_t ap_module_beamformer_init(void *memory, size_t memory_size,
                                      uint32_t rate, float spacing,
                                      ap_beamformer_module_t **out) {
    ap_beamformer_module_impl_t *m;
    if (!memory || !out || !aligned16(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(*m)) return AP_ENOMEM;
    if ((rate != 8000u && rate != 16000u) ||
        rate > AP_BUILD_MAX_INTERNAL_RATE_HZ || !isfinite(spacing) ||
        spacing < 5.0f || spacing > 200.0f)
        return AP_EINVAL;
    m = (ap_beamformer_module_impl_t *)memory;
    m->rate = rate;
    m->spacing = spacing;
    ap_beamformer_init(&m->state, rate, spacing);
    *out = (ap_beamformer_module_t *)m;
    return AP_OK;
}
void ap_module_beamformer_reset(ap_beamformer_module_t *module) {
    ap_beamformer_module_impl_t *m = (ap_beamformer_module_impl_t *)module;
    if (m) ap_beamformer_init(&m->state, m->rate, m->spacing);
}
ap_status_t ap_module_beamformer_process(ap_beamformer_module_t *module,
                                         int track, float *mic0, float *mic1,
                                         float *output, size_t frame_samples) {
    ap_beamformer_module_impl_t *m = (ap_beamformer_module_impl_t *)module;
    if (!m || !mic0 || !mic1 || !output || frame_samples != m->rate / 100u)
        return AP_EINVAL;
    ap_beamformer_process(&m->state, track, mic0, mic1, output,
                          (uint32_t)frame_samples);
    return AP_OK;
}
