#include "ap_internal.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(AP_ENABLE_NEON) && (defined(__ARM_NEON) || defined(__ARM_NEON__))
#include <arm_neon.h>
#define AP_MDF_HAVE_NEON 1
#else
#define AP_MDF_HAVE_NEON 0
#endif

static void ap_mdf_make_hermitian(ap_complex_t *x, uint32_t nfft, uint32_t bins) {
    uint32_t k;
    x[0].im = 0.0f;
    if ((nfft & 1u) == 0u) x[nfft / 2u].im = 0.0f;
    for (k = 1u; k + 1u < bins; ++k) {
        x[nfft - k].re = x[k].re;
        x[nfft - k].im = -x[k].im;
    }
}

static void ap_mdf_complex_mac(ap_complex_t *acc,
                               const ap_complex_t *w,
                               const ap_complex_t *x,
                               uint32_t bins) {
    uint32_t k = 0u;
#if AP_MDF_HAVE_NEON
    for (; k + 4u <= bins; k += 4u) {
        float32x4x2_t va = vld2q_f32((const float *)(acc + k));
        const float32x4x2_t vw = vld2q_f32((const float *)(w + k));
        const float32x4x2_t vx = vld2q_f32((const float *)(x + k));
        va.val[0] = vmlaq_f32(va.val[0], vw.val[0], vx.val[0]);
        va.val[0] = vmlsq_f32(va.val[0], vw.val[1], vx.val[1]);
        va.val[1] = vmlaq_f32(va.val[1], vw.val[0], vx.val[1]);
        va.val[1] = vmlaq_f32(va.val[1], vw.val[1], vx.val[0]);
        vst2q_f32((float *)(acc + k), va);
    }
#endif
    for (; k < bins; ++k) {
        const float wr = w[k].re;
        const float wi = w[k].im;
        const float xr = x[k].re;
        const float xi = x[k].im;
        acc[k].re += wr * xr - wi * xi;
        acc[k].im += wr * xi + wi * xr;
    }
}

static void ap_mdf_constrain(ap_pipeline_t *p, uint32_t partition) {
    ap_mdf_state_t *s = &p->mdf;
    uint32_t i;
    if (partition >= s->active_partitions) return;
    memset(s->acc, 0, s->nfft * sizeof(s->acc[0]));
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

void ap_mdf_init(ap_pipeline_t *p) {
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

void ap_mdf_reset(ap_pipeline_t *p, int count_reset) {
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

void ap_mdf_set_active(ap_pipeline_t *p) {
    ap_mdf_state_t *s = &p->mdf;
    uint32_t parts;
    if (s->block == 0u) return;
    parts = (p->active_aec_taps + s->block - 1u) / s->block;
    if (parts < 1u) parts = 1u;
    if (parts > s->partitions) parts = s->partitions;
    s->active_partitions = parts;
    p->metrics.active_aec_partitions = parts;
    p->metrics.aec_block_samples = s->block;
}

static void ap_mdf_adapt(ap_pipeline_t *p, const float *error) {
    ap_mdf_state_t *s = &p->mdf;
    uint32_t k, part;
    memset(s->fft, 0, s->nfft * sizeof(s->fft[0]));
    for (k = 0u; k < s->block; ++k) s->fft[s->block + k].re = error[k];
    ap_fft(s->fft, s->nfft, 0);

    for (k = 0u; k < s->bins; ++k) {
        float denom = 1.0e-5f;
        for (part = 0u; part < s->active_partitions; ++part) {
            const uint32_t xi = (s->x_head + s->partitions - part) % s->partitions;
            const float xr = s->x_history[xi][k].re;
            const float xi_im = s->x_history[xi][k].im;
            denom += xr * xr + xi_im * xi_im;
        }
        {
            const float scale = p->cfg.aec_mu / denom;
            const float er = s->fft[k].re;
            const float ei = s->fft[k].im;
            for (part = 0u; part < s->active_partitions; ++part) {
                const uint32_t xi = (s->x_head + s->partitions - part) % s->partitions;
                const float xr = s->x_history[xi][k].re;
                const float xi_im = s->x_history[xi][k].im;
                s->weights[part][k].re += scale * (xr * er + xi_im * ei);
                s->weights[part][k].im += scale * (xr * ei - xi_im * er);
            }
        }
    }

    if (s->active_partitions > 0u) {
        ap_mdf_constrain(p, s->constrain_partition % s->active_partitions);
        s->constrain_partition++;
    }
}

void ap_mdf_process(ap_pipeline_t *p,
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
    double echo_energy = 1.0e-12;
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
        uint32_t i, part;
        memset(s->fft, 0, s->nfft * sizeof(s->fft[0]));
        for (i = 0u; i < s->block; ++i) {
            s->fft[i].re = s->prev_ref[i];
            s->fft[s->block + i].re = ref[off + i];
            s->prev_ref[i] = ref[off + i];
        }
        ap_fft(s->fft, s->nfft, 0);

        s->x_head = (s->x_head + 1u) % s->partitions;
        memcpy(s->x_history[s->x_head], s->fft, s->bins * sizeof(s->fft[0]));

        memset(s->acc, 0, s->nfft * sizeof(s->acc[0]));
        for (part = 0u; part < s->active_partitions; ++part) {
            const uint32_t xi = (s->x_head + s->partitions - part) % s->partitions;
            ap_mdf_complex_mac(s->acc, s->weights[part], s->x_history[xi], s->bins);
        }
        ap_mdf_make_hermitian(s->acc, s->nfft, s->bins);
        ap_fft(s->acc, s->nfft, 1);

        for (i = 0u; i < s->block; ++i) {
            const float y = s->acc[s->block + i].re;
            const float e = mic[off + i] - y;
            echo_out[off + i] = y;
            out[off + i] = e;
            error[i] = e;
            echo_energy += (double)y * (double)y;
        }

        s->block_counter++;
        if (far_active && !double_talk &&
            (s->block_counter % p->active_aec_adapt_stride) == 0u) {
            ap_mdf_adapt(p, error);
        }
    }

    *echo_energy_out = (float)(echo_energy / (double)p->internal_frame);
}
