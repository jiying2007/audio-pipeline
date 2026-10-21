/* Fixed engineering contrast: actual tracker, no mocked score or audio quality claim. */
#include "sync/ap_sync.c"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static ap_sync_state_t state;

static float raw(uint32_t n) {
    uint32_t x = n + 0x9e3779b9u;
    x ^= x >> 16u; x *= 0x7feb352du; x ^= x >> 15u;
    x *= 0x846ca68bu; x ^= x >> 16u;
    return (float)(x >> 8u) / 16777216.0f - 0.5f;
}

static float signal(uint32_t n) {
    return (raw(n) + raw(n - 1u) + raw(n - 2u)) / 3.0f;
}

static void prepare(uint32_t rate, uint32_t truth, uint32_t anchor, float *mic) {
    const uint32_t total = 6400u, window = rate / 25u, hop = rate / 100u;
    uint32_t i;
    ap_sync_init(&state, rate / 25u);
    state.render_total = total;
    state.route_mic_total = total - hop;
    for (i = 0u; i < total; ++i)
        state.render_ring[i & (AP_RENDER_CAP - 1u)] = signal(i);
    for (i = 0u; i < window; i += 4u) {
        const uint32_t at = total - window + i;
        state.route_mic_history[(at / 4u) % AP_SYNC_ROUTE_HISTORY_VALUES] = signal(at - truth);
    }
    for (i = 0u; i < hop; ++i) mic[i] = signal(total - hop + i - truth);
    state.route_candidate_delay = anchor;
    state.route_candidate_confirmations = 2u;
    state.delay_update_counter = 9u;
    state.drift_ppm = 17.0f;
    state.drift_credit = 0.125f;
    state.last_best_delay = rate / 25u + 2u;
    state.have_last_best_delay = 1u;
}

int main(void) {
    float mic[160];
    ap_sync_event_t event;
    uint32_t r;
    for (r = 0u; r < 2u; ++r) {
        const uint32_t rate = r ? 16000u : 8000u;
        const uint32_t truth = r ? 15u : 7u, weak_anchor = r ? 20u : 10u;
        const uint32_t old = rate / 25u, hop = rate / 100u;
        prepare(rate, truth, weak_anchor, mic);
        /* Inspect a paired pre-call copy at the exact post-append time. */
        {
            ap_sync_state_t paired = state;
            paired.route_mic_total += hop;
            assert(ap_sync_route_history_score(&paired, rate, hop, rate / 10u, truth) > 0.99f);
            assert(ap_sync_route_history_score(&paired, rate, hop, rate / 10u, weak_anchor) < AP_SYNC_MIN_CORRELATION_SQUARED);
        }
        ap_sync_track_delay(&state, mic, hop, rate, 100u, 1, 1, &event);
        assert(event.delay_error_samples == (int32_t)truth - (int32_t)old);
        assert(state.route_candidate_confirmations == 0u && state.route_candidate_delay == weak_anchor);
        assert(state.delay_update_counter == 0u && state.route_mic_total == state.render_total);
        assert(event.reference_sample_slips == 0u);
#if D16_EXPECT_GUARD
        assert(state.delay_samples == old && !event.route_jump && !event.delay_observed);
        assert(state.drift_ppm == 17.0f && state.drift_credit == 0.125f);
        assert(state.last_best_delay == old + 2u && state.have_last_best_delay == 1u);
        {
            float render[160];
            uint32_t i;
            for (i = 0u; i < hop; ++i) {
                render[i] = signal(6400u + i);
                mic[i] = signal(6400u + i - truth);
            }
            ap_sync_push_render(&state, render, hop, 1u);
            state.delay_update_counter = 9u; /* Controlled next eligible engineering update. */
            ap_sync_track_delay(&state, mic, hop, rate, 100u, 1, 1, &event);
            assert(state.delay_samples == old && !event.route_jump && !event.delay_observed);
            {
                const int32_t selected = (int32_t)old + event.delay_error_samples;
                assert(selected >= 0 && (uint32_t)selected <= rate / 10u);
                assert(state.route_candidate_confirmations == 1u && state.route_candidate_delay == (uint32_t)selected);
                printf("D16_POST_REJECT_DIAGNOSTIC rate=%u truth=%u selected=%u truth_match=%u\n",
                       rate, truth, (uint32_t)selected, (uint32_t)((uint32_t)selected == truth));
            }
        }
#else
        assert(state.delay_samples == weak_anchor && event.route_jump && event.delay_observed);
        assert(state.drift_ppm == 0.0f && state.drift_credit == 0.0f);
#endif
        prepare(rate, truth, truth, mic);
        ap_sync_track_delay(&state, mic, hop, rate, 100u, 1, 1, &event);
        assert(state.delay_samples == truth && event.route_jump && event.delay_observed);
        assert(event.delay_error_samples == (int32_t)truth - (int32_t)old);
        assert(state.route_candidate_confirmations == 0u && state.drift_ppm == 0.0f && state.drift_credit == 0.0f);
        printf("D16_ANCHOR_CONTRAST_PASS rate=%u guard=%d weak_anchor=%u strong_anchor=%u\n", rate, D16_EXPECT_GUARD, weak_anchor, truth);
    }
    return 0;
}
