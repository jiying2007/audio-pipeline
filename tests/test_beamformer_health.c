#include "audio_pipeline/audio_modules.h"
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include "frontend/ap_frontend.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Frozen engineering controls, not acoustic/KWS or physical-target evidence.
 * This file also builds against 438fe09: its behavioral failure is the base
 * counterexample, and --legacy-trace compares the unchanged tracking path. */
#define FRAME_MAX 160u
#define PI_D 3.14159265358979323846
#define LEGACY_BYTES (offsetof(ap_beamformer_state_t, fallback_hard_arm_count) + \
                      sizeof(((ap_beamformer_state_t *)0)->fallback_hard_arm_count))

static unsigned failures;
static unsigned checks;

#define CHECK(condition, label) do { \
    ++checks; \
    if (!(condition)) { \
        if (failures < 32u) fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, label); \
        ++failures; \
    } \
} while (0)

typedef struct direction_snapshot {
    int lag;
    uint32_t counter;
    uint32_t score_updates;
    float scores[AP_BF_LAG_SCORE_COUNT];
} direction_snapshot_t;

typedef enum signal_case {
    SIGNAL_CLEAN, SIGNAL_HARD0, SIGNAL_HARD1, SIGNAL_GAIN0, SIGNAL_GAIN1,
    SIGNAL_WEAK0, SIGNAL_WEAK1, SIGNAL_VERY_WEAK0, SIGNAL_VERY_WEAK1,
    SIGNAL_DELAY_POS, SIGNAL_DELAY_NEG, SIGNAL_MOTION, SIGNAL_NOISE,
    SIGNAL_SILENCE, SIGNAL_QUIET, SIGNAL_ZERO0, SIGNAL_ZERO1,
    SIGNAL_RAIL0, SIGNAL_RAIL1, SIGNAL_POLARITY
} signal_case_t;

