#include "arch/ap_kernels.h"
#include <stdint.h>

float ap_kernel_dot_f32(const float *a, const float *b, uint32_t n) {
    float s = 0.0f;
    uint32_t i;
    for (i = 0u; i < n; ++i) s += a[i] * b[i];
    return s;
}

void ap_kernel_complex_mac(ap_complex_t *acc,
                           const ap_complex_t *w,
                           const ap_complex_t *x,
                           uint32_t bins) {
    uint32_t k;
    for (k = 0u; k < bins; ++k) {
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
    uint32_t k;
    for (k = 0u; k < bins; ++k) {
        const float xr = x[k].re, xi = x[k].im;
        const float gr = g[k].re, gi = g[k].im;
        w[k].re += xr * gr + xi * gi;
        w[k].im += xr * gi - xi * gr;
    }
}

void ap_kernel_nlms_update(float *w, const float *x, float step, uint32_t n) {
    uint32_t k;
    for (k = 0u; k < n; ++k) w[k] += step * x[k];
}
