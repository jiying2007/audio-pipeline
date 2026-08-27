#include "audio_pipeline/audio_modules.h"
#include "frontend/ap_frontend.h"
#include "ap_limits.h"
#include <stdint.h>

typedef struct ap_beamformer_module_impl { ap_beamformer_state_t state; } ap_beamformer_module_impl_t;

static int ap_module_bf_aligned(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

size_t ap_module_beamformer_state_size(void) { return sizeof(ap_beamformer_module_impl_t); }

ap_status_t ap_module_beamformer_init(void *memory, size_t memory_size,
                                      uint32_t sample_rate_hz,
                                      float mic_spacing_mm,
                                      ap_beamformer_module_t **out) {
    ap_beamformer_module_impl_t *m;
    if (!memory || !out || !ap_module_bf_aligned(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_beamformer_module_impl_t)) return AP_ENOMEM;
    if ((sample_rate_hz != 8000u && sample_rate_hz != 16000u) ||
        mic_spacing_mm < 0.0f || mic_spacing_mm > 200.0f) return AP_EINVAL;
    m = (ap_beamformer_module_impl_t *)memory;
    ap_beamformer_init(&m->state, sample_rate_hz, mic_spacing_mm);
    *out = (ap_beamformer_module_t *)m;
    return AP_OK;
}

ap_status_t ap_module_beamformer_process(ap_beamformer_module_t *module,
                                         int track_direction,
                                         float *mic0, float *mic1,
                                         float *output,
                                         size_t frame_samples) {
    ap_beamformer_module_impl_t *m = (ap_beamformer_module_impl_t *)module;
    if (!m || !mic0 || !mic1 || !output || frame_samples == 0u ||
        frame_samples > AP_INTERNAL_FRAME_MAX) return AP_EINVAL;
    ap_beamformer_process(&m->state, track_direction, mic0, mic1, output,
                          (uint32_t)frame_samples);
    return AP_OK;
}
