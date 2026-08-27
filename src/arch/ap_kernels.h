#ifndef AUDIO_PIPELINE_AP_KERNELS_H
#define AUDIO_PIPELINE_AP_KERNELS_H

#include "dsp/ap_dsp.h"
#include <stdint.h>

float ap_kernel_dot_f32(const float *a, const float *b, uint32_t n);
void ap_kernel_complex_mac(ap_complex_t *acc,
                           const ap_complex_t *w,
                           const ap_complex_t *x,
                           uint32_t bins);
void ap_kernel_complex_adapt(ap_complex_t *w,
                             const ap_complex_t *x,
                             const ap_complex_t *gradient,
                             uint32_t bins);
void ap_kernel_nlms_update(float *w, const float *x, float step, uint32_t n);

#endif
