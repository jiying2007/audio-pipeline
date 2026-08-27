#include "ap_internal.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define TEST_PI 3.14159265358979323846f

static void test_impulse_spectrum(uint32_t n) {
    ap_complex_t x[AP_NS_FFT_MAX];
    uint32_t k;
    memset(x, 0, sizeof(x));
    x[1].re = 1.0f;

    ap_fft(x, n, 0);
    for (k = 0u; k < n; ++k) {
        const float phase = 2.0f * TEST_PI * (float)k / (float)n;
        const float er = cosf(phase);
        const float ei = -sinf(phase);
        assert(fabsf(x[k].re - er) < 2.5e-5f);
        assert(fabsf(x[k].im - ei) < 2.5e-5f);
    }

    ap_fft(x, n, 1);
    for (k = 0u; k < n; ++k) {
        const float er = k == 1u ? 1.0f : 0.0f;
        assert(fabsf(x[k].re - er) < 2.5e-5f);
        assert(fabsf(x[k].im) < 2.5e-5f);
    }
}

static void test_round_trip(uint32_t n) {
    ap_complex_t x[AP_NS_FFT_MAX];
    ap_complex_t original[AP_NS_FFT_MAX];
    uint32_t i;
    for (i = 0u; i < n; ++i) {
        const float t = (float)i / (float)n;
        x[i].re = 0.31f * sinf(2.0f * TEST_PI * 3.0f * t) +
                  0.17f * cosf(2.0f * TEST_PI * 7.0f * t) +
                  (float)((int)(i % 11u) - 5) * 0.003f;
        x[i].im = 0.09f * cosf(2.0f * TEST_PI * 5.0f * t);
    }
    memcpy(original, x, n * sizeof(x[0]));

    ap_fft(x, n, 0);
    ap_fft(x, n, 1);
    for (i = 0u; i < n; ++i) {
        assert(fabsf(x[i].re - original[i].re) < 3.0e-5f);
        assert(fabsf(x[i].im - original[i].im) < 3.0e-5f);
    }
}

int main(void) {
    static const uint32_t sizes[] = {32u, 64u, 256u, 512u};
    uint32_t i;
    for (i = 0u; i < sizeof(sizes) / sizeof(sizes[0]); ++i) {
        test_impulse_spectrum(sizes[i]);
        test_round_trip(sizes[i]);
    }
    puts("audio-pipeline FFT tests: OK");
    return 0;
}
