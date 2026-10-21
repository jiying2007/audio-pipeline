/* Research-only fixed minimum dwell; no shipping API or AEC changes. */
#ifndef DEVICE_DWELL_SELECTOR_D27_H
#define DEVICE_DWELL_SELECTOR_D27_H
#include "device_shadow_selector_d24.h"
typedef struct d27_selection {
    d24_selection_t base;
    uint32_t last_switch, has_last;
} d27_selection_t;
static inline uint32_t d27_remaining(const d27_selection_t *s, uint32_t frame, uint32_t dwell) {
    return s->has_last && frame-s->last_switch<dwell ? dwell-(frame-s->last_switch) : 0u;
}
static inline int d27_choose(d27_selection_t *s, uint32_t frame, uint32_t dwell,
                            int active, int eligible, double primary, double shadow) {
    int change;
    if (!isfinite(primary) || !isfinite(shadow) || primary<0.0 || shadow<0.0 || s->base.bank>1u) return -1;
    if (!active) s->has_last=0u;
    if (active && d27_remaining(s,frame,dwell)) { s->base.streak=0u; return 0; }
    change=d24_choose(&s->base,active,eligible,primary,shadow);
    if (change==1) { s->last_switch=frame; s->has_last=1u; }
    return change;
}
#endif
