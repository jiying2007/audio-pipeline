/* Deterministic timing regressions, not acoustic or device qualification.
 * Public module calls exercise the real correlation search and drift update.
 * The optional internal case covers unreachable-in-practice counter rollover.
 */
#include "audio_pipeline/audio_modules.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(AP_SYNC_TEST_INTERNAL_COUNTERS)
#include "sync/ap_sync.h"
#endif

typedef struct fixture {
    _Alignas(AP_MODULE_STATE_ALIGNMENT) unsigned char memory[AP_MODULE_STATE_MAX_BYTES];
    ap_sync_module_t *module;
    uint32_t rate, maximum_ms, next_sample, frames, initial_delay;
    ap_module_sync_status_t status;
} fixture_t;

typedef struct observation {
    ap_module_sync_event_t event;
    ap_module_sync_status_t status;
    int32_t selected_delay;
} observation_t;

enum { SIGNAL_MATCHED, SIGNAL_ZERO_MIC, SIGNAL_PERIODIC };
static fixture_t fixture;
static unsigned char saved_memory[AP_MODULE_STATE_MAX_BYTES];
static float render[160], mic[160], reference[160];
static FILE *continuous_trace;

/* Same fixed hash family as existing engineering fixtures. A declared boxcar
 * keeps the coarse lag grid well-conditioned; no seed/parameter search. */
static float raw_sample(uint32_t n) {
    uint32_t x = n + 0x9e3779b9u;
    x ^= x >> 16u; x *= 0x7feb352du; x ^= x >> 15u;
    x *= 0x846ca68bu; x ^= x >> 16u;
    return (float)(x >> 8u) / 16777216.0f - 0.5f;
}

static float signal_sample(uint32_t n, uint32_t rate, int mode) {
    uint32_t j, width = rate / 250u;
    float sum = 0.0f;
    if (mode == SIGNAL_PERIODIC) return n % 8u < 4u ? 0.25f : -0.25f;
    for (j = 0u; j < width; ++j) sum += raw_sample(n - j);
    return sum / (float)width;
}

static void fill(uint32_t at, uint32_t rate, uint32_t truth, int mode) {
    uint32_t i;
    for (i = 0u; i < rate / 100u; ++i) {
        render[i] = signal_sample(at + i, rate, mode);
        mic[i] = mode == SIGNAL_ZERO_MIC ? 0.0f :
                 0.6f * signal_sample(at + i - truth, rate, mode);
    }
}

static void require_ppm(const char *label, uint32_t rate, float actual, float expected) {
    if (!isfinite(actual) || fabsf(actual - expected) > 1.0e-4f) {
        fprintf(stderr, "%s rate=%u actual_ppm=%.9g expected_ppm=%.9g\n",
                label, rate, (double)actual, (double)expected);
        exit(EXIT_FAILURE);
    }
}

static observation_t step(fixture_t *f, uint32_t truth, int mode,
                          int tracking, int drift) {
    observation_t result;
    const uint32_t hop = f->rate / 100u;
    const uint32_t old_delay = f->status.delay_samples;
    int underrun;
    fill(f->next_sample, f->rate, truth, mode);
    assert(ap_module_sync_push_render(f->module, render, hop, f->frames) == AP_OK);
    assert(ap_module_sync_track(f->module, mic, hop, f->rate, f->maximum_ms,
                                tracking, drift, &result.event) == AP_OK);
    assert(ap_module_sync_get_reference(f->module, hop, reference, &underrun) == AP_OK);
    assert(!underrun);
    ap_module_sync_get_status(f->module, &result.status);
    assert(isfinite(result.status.estimated_drift_ppm));
    result.selected_delay = (int32_t)old_delay + result.event.delay_error_samples;
    if (result.event.delay_observed && mode == SIGNAL_MATCHED)
        assert(result.selected_delay == (int32_t)truth);
    f->status = result.status;
    f->next_sample += hop;
    f->frames++;
    if (continuous_trace) {
        const size_t bytes = ap_module_sync_state_size();
        assert(fwrite(f->memory, 1u, bytes, continuous_trace) == bytes);
        assert(fwrite(reference, sizeof(float), hop, continuous_trace) == hop);
    }
    return result;
}

