#ifndef AUDIO_PIPELINE_AP_NUMERIC_H
#define AUDIO_PIPELINE_AP_NUMERIC_H

#include <math.h>
#include <stdint.h>
#include <string.h>

/* IEEE-754 binary32 finite check that remains valid even when the DSP target is
 * compiled with -ffast-math/-ffinite-math-only. Public/config validation must
 * not inherit the optimizer's assumption that NaN/Inf can never arrive from an
 * application, file or control plane. */
static inline int ap_float_is_finite(float value) {
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return (bits & UINT32_C(0x7f800000)) != UINT32_C(0x7f800000);
}

/* Include math.h first, then replace its isfinite macro once. Subsequent math.h
 * includes are guarded, so private validation remains independent of fast-math
 * assumptions and include ordering. */
#ifdef isfinite
#undef isfinite
#endif
#define isfinite(value) ap_float_is_finite((float)(value))

#endif
