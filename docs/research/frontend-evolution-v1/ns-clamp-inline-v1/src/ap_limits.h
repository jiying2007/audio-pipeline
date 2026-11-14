#ifndef AUDIO_PIPELINE_AP_LIMITS_H
#define AUDIO_PIPELINE_AP_LIMITS_H

#include "audio_pipeline/audio_pipeline_build.h"
#include "ap_numeric.h"

#define AP_INTERNAL_RATE_MAX AP_BUILD_MAX_INTERNAL_RATE_HZ
#define AP_INTERNAL_FRAME_MAX AP_BUILD_INTERNAL_FRAME_MAX
#define AP_IO_FRAME_MAX AP_BUILD_IO_FRAME_MAX
#define AP_BUILD_MIC_CHANNEL_MAX AP_BUILD_MAX_MIC_CHANNELS

/* ---- Public control-plane value ranges --------------------------------
 * ap_config_t validation, ap_pipeline_apply_tuning() and the Linux runtime
 * command audit must accept exactly the same values. Duplicating the literals
 * at each entry point let them drift apart, so the ranges live here and every
 * caller goes through the predicates below. */
#define AP_TUNING_AEC_MU_MIN 0.0f /* exclusive */
#define AP_TUNING_AEC_MU_MAX 1.0f /* inclusive */
#define AP_TUNING_NS_FLOOR_MIN 0.02f
#define AP_TUNING_NS_FLOOR_MAX 1.0f
#define AP_TUNING_AGC_TARGET_MIN_DBFS (-60.0f)
#define AP_TUNING_AGC_TARGET_MAX_DBFS (-1.0f)
#define AP_TUNING_LIMITER_MIN_DBFS (-20.0f)
#define AP_TUNING_LIMITER_MAX_DBFS (-0.1f)

static inline int ap_tuning_aec_mu_ok(float value) {
    return ap_float_is_finite(value) && value > AP_TUNING_AEC_MU_MIN &&
           value <= AP_TUNING_AEC_MU_MAX;
}
static inline int ap_tuning_ns_floor_ok(float value) {
    return ap_float_is_finite(value) && value >= AP_TUNING_NS_FLOOR_MIN &&
           value <= AP_TUNING_NS_FLOOR_MAX;
}
static inline int ap_tuning_agc_target_ok(float value) {
    return ap_float_is_finite(value) &&
           value >= AP_TUNING_AGC_TARGET_MIN_DBFS &&
           value <= AP_TUNING_AGC_TARGET_MAX_DBFS;
}
static inline int ap_tuning_limiter_ok(float value) {
    return ap_float_is_finite(value) && value >= AP_TUNING_LIMITER_MIN_DBFS &&
           value <= AP_TUNING_LIMITER_MAX_DBFS;
}
/* The limiter must stay strictly above the AGC target, otherwise the chain
 * cannot reach target without being clipped. */
static inline int ap_tuning_agc_pair_ok(float target_dbfs, float limiter_dbfs) {
    return ap_tuning_agc_target_ok(target_dbfs) &&
           ap_tuning_limiter_ok(limiter_dbfs) && target_dbfs < limiter_dbfs;
}

#endif
