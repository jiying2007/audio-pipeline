#include <math.h>
#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#define AP_EXPORT __declspec(dllexport)
#else
#define AP_EXPORT __attribute__((visibility("default")))
#endif

/* Validation-only exact lag oracle for the canonical render correlation.
 * Every integer lag in the existing +/-100 ms window is evaluated with the
 * canonical stride of four samples. This file is never linked into the
 * product DSP/runtime and does not define acceptance thresholds. */
AP_EXPORT double ap_validation_max_abs_corr(const int16_t *a,
                                            size_t a_count,
                                            const int16_t *b,
                                            size_t b_count,
                                            int sample_rate,
                                            int *best_lag) {
    int max_lag;
    double best = 0.0;
    int selected_lag = 0;

    if (a == NULL || b == NULL || sample_rate <= 0) {
        if (best_lag != NULL) {
            *best_lag = 0;
        }
        return 0.0;
    }

    max_lag = sample_rate / 10;
    if (max_lag < 1) {
        max_lag = 1;
    }

    for (int lag = -max_lag; lag <= max_lag; ++lag) {
        size_t count;
        size_t ai;
        size_t bi;
        double xy = 0.0;
        double xx = 0.0;
        double yy = 0.0;

        if (lag >= 0) {
            const size_t shift = (size_t)lag;
            if (shift >= a_count) {
                continue;
            }
            count = a_count - shift;
            if (b_count < count) {
                count = b_count;
            }
            ai = shift;
            bi = 0u;
        } else {
            const size_t shift = (size_t)(-lag);
            if (shift >= b_count) {
                continue;
            }
            count = b_count - shift;
            if (a_count < count) {
                count = a_count;
            }
            ai = 0u;
            bi = shift;
        }

        if (count < 64u) {
            continue;
        }

        for (size_t offset = 0u; offset < count; offset += 4u) {
            const double x = (double)a[ai + offset];
            const double y = (double)b[bi + offset];
            xy += x * y;
            xx += x * x;
            yy += y * y;
        }

        if (xx > 1.0e-12 && yy > 1.0e-12) {
            const double corr = fabs(xy / sqrt(xx * yy));
            if (corr > best) {
                best = corr;
                selected_lag = lag;
            }
        }
    }

    if (best_lag != NULL) {
        *best_lag = selected_lag;
    }
    return best;
}