static uint32_t xorshift32(uint32_t *state) {
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static float noise_sample(uint32_t *state) {
    return 0.06f * ((float)(xorshift32(state) >> 8) / 8388608.0f - 1.0f);
}

static float clean_sample(int64_t sample, uint32_t rate) {
    const double t = (double)sample / (double)rate;
    return (float)(0.045 * sin(2.0 * PI_D * 1400.0 * t) +
                   0.020 * sin(2.0 * PI_D * 2100.0 * t) +
                   0.010 * sin(2.0 * PI_D * 3200.0 * t));
}

static void fill_frame(float *a, float *b, uint32_t rate, uint32_t frame,
                       signal_case_t kind, uint32_t *rng0, uint32_t *rng1) {
    const uint32_t n = rate / 100u;
    const int delay = rate == 8000u ? 1 : 3;
    uint32_t i;
    for (i = 0u; i < n; ++i) {
        const int64_t sample = (int64_t)frame * n + i;
        const double t = (double)sample / rate;
        const float clean = clean_sample(sample, rate);
        const float bad = (float)(0.24 * sin(2.0 * PI_D * 120.0 * t)) + 0.05f * clean;
        a[i] = b[i] = clean;
        switch (kind) {
        case SIGNAL_HARD0: a[i] = bad; break;
        case SIGNAL_HARD1: b[i] = bad; break;
        case SIGNAL_GAIN0: a[i] *= 0.75f; break;
        case SIGNAL_GAIN1: b[i] *= 0.75f; break;
        case SIGNAL_WEAK0: a[i] *= 0.25f; break;
        case SIGNAL_WEAK1: b[i] *= 0.25f; break;
        case SIGNAL_VERY_WEAK0: a[i] *= 0.10f; break;
        case SIGNAL_VERY_WEAK1: b[i] *= 0.10f; break;
        case SIGNAL_DELAY_POS: b[i] = clean_sample(sample - delay, rate); break;
        case SIGNAL_DELAY_NEG: a[i] = clean_sample(sample - delay, rate); break;
        case SIGNAL_MOTION:
            if ((frame / 12u) % 3u == 0u) b[i] = clean_sample(sample - delay, rate);
            else if ((frame / 12u) % 3u == 2u) a[i] = clean_sample(sample - delay, rate);
            break;
        case SIGNAL_NOISE:
            a[i] = noise_sample(rng0);
            b[i] = noise_sample(rng1);
            break;
        case SIGNAL_SILENCE: a[i] = b[i] = 0.0f; break;
        case SIGNAL_QUIET:
            a[i] = bad * (0.5f / (32768.0f * 0.25f));
            b[i] = clean * (0.5f / (32768.0f * 0.25f));
            break;
        case SIGNAL_ZERO0: a[i] = 0.0f; break;
        case SIGNAL_ZERO1: b[i] = 0.0f; break;
        case SIGNAL_RAIL0: a[i] = 0.95f; break;
        case SIGNAL_RAIL1: b[i] = 0.95f; break;
        case SIGNAL_POLARITY: b[i] = -clean; break;
        case SIGNAL_CLEAN: break;
        }
    }
}

static void maybe_hpf(ap_hpf_state_t *hpf, int use_hpf, float *a, float *b,
                      uint32_t n) {
#if AP_HAVE_MODULE_HPF
    if (use_hpf) {
        ap_hpf_process(hpf, a, n, 0u);
        ap_hpf_process(hpf, b, n, 1u);
    }
#else
    (void)hpf; (void)use_hpf; (void)a; (void)b; (void)n;
#endif
}

static void init_hpf(ap_hpf_state_t *hpf, uint32_t rate) {
#if AP_HAVE_MODULE_HPF
    ap_hpf_init(hpf, rate, 2u);
#else
    (void)hpf; (void)rate;
#endif
}

static direction_snapshot_t direction_snapshot(const ap_beamformer_state_t *s) {
    direction_snapshot_t result;
    result.lag = s->lag;
    result.counter = s->counter;
    result.score_updates = s->score_updates;
    memcpy(result.scores, s->lag_score, sizeof(result.scores));
    return result;
}

static void check_direction(const ap_beamformer_state_t *s,
                            const direction_snapshot_t *saved) {
    CHECK(s->lag == saved->lag, "fixed lag unchanged");
    CHECK(s->counter == saved->counter, "tracking cadence unchanged while fixed");
    CHECK(s->score_updates == saved->score_updates, "tracking update count unchanged");
    CHECK(memcmp(s->lag_score, saved->scores, sizeof(saved->scores)) == 0,
          "tracking scores unchanged");
}

static float prior_sample(const ap_beamformer_state_t *before, const float *x,
                           unsigned ch, int index) {
    return index >= 0 ? x[index] : before->history[ch][(int)AP_BF_HISTORY + index];
}

static float route_sample(const ap_beamformer_state_t *route,
                           const ap_beamformer_state_t *history,
                           const float *a, const float *b, uint32_t i) {
    const int lag = route->fallback_active ? route->fallback_lag : route->lag;
    const float x = prior_sample(history, a, 0u, (int)i + (lag < 0 ? lag : 0));
    const float y = prior_sample(history, b, 1u, (int)i - (lag > 0 ? lag : 0));
    if (route->fallback_active && route->fallback_hard_fault)
        return route->fallback_strong_channel == 0u ? x : y;
    return 0.5f * (x + y);
}

static void check_complete_output(const float *out, uint32_t n) {
    uint32_t i;
    for (i = 0u; i < n; ++i) CHECK(isfinite(out[i]), "complete finite output frame");
}

/* Independent double-precision input check for the frozen HPF recovery origin.
 * Expected frame numbers below are constants, never derived from DSP state. */
static int input_has_recovery_evidence(const ap_beamformer_state_t *history,
                                       int lag, const float *a, const float *b,
                                       uint32_t n) {
    double aa = 0.0, bb = 0.0;
    double ea = 1.0e-12, eb = 1.0e-12, da = 1.0e-12, db = 1.0e-12;
    double ra, rb, ratio;
    uint32_t i;
    for (i = 0u; i < n; ++i) {
        ea += (double)a[i] * a[i];
        eb += (double)b[i] * b[i];
        if (i > 0u) {
            const double xa = (double)a[i] - a[i - 1u];
            const double xb = (double)b[i] - b[i - 1u];
            da += xa * xa;
            db += xb * xb;
        }
        if ((i & 1u) == 0u) {
            const double x = prior_sample(history, a, 0u, (int)i + (lag < 0 ? lag : 0));
            const double y = prior_sample(history, b, 1u, (int)i - (lag > 0 ? lag : 0));
            aa += x * x;
            bb += y * y;
        }
    }
    if (aa <= (double)((n + 1u) / 2u) / (32768.0 * 32768.0) ||
        bb <= (double)((n + 1u) / 2u) / (32768.0 * 32768.0)) return 0;
    ratio = sqrt(fmin(aa, bb) / fmax(aa, bb));
    ra = da / ea;
    rb = db / eb;
    return ratio > 0.52 && (aa >= bb ? ra > 0.60 * rb : rb > 0.60 * ra);
}

static void test_negative_controls(uint32_t rate, int use_hpf) {
    static const signal_case_t cases[] = {
        SIGNAL_CLEAN, SIGNAL_GAIN0, SIGNAL_GAIN1, SIGNAL_WEAK0, SIGNAL_WEAK1,
        SIGNAL_VERY_WEAK0, SIGNAL_VERY_WEAK1, SIGNAL_DELAY_POS, SIGNAL_DELAY_NEG,
        SIGNAL_MOTION, SIGNAL_NOISE, SIGNAL_SILENCE, SIGNAL_QUIET,
        SIGNAL_ZERO0, SIGNAL_ZERO1, SIGNAL_RAIL0, SIGNAL_RAIL1, SIGNAL_POLARITY
    };
    const uint32_t n = rate / 100u;
    size_t c;
    int lag;
    for (c = 0u; c < sizeof(cases) / sizeof(cases[0]); ++c) {
        for (lag = -1; lag <= 1; ++lag) {
            ap_beamformer_state_t s;
            ap_hpf_state_t hpf;
            float a[FRAME_MAX], b[FRAME_MAX], out[FRAME_MAX];
            uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu;
            uint32_t frame, i;
            direction_snapshot_t saved;
            ap_beamformer_init(&s, rate, 70.0f);
            init_hpf(&hpf, rate);
            s.lag = lag;
            s.score_updates = 17u;
            for (i = 0u; i < AP_BF_LAG_SCORE_COUNT; ++i) s.lag_score[i] = (float)i * 0.01f;
            saved = direction_snapshot(&s);
            for (frame = 0u; frame < 96u; ++frame) {
                const ap_beamformer_state_t before = s;
                fill_frame(a, b, rate, frame, cases[c], &rng0, &rng1);
                maybe_hpf(&hpf, use_hpf, a, b, n);
                for (i = 0u; i < n; ++i) out[i] = NAN;
                ap_beamformer_process(&s, 0, a, b, out, n);
                check_direction(&s, &saved);
                CHECK(s.fallback_active == 0u && s.fallback_hard_fault == 0u,
                      "fixed negative control stays equal-weight");
                for (i = 0u; i < n; ++i)
                    CHECK(out[i] == route_sample(&before, &before, a, b, i),
                          "negative control output equals original fixed route");
                check_complete_output(out, n);
            }
        }
    }
}

static void test_hard_and_recovery(uint32_t rate, int use_hpf, unsigned bad_ch,
                                  int lag) {
    ap_beamformer_state_t s;
    ap_hpf_state_t hpf;
    direction_snapshot_t saved;
    const uint32_t n = rate / 100u;
    float a[FRAME_MAX], b[FRAME_MAX], out[FRAME_MAX];
    float previous_last = 0.0f;
    double entry_added_step = 0.0, recovery_added_step = 0.0;
    double entry_boundary = 0.0, recovery_boundary = 0.0;
    double fault_output_energy = 0.0, recovery_output_energy = 0.0;
    uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu;
    uint32_t frame, i, entry = UINT32_MAX, recovery = UINT32_MAX;
    uint32_t first_valid_recovery = UINT32_MAX;
    const uint32_t expected_first_valid = use_hpf ? 84u : 80u;
    const uint32_t expected_recovery = use_hpf ? 112u : 108u;
    ap_beamformer_init(&s, rate, 70.0f);
    init_hpf(&hpf, rate);
    s.lag = lag;
    saved = direction_snapshot(&s);
    for (frame = 0u; frame < 128u; ++frame) {
        const ap_beamformer_state_t before = s;
        const signal_case_t kind = frame >= 20u && frame < 80u ?
            (bad_ch == 0u ? SIGNAL_HARD0 : SIGNAL_HARD1) : SIGNAL_CLEAN;
        fill_frame(a, b, rate, frame, kind, &rng0, &rng1);
        maybe_hpf(&hpf, use_hpf, a, b, n);
        if (frame >= 80u && (frame & 3u) == 0u) {
            const int valid = input_has_recovery_evidence(&before, lag, a, b, n);
            CHECK(valid == (frame >= expected_first_valid),
                  "frozen raw/HPF input recovery qualification");
            if (valid && first_valid_recovery == UINT32_MAX) first_valid_recovery = frame;
        }
        for (i = 0u; i < n; ++i) out[i] = NAN;
        ap_beamformer_process(&s, 0, a, b, out, n);
        check_direction(&s, &saved);
        check_complete_output(out, n);
        if (frame >= 80u) {
            const uint32_t expected_count = frame < expected_first_valid || frame >= expected_recovery ?
                0u : (frame - expected_first_valid) / 4u + 1u;
            CHECK(s.fallback_recovery_count == expected_count,
                  "frozen sequence counts exactly eight valid recovery observations");
        }
        if (frame < 20u) CHECK(!s.fallback_active, "healthy prefix does not arm");
        if (s.fallback_hard_fault) {
            if (entry == UINT32_MAX) {
                entry = frame;
                entry_added_step = (double)out[0] - route_sample(&before, &before, a, b, 0u);
                entry_boundary = (double)out[0] - previous_last;
            }
            CHECK(s.fallback_active, "hard mode is active");
            CHECK(s.fallback_strong_channel == 1u - bad_ch, "select the reliable weak channel");
            CHECK(s.fallback_lag == lag, "hard mode preserves frozen steering");
            for (i = 0u; i < n; ++i)
                CHECK(out[i] == route_sample(&s, &before, a, b, i), "hard output is selected input");
        } else if (entry != UINT32_MAX && recovery == UINT32_MAX) {
            recovery = frame;
            recovery_added_step = (double)out[0] - route_sample(&before, &before, a, b, 0u);
            recovery_boundary = (double)out[0] - previous_last;
        }
        for (i = 0u; i < n; ++i) {
            if (frame >= 32u && frame < 80u) fault_output_energy += (double)out[i] * out[i];
            if (frame >= 112u) recovery_output_energy += (double)out[i] * out[i];
        }
        previous_last = out[n - 1u];
    }
    CHECK(entry >= 20u && entry < 28u, "sustained hard signature confirms within eight frames");
    CHECK(first_valid_recovery == expected_first_valid, "independent first recovery observation");
    CHECK(recovery == expected_recovery, "eighth frozen valid observation releases hard route");
    CHECK(recovery - 80u + 1u == (use_hpf ? 33u : 29u),
          "raw recovery latency includes HPF transient rather than hiding it");
    CHECK(!s.fallback_active && !s.fallback_hard_fault, "hard route releases after recovery");
    printf("hard rate=%u hpf=%d bad=%u lag=%d entry=%u recovery=%u first_valid_recovery=%u "
           "raw_recovery_frames=%u "
           "entry_added_step=%.9g recovery_added_step=%.9g "
           "entry_boundary=%.9g recovery_boundary=%.9g fault_rms=%.9g recovered_rms=%.9g\n",
           rate, use_hpf, bad_ch, lag, entry, recovery, first_valid_recovery,
           recovery == UINT32_MAX ? UINT32_MAX : recovery - 80u + 1u,
           entry_added_step, recovery_added_step,
           entry_boundary, recovery_boundary, sqrt(fault_output_energy / (48u * n)),
           sqrt(recovery_output_energy / (16u * n)));
}

static int prime_fixed_hard(ap_beamformer_state_t *s, uint32_t rate) {
    float a[FRAME_MAX], b[FRAME_MAX], out[FRAME_MAX];
    uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu, frame;
    ap_beamformer_init(s, rate, 70.0f);
    for (frame = 0u; frame < 8u; ++frame) {
        fill_frame(a, b, rate, frame, SIGNAL_HARD0, &rng0, &rng1);
        ap_beamformer_process(s, 0, a, b, out, rate / 100u);
    }
    CHECK(s->fallback_hard_fault == 1u, "fixed-mode hard setup reached confirmation");
    return s->fallback_hard_fault != 0u;
}

static void test_confirmation_and_silence(uint32_t rate) {
    ap_beamformer_state_t s;
    float a[FRAME_MAX], b[FRAME_MAX], out[FRAME_MAX];
    uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu;
    const uint32_t n = rate / 100u;
    uint32_t frame, i;
    ap_beamformer_init(&s, rate, 70.0f);
    for (frame = 0u; frame < 40u; ++frame) {
        fill_frame(a, b, rate, frame,
                   (frame / 4u) % 2u == 0u ? SIGNAL_HARD0 : SIGNAL_HARD1, &rng0, &rng1);
        ap_beamformer_process(&s, 0, a, b, out, n);
        CHECK(!s.fallback_hard_fault && !s.fallback_active, "alternating targets cannot confirm");
    }
    ap_beamformer_init(&s, rate, 70.0f);
    for (frame = 0u; frame < 20u; ++frame) {
        fill_frame(a, b, rate, frame, frame == 0u ? SIGNAL_HARD0 : SIGNAL_CLEAN, &rng0, &rng1);
        ap_beamformer_process(&s, 0, a, b, out, n);
        CHECK(!s.fallback_hard_fault && !s.fallback_active, "one hard observation cannot confirm");
    }
    if (!prime_fixed_hard(&s, rate)) return;
    for (frame = 8u; frame < 36u; ++frame) {
        fill_frame(a, b, rate, frame, SIGNAL_CLEAN, &rng0, &rng1);
        ap_beamformer_process(&s, 0, a, b, out, n);
        CHECK(s.fallback_hard_fault, "seven recovery observations do not release");
    }
    CHECK(s.fallback_recovery_count == 7u, "seven valid recovery observations counted");
    for (frame = 36u; frame < 52u; ++frame) {
        fill_frame(a, b, rate, frame, SIGNAL_SILENCE, &rng0, &rng1);
        ap_beamformer_process(&s, 0, a, b, out, n);
        CHECK(s.fallback_hard_fault && s.fallback_strong_channel == 1u,
              "silence preserves confirmed route");
        CHECK(s.fallback_recovery_count == 0u && s.fallback_hard_arm_count == 0u,
              "silence clears consecutive evidence");
        for (i = 0u; i < n; ++i) CHECK(out[i] == 0.0f, "silence does not generate sound");
    }
    for (frame = 52u; frame < 68u; ++frame) {
        fill_frame(a, b, rate, frame, SIGNAL_QUIET, &rng0, &rng1);
        ap_beamformer_process(&s, 0, a, b, out, n);
        CHECK(s.fallback_hard_fault && s.fallback_recovery_count == 0u,
              "sub-LSB observation does not recover");
    }
    for (frame = 68u; frame <= 96u; ++frame) {
        fill_frame(a, b, rate, frame, SIGNAL_CLEAN, &rng0, &rng1);
        ap_beamformer_process(&s, 0, a, b, out, n);
        CHECK(s.fallback_hard_fault == (frame < 96u ? 1u : 0u),
              "recovery restarts after an invalid observation");
    }
    ap_beamformer_init(&s, rate, 70.0f);
    CHECK(!s.fallback_active && !s.fallback_hard_fault && s.fallback_gain == 1.0f,
          "reset clears fallback");
}

static void test_one_lsb_boundary(uint32_t rate) {
    const float lsb = 1.0f / 32768.0f;
    const uint32_t n = rate / 100u;
    uint32_t factor;
    for (factor = 1u; factor <= 2u; ++factor) {
        ap_beamformer_state_t s;
        float a[FRAME_MAX], b[FRAME_MAX], out[FRAME_MAX];
        uint32_t frame, i;
        ap_beamformer_init(&s, rate, 70.0f);
        for (frame = 0u; frame < 8u; ++frame) {
            for (i = 0u; i < n; ++i) {
                const double t = (double)(frame * n + i) / rate;
                a[i] = (float)(12.0 * lsb * sin(2.0 * PI_D * 120.0 * t));
                b[i] = (i & 1u) ? -(float)factor * lsb : (float)factor * lsb;
            }
            ap_beamformer_process(&s, 0, a, b, out, n);
            check_complete_output(out, n);
        }
        CHECK(s.fallback_hard_fault == (factor == 1u ? 0u : 1u),
              "one-LSB RMS is ineligible; above-floor signature may confirm");
    }
}

static void test_mode_switch(uint32_t rate) {
    ap_beamformer_state_t s;
    direction_snapshot_t saved;
    float a[FRAME_MAX], b[FRAME_MAX], out[FRAME_MAX];
    const uint32_t n = rate / 100u;
    uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu, frame, i;
    ap_beamformer_init(&s, rate, 70.0f);
    for (frame = 0u; frame < 32u; ++frame) {
        fill_frame(a, b, rate, frame, SIGNAL_HARD0, &rng0, &rng1);
        ap_beamformer_process(&s, 1, a, b, out, n);
    }
    CHECK(s.fallback_hard_fault, "original tracking path confirms hard input");
    saved = direction_snapshot(&s);
    for (frame = 32u; frame < 48u; ++frame) {
        fill_frame(a, b, rate, frame, SIGNAL_HARD0, &rng0, &rng1);
        ap_beamformer_process(&s, 0, a, b, out, n);
        CHECK(s.fallback_hard_fault && s.fallback_strong_channel == 1u,
              "turning tracking off retains confirmed hard state");
        check_direction(&s, &saved);
        check_complete_output(out, n);
    }
    fill_frame(a, b, rate, 48u, SIGNAL_HARD0, &rng0, &rng1);
    ap_beamformer_process(&s, 1, a, b, out, n);
    CHECK(s.fallback_hard_fault && s.fallback_strong_channel == 1u,
          "turning tracking on does not clear hard state");
    CHECK(s.counter == saved.counter + 1u, "tracking resumes its original cadence");

    ap_beamformer_init(&s, rate, 70.0f);
    s.fallback_active = 1u;
    s.fallback_hard_fault = 0u;
    s.fallback_hard_arm_count = 1u;
    s.fallback_strong_channel = 0u;
    s.fallback_gain = 0.8f;
    s.lag = 1;
    s.fallback_lag = -1;
    fill_frame(a, b, rate, 0u, SIGNAL_CLEAN, &rng0, &rng1);
    {
        ap_beamformer_state_t expected_route = s;
        const ap_beamformer_state_t before = s;
        expected_route.fallback_active = 0u;
        ap_beamformer_process(&s, 0, a, b, out, n);
        CHECK(!s.fallback_active && !s.fallback_hard_fault && !s.fallback_hard_arm_count,
              "unconfirmed soft route is not carried into fixed mode");
        for (i = 0u; i < n; ++i)
            CHECK(out[i] == route_sample(&expected_route, &before, a, b, i),
                  "soft-to-fixed output uses held steering");
    }
}

static void test_pending_mode_epoch(uint32_t rate) {
    static const uint32_t gaps[] = {1u, 4u};
    const uint32_t n = rate / 100u;
    size_t gap_index;
    unsigned next_bad;
    for (gap_index = 0u; gap_index < sizeof(gaps) / sizeof(gaps[0]); ++gap_index) {
        for (next_bad = 0u; next_bad < 2u; ++next_bad) {
            ap_beamformer_state_t s;
            float a[FRAME_MAX], b[FRAME_MAX], out[FRAME_MAX];
            uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu;
            uint32_t frame = 0u, i;
            ap_beamformer_init(&s, rate, 70.0f);
            fill_frame(a, b, rate, frame++, SIGNAL_CLEAN, &rng0, &rng1);
            ap_beamformer_process(&s, 1, a, b, out, n);
            CHECK(s.counter == 4u, "establish a tracking interval with no next-frame update");
            fill_frame(a, b, rate, frame++, SIGNAL_HARD0, &rng0, &rng1);
            ap_beamformer_process(&s, 0, a, b, out, n);
            CHECK(s.fallback_hard_arm_count == 1u && !s.fallback_hard_fault,
                  "one fixed observation is pending before mode change");
            for (i = 0u; i < gaps[gap_index]; ++i) {
                fill_frame(a, b, rate, frame++, SIGNAL_CLEAN, &rng0, &rng1);
                ap_beamformer_process(&s, 1, a, b, out, n);
                CHECK(!s.fallback_hard_arm_count && !s.fallback_hard_fault,
                      "tracking interval invalidates unfinished fixed confirmation");
            }
            for (i = 0u; i < 4u; ++i) {
                fill_frame(a, b, rate, frame++, next_bad == 0u ? SIGNAL_HARD0 : SIGNAL_HARD1,
                           &rng0, &rng1);
                ap_beamformer_process(&s, 0, a, b, out, n);
                CHECK(!s.fallback_hard_fault, "return to fixed requires two fresh observations");
                check_complete_output(out, n);
            }
            for (i = 0u; i < 4u; ++i) {
                fill_frame(a, b, rate, frame++, next_bad == 0u ? SIGNAL_HARD0 : SIGNAL_HARD1,
                           &rng0, &rng1);
                ap_beamformer_process(&s, 0, a, b, out, n);
            }
            CHECK(s.fallback_hard_fault && s.fallback_strong_channel == 1u - next_bad,
                  "new fixed epoch confirms only its own consistent target");
        }
    }
}

static void test_fixed_cadence_reinitialization(uint32_t rate) {
    static const uint32_t invalid_phases[] = {0u, 2u, 8u, UINT32_MAX};
    ap_beamformer_state_t s;
    float a[FRAME_MAX] = {0}, b[FRAME_MAX] = {0}, out[FRAME_MAX];
    size_t i;
    /* Keep this counterexample executable against the old struct as well.
     * Only the candidate has the append-only cadence field after the legacy
     * prefix. Byte access avoids depending on a missing baseline member. */
    if (sizeof(s) == LEGACY_BYTES) return;
    CHECK(sizeof(s) == LEGACY_BYTES + sizeof(uint32_t), "only one private uint32 was appended");
    for (i = 0u; i < sizeof(invalid_phases) / sizeof(invalid_phases[0]); ++i) {
        uint32_t phase;
        ap_beamformer_init(&s, rate, 70.0f);
        s.fallback_active = 1u;
        s.fallback_hard_fault = 1u;
        s.fallback_strong_channel = 1u;
        s.fallback_hard_arm_count = 1u;
        s.fallback_recovery_count = 7u;
        memcpy((unsigned char *)&s + LEGACY_BYTES, &invalid_phases[i], sizeof(uint32_t));
        ap_beamformer_process(&s, 0, a, b, out, rate / 100u);
        memcpy(&phase, (const unsigned char *)&s + LEGACY_BYTES, sizeof(phase));
        CHECK(phase == 4u, "invalid private cadence starts a bounded fixed epoch");
        CHECK(s.fallback_active && s.fallback_hard_fault && s.fallback_strong_channel == 1u,
              "cadence restart preserves confirmed hard routing");
        CHECK(!s.fallback_hard_arm_count && !s.fallback_recovery_count,
              "cadence restart cannot reuse incomplete evidence");
        check_complete_output(out, rate / 100u);
    }
}

#if AP_HAVE_PIPELINE
static _Alignas(AP_PIPELINE_STATE_ALIGNMENT) unsigned char pipeline_memory[AP_PIPELINE_STATE_MAX_BYTES];

static void test_pipeline_quality(uint32_t rate, ap_profile_t profile) {
    ap_config_t cfg = ap_config_default(profile);
    ap_pipeline_t *pipeline = NULL;
    ap_metrics_t metrics;
    const uint32_t n = rate / 100u;
    int16_t mic[FRAME_MAX * 2u], output[FRAME_MAX];
    float a[FRAME_MAX], b[FRAME_MAX];
    uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu, frame, i;
    if (AP_BUILD_MAX_MIC_CHANNELS < 2u || rate > AP_BUILD_MAX_IO_RATE_HZ) return;
    cfg.io_sample_rate_hz = rate;
    cfg.internal_sample_rate_hz = rate;
    cfg.mic_channels = 2u;
    cfg.mic_spacing_mm = 70.0f;
    cfg.stages = AP_STAGE_BF;
    cfg.enable_delay_tracking = 0u;
    cfg.enable_clock_drift_compensation = 0u;
    CHECK(ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory), &cfg, &pipeline) == AP_OK,
          "initialize BF-only public pipeline");
    if (!pipeline) return;
    for (frame = 0u; frame < 80u; ++frame) {
        ap_quality_t quality = frame < 32u ? AP_QUALITY_FULL :
            (frame < 64u ? AP_QUALITY_LITE : (frame < 68u ? AP_QUALITY_SAFE : AP_QUALITY_LITE));
        fill_frame(a, b, rate, frame, SIGNAL_HARD0, &rng0, &rng1);
        for (i = 0u; i < n; ++i) {
            mic[2u * i] = (int16_t)lrintf(a[i] * 32768.0f);
            mic[2u * i + 1u] = (int16_t)lrintf(b[i] * 32768.0f);
            output[i] = INT16_MIN;
        }
        CHECK(ap_pipeline_set_quality(pipeline, quality) == AP_OK, "set public quality");
        CHECK(ap_pipeline_process_capture(pipeline, mic, n, output) == AP_OK,
              "public quality path emits a complete frame");
        ap_pipeline_get_metrics(pipeline, &metrics);
        CHECK(metrics.processed_frames == frame + 1u, "public pipeline frame continuity");
        CHECK(metrics.quality == quality, "public quality readback");
        CHECK(isfinite(metrics.input_rms_dbfs) && isfinite(metrics.output_rms_dbfs),
              "public pipeline metrics finite across switches");
        if (frame >= 16u) {
            for (i = 0u; i < n; ++i) {
                const int16_t expected = mic[2u * i + (quality == AP_QUALITY_SAFE ? 0u : 1u)];
                CHECK(output[i] >= expected - 1 && output[i] <= expected + 1,
                      "FULL/LITE preserve reliable input; SAFE remains mic0");
            }
        }
    }
    ap_pipeline_reset(pipeline);
    ap_pipeline_get_metrics(pipeline, &metrics);
    CHECK(metrics.processed_frames == 0u, "public pipeline reset clears frame lifecycle");
}

