/* Read-only internal diagnostics on disclosed D9 inputs; no algorithm change. */
#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sync/ap_sync.c"

typedef struct observation {
    uint32_t eligible, coarse, refined, lo, hi;
    float coarse_score, refined_score, truth_score, floor_score, ceil_score;
} observation_t;
static ap_sync_state_t state, snapshot;

static observation_t observe(const float *mic, uint32_t hop, uint32_t rate,
                              uint32_t truth) {
    observation_t o = {0};
    const uint32_t step = rate / 500u, maximum = rate / 10u;
    uint32_t d;
    memcpy(&snapshot, &state, sizeof(state));
    if (state.render_total >= (uint64_t)(maximum + hop) &&
        state.delay_update_counter == 9u) {
        o.eligible = 1u; o.coarse = state.delay_samples;
        for (d = 0u; d <= maximum; d += step) {
            const float score = ap_sync_delay_score(&state, mic, hop, d, 4u);
            if (score > o.coarse_score) { o.coarse_score = score; o.coarse = d; }
        }
        o.lo = o.coarse > step ? o.coarse - step : 0u;
        o.hi = o.coarse + step < maximum ? o.coarse + step : maximum;
        o.refined = o.coarse; o.refined_score = o.coarse_score;
        for (d = o.lo; d <= o.hi; ++d) {
            const float score = ap_sync_delay_score(&state, mic, hop, d, 4u);
            if (score > o.refined_score) { o.refined_score = score; o.refined = d; }
        }
        o.truth_score = ap_sync_delay_score(&state, mic, hop, truth, 4u);
        o.floor_score = ap_sync_delay_score(&state, mic, hop, truth / step * step, 4u);
        o.ceil_score = ap_sync_delay_score(&state, mic, hop,
                                          (truth + step - 1u) / step * step, 4u);
        assert(isfinite(o.coarse_score) && isfinite(o.refined_score) &&
               isfinite(o.truth_score) && isfinite(o.floor_score) && isfinite(o.ceil_score));
    }
    assert(memcmp(&snapshot, &state, sizeof(state)) == 0);
    return o;
}

static float read_s16(FILE *f) {
    const int lo = fgetc(f), hi = fgetc(f);
    unsigned int u;
    int value;
    assert(lo != EOF && hi != EOF);
    u = (unsigned int)lo + ((unsigned int)hi << 8u);
    value = u < 32768u ? (int)u : (int)u - 65536;
    return (float)value * (1.0f / 32768.0f);
}

int main(int argc, char **argv) {
    FILE *input, *output;
    float render[160], mic[160];
    uint32_t rate, truth_ms, truth, hop, frame, i;
    uint64_t jumps = 0u, slips = 0u;
    if (argc != 5) return 2;
    rate = (uint32_t)strtoul(argv[3], NULL, 10);
    truth_ms = (uint32_t)strtoul(argv[4], NULL, 10);
    if ((rate != 8000u && rate != 16000u) ||
        (truth_ms != 1u && truth_ms != 7u && truth_ms != 80u)) return 2;
    hop = rate / 100u; truth = truth_ms * rate / 1000u;
    input = fopen(argv[1], "rb"); output = fopen(argv[2], "wb");
    assert(input != NULL && output != NULL);
    ap_sync_init(&state, rate * 40u / 1000u);
    assert(fprintf(output, "frame,delay_ms,jumps,slips,eligible,old_samples,coarse,coarse_score,lo,hi,refined,refined_score,truth_score,floor_score,ceil_score,confirm_before,candidate_before,confirm_after,candidate_after,observed,route_jump,history_score\n") > 0);
    for (frame = 0u; frame < 300u; ++frame) {
        ap_sync_event_t event;
        observation_t o;
        uint32_t old, before, candidate;
        float history_score = -1.0f;
        for (i = 0u; i < hop; ++i) {
            render[i] = read_s16(input); mic[i] = read_s16(input);
        }
        ap_sync_push_render(&state, render, hop, frame);
        old = state.delay_samples; before = state.route_candidate_confirmations;
        candidate = state.route_candidate_delay;
        o = observe(mic, hop, rate, truth);
        ap_sync_track_delay(&state, mic, hop, rate, 100u, 1, 1, &event);
        if (o.eligible && event.delay_observed)
            assert(event.delay_error_samples == (int32_t)o.refined - (int32_t)old);
#if D10_D8
        if (o.eligible) {
            memcpy(&snapshot, &state, sizeof(state));
            history_score = ap_sync_route_history_score(&state, rate, hop, rate / 10u, o.refined);
            assert(isfinite(history_score));
            assert(memcmp(&snapshot, &state, sizeof(state)) == 0);
        }
#endif
        jumps += event.route_jump; slips += event.reference_sample_slips;
        assert(fprintf(output, "%u,%u,%" PRIu64 ",%" PRIu64 ",%u,%u,%u,%.9g,%u,%u,%u,%.9g,%.9g,%.9g,%.9g,%u,%u,%u,%u,%u,%u,%.9g\n",
            frame, state.delay_samples * 1000u / rate, jumps, slips, o.eligible, old,
            o.coarse, (double)o.coarse_score, o.lo, o.hi, o.refined, (double)o.refined_score,
            (double)o.truth_score, (double)o.floor_score, (double)o.ceil_score,
            before, candidate, (uint32_t)state.route_candidate_confirmations,
            state.route_candidate_delay, (uint32_t)event.delay_observed,
            (uint32_t)event.route_jump, (double)history_score) > 0);
    }
    assert(fgetc(input) == EOF && !ferror(input));
    assert(fclose(input) == 0 && fclose(output) == 0);
    return 0;
}
