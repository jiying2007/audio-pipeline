#include "activity/ap_activity.h"
#include <string.h>
void ap_activity_init(ap_activity_state_t *s, float far_threshold, float dt_ratio, uint32_t hold) { memset(s, 0, sizeof(*s)); s->far_end_threshold = far_threshold; s->double_talk_ratio = dt_ratio; s->hangover_frames = hold; }
void ap_activity_reset(ap_activity_state_t *s) { s->double_talk_hangover = 0u; }
void ap_activity_process(ap_activity_state_t *s, float mic_energy, float reference_energy, ap_activity_result_t *r) {
    const int far = reference_energy > s->far_end_threshold;
    const int dt = far && mic_energy > reference_energy * s->double_talk_ratio;
    if (dt) s->double_talk_hangover = s->hangover_frames;
    else if (s->double_talk_hangover) s->double_talk_hangover--;
    r->far_end_active = (uint8_t)(far ? 1u : 0u);
    r->double_talk_active = (uint8_t)(far && s->double_talk_hangover > 0u ? 1u : 0u);
}
