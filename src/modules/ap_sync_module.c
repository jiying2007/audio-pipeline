#include "audio_pipeline/audio_modules.h"
#include "sync/ap_sync.h"
#include "ap_limits.h"
#include <stdint.h>

typedef struct ap_sync_module_impl {
    ap_sync_state_t state;
} ap_sync_module_impl_t;

static int ap_module_sync_aligned(const void *p) {
    return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u;
}

size_t ap_module_sync_state_size(void) { return sizeof(ap_sync_module_impl_t); }

ap_status_t ap_module_sync_init(void *memory, size_t memory_size,
                                uint32_t initial_delay_samples,
                                ap_sync_module_t **out) {
    ap_sync_module_impl_t *m;
    if (!memory || !out || !ap_module_sync_aligned(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_sync_module_impl_t)) return AP_ENOMEM;
    if (initial_delay_samples >= AP_RENDER_CAP) return AP_EINVAL;
    m = (ap_sync_module_impl_t *)memory;
    ap_sync_init(&m->state, initial_delay_samples);
    *out = (ap_sync_module_t *)m;
    return AP_OK;
}

ap_status_t ap_module_sync_push_render(ap_sync_module_t *module,
                                       const float *render, size_t samples,
                                       uint64_t processed_frames) {
    ap_sync_module_impl_t *m = (ap_sync_module_impl_t *)module;
    if (!m || !render || samples == 0u || samples > AP_INTERNAL_FRAME_MAX)
        return AP_EINVAL;
    ap_sync_push_render(&m->state, render, (uint32_t)samples, processed_frames);
    return AP_OK;
}

ap_status_t ap_module_sync_track(ap_sync_module_t *module,
                                 const float *mic, size_t frame_samples,
                                 uint32_t sample_rate_hz,
                                 uint32_t max_delay_ms,
                                 int enable_delay_tracking,
                                 int enable_clock_drift_compensation,
                                 ap_module_sync_event_t *event) {
    ap_sync_module_impl_t *m = (ap_sync_module_impl_t *)module;
    ap_sync_event_t internal;
    if (!m || !mic || !event || frame_samples == 0u ||
        frame_samples > AP_INTERNAL_FRAME_MAX ||
        (sample_rate_hz != 8000u && sample_rate_hz != 16000u) ||
        max_delay_ms > 300u) return AP_EINVAL;
    ap_sync_track_delay(&m->state, mic, (uint32_t)frame_samples,
                        sample_rate_hz, max_delay_ms, enable_delay_tracking,
                        enable_clock_drift_compensation, &internal);
    event->delay_error_samples = internal.delay_error_samples;
    event->reference_sample_slips = internal.reference_sample_slips;
    event->delay_observed = internal.delay_observed;
    event->route_jump = internal.route_jump;
    return AP_OK;
}

ap_status_t ap_module_sync_get_reference(ap_sync_module_t *module,
                                         size_t frame_samples,
                                         float *output,
                                         int *underrun) {
    ap_sync_module_impl_t *m = (ap_sync_module_impl_t *)module;
    if (!m || !output || !underrun || frame_samples == 0u ||
        frame_samples > AP_INTERNAL_FRAME_MAX) return AP_EINVAL;
    *underrun = ap_sync_get_reference(&m->state, (uint32_t)frame_samples, output);
    return AP_OK;
}

void ap_module_sync_get_status(const ap_sync_module_t *module,
                               ap_module_sync_status_t *status) {
    const ap_sync_module_impl_t *m = (const ap_sync_module_impl_t *)module;
    ap_sync_status_t internal;
    if (!m || !status) return;
    ap_sync_get_status(&m->state, &internal);
    status->estimated_drift_ppm = internal.estimated_drift_ppm;
    status->delay_samples = internal.delay_samples;
}
