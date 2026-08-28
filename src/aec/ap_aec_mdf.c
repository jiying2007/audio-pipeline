#include "aec/ap_aec.h"
#include <stdint.h>
#include <string.h>

static void ap_mdf_make_hermitian(ap_complex_t *x, uint32_t nfft, uint32_t bins) {
    uint32_t k;
    x[0].im = 0.0f;
    if ((nfft & 1u) == 0u) x[nfft / 2u].im = 0.0f;
    for (k = 1u; k + 1u < bins; ++k) {
        x[nfft - k].re = x[k].re;
        x[nfft - k].im = -x[k].im;
    }
}

static uint32_t ap_aec_steady_stride(uint32_t configured) {
    return configured < AP_AEC_STEADY_MIN_STRIDE ?
           AP_AEC_STEADY_MIN_STRIDE : configured;
}

static void ap_aec_update_runtime_stride(ap_aec_state_t *state,
                                         int far_end_active,
                                         int double_talk_active) {
    if (far_end_active && !double_talk_active) {
        if (state->steady_frames < AP_AEC_STEADY_FRAMES)
            state->steady_frames++;
        if (state->steady_frames >= AP_AEC_STEADY_FRAMES)
            state->runtime_adapt_stride =
                ap_aec_steady_stride(state->active_adapt_stride);
    } else {
        state->steady_frames = 0u;
        state->runtime_adapt_stride = state->active_adapt_stride;
    }
}

static void ap_mdf_constrain(ap_aec_state_t *state, uint32_t partition) {
    ap_mdf_state_t *s = &state->backend;
    uint32_t i;
    if (partition >= s->active_partitions) return;
    memcpy(s->acc, s->weights[partition], s->bins * sizeof(s->acc[0]));
    ap_mdf_make_hermitian(s->acc, s->nfft, s->bins);
    ap_fft(s->acc, s->nfft, 1);
    for (i = s->block; i < s->nfft; ++i) {
        s->acc[i].re = 0.0f;
        s->acc[i].im = 0.0f;
    }
    ap_fft(s->acc, s->nfft, 0);
    memcpy(s->weights[partition], s->acc, s->bins * sizeof(s->acc[0]));
}

static void ap_mdf_rebuild_power_sum(ap_mdf_state_t *s) {
    uint32_t part, k, xi;
    float total = 0.0f;
    memset(s->x_power_sum, 0, sizeof(s->x_power_sum));
    if (s->partitions == 0u || s->active_partitions == 0u) {
        s->x_power_total = 0.0f;
        return;
    }
    xi = s->x_head;
    for (part = 0u; part < s->active_partitions; ++part) {
        for (k = 0u; k < s->bins; ++k) {
            const float xr = s->x_history[xi][k].re;
            const float xi_im = s->x_history[xi][k].im;
            s->x_power_sum[k] += xr * xr + xi_im * xi_im;
        }
        xi = xi ? xi - 1u : s->partitions - 1u;
    }
    for (k = 0u; k < s->bins; ++k) total += s->x_power_sum[k];
    s->x_power_total = total;
}

static void ap_mdf_push_render_spectrum(ap_mdf_state_t *s) {
    uint32_t leaving, k;
    float total = 0.0f;
    ap_complex_t *dst;
    s->x_head++;
    if (s->x_head == s->partitions) s->x_head = 0u;
    if (s->x_head >= s->active_partitions)
        leaving = s->x_head - s->active_partitions;
    else
        leaving = s->partitions - (s->active_partitions - s->x_head);
    dst = s->x_history[s->x_head];
    for (k = 0u; k < s->bins; ++k) {
        const float old_re = s->x_history[leaving][k].re;
        const float old_im = s->x_history[leaving][k].im;
        const float new_re = s->fft[k].re;
        const float new_im = s->fft[k].im;
        float power = s->x_power_sum[k] +
                      new_re * new_re + new_im * new_im -
                      old_re * old_re - old_im * old_im;
        if (power < 0.0f) power = 0.0f;
        s->x_power_sum[k] = power;
        total += power;
        dst[k].re = new_re;
        dst[k].im = new_im;
    }
    s->x_power_total = total;
}

static void ap_mdf_set_active(ap_aec_state_t *state) {
    ap_mdf_state_t *s = &state->backend;
    uint32_t parts;
    if (s->block == 0u) return;
    parts = (state->active_taps + s->block - 1u) / s->block;
    if (parts < 1u) parts = 1u;
    if (parts > s->partitions) parts = s->partitions;
    s->active_partitions = parts;
    if (s->constrain_partition >= parts) s->constrain_partition = 0u;
    if (s->adapt_phase >= state->runtime_adapt_stride) s->adapt_phase = 0u;
    ap_mdf_rebuild_power_sum(s);
}

void ap_aec_backend_init(ap_aec_state_t *state,
                         uint32_t frame_samples,
                         uint32_t taps,
                         uint32_t adapt_stride) {
    ap_mdf_state_t *s;
    memset(state, 0, sizeof(*state));
    state->taps = taps;
    state->active_taps = taps;
    state->active_adapt_stride = adapt_stride;
    state->runtime_adapt_stride = adapt_stride;
    s = &state->backend;
    s->block = frame_samples / AP_AEC_SUBBLOCKS_PER_FRAME;
    s->nfft = s->block * 2u;
    s->bins = s->nfft / 2u + 1u;
    s->partitions = (taps + s->block - 1u) / s->block;
    if (s->partitions < 1u) s->partitions = 1u;
    if (s->partitions > AP_AEC_PARTITIONS_MAX) s->partitions = AP_AEC_PARTITIONS_MAX;
    s->x_head = s->partitions - 1u;
    ap_mdf_set_active(state);
}