/* All SAFE lifecycle stimuli below go through public APIs. The second arena
 * holds either a fresh public oracle or an opaque state snapshot for rejection
 * atomicity; no private BF fields are written to manufacture an epoch. */
static _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
unsigned char pipeline_auxiliary_memory[AP_PIPELINE_STATE_MAX_BYTES];

static ap_pipeline_t *init_public_fixed_bf(unsigned char *memory, uint32_t rate,
                                          ap_profile_t profile) {
    ap_config_t cfg = ap_config_default(profile);
    ap_pipeline_t *pipeline = NULL;
    cfg.io_sample_rate_hz = rate;
    cfg.internal_sample_rate_hz = rate;
    cfg.mic_channels = 2u;
    cfg.mic_spacing_mm = 70.0f;
    cfg.stages = AP_STAGE_BF;
    cfg.enable_delay_tracking = 0u;
    cfg.enable_clock_drift_compensation = 0u;
    CHECK(ap_pipeline_init(memory, AP_PIPELINE_STATE_MAX_BYTES, &cfg, &pipeline) == AP_OK,
          "initialize public fixed BF lifecycle test");
    if (pipeline)
        CHECK(ap_pipeline_set_quality(pipeline, AP_QUALITY_LITE) == AP_OK,
              "select public fixed BF mode");
    return pipeline;
}

