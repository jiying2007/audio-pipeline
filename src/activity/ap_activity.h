#ifndef AUDIO_PIPELINE_AP_ACTIVITY_H
#define AUDIO_PIPELINE_AP_ACTIVITY_H
#include <stdint.h>
typedef struct ap_activity_state { float far_end_threshold; float double_talk_ratio; uint32_t hangover_frames; uint32_t double_talk_hangover; } ap_activity_state_t;
typedef struct ap_activity_result { uint8_t far_end_active; uint8_t double_talk_active; } ap_activity_result_t;
void ap_activity_init(ap_activity_state_t *, float, float, uint32_t);
void ap_activity_reset(ap_activity_state_t *);
void ap_activity_process(ap_activity_state_t *, float, float, ap_activity_result_t *);
#endif
