#ifndef DEVICE_NOISE_CONDITIONED_PROTECTION_D42_H
#define DEVICE_NOISE_CONDITIONED_PROTECTION_D42_H
#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <string.h>
typedef struct {
    double e[AP_NS_BINS_MAX],r[AP_NS_BINS_MAX],cr[AP_NS_BINS_MAX],ci[AP_NS_BINS_MAX];
    float er[AP_NS_BINS_MAX],ei[AP_NS_BINS_MAX];
    uint32_t count,count_before,valid_bins,raised_bins;
    double floor_mean;
} ap_noise_conditioned_guard_d42_t;
static inline int ap_noise_conditioned_floor_d42(double e,double r,double cr,double ci,double noise,uint32_t count,float *floor,int *valid) {
    double q,fraction;
    *floor=0.0f;*valid=0;
    if (!isfinite(e) || !isfinite(r) || !isfinite(cr) || !isfinite(ci) || !isfinite(noise) || noise<0.0 || e<0.0 || r<0.0 || count>10u) return 0;
    if (count<10u || e<=1e-12 || r<=1e-12) return 1;
    q=(cr*cr+ci*ci)/(e*r);
    if (!isfinite(q)) return 0;
    q=q<0.0 ? 0.0 : q>1.0 ? 1.0 : q;
    fraction=1.0-q-noise/r;
    if (!isfinite(fraction)) return 0;
    fraction=fraction<0.0 ? 0.0 : fraction;
    *floor=(float)sqrt(fraction);*valid=1;return isfinite(*floor);
}
static inline int ap_noise_conditioned_update_d42(ap_noise_conditioned_guard_d42_t *g,uint32_t k,float er,float ei,float rr,float ri) {
    double a=(double)er,b=(double)ei,c=(double)rr,d=(double)ri;
    if (k>=AP_NS_BINS_MAX || !isfinite(a) || !isfinite(b) || !isfinite(c) || !isfinite(d)) return 0;
    g->e[k]=0.8*g->e[k]+0.2*(a*a+b*b);
    g->r[k]=0.8*g->r[k]+0.2*(c*c+d*d);
    g->cr[k]=0.8*g->cr[k]+0.2*(c*a+d*b);
    g->ci[k]=0.8*g->ci[k]+0.2*(d*a-c*b);
    return isfinite(g->e[k]) && isfinite(g->r[k]) && isfinite(g->cr[k]) && isfinite(g->ci[k]);
}
int ap_ns_process_d42(ap_ns_state_t *,ap_noise_conditioned_guard_d42_t *,int,ap_enhance_mode_t,float,const float *,const float *,float *,uint32_t,int,int,int,ap_ns_result_t *);
#endif