static void process_public_bf(ap_pipeline_t *pipeline, uint32_t rate, uint32_t frame,
                              signal_case_t kind, int16_t *mic, int16_t *output) {
    float a[FRAME_MAX], b[FRAME_MAX];
    ap_metrics_t before, after;
    uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu, i;
    fill_frame(a, b, rate, frame, kind, &rng0, &rng1);
    for (i = 0u; i < rate / 100u; ++i) {
        mic[2u * i] = (int16_t)lrintf(a[i] * 32768.0f);
        mic[2u * i + 1u] = (int16_t)lrintf(b[i] * 32768.0f);
        output[i] = INT16_MIN;
    }
    ap_pipeline_get_metrics(pipeline, &before);
    CHECK(ap_pipeline_process_capture(pipeline, mic, rate / 100u, output) == AP_OK,
          "SAFE lifecycle emits a complete public frame");
    ap_pipeline_get_metrics(pipeline, &after);
    CHECK(after.processed_frames == before.processed_frames + 1u,
          "SAFE lifecycle keeps public frame continuity");
    CHECK(isfinite(after.input_rms_dbfs) && isfinite(after.output_rms_dbfs),
          "SAFE lifecycle metrics stay finite");
}

static int public_route_error(const int16_t *output, const int16_t *mic,
                              uint32_t n, int channel) {
    int maximum = 0;
    uint32_t i;
    for (i = 0u; i < n; ++i) {
        const int expected = channel >= 0 ? mic[2u * i + (unsigned)channel] :
            (int)lrintf(0.5f * ((float)mic[2u * i] + mic[2u * i + 1u]));
        int difference = (int)output[i] - expected;
        if (difference < 0) difference = -difference;
        if (difference > maximum) maximum = difference;
    }
    return maximum;
}

