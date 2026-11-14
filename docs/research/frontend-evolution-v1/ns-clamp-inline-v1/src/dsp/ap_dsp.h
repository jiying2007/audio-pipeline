#ifndef AUDIO_PIPELINE_AP_DSP_H
#define AUDIO_PIPELINE_AP_DSP_H

#include <stdint.h>

#define AP_PI 3.14159265358979323846f

typedef struct ap_complex {
    float re;
    float im;
} ap_complex_t;

void ap_fft(ap_complex_t *x, uint32_t n, int inverse);
float ap_clampf(float x, float lo, float hi);
float ap_rms_dbfs(const float *x, uint32_t n);

#endif
