#include "aec/ap_aec.h"
#include <stdint.h>
#include <string.h>

void ap_aec_backend_init(ap_aec_state_t *state,
                         uint32_t frame_samples,
                         uint32_t taps,
                         uint32_t adapt_stride) {
    (void)frame_samples;
    memset(state, 0, sizeof(*state));
    state->taps = taps;
    state->active_taps = taps;
    state->active_adapt_stride = adapt_stride;
}

void ap_aec_backend_reset(ap_aec_state_t *state) {
    memset(state->history, 0, sizeof(state->history));
    memset(state->weights, 0, sizeof(state->weights));
    state->pos = 0u;
    state->adapt_phase = 0u;
}

void ap_aec_backend_set_active(ap_aec_state_t *state,
                               uint32_t active_taps,
                               uint32_t adapt_stride) {
    if (active_taps > state->taps) active_taps = state->taps;
    state->active_taps = active_taps;
    state->active_adapt_stride = adapt_stride;
    if (state->adapt_phase >= adapt_stride) state->adapt_phase = 0u;
}

void ap_aec_backend_process(ap_aec_state_t *state,
                            int enabled,
                            float mu,
                            uint32_t frame_samples,
                            const float *mic,
                            const float *ref,
                            float *out,
                            float *echo_out,
                            int far_end_active,
                            int double_talk_active,
                            ap_aec_result_t *result) {
    uint32_t i;
    float echo_energy = 1.0e-12f;
    const uint32_t taps = state->active_taps;
    const uint32_t woff = state->taps - taps;
    float *w = state->weights + woff;

    result->echo_energy = 0.0f;
    if (!enabled || taps == 0u) {
        memcpy(out, mic, frame_samples * sizeof(float));
        memset(echo_out, 0, frame_samples * sizeof(float));
        return;
    }
    for (i = 0u; i < frame_samples; ++i) {
        const float x = ref[i];
        const uint32_t pos = state->pos;
        const float *hist;
        float y, e;
        state->history[pos] = x;
        state->history[pos + AP_AEC_CAP] = x;
        hist = state->history + pos + AP_AEC_CAP - taps + 1u;
        y = ap_kernel_dot_f32(w, hist, taps);
        e = mic[i] - y;
        echo_out[i] = y;
        out[i] = e;
        echo_energy += y * y;
        if (far_end_active && !double_talk_active) {
            state->adapt_phase++;
            if (state->adapt_phase >= state->active_adapt_stride) {
                const float norm = 1.0e-6f + ap_kernel_dot_f32(hist, hist, taps);
                const float step = mu * e / norm;
                state->adapt_phase = 0u;
                ap_kernel_nlms_update(w, hist, step, taps);
            }
        }
        state->pos = pos + 1u == AP_AEC_CAP ? 0u : pos + 1u;
    }
    result->echo_energy = echo_energy / (float)frame_samples;
}

void ap_aec_backend_get_status(const ap_aec_state_t *state,
                               ap_aec_status_t *status) {
    status->kind = AP_AEC_KIND_NLMS;
    status->active_taps = state->active_taps;
    status->active_adapt_stride = state->active_adapt_stride;
    status->active_partitions = 0u;
    status->block_samples = 1u;
}