static observation_t frames(fixture_t *f, uint32_t count, uint32_t truth,
                            int mode, int tracking, int drift) {
    observation_t result;
    uint32_t i;
    memset(&result, 0, sizeof(result));
    for (i = 0u; i < count; ++i) result = step(f, truth, mode, tracking, drift);
    return result;
}

static void prepare(fixture_t *f, uint32_t rate, uint32_t maximum_ms) {
    uint32_t i, hop = rate / 100u;
    observation_t result;
    memset(f, 0, sizeof(*f));
    f->rate = rate;
    f->maximum_ms = maximum_ms;
    f->initial_delay = rate / 125u;
    assert(ap_module_sync_state_size() <= sizeof(f->memory));
    assert(ap_module_sync_init(f->memory, sizeof(f->memory), f->initial_delay,
                               &f->module) == AP_OK);
    for (i = 0u; i < 20u; ++i) {
        fill(f->next_sample, rate, f->initial_delay, SIGNAL_MATCHED);
        assert(ap_module_sync_push_render(f->module, render, hop, f->frames) == AP_OK);
        f->next_sample += hop;
        f->frames++;
    }
    ap_module_sync_get_status(f->module, &f->status);
    for (i = 0u; i < 10u; ++i) {
        result = step(f, f->initial_delay, SIGNAL_MATCHED, 1, 1);
        assert(result.event.delay_observed == (i == 9u));
        assert(!result.event.route_jump);
    }
    require_ppm("first acoustic basis", rate, f->status.estimated_drift_ppm, 0.0f);
}

static void test_elapsed(uint32_t rate) {
    static const int gaps[] = {SIGNAL_ZERO_MIC, SIGNAL_PERIODIC};
    uint32_t g, i;
    int sign;
    observation_t result;
    prepare(&fixture, rate, 20u);
    result = frames(&fixture, 10u, fixture.initial_delay + 1u, SIGNAL_MATCHED, 1, 1);
    assert(result.event.delay_observed && !result.event.route_jump);
    require_ppm("100 ms", rate, result.status.estimated_drift_ppm, 500000.0f / (float)rate);
    for (g = 0u; g < sizeof(gaps) / sizeof(gaps[0]); ++g) {
        for (sign = 1; sign >= -1; sign -= 2) {
            prepare(&fixture, rate, 20u);
            for (i = 0u; i < 90u; ++i) {
                result = step(&fixture, fixture.initial_delay, gaps[g], 1, 1);
                assert(!result.event.delay_observed && !result.event.route_jump);
                require_ppm("rejected observation", rate, result.status.estimated_drift_ppm, 0.0f);
            }
            result = frames(&fixture, 10u, (uint32_t)((int32_t)fixture.initial_delay + sign),
                            SIGNAL_MATCHED, 1, 1);
            assert(result.event.delay_observed && !result.event.route_jump);
            require_ppm("1 s interval", rate, result.status.estimated_drift_ppm,
                        (float)sign * 50000.0f / (float)rate);
        }
    }
    prepare(&fixture, rate, 20u);
    frames(&fixture, 90u, fixture.initial_delay, SIGNAL_ZERO_MIC, 1, 1);
    result = frames(&fixture, 10u, fixture.initial_delay + 4u, SIGNAL_MATCHED, 1, 1);
    assert(result.event.delay_observed && !result.event.route_jump);
    require_ppm("normalize before clamp", rate, result.status.estimated_drift_ppm,
                200000.0f / (float)rate);
    printf("elapsed rate=%u 100ms_delta1=%.9g 1s_delta1=%.9g 1s_delta4=%.9g PASS\n",
           rate, (double)(500000.0f / (float)rate), (double)(50000.0f / (float)rate),
           (double)result.status.estimated_drift_ppm);
}