static void test_public_safe_pending_confirmation(uint32_t rate) {
    static const uint32_t gaps[] = {1u, 4u};
    static const signal_case_t safe_inputs[] = {SIGNAL_CLEAN, SIGNAL_HARD1};
    const uint32_t n = rate / 100u;
    size_t gap, safe;
    unsigned next_bad;
    for (gap = 0u; gap < 2u; ++gap) for (safe = 0u; safe < 2u; ++safe)
    for (next_bad = 0u; next_bad < 2u; ++next_bad) {
        ap_pipeline_t *pipeline = init_public_fixed_bf(pipeline_memory, rate, AP_PROFILE_CALL);
        ap_pipeline_t *fresh = init_public_fixed_bf(pipeline_auxiliary_memory, rate, AP_PROFILE_CALL);
        const signal_case_t resumed = next_bad ? SIGNAL_HARD1 : SIGNAL_HARD0;
        int16_t mic[FRAME_MAX * 2u], output[FRAME_MAX], oracle[FRAME_MAX];
        uint32_t frame = 0u, i;
        int first_average_error = 0, fifth_target_error = 0;
        if (!pipeline || !fresh) return;
        /* Only frame zero is an observation; the next one would be frame four. */
        for (i = 0u; i < 4u; ++i) {
            process_public_bf(pipeline, rate, frame++, SIGNAL_HARD0, mic, output);
            CHECK(public_route_error(output, mic, n, -1) <= 1,
                  "one pre-SAFE observation cannot confirm");
        }
        CHECK(ap_pipeline_set_quality(pipeline, AP_QUALITY_SAFE) == AP_OK, "enter SAFE");
        for (i = 0u; i < gaps[gap]; ++i) {
            process_public_bf(pipeline, rate, frame++, safe_inputs[safe], mic, output);
            CHECK(public_route_error(output, mic, n, 0) <= 1, "SAFE retains mic0 bypass");
        }
        CHECK(ap_pipeline_set_quality(pipeline, AP_QUALITY_LITE) == AP_OK, "return from SAFE");
        for (i = 0u; i < 8u; ++i, ++frame) {
            process_public_bf(pipeline, rate, frame, resumed, mic, output);
            process_public_bf(fresh, rate, frame, resumed, mic, oracle);
            CHECK(memcmp(output, oracle, n * sizeof(output[0])) == 0,
                  "SAFE invalidates pending confirmation exactly like a fresh public epoch");
            CHECK(public_route_error(output, mic, n, i < 4u ? -1 : (int)(1u - next_bad)) <= 1,
                  "post-SAFE route requires two new consistent observations");
            if (i == 0u) first_average_error = public_route_error(output, mic, n, -1);
            if (i == 4u) fifth_target_error = public_route_error(output, mic, n, (int)(1u - next_bad));
        }
        printf("safe_arm rate=%u gap=%u safe=%s next_bad=%u first_average_error=%d "
               "fifth_target_error=%d\n", rate, gaps[gap], safe ? "hard1" : "healthy",
               next_bad, first_average_error, fifth_target_error);
    }
}

