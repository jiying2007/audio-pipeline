#ifndef AUDIO_PIPELINE_AP_FRONTEND_H
#define AUDIO_PIPELINE_AP_FRONTEND_H

#include <stdint.h>

#include "ap_numeric.h"

#define AP_FRONTEND_MAX_MIC_CHANNELS 2u
#define AP_BF_HISTORY 8u
#define AP_BF_LAG_SCORE_COUNT (2u * AP_BF_HISTORY + 1u)

#define AP_BF_SOUND_SPEED_MM_PER_S 343000.0f
#define AP_BF_MIC_SPACING_MIN_MM 5.0f

/* Nominal largest microphone spacing whose acoustic TDOA still fits the lag
 * search window (AP_BF_HISTORY samples). Beyond it ap_beamformer_init() clamps
 * max_lag to the history length and the outer lags silently degrade to zero
 * correlation, so the control plane rejects the geometry instead. At sample
 * rates where the float round-trip below overshoots, the exact accepted maximum
 * is one ULP lower; ap_bf_mic_spacing_ok() is authoritative. */
static inline float ap_bf_max_mic_spacing_mm(uint32_t sample_rate_hz) {
    return (float)AP_BF_HISTORY * AP_BF_SOUND_SPEED_MM_PER_S /
           (float)sample_rate_hz;
}

/* Lag span in samples required by the geometry, evaluated with the same float
 * expression ap_beamformer_init() uses so the validator and the clamp cannot
 * disagree by a rounding step. */
static inline float ap_bf_lag_span(float spacing_mm,
                                   uint32_t sample_rate_hz) {
    return spacing_mm * (float)sample_rate_hz /
           AP_BF_SOUND_SPEED_MM_PER_S;
}

/* ap_beamformer_init() computes max_lag = ceilf(span) + 1 and clamps it to
 * AP_BF_HISTORY, so the search radius still covers the required lag exactly
 * while span <= AP_BF_HISTORY. A larger span is truncated and degrades the
 * outer lags, so it is rejected here. */
static inline int ap_bf_mic_spacing_ok(float spacing_mm,
                                       uint32_t sample_rate_hz) {
    float span;

    if (!ap_float_is_finite(spacing_mm) ||
        spacing_mm < AP_BF_MIC_SPACING_MIN_MM) {
        return 0;
    }
    span = ap_bf_lag_span(spacing_mm, sample_rate_hz);
    return ap_float_is_finite(span) && span <= (float)AP_BF_HISTORY;
}

typedef struct ap_hpf_state {
    float r;
    float x[AP_FRONTEND_MAX_MIC_CHANNELS];
    float y[AP_FRONTEND_MAX_MIC_CHANNELS];
    uint32_t channels;
} ap_hpf_state_t;

typedef struct ap_beamformer_state {
    float history[AP_FRONTEND_MAX_MIC_CHANNELS][AP_BF_HISTORY];
    float lag_score[AP_BF_LAG_SCORE_COUNT];
    float fallback_gain;
    int lag;
    int max_lag;
    int fallback_lag;
    uint32_t counter;
    uint32_t score_updates;
    uint32_t fallback_active;
    uint32_t fallback_strong_channel;
    uint32_t fallback_recovery_count;
    uint32_t fallback_hard_fault;
    uint32_t fallback_hard_arm_count;
} ap_beamformer_state_t;

void ap_hpf_init(ap_hpf_state_t *state,
                 uint32_t sample_rate_hz,
                 uint32_t channels);
void ap_hpf_process(ap_hpf_state_t *state,
                    float *x,
                    uint32_t n,
                    uint32_t channel);

void ap_beamformer_init(ap_beamformer_state_t *state,
                        uint32_t sample_rate_hz,
                        float mic_spacing_mm);
void ap_beamformer_process(ap_beamformer_state_t *state,
                           int track_direction,
                           float *mic0,
                           float *mic1,
                           float *out,
                           uint32_t n);

#endif