static void test_continuous(uint32_t rate) {
    uint32_t i, previous_offset = 0u;
    float expected = 0.0f;
    prepare(&fixture, rate, 20u);
    for (i = 1u; i <= 10u; ++i) {
        /* At 8 kHz the decimated search has only 20 points. Keep this timing
         * fixture beside an exact coarse anchor instead of testing unrelated
         * coarse-search misses at larger off-grid displacements. */
        const uint32_t offset = rate == 8000u ? i % 2u : i;
        const float raw = (float)((int32_t)offset - (int32_t)previous_offset) *
                          10000000.0f / (float)rate;
        observation_t result = frames(&fixture, 10u, fixture.initial_delay + offset,
                                      SIGNAL_MATCHED, 1, 1);
        assert(result.event.delay_observed && !result.event.route_jump);
        expected = 0.95f * expected + 0.05f * raw;
        require_ppm("continuous EMA", rate, result.status.estimated_drift_ppm, expected);
        printf("continuous rate=%u update=%u ppm=%a delay=%u slips=%u\n", rate, i,
               (double)result.status.estimated_drift_ppm, result.status.delay_samples,
               result.event.reference_sample_slips);
        previous_offset = offset;
    }
}

static void test_reset_and_timestamp(uint32_t rate) {
    observation_t result;
    uint32_t i;
    const uint32_t hop = rate / 100u;
    const uint64_t render_ns = 1000000000ull;
    ap_module_sync_event_t event;
    prepare(&fixture, rate, 20u);
    frames(&fixture, 10u, fixture.initial_delay + 1u, SIGNAL_MATCHED, 1, 1);
    frames(&fixture, 25u, fixture.initial_delay, SIGNAL_ZERO_MIC, 1, 1);
    ap_module_sync_reset(fixture.module);
    ap_module_sync_get_status(fixture.module, &fixture.status);
    assert(fixture.status.delay_samples == fixture.initial_delay);
    require_ppm("reset", rate, fixture.status.estimated_drift_ppm, 0.0f);
    for (i = 0u; i < 20u; ++i) {
        fill(fixture.next_sample, rate, fixture.initial_delay, SIGNAL_MATCHED);
        assert(ap_module_sync_push_render(fixture.module, render, hop, fixture.frames) == AP_OK);
        fixture.next_sample += hop;
        fixture.frames++;
    }
    result = frames(&fixture, 10u, fixture.initial_delay + 1u, SIGNAL_MATCHED, 1, 1);
    assert(result.event.delay_observed);
    require_ppm("reset first basis", rate, result.status.estimated_drift_ppm, 0.0f);
    result = frames(&fixture, 10u, fixture.initial_delay + 2u, SIGNAL_MATCHED, 1, 1);
    require_ppm("reset next observation", rate, result.status.estimated_drift_ppm,
                500000.0f / (float)rate);

    /* Timestamp is authoritative for alignment, not a comparable acoustic
     * lag sample for the next rate derivative. Keep the search phase intact. */
    frames(&fixture, 5u, fixture.initial_delay, SIGNAL_ZERO_MIC, 1, 1);
    assert(ap_module_sync_observe_timestamps(fixture.module, render_ns + 8000000ull,
                                             render_ns, rate, 20u, &event) == AP_OK);
    assert(event.timestamp_observed && event.delay_observed && !event.route_jump);
    ap_module_sync_get_status(fixture.module, &fixture.status);
    assert(fixture.status.delay_samples == fixture.initial_delay);
    require_ppm("timestamp reset", rate, fixture.status.estimated_drift_ppm, 0.0f);
    result = frames(&fixture, 5u, fixture.initial_delay + 1u, SIGNAL_MATCHED, 1, 1);
    assert(result.event.delay_observed);
    require_ppm("timestamp first acoustic basis", rate, result.status.estimated_drift_ppm, 0.0f);
    result = frames(&fixture, 10u, fixture.initial_delay + 2u, SIGNAL_MATCHED, 1, 1);
    require_ppm("timestamp next observation", rate, result.status.estimated_drift_ppm,
                500000.0f / (float)rate);
    printf("reset/timestamp rate=%u PASS\n", rate);
}

