#ifndef AUDIO_PIPELINE_AP_RESAMPLER_H
#define AUDIO_PIPELINE_AP_RESAMPLER_H

#include "audio_pipeline/audio_pipeline_build.h"
#include <stdint.h>

#define AP_RESAMPLER_HISTORY 14u
#define AP_RESAMPLER_INPUT_STREAMS 3u

typedef struct ap_resampler_state {
    float input_history[AP_RESAMPLER_INPUT_STREAMS][AP_RESAMPLER_HISTORY];
    float output_history[AP_RESAMPLER_HISTORY];
} ap_resampler_state_t;

void ap_resampler_init(ap_resampler_state_t *state);
void ap_resampler_reset(ap_resampler_state_t *state);
int ap_supported_io_rate(uint32_t hz);
void ap_resample_input_channel(ap_resampler_state_t *state,
                               uint32_t stream,
                               const int16_t *in,
                               uint32_t in_frames,
                               uint32_t channels,
                               uint32_t channel,
                               float *out,
                               uint32_t out_frames);
void ap_resample_output(ap_resampler_state_t *state,
                        const float *in,
                        uint32_t in_frames,
                        int16_t *out,
                        uint32_t out_frames);
uint32_t ap_resampler_filter_delay_samples(uint32_t in_frames, uint32_t out_frames);

#endif
