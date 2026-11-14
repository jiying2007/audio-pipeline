#include "enhance/ap_noise_tracker.h"
#include "enhance/ap_window.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

#define TEST_PI 3.14159265358979323846f

static float run_power(ap_noise_tracker_state_t *s, float power, unsigned frames) {
    ap_noise_tracker_result_t r = {0};
    unsigned i;
    for (i = 0u; i < frames; ++i) {
        ap_noise_tracker_update(s, 10u, power, &r);
        assert(isfinite(r.noise));
        assert(isfinite(r.speech_probability));
        assert(r.noise >= 0.0f);
        assert(r.speech_probability >= 0.0f && r.speech_probability <= 1.0f);
        ap_noise_tracker_next_frame(s);
    }
    return r.noise;
}

static void test_static_windows(void) {
    static const unsigned frames[] = {80u, 160u};
    unsigned fi;
    for (fi = 0u; fi < sizeof(frames) / sizeof(frames[0]); ++fi) {
        const unsigned f = frames[fi];
        const float *w = ap_window_half(f);
        unsigned i;
        assert(w != NULL);
        for (i = 0u; i < f; ++i) {
            const float expected = sinf(TEST_PI * ((float)i + 0.5f) / (2.0f * (float)f));
            assert(fabsf(w[i] - expected) < 2.0e-6f);
        }
    }
    assert(ap_window_half(120u) == NULL);
}

int main(void) {
    ap_noise_tracker_state_t state;
    float noise;
    test_static_windows();
    ap_noise_tracker_init(&state);

    noise = run_power(&state, 0.01f, 100u);
    assert(fabsf(noise - 0.01f) < 0.002f);

#if defined(AP_BUILD_NS_MCRA)
    /* A short high-energy burst must not be learned as the new floor. */
    noise = run_power(&state, 0.25f, 20u);
    assert(noise < 0.03f);

    /* A persistent environmental change must eventually become the floor. */
    noise = run_power(&state, 0.04f, 150u);
    assert(noise > 0.032f && noise < 0.05f);
#else
    noise = run_power(&state, 0.04f, 100u);
    assert(noise > 0.0f && noise < 0.06f);
#endif

    puts("audio-pipeline noise/window tests: OK");
    return 0;
}