static void test_rejected_inputs(uint32_t rate) {
    ap_module_sync_event_t event;
    observation_t result;
    const uint32_t hop = rate / 100u;
    const size_t bytes = ap_module_sync_state_size();
    const uint64_t overflow_delta = UINT64_MAX / rate;
    prepare(&fixture, rate, 20u);
    frames(&fixture, 5u, fixture.initial_delay, SIGNAL_MATCHED, 1, 1);
    memcpy(saved_memory, fixture.memory, bytes);
    assert(ap_module_sync_track(fixture.module, mic, hop - 1u, rate, 20u, 1, 1, &event) == AP_EINVAL);
    assert(ap_module_sync_track(fixture.module, mic, hop, 44100u, 20u, 1, 1, &event) == AP_EINVAL);
    assert(ap_module_sync_track(fixture.module, mic, hop, rate,
                                AP_BUILD_MAX_DELAY_MS + 1u, 1, 1, &event) == AP_EINVAL);
    assert(ap_module_sync_observe_timestamps(fixture.module, 0u, 1u, rate, 20u, &event) == AP_EINVAL);
    assert(ap_module_sync_observe_timestamps(fixture.module, 1u, 1u, rate, 20u, &event) == AP_EINVAL);
    assert(ap_module_sync_observe_timestamps(fixture.module, overflow_delta + 1u,
                                             1u, rate, 20u, &event) == AP_EINVAL);
    assert(memcmp(saved_memory, fixture.memory, bytes) == 0);
    result = frames(&fixture, 5u, fixture.initial_delay + 1u, SIGNAL_MATCHED, 1, 1);
    assert(result.event.delay_observed);
    require_ppm("rejected calls do not advance time", rate, result.status.estimated_drift_ppm,
                500000.0f / (float)rate);
    printf("atomic rejection rate=%u PASS\n", rate);
}

static void test_disabled(uint32_t rate) {
    int disable_tracking;
    for (disable_tracking = 0; disable_tracking <= 1; ++disable_tracking) {
        observation_t result;
        float before_resume;
        uint32_t i;
        prepare(&fixture, rate, 20u);
        frames(&fixture, 10u, fixture.initial_delay + 1u, SIGNAL_MATCHED, 1, 1);
        for (i = 0u; i < 90u; ++i) {
            const ap_module_sync_status_t before = fixture.status;
            result = step(&fixture, fixture.initial_delay + 2u, SIGNAL_MATCHED,
                          !disable_tracking, disable_tracking);
            assert(!result.event.route_jump && !result.event.reference_sample_slips);
            if (disable_tracking) {
                assert(!result.event.delay_observed);
                assert(result.status.delay_samples == before.delay_samples);
                assert(result.status.estimated_drift_ppm == before.estimated_drift_ppm);
            }
        }
        before_resume = fixture.status.estimated_drift_ppm;
        result = frames(&fixture, 10u, fixture.initial_delay + 2u, SIGNAL_MATCHED, 1, 1);
        assert(result.event.delay_observed);
        require_ppm("reenable first basis", rate, result.status.estimated_drift_ppm, before_resume);
        result = frames(&fixture, 10u, fixture.initial_delay + 3u, SIGNAL_MATCHED, 1, 1);
        require_ppm("reenable next observation", rate, result.status.estimated_drift_ppm,
                    0.95f * before_resume + 500000.0f / (float)rate);
    }
    printf("disable/reenable rate=%u PASS\n", rate);
}