static void check_invalid_quality_atomic(ap_pipeline_t *pipeline) {
    static const ap_quality_t invalid[] = {(ap_quality_t)-1, (ap_quality_t)(AP_QUALITY_FULL + 1)};
    const size_t bytes = ap_pipeline_state_size();
    size_t i;
    CHECK(bytes <= sizeof(pipeline_auxiliary_memory), "opaque snapshot fits test arena");
    if (bytes > sizeof(pipeline_auxiliary_memory)) return;
    for (i = 0u; i < sizeof(invalid) / sizeof(invalid[0]); ++i) {
        memcpy(pipeline_auxiliary_memory, pipeline_memory, bytes);
        CHECK(ap_pipeline_set_quality(pipeline, invalid[i]) == AP_EINVAL,
              "invalid quality is rejected before SAFE epoch mutation");
        CHECK(memcmp(pipeline_auxiliary_memory, pipeline_memory, bytes) == 0,
              "invalid quality leaves the entire opaque state unchanged");
    }
}

static void test_public_safe_confirmed_route(uint32_t rate, ap_profile_t profile) {
    static const ap_quality_t destinations[] = {AP_QUALITY_LITE, AP_QUALITY_FULL};
    const uint32_t n = rate / 100u;
    size_t destination;
    for (destination = 0u; destination < 2u; ++destination) {
        ap_pipeline_t *pipeline = init_public_fixed_bf(pipeline_memory, rate, profile);
        int16_t mic[FRAME_MAX * 2u], output[FRAME_MAX];
        uint32_t frame;
        int resumed_route_error = 0;
        if (!pipeline) return;
        for (frame = 0u; frame < 8u; ++frame) {
            CHECK(ap_pipeline_set_quality(pipeline, AP_QUALITY_LITE) == AP_OK,
                  "repeated LITE remains valid");
            process_public_bf(pipeline, rate, frame, SIGNAL_HARD0, mic, output);
            CHECK(public_route_error(output, mic, n, frame < 4u ? -1 : 1) <= 1,
                  "repeated quality does not restart pending confirmation");
            if (frame == 3u) check_invalid_quality_atomic(pipeline);
        }
        for (frame = 8u; frame < 12u; ++frame) {
            CHECK(ap_pipeline_set_quality(pipeline, AP_QUALITY_SAFE) == AP_OK,
                  "enter or repeat SAFE without losing confirmed route");
            process_public_bf(pipeline, rate, frame, SIGNAL_HARD1, mic, output);
            CHECK(public_route_error(output, mic, n, 0) <= 1, "SAFE uses mic0 despite retained hard state");
        }
        for (frame = 12u; frame < 16u; ++frame) {
            CHECK(ap_pipeline_set_quality(pipeline, destinations[destination]) == AP_OK,
                  "resume fixed or tracking quality after SAFE");
            process_public_bf(pipeline, rate, frame, SIGNAL_HARD0, mic, output);
            {
                const int error = public_route_error(output, mic, n, 1);
                if (error > resumed_route_error) resumed_route_error = error;
            }
            CHECK(resumed_route_error <= 1,
                  "SAFE boundary preserves an already confirmed hard route");
        }
        printf("safe_confirmed rate=%u profile=%u return_quality=%u max_resumed_route_error=%d\n",
               rate, (unsigned)profile, (unsigned)destinations[destination], resumed_route_error);
    }
}

