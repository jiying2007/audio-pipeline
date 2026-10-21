/* Fixed synthetic engineering fixtures, no acoustic qualification. */
#include "sync/ap_sync.c"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static float sample(uint32_t n) {
    uint32_t x = n + 0x9e3779b9u;
    x ^= x >> 16u; x *= 0x7feb352du; x ^= x >> 15u; x *= 0x846ca68bu; x ^= x >> 16u;
    return (float)(int32_t)(x >> 8u) / 16777216.0f - 0.5f;
}
static void prepared(ap_sync_state_t *s, uint32_t rate, uint32_t delay) {
    const uint32_t window = rate / 25u;
    uint32_t i;
    ap_sync_init(s, 16u);
    s->render_total = 6400u; s->route_mic_total = s->render_total;
    for (i = 0u; i < 6400u; ++i) s->render_ring[i & (AP_RENDER_CAP - 1u)] = sample(i);
    for (i = 0u; i < window; i += 4u) {
        const uint64_t at = s->route_mic_total - window + i;
        s->route_mic_history[(at / 4u) % AP_SYNC_ROUTE_HISTORY_VALUES] = sample((uint32_t)at - delay);
    }
}
int main(void) {
    ap_sync_state_t a, b;
    ap_sync_event_t e;
    float mic[160] = {0.0f};
    uint32_t i;
    for (i = 0u; i < 2u; ++i) {
        const uint32_t rate = i ? 16000u : 8000u;
        prepared(&a, rate, 640u);
        assert(fabsf(ap_sync_route_history_score(&a, rate, rate / 100u, 1600u, 640u) - 1.0f) < 1.0e-5f);
        assert(ap_sync_route_history_score(&a, rate, rate / 100u, 1600u, 320u) < 0.0324f);
        a.route_mic_total--;
        assert(ap_sync_route_history_score(&a, rate, rate / 100u, 1600u, 640u) == 0.0f);
        prepared(&a, rate, 640u); a.route_mic_total = 0u;
        assert(ap_sync_route_history_score(&a, rate, rate / 100u, 1600u, 640u) == 0.0f);
    }
    prepared(&a, 16000u, 640u); prepared(&b, 16000u, 1280u);
    assert(ap_sync_route_history_score(&a, 16000u, 160u, 1600u, 640u) > 0.99f);
    assert(ap_sync_route_history_score(&b, 16000u, 160u, 1600u, 1280u) > 0.99f);
    assert(ap_sync_route_history_score(&a, 16000u, 160u, 1600u, 640u) > 0.99f);
    a.route_candidate_confirmations = 2u;
    ap_sync_reset(&a);
    assert(a.route_mic_total == 0u && a.route_candidate_confirmations == 0u);
    for (i = 0u; i < AP_SYNC_ROUTE_HISTORY_VALUES; ++i) assert(a.route_mic_history[i] == 0.0f);
    prepared(&a, 16000u, 640u);
    ap_sync_track_delay(&a, mic, 160u, 16000u, 100u, 0, 0, &e);
    assert(a.delay_samples == 16u && e.route_jump == 0u && e.delay_observed == 0u);
    /* Low long-window correlation cannot complete a pre-existing 2/3 confirmation. */
    prepared(&a, 16000u, 640u);
    for (i = 0u; i < AP_SYNC_ROUTE_HISTORY_VALUES; ++i) a.route_mic_history[i] = 1.0f;
    a.route_mic_total = 6240u;
    for (i = 0u; i < 160u; ++i) mic[i] = sample(6240u + i - 1280u);
    a.route_candidate_delay = 1280u; a.route_candidate_confirmations = 2u;
    a.delay_update_counter = 9u;
    ap_sync_track_delay(&a, mic, 160u, 16000u, 100u, 1, 0, &e);
    assert(e.route_jump == 0u && a.delay_samples == 16u && a.route_candidate_confirmations == 0u);
    printf("D8_ENGINEERING_PASS rate8k/rate16k/history/mismatch/reset/isolation/disabled/lowcorr\n");
    return 0;
}
