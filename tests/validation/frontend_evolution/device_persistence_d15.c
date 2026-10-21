/* Research observer only. Scores never control the actual pipeline. */
#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ap_sync_init d15_unused_init
#define ap_sync_reset d15_unused_reset
#define ap_sync_push_render d15_unused_push_render
#define ap_sync_track_delay d15_unused_track_delay
#define ap_sync_observe_timestamps d15_unused_observe_timestamps
#define ap_sync_get_reference d15_unused_get_reference
#define ap_sync_note_capture d15_unused_note_capture
#define ap_sync_get_status d15_unused_get_status
#include "sync/ap_sync.c"
#undef ap_sync_init
#undef ap_sync_reset
#undef ap_sync_push_render
#undef ap_sync_track_delay
#undef ap_sync_observe_timestamps
#undef ap_sync_get_reference
#undef ap_sync_note_capture
#undef ap_sync_get_status

extern int d15_public_runner_main(int, char **);
extern void d15_real_ap_sync_track_delay(ap_sync_state_t *, const float *, uint32_t,
                                        uint32_t, uint32_t, int, int, ap_sync_event_t *);
static ap_sync_state_t saved, probe;
static float mono_history[800];
static uint64_t mono_total;
static FILE *trace, *mono_file, *render_file;
static uint32_t frame;
static int observe_enabled;

static void append_mono(const float *mic, uint32_t hop) {
    uint32_t i;
    assert(mono_total % 4u == 0u && hop % 4u == 0u);
    for (i = 0u; i < hop; i += 4u)
        mono_history[((mono_total + i) / 4u) % 800u] = mic[i];
    mono_total += hop;
}

static float context_score(const ap_sync_state_t *s, uint32_t rate,
                            uint32_t hop, uint32_t maximum, uint32_t delay,
                            uint32_t milliseconds) {
    const uint32_t window = rate * milliseconds / 1000u;
    const float unavailable = milliseconds == 40u ? 0.0f : -1.0f;
    float xy = 0.0f, xx = 1.0e-12f, yy = 1.0e-12f;
    uint32_t i;
    int64_t start;
    if ((rate != 8000u && rate != 16000u) || hop != rate / 100u ||
        mono_total != s->render_total || mono_total < window ||
        s->render_total < (uint64_t)(maximum + window) ||
        maximum + window > AP_RENDER_CAP || window / 4u > 800u ||
        mono_total % 4u != 0u || delay > maximum) return unavailable;
    start = (int64_t)s->render_total - (int64_t)window - (int64_t)delay;
    for (i = 0u; i < window; i += 4u) {
        const float x = ap_sync_render_absolute(s, start + (int64_t)i);
        const float y = mono_history[((mono_total - window + i) / 4u) % 800u];
        xy += x * y; xx += x * x; yy += y * y;
    }
    return (xy * xy) / (xx * yy);
}

static void self_test(void) {
    static float all[9600];
    float mic[160];
    uint32_t at, i, rng = 19u;
    double xy = 0.0, xx = 1.0e-12, yy = 1.0e-12;
    d15_unused_init(&probe, 0u);
    mono_total = 0u;
    assert(context_score(&probe, 16000u, 160u, 4800u, 0u, 200u) == -1.0f);
    for (at = 0u; at < 9600u; at += 160u) {
        for (i = 0u; i < 160u; ++i) {
            rng = rng * 1664525u + 1013904223u;
            all[at + i] = mic[i] = (float)(rng >> 8u) / 16777216.0f - 0.5f;
        }
        d15_unused_push_render(&probe, mic, 160u, at / 160u);
        append_mono(mic, 160u);
        if (at + 160u < 8000u)
            assert(context_score(&probe, 16000u, 160u, 4800u, 0u, 200u) == -1.0f);
        else assert(context_score(&probe, 16000u, 160u, 4800u, 0u, 200u) > 0.99999f);
    }
    for (i = 6400u; i < 9600u; i += 4u) {
        const double x = all[i - 4u], y = all[i];
        xy += x * y; xx += x * x; yy += y * y;
    }
    assert(fabs((double)context_score(&probe, 16000u, 160u, 4800u, 4u, 200u) - xy * xy / (xx * yy)) < 1.0e-6);
    probe.render_total--;
    assert(context_score(&probe, 16000u, 160u, 4800u, 0u, 200u) == -1.0f);
    d15_unused_reset(&probe);
    mono_total = 0u;
    memset(mono_history, 0, sizeof(mono_history));
    assert(context_score(&probe, 16000u, 160u, 4800u, 0u, 200u) == -1.0f);
    assert(context_score(&probe, 16000u, 160u, 4800u, 0u, 40u) == 0.0f);
    puts("D15_CONTEXT_SELF_TEST_PASS ring800 boundary pairing reset independent_linear");
}

