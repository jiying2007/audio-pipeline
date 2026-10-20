/* Research-only link wrapper. Actual public pipeline calls its unchanged library. */
#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ap_sync_init d12_unused_init
#define ap_sync_reset d12_unused_reset
#define ap_sync_push_render d12_unused_push_render
#define ap_sync_track_delay d12_unused_track_delay
#define ap_sync_observe_timestamps d12_unused_observe_timestamps
#define ap_sync_get_reference d12_unused_get_reference
#define ap_sync_note_capture d12_unused_note_capture
#define ap_sync_get_status d12_unused_get_status
#include "sync/ap_sync.c"
#undef ap_sync_init
#undef ap_sync_reset
#undef ap_sync_push_render
#undef ap_sync_track_delay
#undef ap_sync_observe_timestamps
#undef ap_sync_get_reference
#undef ap_sync_note_capture
#undef ap_sync_get_status

extern int d12_public_runner_main(int argc, char **argv);
extern void __real_ap_sync_track_delay(ap_sync_state_t *, const float *, uint32_t,
                                       uint32_t, uint32_t, int, int, ap_sync_event_t *);
static ap_sync_state_t saved, probe;
static FILE *trace;
static uint32_t frame;
static int observe_enabled;

void __wrap_ap_sync_track_delay(ap_sync_state_t *s, const float *mic,
                                uint32_t hop, uint32_t rate, uint32_t maximum_ms,
                                int tracking, int drift, ap_sync_event_t *event) {
    const uint32_t maximum = maximum_ms * rate / 1000u;
    const uint32_t step = rate / D12_DIVISOR ? rate / D12_DIVISOR : 1u;
    const uint32_t old = s->delay_samples;
    const uint32_t before = s->route_candidate_confirmations;
    const uint32_t candidate_before = s->route_candidate_delay;
    const uint32_t counter_before = s->delay_update_counter;
    ap_sync_coarse_peak_t peaks[AP_SYNC_UNIQUENESS_PEAKS];
    uint32_t peak_count = 0u, coarse = old, refined = old, lo = 0u, hi = 0u, d;
    float best = 0.0f, coarse_score = 0.0f, history = -1.0f, old_history = -1.0f;
    float runner_up = 0.0f, old_short = -1.0f;
    int unique = -1;
    const int eligible = observe_enabled && tracking &&
        s->render_total >= (uint64_t)(maximum + hop) && counter_before == 9u;
    memcpy(&saved, s, sizeof(saved));
    if (eligible) {
        memcpy(&probe, s, sizeof(probe));
        /* Original tracker appends this actual HPF/BF mono before history gating. */
        if ((probe.route_mic_total % 4u) == 0u && (hop % 4u) == 0u) {
            for (d = 0u; d < hop; d += 4u) {
                const uint64_t at = (probe.route_mic_total + d) / 4u;
                probe.route_mic_history[at % AP_SYNC_ROUTE_HISTORY_VALUES] = mic[d];
            }
        }
        probe.route_mic_total += hop;
        for (d = 0u; d <= maximum; d += step) {
            const float score = ap_sync_delay_score(&probe, mic, hop, d, 4u);
            ap_sync_record_coarse_peak(peaks, &peak_count, d, score);
            if (score > best) { best = score; coarse = d; }
        }
        coarse_score = best;
        lo = coarse > step ? coarse - step : 0u;
        hi = coarse + step < maximum ? coarse + step : maximum;
        refined = coarse;
        for (d = lo; d <= hi; ++d) {
            const float score = ap_sync_delay_score(&probe, mic, hop, d, 4u);
            if (score > best) { best = score; refined = d; }
        }
        for (d = 0u; d < peak_count; ++d) {
            if (ap_sync_distance(peaks[d].delay, refined) > step &&
                peaks[d].score > runner_up) runner_up = peaks[d].score;
        }
        unique = ap_sync_peak_is_unique(peaks, peak_count, refined, best, step);
        history = ap_sync_route_history_score(&probe, rate, hop, maximum, refined);
        old_history = ap_sync_route_history_score(&probe, rate, hop, maximum, old);
        old_short = ap_sync_delay_score(&probe, mic, hop, old, 4u);
        assert(isfinite(best) && isfinite(history) && isfinite(old_history) &&
               isfinite(runner_up) && isfinite(old_short));
    }
    assert(memcmp(&saved, s, sizeof(saved)) == 0);
    __real_ap_sync_track_delay(s, mic, hop, rate, maximum_ms, tracking, drift, event);
    if (eligible && best >= AP_SYNC_MIN_CORRELATION_SQUARED) {
        assert(event->delay_error_samples == (int32_t)refined - (int32_t)old);
        if (ap_sync_distance(refined, old) > rate / 50u) {
            if (history < AP_SYNC_MIN_CORRELATION_SQUARED) {
                assert(s->route_candidate_confirmations == 0u && !event->route_jump);
            } else if (event->route_jump) {
                assert(before >= 2u && ap_sync_distance(refined, candidate_before) <= step);
                assert(s->delay_samples == candidate_before);
            }
        }
    }
    assert(fprintf(trace,
        "%u,%u,%u,%u,%u,%u,%u,%u,%u,%.9g,%.9g,%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%d,%u,%u,%u,%u,%u,%u,%u,%d,%u\n",
        frame++, old, s->delay_samples, counter_before, (uint32_t)eligible, step,
        coarse, refined, ap_sync_distance(refined, old), (double)coarse_score,
        (double)best, lo, hi, (double)history, (double)old_history,
        (double)runner_up, (double)old_short,
        runner_up > 1.0e-12f ? (double)(best / runner_up) : -1.0,
        unique, before, candidate_before, (uint32_t)s->route_candidate_confirmations,
        s->route_candidate_delay, (uint32_t)event->delay_observed,
        (uint32_t)event->route_jump, event->reference_sample_slips,
        event->delay_error_samples, (uint32_t)(s->route_mic_total == s->render_total)) > 0);
}

int main(int argc, char **argv) {
    int result;
    if (argc != 8 || (strcmp(argv[7], "observe") != 0 &&
                      strcmp(argv[7], "no-observe") != 0)) return 2;
    observe_enabled = strcmp(argv[7], "observe") == 0;
    trace = fopen(argv[6], "wb");
    if (!trace) return 4;
    assert(fprintf(trace, "frame,old_samples,new_samples,counter_before,eligible,step,coarse,refined,raw_distance,coarse_score,short_score,lo,hi,history_score,old_history_score,runner_up,old_short_score,peak_ratio,unique,confirm_before,candidate_before,confirm_after,candidate_after,observed,route_jump,slips,error_samples,history_paired\n") > 0);
    result = d12_public_runner_main(6, argv);
    if (fclose(trace) != 0) return 9;
    return result;
}
