#include "arch/ap_kernels.h"
#include <arm_neon.h>
#include <stdint.h>

float ap_kernel_dot_f32(const float *a, const float *b, uint32_t n) {
    float s = 0.0f;
    uint32_t i = 0u;
    float32x4_t acc = vdupq_n_f32(0.0f);
    for (; i + 4u <= n; i += 4u)
        acc = vmlaq_f32(acc, vld1q_f32(a + i), vld1q_f32(b + i));
    {
        float tmp[4];
        vst1q_f32(tmp, acc);
        s = tmp[0] + tmp[1] + tmp[2] + tmp[3];
    }
    for (; i < n; ++i) s += a[i] * b[i];
    return s;
}

void ap_kernel_complex_mac(ap_complex_t *acc,
                           const ap_complex_t *w,
                           const ap_complex_t *x,
                           uint32_t bins) {
    uint32_t k = 0u;
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
    for (; k < bins; ++k) {
        const float wr = w[k].re, wi = w[k].im;
        const float xr = x[k].re, xi = x[k].im;
        acc[k].re += wr * xr - wi * xi;
        acc[k].im += wr * xi + wi * xr;
    }
}

void ap_kernel_complex_adapt(ap_complex_t *w,
                             const ap_complex_t *x,
                             const ap_complex_t *g,
                             uint32_t bins) {
    uint32_t k = 0u;
    for (; k + 4u <= bins; k += 4u) {
        float32x4x2_t vw = vld2q_f32((const float *)(w + k));
        const float32x4x2_t vx = vld2q_f32((const float *)(x + k));
        const float32x4x2_t vg = vld2q_f32((const float *)(g + k));
        vw.val[0] = vmlaq_f32(vw.val[0], vx.val[0], vg.val[0]);
        vw.val[0] = vmlaq_f32(vw.val[0], vx.val[1], vg.val[1]);
        vw.val[1] = vmlaq_f32(vw.val[1], vx.val[0], vg.val[1]);
        vw.val[1] = vmlsq_f32(vw.val[1], vx.val[1], vg.val[0]);
        vst2q_f32((float *)(w + k), vw);
    }
    for (; k < bins; ++k) {
        const float xr = x[k].re, xi = x[k].im;
        const float gr = g[k].re, gi = g[k].im;
        w[k].re += xr * gr + xi * gi;
        w[k].im += xr * gi - xi * gr;
    }
}

void ap_kernel_nlms_update(float *w, const float *x, float step, uint32_t n) {
    uint32_t k = 0u;
    for (; k + 4u <= n; k += 4u) {
        float32x4_t vw = vld1q_f32(w + k);
        vw = vmlaq_n_f32(vw, vld1q_f32(x + k), step);
        vst1q_f32(w + k, vw);
    }
    for (; k < n; ++k) w[k] += step * x[k];
}
