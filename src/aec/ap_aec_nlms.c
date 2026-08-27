#include "ap_internal.h"
#include <stdint.h>
#include <string.h>

void ap_aec_backend_init(ap_pipeline_t *p) {
    memset(p->aec_history, 0, sizeof(p->aec_history));
    memset(p->aec_weights, 0, sizeof(p->aec_weights));
    p->aec_pos = 0u;
    p->aec_adapt_phase = 0u;
    p->metrics.aec_backend = AP_AEC_BACKEND_NLMS;
    p->metrics.aec_block_samples = 1u;
    p->metrics.active_aec_partitions = 0u;
}

void ap_aec_backend_reset(ap_pipeline_t *p, int count_reset) {
    memset(p->aec_history, 0, sizeof(p->aec_history));
    memset(p->aec_weights, 0, sizeof(p->aec_weights));
    p->aec_pos = 0u;
    p->aec_adapt_phase = 0u;
    if (count_reset) p->metrics.aec_resets++;
}

void ap_aec_backend_set_active(ap_pipeline_t *p) {
    if (p->aec_adapt_phase >= p->active_aec_adapt_stride) p->aec_adapt_phase = 0u;
    p->metrics.active_aec_partitions = 0u;
    p->metrics.aec_block_samples = 1u;
}

void ap_aec_backend_process(ap_pipeline_t *p,
                            const float *mic,
                            const float *ref,
                            float *out,
                            float *echo_out,
                            float mic_energy,
                            float ref_energy,
                            float *echo_energy_out) {
    uint32_t i;
    float echo_energy = 1.0e-12f;
    const int far_active = ref_energy > 1.0e-7f;
    const int double_talk = far_active && mic_energy > ref_energy * 1.5f;
    const uint32_t taps = p->active_aec_taps;
    const uint32_t woff = p->aec_taps - taps;
    float *w = p->aec_weights + woff;
    p->metrics.double_talk_active = (uint8_t)(double_talk ? 1u : 0u);
    if (!p->cfg.enable_aec || taps == 0u) {
        memcpy(out, mic, p->internal_frame * sizeof(float));
        memset(echo_out, 0, p->internal_frame * sizeof(float));
        *echo_energy_out = 0.0f;
        return;
    }
    for (i = 0u; i < p->internal_frame; ++i) {
        const float x = ref[i];
        const uint32_t pos = p->aec_pos;
        const float *hist;
        float y, e;
        p->aec_history[pos] = x;
        p->aec_history[pos + AP_AEC_CAP] = x;
        hist = p->aec_history + pos + AP_AEC_CAP - taps + 1u;
        y = ap_kernel_dot_f32(w, hist, taps);
        e = mic[i] - y;
        echo_out[i] = y;
        out[i] = e;
        echo_energy += y * y;
        if (far_active && !double_talk) {
            p->aec_adapt_phase++;
            if (p->aec_adapt_phase >= p->active_aec_adapt_stride) {
                const float norm = 1.0e-6f + ap_kernel_dot_f32(hist, hist, taps);
                const float step = p->cfg.aec_mu * e / norm;
                p->aec_adapt_phase = 0u;
                ap_kernel_nlms_update(w, hist, step, taps);
            }
        }
        p->aec_pos = pos + 1u == AP_AEC_CAP ? 0u : pos + 1u;
    }
    *echo_energy_out = echo_energy / (float)p->internal_frame;
}
