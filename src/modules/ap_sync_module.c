#include "audio_pipeline/audio_modules.h"
#include "sync/ap_sync.h"
#include "ap_limits.h"
#include <stdint.h>

typedef struct ap_sync_module_impl { ap_sync_state_t state; } ap_sync_module_impl_t;
static int aligned16(const void *p) { return ((uintptr_t)p & (AP_MODULE_STATE_ALIGNMENT - 1u)) == 0u; }
static void copy_event(ap_module_sync_event_t *out, const ap_sync_event_t *in) {
    out->delay_error_samples = in->delay_error_samples;
    out->reference_sample_slips = in->reference_sample_slips;
    out->delay_observed = in->delay_observed;
    out->route_jump = in->route_jump;
    out->timestamp_observed = in->timestamp_observed;
}
size_t ap_module_sync_state_size(void) { return sizeof(ap_sync_module_impl_t); }
ap_status_t ap_module_sync_init(void *memory, size_t memory_size,
                                uint32_t initial_delay_samples,
                                ap_sync_module_t **out) {
    ap_sync_module_impl_t *m;
    if (!memory || !out || !aligned16(memory)) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(*m)) return AP_ENOMEM;
    if (initial_delay_samples >= AP_RENDER_CAP) return AP_EINVAL;
    m = (ap_sync_module_impl_t *)memory;
    ap_sync_init(&m->state, initial_delay_samples);
    *out = (ap_sync_module_t *)m;
    return AP_OK;
}
void ap_module_sync_reset(ap_sync_module_t *module) {
    ap_sync_module_impl_t *m = (ap_sync_module_impl_t *)module;
    if (m) ap_sync_reset(&m->state);
}
ap_status_t ap_module_sync_push_render(ap_sync_module_t *module,
                                       const float *render, size_t samples,
                                       uint64_t frames) {
    ap_sync_module_impl_t *m = (ap_sync_module_impl_t *)module;
    if (!m || !render || samples == 0u || samples > AP_INTERNAL_FRAME_MAX)
        return AP_EINVAL;
    ap_sync_push_render(&m->state, render, (uint32_t)samples, frames);
    return AP_OK;
}
ap_status_t ap_module_sync_track(ap_sync_module_t *module,
                                 const float *mic, size_t frame_samples,
                                 uint32_t rate, uint32_t max_delay_ms,
                                 int delay, int drift,
                                 ap_module_sync_event_t *event) {
    ap_sync_module_impl_t *m = (ap_sync_module_impl_t *)module;
    ap_sync_event_t e;
    if (!m || !mic || !event ||
        (rate != 8000u && rate != 16000u) ||
        rate > AP_BUILD_MAX_INTERNAL_RATE_HZ ||
        frame_samples != rate / 100u ||
        max_delay_ms > AP_BUILD_MAX_DELAY_MS)
        return AP_EINVAL;
    ap_sync_track_delay(&m->state, mic, (uint32_t)frame_samples, rate,
                        max_delay_ms, delay, drift, &e);
    copy_event(event, &e);
    return AP_OK;
}
ap_status_t ap_module_sync_observe_timestamps(ap_sync_module_t *module,
                                              uint64_t capture_ns,
                                              uint64_t render_ns,
                                              uint32_t rate,
                                              uint32_t max_delay_ms,
                                              ap_module_sync_event_t *event) {
    ap_sync_module_impl_t *m = (ap_sync_module_impl_t *)module;
    ap_sync_event_t e;
    if (!m || !event || (rate != 8000u && rate != 16000u) ||
        rate > AP_BUILD_MAX_INTERNAL_RATE_HZ ||
        max_delay_ms > AP_BUILD_MAX_DELAY_MS)
        return AP_EINVAL;
    if (!ap_sync_observe_timestamps(&m->state, capture_ns, render_ns, rate,
                                    max_delay_ms, &e))
        return AP_EINVAL;
    copy_event(event, &e);
    return AP_OK;
}
ap_status_t ap_module_sync_get_reference(ap_sync_module_t *module,
                                         size_t frame_samples,
                                         float *output, int *underrun) {
    ap_sync_module_impl_t *m = (ap_sync_module_impl_t *)module;
    if (!m || !output || !underrun ||
        (frame_samples != 80u && frame_samples != 160u) ||
        frame_samples > AP_INTERNAL_FRAME_MAX)
        return AP_EINVAL;
    *underrun = ap_sync_get_reference(&m->state, (uint32_t)frame_samples, output);
    return AP_OK;
}
void ap_module_sync_get_status(const ap_sync_module_t *module,
                               ap_module_sync_status_t *status) {
    const ap_sync_module_impl_t *m = (const ap_sync_module_impl_t *)module;
    ap_sync_status_t s;
    if (!m || !status) return;
    ap_sync_get_status(&m->state, &s);
    status->estimated_drift_ppm = s.estimated_drift_ppm;
    status->delay_samples = s.delay_samples;
}
