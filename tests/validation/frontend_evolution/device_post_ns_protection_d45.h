#ifndef DEVICE_POST_NS_PROTECTION_D45_H
#define DEVICE_POST_NS_PROTECTION_D45_H
#include "device_power_attribution_d43.h"

/* D45 observer extends each saved D43 bin without altering algorithm state. */
typedef struct {
    ap_power_bin_d43_t base;
    float updated_noise,combined_gain_before,combined_gain_after;
} ap_post_ns_bin_d45_t;
typedef struct { ap_post_ns_bin_d45_t bin[AP_NS_BINS_MAX]; } ap_post_ns_observer_d45_t;

static inline float ap_post_ns_gain_d45(float combined,float floor,int active,int protect) {
    return active && protect && floor>combined ? floor : combined;
}

/* One fixed mapping; the D42 state/update and D43 observer remain unchanged. */
static inline int ap_innovation_noise_floor_d45(double e,double r,double cr,double ci,double noise,uint32_t count,float *floor,int *valid) {
    double q,fraction,innovation,bound;
    *floor=0.0f;*valid=0;
    if (!isfinite(e) || !isfinite(r) || !isfinite(cr) || !isfinite(ci) || !isfinite(noise) || noise<0.0 || e<0.0 || r<0.0 || count>10u) return 0;
    if (count<10u || e<=1e-12 || r<=1e-12) return 1;
    q=(cr*cr+ci*ci)/(e*r);
    if (!isfinite(q)) return 0;
    q=q<0.0 ? 0.0 : q>1.0 ? 1.0 : q;
    fraction=1.0-q;
    innovation=r*fraction;
    bound=2.0*noise;
    if (!isfinite(fraction) || !isfinite(innovation) || !isfinite(bound)) return 0;
    if (innovation>bound) *floor=(float)sqrt(fraction);
    *valid=1;return isfinite(*floor);
}
int ap_ns_process_d45(ap_ns_state_t *,ap_noise_conditioned_guard_d42_t *,
    ap_post_ns_observer_d45_t *,int,ap_enhance_mode_t,float,const float *,
    const float *,float *,uint32_t,int,int,int,ap_ns_result_t *);
#endif
