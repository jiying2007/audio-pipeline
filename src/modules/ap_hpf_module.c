#include "audio_pipeline/audio_modules.h"
#include "frontend/ap_frontend.h"
#include "ap_limits.h"
#include <stdint.h>

typedef struct ap_hpf_module_impl { ap_hpf_state_t state; } ap_hpf_module_impl_t;

static int ap_module_hpf_aligned(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

size_t ap_module_hpf_state_size(void) { return sizeof(ap_hpf_module_impl_t); }

ap_status_t ap_module_hpf_init(void *memory, size_t memory_size,
                               uint32_t sample_rate_hz, uint32_t channels,
                               ap_hpf_module_t **out) {
    ap_hpf_module_impl_t *m;
    if (!memory || !out || !ap_module_hpf_aligned(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_hpf_module_impl_t)) return AP_ENOMEM;
    if ((sample_rate_hz != 8000u && sample_rate_hz != 16000u) ||
        channels < 1u || channels > 2u) return AP_EINVAL;
    m = (ap_hpf_module_impl_t *)memory;
    ap_hpf_init(&m->state, sample_rate_hz, channels);
    *out = (ap_hpf_module_t *)m;
    return AP_OK;
}

ap_status_t ap_module_hpf_process(ap_hpf_module_t *module,
                                  float *samples, size_t frame_samples,
                                  uint32_t channel) {
    ap_hpf_module_impl_t *m = (ap_hpf_module_impl_t *)module;
    if (!m || !samples || frame_samples == 0u ||
        frame_samples > AP_INTERNAL_FRAME_MAX || channel >= m->state.channels)
        return AP_EINVAL;
    ap_hpf_process(&m->state, samples, (uint32_t)frame_samples, channel);
    return AP_OK;
}
