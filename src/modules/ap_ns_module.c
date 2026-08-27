#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "ap_limits.h"
#include <stdint.h>
#include <string.h>

typedef struct ap_ns_module_impl {
    ap_ns_state_t state;
    float floor_gain;
    uint32_t frame_samples;
} ap_ns_module_impl_t;

static int ap_module_ns_aligned(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

static ap_enhance_mode_t ap_module_ns_mode(ap_quality_t q) {
    if (q == AP_QUALITY_FULL) return AP_ENHANCE_FULL;
    if (q == AP_QUALITY_LITE) return AP_ENHANCE_LITE;
    return AP_ENHANCE_SAFE;
}

size_t ap_module_ns_state_size(void) { return sizeof(ap_ns_module_impl_t); }

ap_status_t ap_module_ns_init(void *memory, size_t memory_size,
                              const ap_module_ns_config_t *config,
                              ap_ns_module_t **out) {
    ap_ns_module_impl_t *m;
    if (!memory || !config || !out || !ap_module_ns_aligned(memory))
        return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_ns_module_impl_t)) return AP_ENOMEM;
    if ((config->sample_rate_hz != 8000u && config->sample_rate_hz != 16000u) ||
        config->floor_gain < 0.02f || config->floor_gain > 1.0f)
        return AP_EINVAL;
    m = (ap_ns_module_impl_t *)memory;
    memset(m, 0, sizeof(*m));
    m->frame_samples = config->sample_rate_hz / 100u;
    m->floor_gain = config->floor_gain;
    ap_ns_init(&m->state, m->frame_samples);
    *out = (ap_ns_module_t *)m;
    return AP_OK;
}

ap_status_t ap_module_ns_process(ap_ns_module_t *module,
                                 ap_quality_t quality,
                                 const float *input,
                                 const float *predicted_echo,
                                 float *output,
                                 size_t frame_samples,
                                 int enable_frequency_res,
                                 int far_end_active,
                                 int double_talk_active,
                                 ap_module_ns_result_t *result) {
    ap_ns_module_impl_t *m = (ap_ns_module_impl_t *)module;
    ap_ns_result_t internal;
    if (!m || !input || !output || !result || frame_samples != m->frame_samples ||
        quality < AP_QUALITY_SAFE || quality > AP_QUALITY_FULL)
        return AP_EINVAL;
#if !AP_BUILD_STAGE_RES
    if (enable_frequency_res) return AP_ESTATE;
#else
    if (enable_frequency_res && !predicted_echo) return AP_EINVAL;
#endif
    ap_ns_process(&m->state, ap_module_ns_mode(quality), m->floor_gain,
                  input, predicted_echo, output, m->frame_samples,
                  enable_frequency_res, far_end_active, double_talk_active,
                  &internal);
    result->noise_rms_dbfs = internal.noise_rms_dbfs;
    result->speech_probability = internal.speech_probability;
    result->residual_echo_gain = internal.residual_echo_gain;
    result->frequency_res_active = internal.frequency_res_active;
    return AP_OK;
}
