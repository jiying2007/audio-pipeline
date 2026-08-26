#include "ap_internal.h"
#include <math.h>

float ap_clampf(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

float ap_rms_dbfs(const float *x, uint32_t n) {
    double e = 1.0e-18;
    uint32_t i;
    for (i = 0; i < n; ++i) {
        e += (double)x[i] * (double)x[i];
    }
    e /= n ? n : 1u;
    return 10.0f * log10f((float)e);
}

void ap_fft(ap_complex_t *x, uint32_t n, int inverse) {
    uint32_t i, j, len;
    for (i = 1u, j = 0u; i < n; ++i) {
        uint32_t bit = n >> 1u;
        for (; j & bit; bit >>= 1u) {
            j ^= bit;
        }
        j ^= bit;
        if (i < j) {
            ap_complex_t t = x[i];
            x[i] = x[j];
            x[j] = t;
        }
    }

    for (len = 2u; len <= n; len <<= 1u) {
        const float angle = (inverse ? 2.0f : -2.0f) * AP_PI / (float)len;
        const float wr_step = cosf(angle);
        const float wi_step = sinf(angle);
        uint32_t base;
        for (base = 0u; base < n; base += len) {
            float wr = 1.0f;
            float wi = 0.0f;
            const uint32_t half = len >> 1u;
            uint32_t k;
            for (k = 0u; k < half; ++k) {
                const ap_complex_t u = x[base + k];
                const ap_complex_t v0 = x[base + k + half];
                ap_complex_t v;
                const float next_wr = wr * wr_step - wi * wi_step;
                const float next_wi = wr * wi_step + wi * wr_step;
                v.re = v0.re * wr - v0.im * wi;
                v.im = v0.re * wi + v0.im * wr;
                x[base + k].re = u.re + v.re;
                x[base + k].im = u.im + v.im;
                x[base + k + half].re = u.re - v.re;
                x[base + k + half].im = u.im - v.im;
                wr = next_wr;
                wi = next_wi;
            }
        }
    }

    if (inverse) {
        const float s = 1.0f / (float)n;
        for (i = 0u; i < n; ++i) {
            x[i].re *= s;
            x[i].im *= s;
        }
    }
}