void ap_sync_track_delay(ap_sync_state_t *s, const float *mic, uint32_t hop,
                         uint32_t rate, uint32_t maximum_ms, int tracking,
                         int drift, ap_sync_event_t *event) {
    const uint32_t maximum = maximum_ms * rate / 1000u;
    const uint32_t step = rate / 1000u ? rate / 1000u : 1u;
    const uint32_t tolerance = step / D15_TOLERANCE_DIVISOR ? step / D15_TOLERANCE_DIVISOR : 1u;
    const uint32_t old = s->delay_samples, before = s->route_candidate_confirmations;
    const uint32_t anchor = s->route_candidate_delay, counter = s->delay_update_counter;
    const int eligible = observe_enabled && tracking && s->render_total >= (uint64_t)(maximum + hop) && counter == 9u;
    ap_sync_coarse_peak_t peaks[AP_SYNC_UNIQUENESS_PEAKS];
    uint32_t count = 0u, coarse = old, refined = old, d, lo = 0u, hi = 0u;
    float best = 0.0f, history = -1.0f, old_history = -1.0f, old_short = -1.0f;
    float scores[3][3];
    const uint32_t windows[3] = {40u, 100u, 200u};
    const uint16_t endian = 1u;
    assert(sizeof(float) == 4u && *(const unsigned char *)&endian == 1u);
    assert(mono_total == s->route_mic_total && hop == rate / 100u);
    memcpy(&saved, s, sizeof(saved));
    for (d = 0u; d < hop; d += 4u) assert(fwrite(mic + d, sizeof(float), 1u, mono_file) == 1u);
    for (d = 0u; d < hop; ++d) {
        const float x = ap_sync_render_absolute(s, (int64_t)s->render_total - (int64_t)hop + d);
        assert(fwrite(&x, sizeof(float), 1u, render_file) == 1u);
    }
    append_mono(mic, hop);
    for (d = 0u; d < 9u; ++d) scores[d / 3u][d % 3u] = -1.0f;
    if (eligible) {
        memcpy(&probe, s, sizeof(probe));
        for (d = 0u; d < hop; d += 4u)
            probe.route_mic_history[((probe.route_mic_total + d) / 4u) % AP_SYNC_ROUTE_HISTORY_VALUES] = mic[d];
        probe.route_mic_total += hop;
        for (d = 0u; d <= maximum; d += step) {
            const float score = ap_sync_delay_score(&probe, mic, hop, d, 4u);
            ap_sync_record_coarse_peak(peaks, &count, d, score);
            if (score > best) { best = score; coarse = d; }
        }
        lo = coarse > step ? coarse - step : 0u;
        hi = coarse + step < maximum ? coarse + step : maximum;
        refined = coarse;
        for (d = lo; d <= hi; ++d) {
            const float score = ap_sync_delay_score(&probe, mic, hop, d, 4u);
            if (score > best) { best = score; refined = d; }
        }
        history = ap_sync_route_history_score(&probe, rate, hop, maximum, refined);
        old_history = ap_sync_route_history_score(&probe, rate, hop, maximum, old);
        old_short = ap_sync_delay_score(&probe, mic, hop, old, 4u);
        for (d = 0u; d < 3u; ++d) {
            scores[d][0] = context_score(&probe, rate, hop, maximum, refined, windows[d]);
            scores[d][1] = context_score(&probe, rate, hop, maximum, old, windows[d]);
            if (before > 0u) scores[d][2] = context_score(&probe, rate, hop, maximum, anchor, windows[d]);
            { uint32_t j; for (j = 0u; j < 3u; ++j) assert(isfinite(scores[d][j]) && scores[d][j] >= -1.0f && scores[d][j] <= 1.00001f); }
        }
        assert(scores[0][0] == history && scores[0][1] == old_history);
    }
    assert(memcmp(&saved, s, sizeof(saved)) == 0);
    d15_real_ap_sync_track_delay(s, mic, hop, rate, maximum_ms, tracking, drift, event);
    if (eligible) {
        const uint32_t distance = ap_sync_distance(refined, old);
        if (best < AP_SYNC_MIN_CORRELATION_SQUARED || distance <= rate / 50u || history < AP_SYNC_MIN_CORRELATION_SQUARED)
            assert(s->route_candidate_confirmations == 0u && !event->route_jump);
        else if (before == 0u || ap_sync_distance(refined, anchor) > tolerance)
            assert(s->route_candidate_confirmations == 1u && s->route_candidate_delay == refined && !event->route_jump);
        else if (before == 1u)
            assert(s->route_candidate_confirmations == 2u && s->route_candidate_delay == anchor && !event->route_jump);
        else assert(before == 2u && s->route_candidate_confirmations == 0u && event->route_jump && s->delay_samples == anchor);
        if (best >= AP_SYNC_MIN_CORRELATION_SQUARED) assert(event->delay_error_samples == (int32_t)refined - (int32_t)old);
    }
    assert(fprintf(trace, "%u,%" PRIu64 ",%" PRIu64 ",%u,%u,%u,%u,%u,%u,%u,%.9g,%.9g,%.9g,%u,%u,%u,%u,%u,%u,%u,%u,%d",
        frame++, mono_total, s->render_total, old, s->delay_samples, counter, (uint32_t)eligible, tolerance, coarse, refined,
        (double)best, (double)history, (double)old_short, before, anchor, (uint32_t)(before > 0u),
        (uint32_t)s->route_candidate_confirmations, s->route_candidate_delay, (uint32_t)event->delay_observed,
        (uint32_t)event->route_jump, event->reference_sample_slips, event->delay_error_samples) > 0);
    for (d = 0u; d < 3u; ++d)
        assert(fprintf(trace, ",%.9g,%.9g,%.9g", (double)scores[d][0], (double)scores[d][1], (double)scores[d][2]) > 0);
    assert(fputc('\n', trace) != EOF);
}

int main(int argc, char **argv) {
    int result;
    if (argc == 2 && strcmp(argv[1], "--self-test") == 0) { self_test(); return 0; }
    if (argc != 10 || (strcmp(argv[7], "observe") != 0 && strcmp(argv[7], "no-observe") != 0)) return 2;
    observe_enabled = strcmp(argv[7], "observe") == 0;
    trace = fopen(argv[6], "wb"); mono_file = fopen(argv[8], "wb"); render_file = fopen(argv[9], "wb");
    if (!trace || !mono_file || !render_file) return 4;
    assert(fprintf(trace, "frame,mic_total,render_total,old_samples,new_samples,counter_before,eligible,tolerance,coarse,refined,short_score,history_score,old_short_score,confirm_before,anchor_before,anchor_valid,confirm_after,anchor_after,observed,route_jump,slips,error_samples,history40_new,history40_old,history40_anchor,history100_new,history100_old,history100_anchor,history200_new,history200_old,history200_anchor\n") > 0);
    result = d15_public_runner_main(6, argv);
    if (fclose(trace) != 0 || fclose(mono_file) != 0 || fclose(render_file) != 0) return 9;
    return result;
}
