#ifndef DEVICE_POWER_ATTRIBUTION_D43_H
#define DEVICE_POWER_ATTRIBUTION_D43_H
#include "device_noise_conditioned_protection_d42.h"

/* Saved inputs of the existing D42 formula, not a new estimator. */
typedef struct {
    double e,r,cr,ci,noise;
    float er,ei,rr,ri,power,echo_power;
    float original_target,old_gain,floor,applied_target,res_gain;
    uint32_t valid;
} ap_power_bin_d43_t;
typedef struct { ap_power_bin_d43_t bin[AP_NS_BINS_MAX]; } ap_power_observer_d43_t;

static inline int ap_power_snapshot_d43(uint32_t frame,uint32_t frames) {
    return frame<frames && (frame%100u==0u || frame+1u==frames ||
        frame==1u || frame==9u || frame==10u || frame==11u ||
        frame==999u || frame==1001u || frame==1199u || frame==1200u ||
        frame==1201u || frame==1599u || frame==1600u || frame==1601u ||
        frame==1799u || frame==1800u || frame==1801u);
}
int ap_ns_process_d43(ap_ns_state_t *,ap_noise_conditioned_guard_d42_t *,
    ap_power_observer_d43_t *,int,ap_enhance_mode_t,float,const float *,
    const float *,float *,uint32_t,int,int,int,ap_ns_result_t *);
#endif