void ap_aec_backend_reset(ap_aec_state_t *state) {
    ap_mdf_state_t *s = &state->backend;
    const uint32_t block = s->block;
    const uint32_t nfft = s->nfft;
    const uint32_t bins = s->bins;
    const uint32_t partitions = s->partitions;
    const uint32_t active_partitions = s->active_partitions;
    memset(s, 0, sizeof(*s));
    s->block = block;
    s->nfft = nfft;
    s->bins = bins;
    s->partitions = partitions;
    s->active_partitions = active_partitions;
    s->x_head = partitions ? partitions - 1u : 0u;
    state->steady_frames = 0u;
    state->runtime_adapt_stride = state->active_adapt_stride;
}

void ap_aec_backend_set_active(ap_aec_state_t *state,
                               uint32_t active_taps,
                               uint32_t adapt_stride) {
    if (active_taps > state->taps) active_taps = state->taps;
    state->active_taps = active_taps;
    state->active_adapt_stride = adapt_stride;
    state->runtime_adapt_stride = adapt_stride;
    state->steady_frames = 0u;
    ap_mdf_set_active(state);
}

static void ap_mdf_adapt(ap_aec_state_t *state,
                         const float *error,
                         float mu) {
    ap_mdf_state_t *s = &state->backend;
    uint32_t k, part, xi;
    for (k = 0u; k < s->block; ++k) {
        s->fft[k].re = 0.0f;
        s->fft[k].im = 0.0f;
        s->fft[s->block + k].re = error[k];
        s->fft[s->block + k].im = 0.0f;
    }
    ap_fft(s->fft, s->nfft, 0);
    for (k = 0u; k < s->bins; ++k) {
        const float scale = mu / (1.0e-5f + s->x_power_sum[k]);
        s->acc[k].re = s->fft[k].re * scale;
        s->acc[k].im = s->fft[k].im * scale;
    }
    xi = s->x_head;
    for (part = 0u; part < s->active_partitions; ++part) {
        ap_kernel_complex_adapt(s->weights[part], s->x_history[xi], s->acc, s->bins);
        xi = xi ? xi - 1u : s->partitions - 1u;
    }
    if (s->active_partitions > 0u) {
        ap_mdf_constrain(state, s->constrain_partition);
        if (++s->constrain_partition == s->active_partitions)
            s->constrain_partition = 0u;
    }
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
    ap_mdf_state_t *s = &state->backend;
    float echo_energy = 1.0e-12f;
    uint32_t off;

    result->echo_energy = 0.0f;
    if (!enabled || state->active_taps == 0u) {
        memcpy(out, mic, frame_samples * sizeof(float));
        memset(echo_out, 0, frame_samples * sizeof(float));
        return;
    }

    ap_aec_update_runtime_stride(state, far_end_active, double_talk_active);
    if (s->adapt_phase >= state->runtime_adapt_stride) s->adapt_phase = 0u;

    for (off = 0u; off < frame_samples; off += s->block) {
        float error[AP_AEC_BLOCK_MAX];
        uint32_t i, part, xi;
        int zero_reference_block = 1;
        int adapt_due;
        int do_adapt;
        for (i = 0u; i < s->block; ++i) {
            const float prev = s->prev_ref[i];
            const float cur = ref[off + i];
            if (prev != 0.0f || cur != 0.0f) zero_reference_block = 0;
            s->fft[i].re = prev;
            s->fft[i].im = 0.0f;
            s->fft[s->block + i].re = cur;
            s->fft[s->block + i].im = 0.0f;
            s->prev_ref[i] = cur;
        }
        if (zero_reference_block)
            memset(s->fft, 0, s->bins * sizeof(s->fft[0]));
        else
            ap_fft(s->fft, s->nfft, 0);
        ap_mdf_push_render_spectrum(s);

        s->adapt_phase++;
        adapt_due = s->adapt_phase >= state->runtime_adapt_stride;
        if (adapt_due) s->adapt_phase = 0u;
        do_adapt = adapt_due && s->x_power_total > 1.0e-20f &&
                   far_end_active && !double_talk_active;

        if (s->x_power_total <= 1.0e-20f) {
            for (i = 0u; i < s->block; ++i) {
                out[off + i] = mic[off + i];
                echo_out[off + i] = 0.0f;
            }
        } else {
            memset(s->acc, 0, s->bins * sizeof(s->acc[0]));
            xi = s->x_head;
            for (part = 0u; part < s->active_partitions; ++part) {
                ap_kernel_complex_mac(s->acc, s->weights[part],
                                      s->x_history[xi], s->bins);
                xi = xi ? xi - 1u : s->partitions - 1u;
            }
            ap_mdf_make_hermitian(s->acc, s->nfft, s->bins);
            ap_fft(s->acc, s->nfft, 1);
            for (i = 0u; i < s->block; ++i) {
                const float y = s->acc[s->block + i].re;
                const float e = mic[off + i] - y;
                echo_out[off + i] = y;
                out[off + i] = e;
                if (do_adapt) error[i] = e;
                echo_energy += y * y;
            }
        }
        if (do_adapt) ap_mdf_adapt(state, error, mu);
    }
    result->echo_energy = echo_energy / (float)frame_samples;
}

void ap_aec_backend_get_status(const ap_aec_state_t *state,
                               ap_aec_status_t *status) {
    const ap_mdf_state_t *s = &state->backend;
    status->kind = AP_AEC_KIND_MDF;
    status->active_taps = state->active_taps;
    status->active_adapt_stride = state->runtime_adapt_stride;
    status->active_partitions = s->active_partitions;
    status->block_samples = s->block;
}
