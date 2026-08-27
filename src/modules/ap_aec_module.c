#include "audio_pipeline/audio_modules.h"
#include "aec/ap_aec.h"
#include <stdint.h>
#include <string.h>

typedef struct ap_aec_module_impl {
    ap_aec_state_t state;
    float mu;
    uint32_t frame_samples;
} ap_aec_module_impl_t;

static int ap_module_aec_aligned(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

size_t ap_module_aec_state_size(void) { return sizeof(ap_aec_module_impl_t); }

ap_status_t ap_module_aec_init(void *memory, size_t memory_size,
                               const ap_module_aec_config_t *config,
                               ap_aec_module_t **out) {
    ap_aec_module_impl_t *m;
    uint32_t taps;
    if (!memory || !config || !out || !ap_module_aec_aligned(memory))
        return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_aec_module_impl_t)) return AP_ENOMEM;
    if ((config->sample_rate_hz != 8000u && config->sample_rate_hz != 16000u) ||
        config->filter_ms < 20u || config->filter_ms > 120u ||
        config->adapt_stride == 0u || config->mu <= 0.0f || config->mu > 1.0f)
        return AP_EINVAL;
    m = (ap_aec_module_impl_t *)memory;
    memset(m, 0, sizeof(*m));
    m->frame_samples = config->sample_rate_hz / 100u;
    m->mu = config->mu;
    taps = config->filter_ms * config->sample_rate_hz / 1000u;
    if (taps > AP_AEC_CAP) taps = AP_AEC_CAP;
    ap_aec_backend_init(&m->state, m->frame_samples, taps, config->adapt_stride);
    *out = (ap_aec_module_t *)m;
    return AP_OK;
}

void ap_module_aec_reset(ap_aec_module_t *module) {
    ap_aec_module_impl_t *m = (ap_aec_module_impl_t *)module;
    if (m) ap_aec_backend_reset(&m->state);
}

ap_status_t ap_module_aec_process(ap_aec_module_t *module,
                                  const float *mic,
                                  const float *reference,
                                  float *output,
                                  float *predicted_echo,
                                  size_t frame_samples,
                                  int far_end_active,
                                  int double_talk_active,
                                  ap_module_aec_result_t *result) {
    ap_aec_module_impl_t *m = (ap_aec_module_impl_t *)module;
    ap_aec_result_t internal_result;
    ap_aec_status_t status;
    if (!m || !mic || !reference || !output || !predicted_echo || !result ||
        frame_samples != m->frame_samples) return AP_EINVAL;
    ap_aec_backend_process(&m->state, 1, m->mu, m->frame_samples,
                           mic, reference, output, predicted_echo,
                           far_end_active, double_talk_active, &internal_result);
    ap_aec_backend_get_status(&m->state, &status);
    result->echo_energy = internal_result.echo_energy;
    result->active_taps = status.active_taps;
    result->active_partitions = status.active_partitions;
    result->block_samples = status.block_samples;
    result->backend = status.kind == AP_AEC_KIND_MDF ?
                      AP_AEC_BACKEND_MDF : AP_AEC_BACKEND_NLMS;
    return AP_OK;
}
