#include "audio_pipeline/audio_modules.h"
#include "aec/ap_aec.h"
#include "ap_numeric.h"
#include <stdint.h>
#include <string.h>

typedef struct ap_aec_module_impl {
    ap_aec_state_t state;
    float mu;
    uint32_t frame_samples;
} ap_aec_module_impl_t;

static int aligned16(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}
size_t ap_module_aec_state_size(void) { return sizeof(ap_aec_module_impl_t); }
ap_status_t ap_module_aec_init(void *memory, size_t memory_size,
                               const ap_module_aec_config_t *c,
                               ap_aec_module_t **out) {
    ap_aec_module_impl_t *m;
    uint32_t taps;
    if (!memory || !c || !out || !aligned16(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(*m)) return AP_ENOMEM;
    if ((c->sample_rate_hz != 8000u && c->sample_rate_hz != 16000u) ||
        c->sample_rate_hz > AP_BUILD_MAX_INTERNAL_RATE_HZ ||
        c->filter_ms < 20u || c->filter_ms > AP_BUILD_MAX_AEC_TAIL_MS ||
        c->adapt_stride == 0u || !isfinite(c->mu) ||
        !(c->mu > 0.0f && c->mu <= 1.0f))
        return AP_EINVAL;
    m = (ap_aec_module_impl_t *)memory;
    memset(m, 0, sizeof(*m));
    m->frame_samples = c->sample_rate_hz / 100u;
    m->mu = c->mu;
    taps = c->filter_ms * c->sample_rate_hz / 1000u;
    if (taps > AP_AEC_CAP) taps = AP_AEC_CAP;
    ap_aec_backend_init(&m->state, m->frame_samples, taps, c->adapt_stride);
    *out = (ap_aec_module_t *)m;
    return AP_OK;
}
void ap_module_aec_reset(ap_aec_module_t *module) {
    ap_aec_module_impl_t *m = (ap_aec_module_impl_t *)module;
    if (m) ap_aec_backend_reset(&m->state);
}
ap_status_t ap_module_aec_process(ap_aec_module_t *module,
                                  const float *mic, const float *reference,
                                  float *output, float *predicted_echo,
                                  size_t frame_samples, int far, int dt,
                                  ap_module_aec_result_t *result) {
    ap_aec_module_impl_t *m = (ap_aec_module_impl_t *)module;
    ap_aec_result_t ir;
    ap_aec_status_t s;
    if (!m || !mic || !reference || !output || !predicted_echo || !result ||
        frame_samples != m->frame_samples)
        return AP_EINVAL;
    ap_aec_backend_process(&m->state, 1, m->mu, m->frame_samples,
                           mic, reference, output, predicted_echo,
                           far, dt, &ir);
    ap_aec_backend_get_status(&m->state, &s);
    result->echo_energy = ir.echo_energy;
    result->active_taps = s.active_taps;
    result->active_partitions = s.active_partitions;
    result->block_samples = s.block_samples;
    result->backend = s.kind == AP_AEC_KIND_MDF ?
                      AP_AEC_BACKEND_MDF : AP_AEC_BACKEND_NLMS;
    return AP_OK;
}
