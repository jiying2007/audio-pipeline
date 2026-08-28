#include "activity/ap_activity.h"
#include <string.h>

static float smooth_energy(float old_value, float value) {
    const float alpha = value > old_value ? 0.35f : 0.08f;
    if (old_value <= 0.0f) return value;
    return old_value + alpha * (value - old_value);
}

void ap_activity_init(ap_activity_state_t *s,
                      float far_threshold,
                      float dt_ratio,
                      uint32_t hold) {
    memset(s, 0, sizeof(*s));
    s->far_end_threshold = far_threshold;
    s->double_talk_ratio = dt_ratio;
    s->hangover_frames = hold;
}

void ap_activity_reset(ap_activity_state_t *s) {
    s->smoothed_mic_energy = 0.0f;
    s->smoothed_reference_energy = 0.0f;
    s->double_talk_hangover = 0u;
    s->far_end_hangover = 0u;
}

void ap_activity_process(ap_activity_state_t *s,
                         float mic_energy,
                         float reference_energy,
                         ap_activity_result_t *r) {
    const uint32_t far_hold = s->hangover_frames > 1u ? 2u : s->hangover_frames;
    float smoothed_ratio;
    float instant_ratio;
    int far;
    int dt_on;
    int dt_hold;

    s->smoothed_mic_energy = smooth_energy(s->smoothed_mic_energy, mic_energy);
    s->smoothed_reference_energy =
        smooth_energy(s->smoothed_reference_energy, reference_energy);

    if (s->smoothed_reference_energy > s->far_end_threshold) {
        s->far_end_hangover = far_hold;
    } else if (s->smoothed_reference_energy < 0.55f * s->far_end_threshold) {
        if (s->far_end_hangover > 0u) s->far_end_hangover--;
    }
    far = s->far_end_hangover > 0u ||
          s->smoothed_reference_energy > s->far_end_threshold;

    smoothed_ratio = s->smoothed_mic_energy /
                     (s->smoothed_reference_energy + 1.0e-12f);
    instant_ratio = mic_energy / (reference_energy + 1.0e-12f);

    /* Smoothed energy rejects one-frame threshold chatter, but the current
     * frame must still contain near-end evidence before double talk can be
     * triggered or held. This prevents the mic EMA tail from continuously
     * refreshing hangover after near-end speech has stopped. */
    dt_on = far && smoothed_ratio > s->double_talk_ratio &&
            instant_ratio > 0.90f * s->double_talk_ratio;
    dt_hold = far && instant_ratio > 0.72f * s->double_talk_ratio;

    if (dt_on) {
        s->double_talk_hangover = s->hangover_frames;
    } else if (!dt_hold && s->double_talk_hangover > 0u) {
        s->double_talk_hangover--;
    }

    r->far_end_active = (uint8_t)(far ? 1u : 0u);
    r->double_talk_active =
        (uint8_t)(far && s->double_talk_hangover > 0u ? 1u : 0u);
}
