#ifndef AP_RESEARCH_DUALMIC_GAIN_RAMP_D6_H
#define AP_RESEARCH_DUALMIC_GAIN_RAMP_D6_H
#include "enhance/ap_enhance.h"
#include <stdint.h>
typedef struct { float previous; uint32_t initialized; } d6_ramp_state_t;
typedef struct { float start, end; } d6_observation_t;
void d6_agc_init(ap_agc_state_t *, float, float);
void d6_agc_process_controlled(ap_agc_state_t *, float *, uint32_t, int,
                               d6_ramp_state_t *, float *, d6_observation_t *);
void d6_agc_process(ap_agc_state_t *, float *, uint32_t,
                    d6_ramp_state_t *, float *, d6_observation_t *);
#endif