static void test_route(uint32_t rate) {
    uint32_t i, jump_delay = rate / 25u;
    int drift;
    observation_t result;
    if (AP_BUILD_MAX_DELAY_MS < 50u) return;
    for (drift = 0; drift <= 1; ++drift) {
        prepare(&fixture, rate, 50u);
        frames(&fixture, 20u, fixture.initial_delay, SIGNAL_ZERO_MIC, 1, drift);
        for (i = 0u; i < 30u; ++i) {
            result = step(&fixture, jump_delay, SIGNAL_MATCHED, 1, drift);
            assert(result.event.route_jump == (i == 29u));
            assert(result.event.delay_observed == (i == 29u));
        }
        assert(result.status.delay_samples == jump_delay);
        require_ppm("route anchor", rate, result.status.estimated_drift_ppm, 0.0f);
        result = frames(&fixture, 10u, jump_delay + 1u, SIGNAL_MATCHED, 1, 1);
        assert(result.event.delay_observed && !result.event.route_jump);
        require_ppm("route next observation", rate, result.status.estimated_drift_ppm,
                    drift ? 500000.0f / (float)rate : 0.0f);
        if (!drift) {
            result = frames(&fixture, 10u, jump_delay + 2u, SIGNAL_MATCHED, 1, 1);
            require_ppm("disabled route reenable", rate, result.status.estimated_drift_ppm,
                        500000.0f / (float)rate);
        }
    }
    printf("route anchor rate=%u PASS\n", rate);
}

static void test_rate_change(uint32_t old_rate, uint32_t new_rate) {
    observation_t result;
    float before_change;
    uint32_t truth;
    prepare(&fixture, old_rate, 20u);
    frames(&fixture, 10u, fixture.initial_delay + 1u, SIGNAL_MATCHED, 1, 1);
    before_change = fixture.status.estimated_drift_ppm;
    truth = fixture.initial_delay + 2u;
    fixture.rate = new_rate;
    result = frames(&fixture, 10u, truth, SIGNAL_MATCHED, 1, 1);
    assert(result.event.delay_observed && !result.event.route_jump);
    require_ppm("rate change first basis", new_rate, result.status.estimated_drift_ppm, before_change);
    result = frames(&fixture, 10u, truth + 1u, SIGNAL_MATCHED, 1, 1);
    require_ppm("rate change next observation", new_rate, result.status.estimated_drift_ppm,
                0.95f * before_change + 500000.0f / (float)new_rate);
    printf("rate basis %u->%u PASS (not acoustic rate-switch qualification)\n", old_rate, new_rate);
}

#if defined(AP_SYNC_TEST_INTERNAL_COUNTERS)
static ap_sync_state_t credit_state;

static ap_sync_event_t credit_step(uint32_t *at, uint32_t rate, uint32_t truth,
                                   int mode, int tracking, int drift) {
    ap_sync_event_t event;
    const uint32_t hop = rate / 100u;
    fill(*at, rate, truth, mode);
    ap_sync_push_render(&credit_state, render, hop, *at / hop);
    ap_sync_track_delay(&credit_state, mic, hop, rate, 20u, tracking, drift, &event);
    *at += hop;
    return event;
}

static uint32_t credit_prepare(uint32_t rate) {
    const uint32_t initial = rate / 125u, hop = rate / 100u;
    uint32_t at = 0u, i;
    ap_sync_event_t event;
    ap_sync_init(&credit_state, initial);
    for (i = 0u; i < 20u; ++i) {
        fill(at, rate, initial, SIGNAL_MATCHED);
        ap_sync_push_render(&credit_state, render, hop, i);
        at += hop;
    }
    for (i = 0u; i < 10u; ++i)
        event = credit_step(&at, rate, initial, SIGNAL_MATCHED, 1, 1);
    assert(event.delay_observed && !event.route_jump);
    assert(credit_state.have_last_best_delay && credit_state.drift_credit == 0.0f);
    return at;
}

static void require_credit(uint32_t rate, float expected) {
    if (!isfinite(credit_state.drift_credit) ||
        fabsf(credit_state.drift_credit - expected) > 2.0e-6f) {
        fprintf(stderr, "credit rate=%u actual=%.9g expected=%.9g\n", rate,
                (double)credit_state.drift_credit, (double)expected);
        exit(EXIT_FAILURE);
    }
}

