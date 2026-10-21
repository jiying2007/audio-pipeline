#ifndef DEVICE_MAGNITUDE_LOWER_BOUND_D49_H
#define DEVICE_MAGNITUDE_LOWER_BOUND_D49_H
#include "device_post_ns_protection_d45.h"

/* Past complex fit predicts the current FFT operands. No state mutation. */
static inline int ap_current_innovation_values_d49(double e,double cr,double ci,
    float er,float ei,float rr,float ri,double *p,double *j) {
    double hr,hi,a,b,c,d,pr,pi,ir,ii,ir2,ii2;
    *p=0.0;*j=0.0;
    if (!isfinite(e) || e<=1e-12 || !isfinite(cr) || !isfinite(ci) ||
        !isfinite(er) || !isfinite(ei) || !isfinite(rr) || !isfinite(ri)) return 0;
    hr=cr/e;hi=ci/e;
    if (!isfinite(hr) || !isfinite(hi)) return 0;
    a=hr*(double)er;b=hi*(double)ei;c=hr*(double)ei;d=hi*(double)er;
    if (!isfinite(a) || !isfinite(b) || !isfinite(c) || !isfinite(d)) return 0;
    pr=a-b;pi=c+d;ir=(double)rr-pr;ii=(double)ri-pi;
    if (!isfinite(pr) || !isfinite(pi) || !isfinite(ir) || !isfinite(ii)) return 0;
    ir2=ir*ir;ii2=ii*ii;
    *p=(double)rr*(double)rr+(double)ri*(double)ri;*j=ir2+ii2;
    return isfinite(ir2) && isfinite(ii2) && isfinite(*p) && isfinite(*j);
}

/* The signed amplitude difference is allowed to be negative. Keep raw J
 * above unchanged; L is a model-relative protection quantity, not near truth.
 * Reproduce the original ordered prediction operands, without new state. */
static inline int ap_magnitude_lower_bound_value_d49(double e,double cr,
    double ci,float er,float ei,double p,double *lower) {
    double hr,hi,a,b,c,d,pr,pi,rmag,pmag,difference;
    *lower=0.0;
    if (!isfinite(e) || e<=1e-12 || !isfinite(cr) || !isfinite(ci) ||
        !isfinite(er) || !isfinite(ei) || !isfinite(p) || p<0.0) return 0;
    hr=cr/e;hi=ci/e;
    if (!isfinite(hr) || !isfinite(hi)) return 0;
    a=hr*(double)er;b=hi*(double)ei;c=hr*(double)ei;d=hi*(double)er;
    if (!isfinite(a) || !isfinite(b) || !isfinite(c) || !isfinite(d)) return 0;
    pr=a-b;pi=c+d;
    if (!isfinite(pr) || !isfinite(pi)) return 0;
    rmag=sqrt(p);pmag=hypot(pr,pi);difference=rmag-pmag;
    if (!isfinite(rmag) || rmag<0.0 || !isfinite(pmag) || pmag<0.0 ||
        !isfinite(difference)) return 0;
    if (difference>0.0) *lower=difference*difference;
    return isfinite(*lower) && *lower>=0.0;
}

static inline int ap_magnitude_lower_bound_floor_d49(double e,double r,double cr,
    double ci,double noise,uint32_t count,float er,float ei,float rr,float ri,
    float *floor,int *valid) {
    double p,j,lower,bound,ratio;
    *floor=0.0f;*valid=0;
    if (!isfinite(e) || !isfinite(r) || !isfinite(cr) || !isfinite(ci) ||
        !isfinite(noise) || noise<0.0 || e<0.0 || r<0.0 || count>10u ||
        !isfinite(er) || !isfinite(ei) || !isfinite(rr) || !isfinite(ri)) return 0;
    if (count<10u || e<=1e-12 || r<=1e-12) return 1;
    if (!ap_current_innovation_values_d49(e,cr,ci,er,ei,rr,ri,&p,&j)) return 0;
    if (!ap_magnitude_lower_bound_value_d49(e,cr,ci,er,ei,p,&lower)) return 0;
    bound=2.0*noise;
    if (!isfinite(bound)) return 0;
    if (p>1e-12 && lower>bound) {
        ratio=lower/p;
        if (!isfinite(ratio)) return 0;
        ratio=ratio<0.0 ? 0.0 : ratio>1.0 ? 1.0 : ratio;
        *floor=(float)sqrt(ratio);
    }
    *valid=1;return isfinite(*floor);
}
int ap_ns_process_d49(ap_ns_state_t *,ap_noise_conditioned_guard_d42_t *,
    ap_post_ns_observer_d45_t *,int,ap_enhance_mode_t,float,const float *,
    const float *,float *,uint32_t,int,int,int,ap_ns_result_t *);
#endif

