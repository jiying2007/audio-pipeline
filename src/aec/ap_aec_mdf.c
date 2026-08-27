#include "ap_internal.h"
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

static void ap_mdf_constrain(ap_pipeline_t *p, uint32_t partition) {
    ap_mdf_state_t *s = &p->mdf;
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

static void ap_mdf_set_active(ap_pipeline_t *p);

void ap_aec_backend_init(ap_pipeline_t *p) {
    ap_mdf_state_t *s = &p->mdf;
    memset(s, 0, sizeof(*s));
    s->block = p->internal_frame / AP_AEC_SUBBLOCKS_PER_FRAME;
    s->nfft = s->block * 2u;
    s->bins = s->nfft / 2u + 1u;
    s->partitions = (p->aec_taps + s->block - 1u) / s->block;
    if (s->partitions < 1u) s->partitions = 1u;
    if (s->partitions > AP_AEC_PARTITIONS_MAX) s->partitions = AP_AEC_PARTITIONS_MAX;
    s->x_head = s->partitions - 1u;
    ap_mdf_set_active(p);
    p->metrics.aec_backend = AP_AEC_BACKEND_MDF;
    p->metrics.aec_block_samples = s->block;
}

void ap_aec_backend_reset(ap_pipeline_t *p, int count_reset) {
    ap_mdf_state_t *s = &p->mdf;
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
    if (count_reset) p->metrics.aec_resets++;
}

static void ap_mdf_set_active(ap_pipeline_t *p) {
    ap_mdf_state_t *s = &p->mdf;
    uint32_t parts;
    if (s->block == 0u) return;
    parts = (p->active_aec_taps + s->block - 1u) / s->block;
    if (parts < 1u) parts = 1u;
    if (parts > s->partitions) parts = s->partitions;
    s->active_partitions = parts;
    if (s->constrain_partition >= parts) s->constrain_partition = 0u;
    if (s->adapt_phase >= p->active_aec_adapt_stride) s->adapt_phase = 0u;
    ap_mdf_rebuild_power_sum(s);
    p->metrics.active_aec_partitions = parts;
    p->metrics.aec_block_samples = s->block;
}

void ap_aec_backend_set_active(ap_pipeline_t *p) {
    ap_mdf_set_active(p);
}

static void ap_mdf_adapt(ap_pipeline_t *p, const float *error) {
    ap_mdf_state_t *s = &p->mdf;
    uint32_t k, part, xi;
    for (k = 0u; k < s->block; ++k) {
        s->fft[k].re = 0.0f;
        s->fft[k].im = 0.0f;
        s->fft[s->block + k].re = error[k];
        s->fft[s->block + k].im = 0.0f;
    }
    ap_fft(s->fft, s->nfft, 0);
    for (k = 0u; k < s->bins; ++k) {
        const float scale = p->cfg.aec_mu / (1.0e-5f + s->x_power_sum[k]);
        s->acc[k].re = s->fft[k].re * scale;
        s->acc[k].im = s->fft[k].im * scale;
    }
    xi = s->x_head;
    for (part = 0u; part < s->active_partitions; ++part) {
        ap_kernel_complex_adapt(s->weights[part], s->x_history[xi], s->acc, s->bins);
        xi = xi ? xi - 1u : s->partitions - 1u;
    }
    if (s->active_partitions > 0u) {
        ap_mdf_constrain(p, s->constrain_partition);
        if (++s->constrain_partition == s->active_partitions)
            s->constrain_partition = 0u;
    }
}

void ap_aec_backend_process(ap_pipeline_t *p,
                            const float *mic,
                            const float *ref,
                            float *out,
                            float *echo_out,
                            float mic_energy,
                            float ref_energy,
                            float *echo_energy_out) {
    ap_mdf_state_t *s = &p->mdf;
    const int far_active = ref_energy > 1.0e-7f;
    const int double_talk = far_active && mic_energy > ref_energy * 1.5f;
    float echo_energy = 1.0e-12f;
    uint32_t off;

    p->metrics.double_talk_active = (uint8_t)(double_talk ? 1u : 0u);
    if (!p->cfg.enable_aec || p->active_aec_taps == 0u) {
        memcpy(out, mic, p->internal_frame * sizeof(float));
        memset(echo_out, 0, p->internal_frame * sizeof(float));
        *echo_energy_out = 0.0f;
        return;
    }

    for (off = 0u; off < p->internal_frame; off += s->block) {
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
        adapt_due = s->adapt_phase >= p->active_aec_adapt_stride;
        if (adapt_due) s->adapt_phase = 0u;
        do_adapt = adapt_due && s->x_power_total > 1.0e-20f && far_active && !double_talk;

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
        if (do_adapt) ap_mdf_adapt(p, error);
    }
    *echo_energy_out = echo_energy / (float)p->internal_frame;
}
