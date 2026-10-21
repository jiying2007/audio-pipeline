/* Frozen research selector; not part of the public SDK. */
#ifndef DEVICE_SHADOW_SELECTOR_D24_H
#define DEVICE_SHADOW_SELECTOR_D24_H
#include <math.h>
#include <stdint.h>
typedef struct d24_selection { uint32_t bank, streak, changes; } d24_selection_t;
static inline int d24_choose(d24_selection_t *s, int active, int eligible, double primary, double shadow) {
    double current, other;
    if (!isfinite(primary) || !isfinite(shadow) || primary < 0.0 || shadow < 0.0 || s->bank > 1u) return -1;
    if (!active) { s->bank = 0u; s->streak = 0u; return 0; }
    current = s->bank ? shadow : primary;
    other = s->bank ? primary : shadow;
    if (eligible && current > 1.0e-20 && other < 0.8 * current) ++s->streak;
    else s->streak = 0u;
    if (s->streak == 3u) { s->bank = 1u-s->bank; s->streak = 0u; ++s->changes; return 1; }
    return 0;
}
#endif
