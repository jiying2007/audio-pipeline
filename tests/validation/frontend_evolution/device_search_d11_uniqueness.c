/* Full-enumeration oracle for bounded top4 uniqueness, not acoustic evidence. */
#include "sync/ap_sync.c"
#include <assert.h>
#include <stdio.h>

int main(void) {
    const uint32_t rates[2] = {8000u, 16000u};
    const float best_scores[3] = {0.02f, 0.8f, 1.0f};
    uint32_t r, pattern, best_delay, level, checks = 0u, max_excluded = 0u;
    for (r = 0u; r < 2u; ++r) {
        const uint32_t step = rates[r] / 1000u, maximum = rates[r] / 10u;
        for (pattern = 0u; pattern < 3u; ++pattern) {
            for (best_delay = 0u; best_delay <= maximum; ++best_delay) {
                ap_sync_coarse_peak_t peaks[AP_SYNC_UNIQUENESS_PEAKS];
                uint32_t count = 0u, excluded = 0u, delay;
                float runner_up = 0.0f;
                for (delay = 0u; delay <= maximum; delay += step) {
                    const uint32_t distance = delay > best_delay ? delay - best_delay : best_delay - delay;
                    float score;
                    if (pattern == 0u) score = 1.0f;
                    else if (pattern == 1u) score = (float)(((delay / step) * 37u + 11u) % 101u) / 100.0f;
                    else score = distance <= step ? 0.99f : 0.5f;
                    ap_sync_record_coarse_peak(peaks, &count, delay, score);
                    if (distance <= step) excluded++;
                    else if (score > runner_up) runner_up = score;
                }
                assert(excluded <= 3u);
                if (excluded > max_excluded) max_excluded = excluded;
                for (level = 0u; level < 3u; ++level) {
                    const float best = best_scores[level];
                    const int oracle = best >= 0.0324f &&
                        (runner_up <= 1.0e-12f || best >= runner_up * 1.01f);
                    assert(ap_sync_peak_is_unique(peaks, count, best_delay, best, step) == oracle);
                    checks++;
                }
            }
        }
    }
    printf("D11_UNIQUENESS_PASS checks=%u max_excluded=%u\n", checks, max_excluded);
    return 0;
}
