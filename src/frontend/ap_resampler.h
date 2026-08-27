#ifndef AUDIO_PIPELINE_AP_RESAMPLER_H
#define AUDIO_PIPELINE_AP_RESAMPLER_H

#include <stdint.h>

int ap_supported_io_rate(uint32_t hz);
void ap_resample_input_channel(const int16_t *in,
                               uint32_t in_frames,
                               uint32_t channels,
                               uint32_t channel,
                               float *out,
                               uint32_t out_frames);
void ap_resample_output(const float *in,
                        uint32_t in_frames,
                        int16_t *out,
                        uint32_t out_frames);

#endif
