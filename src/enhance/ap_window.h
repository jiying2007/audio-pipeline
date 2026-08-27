#ifndef AUDIO_PIPELINE_AP_WINDOW_H
#define AUDIO_PIPELINE_AP_WINDOW_H

#include <stdint.h>

/* Return the first half of the symmetric sine analysis/synthesis window.
 * Supported internal frame geometries are 80 and 160 samples. */
const float *ap_window_half(uint32_t frame_samples);

#endif