static void test_sparse_credit(uint32_t rate) {
    static const uint32_t intervals[] = {40u, 100u, 130u};
    static const int rejected[] = {SIGNAL_ZERO_MIC, SIGNAL_PERIODIC};
    uint32_t n, g, i;
    int sign;
    for (n = 0u; n < 3u; ++n) for (g = 0u; g < 2u; ++g)
        for (sign = -1; sign <= 1; sign += 2) {
            uint32_t at = credit_prepare(rate);
            const uint32_t initial = rate / 125u;
            ap_sync_event_t event;
            credit_state.drift_credit = (float)sign * 0.98f;
            for (i = 0u; i < intervals[n]; ++i) {
                event = credit_step(&at, rate, (uint32_t)((int32_t)initial + sign),
                    i < intervals[n] - 10u ? rejected[g] : SIGNAL_MATCHED, 1, 1);
                if (i + 1u < intervals[n]) assert(!event.delay_observed);
            }
            assert(event.delay_observed && !event.route_jump);
            /* One-sample lag innovation with alpha=0.05 contributes 0.05
             * sample of integrated credit, independent of the valid gap. */
            if (event.reference_sample_slips != 1u) {
                fprintf(stderr, "sparse credit rate=%u frames=%u sign=%d slips=%u credit=%.9g\n",
                        rate, intervals[n], sign, event.reference_sample_slips,
                        (double)credit_state.drift_credit);
                exit(EXIT_FAILURE);
            }
            assert(credit_state.delay_samples == (uint32_t)((int32_t)initial + sign));
            require_credit(rate, (float)sign * 0.03f);
        }
    for (sign = -1; sign <= 1; sign += 2) {
        uint32_t at = credit_prepare(rate);
        ap_sync_event_t event;
        credit_state.drift_ppm = (float)sign * 2000.0f;
        for (i = 0u; i < 100u; ++i)
            event = credit_step(&at, rate, rate / 125u,
                i < 90u ? SIGNAL_ZERO_MIC : SIGNAL_MATCHED, 1, 1);
        assert(event.delay_observed && event.reference_sample_slips == 4u);
        assert(fabsf(credit_state.drift_credit) > 1.0f);
    }
    for (g = 0u; g < 2u; ++g) {
        uint32_t at = credit_prepare(rate);
        ap_sync_event_t event;
        credit_state.drift_ppm = 17.0f;
        credit_state.drift_credit = 0.2f;
        for (i = 0u; i < 90u; ++i) {
            event = credit_step(&at, rate, rate / 125u, SIGNAL_ZERO_MIC, g == 0u, g != 0u);
            assert(!event.delay_observed && !event.reference_sample_slips);
            require_credit(rate, 0.2f);
        }
        for (i = 0u; i < 10u; ++i)
            event = credit_step(&at, rate, rate / 125u, SIGNAL_MATCHED, 1, 1);
        assert(event.delay_observed && !event.reference_sample_slips);
        assert(credit_state.drift_ppm == 17.0f);
        require_credit(rate, 0.2f + 17.0f * (float)rate / 10000000.0f);
    }
    printf("sparse credit rate=%u intervals=40/100/130 signs=both gaps=both cap/invalidation PASS\n", rate);
}

