/* Internal confirmation properties; full public event/recovery tests are separate. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "sync/ap_sync.c"

static ap_sync_state_t state;

int main(void) {
    const uint32_t rates[2] = {8000u, 16000u};
    uint32_t i;
    for (i = 0u; i < 2u; ++i) {
        const uint32_t step = rates[i] / 1000u;
        const uint32_t tolerance = step / 2u;
        ap_sync_init(&state, 0u);
        assert(!ap_sync_confirm_route_candidate(&state, 100u, tolerance));
        assert(state.route_candidate_confirmations == 1u);
        assert(!ap_sync_confirm_route_candidate(&state, 100u + tolerance, tolerance));
        assert(state.route_candidate_delay == 100u && state.route_candidate_confirmations == 2u);
        assert(ap_sync_confirm_route_candidate(&state, 100u - tolerance, tolerance));
        assert(state.route_candidate_delay == 100u && state.route_candidate_confirmations == 0u);
        /* Inclusive anchor tolerance allows two extrema a full 1 ms apart. */
        ap_sync_init(&state, 0u);
        assert(!ap_sync_confirm_route_candidate(&state, 100u, tolerance));
        assert(!ap_sync_confirm_route_candidate(&state, 100u + tolerance + 1u, tolerance));
        assert(state.route_candidate_delay == 100u + tolerance + 1u);
        assert(state.route_candidate_confirmations == 1u);
        assert(!ap_sync_confirm_route_candidate(&state, 100u + tolerance + 1u, tolerance));
        assert(ap_sync_confirm_route_candidate(&state, 100u + tolerance + 1u, tolerance));
        assert(state.route_candidate_confirmations == 0u);
        ap_sync_init(&state, 0u);
        assert(!ap_sync_confirm_route_candidate(&state, UINT32_MAX, tolerance));
        assert(!ap_sync_confirm_route_candidate(&state, 0u, tolerance));
        assert(state.route_candidate_delay == 0u && state.route_candidate_confirmations == 1u);
        assert(!ap_sync_confirm_route_candidate(&state, 0u, tolerance));
        assert(ap_sync_confirm_route_candidate(&state, 0u, tolerance));
    }
    ap_sync_init(&state, 0u);
    assert(!ap_sync_confirm_route_candidate(&state, 15u, 8u));
    assert(!ap_sync_confirm_route_candidate(&state, 16u, 8u));
    assert(!ap_sync_confirm_route_candidate(&state, 24u, 8u));
    assert(state.route_candidate_delay == 24u && state.route_candidate_confirmations == 1u);
    ap_sync_init(&state, 0u);
    assert(!ap_sync_confirm_route_candidate(&state, 31u, 8u));
    assert(!ap_sync_confirm_route_candidate(&state, 16u, 8u));
    assert(!ap_sync_confirm_route_candidate(&state, 16u, 8u));
    assert(state.route_candidate_delay == 16u && state.route_candidate_confirmations == 2u);
    puts("D14_CONFIRM_PROPERTIES_PASS rates=8000,16000 inclusive_anchor outlier_restart uint_boundary historical_triplets");
    return 0;
}