static void test_public_safe_pending_recovery(uint32_t rate, ap_profile_t profile) {
    static const signal_case_t safe_inputs[] = {SIGNAL_CLEAN, SIGNAL_HARD0};
    const uint32_t n = rate / 100u;
    size_t safe;
    for (safe = 0u; safe < 2u; ++safe) {
        ap_pipeline_t *pipeline = init_public_fixed_bf(pipeline_memory, rate, profile);
        int16_t mic[FRAME_MAX * 2u], output[FRAME_MAX];
        uint32_t frame;
        int first_selected_error = 0, last_average_error = 0;
        if (!pipeline) return;
        for (frame = 0u; frame < 36u; ++frame) {
            CHECK(ap_pipeline_set_quality(pipeline, AP_QUALITY_LITE) == AP_OK,
                  "repeated LITE does not reset recovery cadence");
            process_public_bf(pipeline, rate, frame,
                              frame < 8u ? SIGNAL_HARD0 : SIGNAL_GAIN0, mic, output);
            CHECK(public_route_error(output, mic, n, frame < 4u ? -1 : 1) <= 1,
                  "seven pre-SAFE recovery observations retain the hard route");
        }
        check_invalid_quality_atomic(pipeline);
        CHECK(ap_pipeline_set_quality(pipeline, AP_QUALITY_SAFE) == AP_OK, "interrupt pending recovery with SAFE");
        for (frame = 36u; frame < 40u; ++frame) {
            process_public_bf(pipeline, rate, frame, safe_inputs[safe], mic, output);
            CHECK(public_route_error(output, mic, n, 0) <= 1, "pending recovery does not alter SAFE bypass");
        }
        for (frame = 40u; frame <= 68u; ++frame) {
            CHECK(ap_pipeline_set_quality(pipeline, AP_QUALITY_LITE) == AP_OK,
                  "return to or repeat LITE while rebuilding recovery evidence");
            process_public_bf(pipeline, rate, frame, SIGNAL_GAIN0, mic, output);
            CHECK(public_route_error(output, mic, n, frame < 68u ? 1 : -1) <= 1,
                  "SAFE requires eight new recovery observations despite repeated quality calls");
            if (frame == 40u) first_selected_error = public_route_error(output, mic, n, 1);
            if (frame == 68u) last_average_error = public_route_error(output, mic, n, -1);
        }
        printf("safe_recovery rate=%u profile=%u safe=%s expected_first_observation=40 "
               "expected_eighth_observation=68 first_selected_error=%d last_average_error=%d\n",
               rate, (unsigned)profile, safe ? "hard0" : "healthy",
               first_selected_error, last_average_error);
    }
}

