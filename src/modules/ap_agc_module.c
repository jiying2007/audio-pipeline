#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "ap_limits.h"
#include <math.h>
#include <stdint.h>
typedef struct ap_agc_module_impl { ap_agc_state_t state; float target,limiter; } ap_agc_module_impl_t;
static int aligned16(const void*p){return ((uintptr_t)p&(AP_MODULE_STATE_ALIGNMENT-1u))==0u;}
size_t ap_module_agc_state_size(void){return sizeof(ap_agc_module_impl_t);}
ap_status_t ap_module_agc_init(void*memory,size_t memory_size,const ap_module_agc_config_t*c,ap_agc_module_t**out){ap_agc_module_impl_t*m;if(!memory||!c||!out||!aligned16(memory))return AP_EINVAL;*out=NULL;if(memory_size<sizeof(*m))return AP_ENOMEM;if(!isfinite(c->target_dbfs)||!isfinite(c->limiter_dbfs)||c->target_dbfs>-1.0f||c->target_dbfs<-60.0f||c->limiter_dbfs>-0.1f||c->limiter_dbfs<-20.0f||c->target_dbfs>=c->limiter_dbfs)return AP_EINVAL;m=(ap_agc_module_impl_t*)memory;m->target=c->target_dbfs;m->limiter=c->limiter_dbfs;ap_agc_init(&m->state,m->target,m->limiter);*out=(ap_agc_module_t*)m;return AP_OK;}
void ap_module_agc_reset(ap_agc_module_t*module){ap_agc_module_impl_t*m=(ap_agc_module_impl_t*)module;if(m)ap_agc_init(&m->state,m->target,m->limiter);}
ap_status_t ap_module_agc_process(ap_agc_module_t*module,float*samples,size_t frame_samples){ap_agc_module_impl_t*m=(ap_agc_module_impl_t*)module;if(!m||!samples||(frame_samples!=80u&&frame_samples!=160u)||frame_samples>AP_INTERNAL_FRAME_MAX)return AP_EINVAL;ap_agc_process(&m->state,samples,(uint32_t)frame_samples);return AP_OK;}
