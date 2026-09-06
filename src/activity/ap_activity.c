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
    s->smoothed_residual_energy = 0.0f;
    s->smoothed_echo_energy = 0.0f;
    s->double_talk_hangover = 0u;
    s->far_end_hangover = 0u;
}

void ap_activity_process_with_residual_echo(ap_activity_state_t *s,
                                            float mic_energy,
                                            float reference_energy,
                                            float residual_energy,
                                            float echo_energy,
                                            int residual_echo_valid,
                                            ap_activity_result_t *r) {
    const uint32_t far_hold = s->hangover_frames > 1u ? 2u : s->hangover_frames;
    float smoothed_ratio;
    float instant_ratio;
    float residual_smoothed_ratio;
    float residual_instant_ratio;
    int far;
    int raw_on;
    int raw_hold;
    int rescue_on;
    int rescue_hold;
    int dt_on;
    int dt_hold;

    s->smoothed_mic_energy = smooth_energy(s->smoothed_mic_energy, mic_energy);
    s->smoothed_reference_energy =
        smooth_energy(s->smoothed_reference_energy, reference_energy);
    s->smoothed_residual_energy =
        smooth_energy(s->smoothed_residual_energy, residual_energy);
    s->smoothed_echo_energy =
        smooth_energy(s->smoothed_echo_energy, echo_energy);

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
    residual_smoothed_ratio = s->smoothed_residual_energy /
                              (s->smoothed_echo_energy + 1.0e-12f);
    residual_instant_ratio = residual_energy / (echo_energy + 1.0e-12f);

    /* Preserve the shipping mic/render DTD path exactly. Once the previous AEC
     * frame is converged, residual/echo supplies a second near-evidence path
     * using the same ratio, EMA constants and hangover. The AEC residual has
     * already removed modeled echo, avoiding the render-vs-echo scale mismatch
     * without treating ordinary echo-estimate under-shoot as near speech. */
    raw_on = smoothed_ratio > s->double_talk_ratio &&
             instant_ratio > 0.90f * s->double_talk_ratio;
    raw_hold = instant_ratio > 0.72f * s->double_talk_ratio;
    rescue_on = residual_echo_valid &&
                residual_smoothed_ratio > s->double_talk_ratio &&
                residual_instant_ratio > 0.90f * s->double_talk_ratio;
    rescue_hold = residual_echo_valid &&
                  residual_instant_ratio > 0.72f * s->double_talk_ratio;
    dt_on = far && (raw_on || rescue_on);
    dt_hold = far && (raw_hold || rescue_hold);

    if (dt_on) {
        s->double_talk_hangover = s->hangover_frames;
    } else if (!dt_hold && s->double_talk_hangover > 0u) {
        s->double_talk_hangover--;
    }

    r->far_end_active = (uint8_t)(far ? 1u : 0u);
    r->double_talk_active =
        (uint8_t)(far && s->double_talk_hangover > 0u ? 1u : 0u);
}

void ap_activity_process(ap_activity_state_t *s,
                         float mic_energy,
                         float reference_energy,
                         ap_activity_result_t *r) {
    ap_activity_process_with_residual_echo(s,
                                           mic_energy,
                                           reference_energy,
                                           0.0f,
                                           0.0f,
                                           0,
                                           r);
}