static void test_public_safe_epochs(uint32_t rate) {
    if (AP_BUILD_MAX_MIC_CHANNELS < 2u || rate > AP_BUILD_MAX_IO_RATE_HZ) return;
    test_public_safe_pending_confirmation(rate);
    test_public_safe_confirmed_route(rate, AP_PROFILE_CALL);
    test_public_safe_confirmed_route(rate, AP_PROFILE_ASSISTANT);
    test_public_safe_pending_recovery(rate, AP_PROFILE_CALL);
    test_public_safe_pending_recovery(rate, AP_PROFILE_ASSISTANT);
}
#endif

static int legacy_trace(const char *path) {
    static const uint32_t rates[] = {8000u, 16000u};
    FILE *file = fopen(path, "wb");
    size_t r;
    int use_hpf;
    if (!file) return 2;
    for (r = 0u; r < sizeof(rates) / sizeof(rates[0]); ++r) {
        const uint32_t rate = rates[r], n = rate / 100u;
        if (rate > AP_BUILD_MAX_INTERNAL_RATE_HZ) continue;
        for (use_hpf = 0; use_hpf <= AP_HAVE_MODULE_HPF; ++use_hpf) {
            ap_beamformer_state_t s;
            ap_hpf_state_t hpf;
            float a[FRAME_MAX], b[FRAME_MAX], out[FRAME_MAX];
            uint32_t rng0 = 0x6d2b79f5u, rng1 = 0x13579bdfu, frame;
            ap_beamformer_init(&s, rate, 70.0f);
            init_hpf(&hpf, rate);
            for (frame = 0u; frame < 720u; ++frame) {
                signal_case_t kind = SIGNAL_CLEAN;
                uint32_t header[4] = {rate, (uint32_t)use_hpf, frame, n};
                if (frame >= 40u && frame < 120u) kind = SIGNAL_HARD0;
                else if (frame >= 160u && frame < 240u) kind = SIGNAL_HARD1;
                else if (frame >= 280u && frame < 320u) kind = SIGNAL_GAIN0;
                else if (frame >= 320u && frame < 360u) kind = SIGNAL_VERY_WEAK1;
                else if (frame >= 360u && frame < 400u) kind = SIGNAL_DELAY_POS;
                else if (frame >= 400u && frame < 440u) kind = SIGNAL_MOTION;
                else if (frame >= 440u && frame < 480u) kind = SIGNAL_NOISE;
                else if (frame >= 480u && frame < 520u) kind = SIGNAL_SILENCE;
                else if (frame >= 520u && frame < 560u) kind = SIGNAL_QUIET;
                else if (frame >= 560u && frame < 600u) kind = SIGNAL_ZERO0;
                else if (frame >= 600u && frame < 640u) kind = SIGNAL_RAIL1;
                else if (frame >= 640u && frame < 680u) kind = SIGNAL_POLARITY;
                fill_frame(a, b, rate, frame, kind, &rng0, &rng1);
                maybe_hpf(&hpf, use_hpf, a, b, n);
                ap_beamformer_process(&s, 1, a, b, out, n);
                if (fwrite(header, sizeof(header), 1u, file) != 1u ||
                    fwrite(out, sizeof(float), n, file) != n ||
                    fwrite(&s, 1u, LEGACY_BYTES, file) != LEGACY_BYTES) {
                    (void)fclose(file);
                    return 2;
                }
            }
        }
    }
    return fclose(file) == 0 ? 0 : 2;
}

int main(int argc, char **argv) {
    static const uint32_t rates[] = {8000u, 16000u};
    size_t r;
    int use_hpf, lag;
    unsigned bad_ch;
    if (argc == 3 && strcmp(argv[1], "--legacy-trace") == 0) return legacy_trace(argv[2]);
    if (argc == 2 && strcmp(argv[1], "--mode-epoch") == 0) {
        for (r = 0u; r < sizeof(rates) / sizeof(rates[0]); ++r)
            if (rates[r] <= AP_BUILD_MAX_INTERNAL_RATE_HZ) test_pending_mode_epoch(rates[r]);
        printf("beamformer pending-mode checks=%u failures=%u\n", checks, failures);
        return failures == 0u ? 0 : 1;
    }
#if AP_HAVE_PIPELINE
    if (argc == 2 && strcmp(argv[1], "--safe-epoch") == 0) {
        for (r = 0u; r < sizeof(rates) / sizeof(rates[0]); ++r)
            if (rates[r] <= AP_BUILD_MAX_INTERNAL_RATE_HZ) test_public_safe_epochs(rates[r]);
        printf("beamformer public-SAFE checks=%u failures=%u\n", checks, failures);
        return failures == 0u ? 0 : 1;
    }
#endif
    if (argc != 1) return 2;
    printf("BF state=%zu module=%zu legacy_fields=%zu", sizeof(ap_beamformer_state_t),
           ap_module_beamformer_state_size(), (size_t)LEGACY_BYTES);
#if AP_HAVE_PIPELINE
    printf(" pipeline=%zu", ap_pipeline_state_size());
#endif
    printf(" tracking_capability=%u\n", (unsigned)AP_BUILD_BF_DIRECTION_TRACKING);
    for (r = 0u; r < sizeof(rates) / sizeof(rates[0]); ++r) {
        const uint32_t rate = rates[r];
        if (rate > AP_BUILD_MAX_INTERNAL_RATE_HZ) continue;
        for (use_hpf = 0; use_hpf <= AP_HAVE_MODULE_HPF; ++use_hpf) {
            test_negative_controls(rate, use_hpf);
            for (bad_ch = 0u; bad_ch < 2u; ++bad_ch)
                for (lag = -1; lag <= 1; ++lag)
                    test_hard_and_recovery(rate, use_hpf, bad_ch, lag);
        }
        test_confirmation_and_silence(rate);
        test_one_lsb_boundary(rate);
        test_mode_switch(rate);
        test_pending_mode_epoch(rate);
        test_fixed_cadence_reinitialization(rate);
#if AP_HAVE_PIPELINE
        test_pipeline_quality(rate, AP_PROFILE_CALL);
        test_pipeline_quality(rate, AP_PROFILE_ASSISTANT);
        test_public_safe_epochs(rate);
#endif
    }
    printf("beamformer fixed-health checks=%u failures=%u\n", checks, failures);
    return failures == 0u ? 0 : 1;
}
