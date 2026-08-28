#ifndef AUDIO_PIPELINE_AP_SYNC_H
#define AUDIO_PIPELINE_AP_SYNC_H

#include "audio_pipeline/audio_pipeline_build.h"
#include <stdint.h>

#define AP_RENDER_CAP AP_BUILD_RENDER_CAP

typedef struct ap_sync_state {
    float render_ring[AP_RENDER_CAP];
    uint64_t render_total;
    uint64_t last_render_capture_frame;
    uint32_t delay_samples;
    uint32_t initial_delay_samples;
    uint32_t delay_update_counter;
    uint32_t last_best_delay;
    uint8_t have_last_best_delay;
    float drift_ppm;
    float drift_credit;
} ap_sync_state_t;

typedef struct ap_sync_event {
    int32_t delay_error_samples;
    uint32_t reference_sample_slips;
    uint8_t delay_observed;
    uint8_t route_jump;
    uint8_t timestamp_observed;
} ap_sync_event_t;

typedef struct ap_sync_status {
    float estimated_drift_ppm;
    uint32_t delay_samples;
} ap_sync_status_t;

void ap_sync_init(ap_sync_state_t *state, uint32_t initial_delay_samples);
void ap_sync_reset(ap_sync_state_t *state);
void ap_sync_push_render(ap_sync_state_t *state,
                         const float *render,
                         uint32_t samples,
                         uint64_t processed_frames);
void ap_sync_track_delay(ap_sync_state_t *state,
                         const float *mic,
                         uint32_t frame_samples,
                         uint32_t sample_rate_hz,
                         uint32_t max_delay_ms,
                         int enable_delay_tracking,
                         int enable_clock_drift_compensation,
                         ap_sync_event_t *event);
int ap_sync_observe_timestamps(ap_sync_state_t *state,
                               uint64_t capture_timestamp_ns,
                               uint64_t render_timestamp_ns,
                               uint32_t sample_rate_hz,
                               uint32_t max_delay_ms,
                               ap_sync_event_t *event);
int ap_sync_get_reference(ap_sync_state_t *state,
                          uint32_t frame_samples,
                          float *out);
int ap_sync_note_capture(const ap_sync_state_t *state, uint64_t processed_frames);
void ap_sync_get_status(const ap_sync_state_t *state, ap_sync_status_t *status);

#endif