static void test_counter_boundaries(uint32_t rate) {
    static ap_sync_state_t state;
    const uint32_t hop = rate / 100u, initial = rate / 125u;
    uint32_t i;
    ap_sync_event_t event;
    /* White-box numeric boundary only: this is not a claim of a physical
     * stream lasting until uint64 rollover. Public cases above test timing. */
    ap_sync_init(&state, initial);
    state.capture_sample_rate_hz = rate;
    state.capture_total = UINT64_MAX - hop;
    state.last_best_capture_total = state.capture_total - hop;
    state.last_best_delay = initial;
    state.have_last_best_delay = 1u;
    state.drift_ppm = 17.0f;
    memset(mic, 0, sizeof(mic));
    ap_sync_track_delay(&state, mic, hop, rate, 20u, 1, 1, &event);
    assert(state.capture_total == UINT64_MAX && state.have_last_best_delay);
    ap_sync_track_delay(&state, mic, hop, rate, 20u, 1, 1, &event);
    assert(state.capture_total == hop && !state.have_last_best_delay);
    assert(state.last_best_capture_total == 0u);
    assert(state.delay_samples == initial && state.drift_ppm == 17.0f);
    assert(!event.delay_observed && !event.route_jump);

    /* A non-increasing observation coordinate must re-anchor, not divide by
     * zero or wrap an unsigned difference. Actual PCM still drives search. */
    ap_sync_init(&state, initial);
    for (i = 0u; i < 20u; ++i) {
        fill(i * hop, rate, initial, SIGNAL_MATCHED);
        ap_sync_push_render(&state, render, hop, i);
    }
    state.capture_sample_rate_hz = rate;
    state.capture_total = 1000u;
    state.last_best_capture_total = 1000u + hop;
    state.last_best_delay = initial - 1u;
    state.have_last_best_delay = 1u;
    state.delay_update_counter = 9u;
    state.drift_ppm = 17.0f;
    fill(20u * hop, rate, initial, SIGNAL_MATCHED);
    ap_sync_push_render(&state, render, hop, 20u);
    ap_sync_track_delay(&state, mic, hop, rate, 20u, 1, 1, &event);
    assert(event.delay_observed && !event.route_jump);
    assert(state.have_last_best_delay && state.last_best_delay == initial);
    assert(state.last_best_capture_total == state.capture_total);
    assert(state.drift_ppm == 17.0f);
    assert(state.drift_credit == 17.0f * (float)rate / 10000000.0f);
    for (i = 21u; i < 31u; ++i) {
        fill(i * hop, rate, initial + 1u, SIGNAL_MATCHED);
        ap_sync_push_render(&state, render, hop, i);
        ap_sync_track_delay(&state, mic, hop, rate, 20u, 1, 1, &event);
    }
    assert(event.delay_observed && !event.route_jump);
    require_ppm("counter re-anchor", rate, state.drift_ppm,
                0.95f * 17.0f + 500000.0f / (float)rate);
    printf("internal counter boundaries rate=%u PASS\n", rate);
}
#endif

int main(int argc, char **argv) {
    static const uint32_t rates[] = {16000u, 8000u};
    size_t i;
    const int only_elapsed = argc == 2 && strcmp(argv[1], "elapsed") == 0;
    const int only_continuous = (argc == 2 || argc == 3) && strcmp(argv[1], "continuous") == 0;
    const int only_credit = argc == 2 && strcmp(argv[1], "credit") == 0;
    if (argc > 3 || (argc == 3 && !only_continuous) ||
        (argc == 2 && !only_elapsed && !only_continuous && !only_credit)) return 2;
    if (argc == 3) { continuous_trace = fopen(argv[2], "wb"); assert(continuous_trace); }
    for (i = 0u; i < sizeof(rates) / sizeof(rates[0]); ++i) {
        const uint32_t rate = rates[i];
        if (rate > AP_BUILD_MAX_INTERNAL_RATE_HZ) continue;
        if (only_credit) {
#if defined(AP_SYNC_TEST_INTERNAL_COUNTERS)
            test_sparse_credit(rate);
            continue;
#else
            return 2;
#endif
        }
        if (!only_continuous) test_elapsed(rate);
        if (!only_elapsed) test_continuous(rate);
        if (only_elapsed || only_continuous) continue;
        test_reset_and_timestamp(rate);
        test_rejected_inputs(rate);
        test_disabled(rate);
        test_route(rate);
#if defined(AP_SYNC_TEST_INTERNAL_COUNTERS)
        test_counter_boundaries(rate);
        test_sparse_credit(rate);
#endif
    }
    if (!only_elapsed && !only_continuous && !only_credit && AP_BUILD_MAX_INTERNAL_RATE_HZ >= 16000u) {
        test_rate_change(8000u, 16000u);
        test_rate_change(16000u, 8000u);
    }
    if (continuous_trace) assert(fclose(continuous_trace) == 0);
    printf("SYNC_OBSERVATION_TIME_PASS state_bytes=%zu\n", ap_module_sync_state_size());
    return 0;
}
