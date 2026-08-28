#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "ap_limits.h"
#include <math.h>
#include <stdint.h>
typedef struct ap_vad_module_impl { ap_vad_state_t state; } ap_vad_module_impl_t;
static int aligned16(const void*p){return ((uintptr_t)p&(AP_MODULE_STATE_ALIGNMENT-1u))==0u;}
size_t ap_module_vad_state_size(void){return sizeof(ap_vad_module_impl_t);}
ap_status_t ap_module_vad_init(void*memory,size_t memory_size,ap_vad_module_t**out){ap_vad_module_impl_t*m;if(!memory||!out||!aligned16(memory))return AP_EINVAL;*out=NULL;if(memory_size<sizeof(*m))return AP_ENOMEM;m=(ap_vad_module_impl_t*)memory;ap_vad_init(&m->state);*out=(ap_vad_module_t*)m;return AP_OK;}
void ap_module_vad_reset(ap_vad_module_t*module){ap_vad_module_impl_t*m=(ap_vad_module_impl_t*)module;if(m)ap_vad_init(&m->state);}
ap_status_t ap_module_vad_process(ap_vad_module_t*module,const float*samples,size_t frame_samples,float upstream,int use_upstream,ap_module_vad_result_t*result){ap_vad_module_impl_t*m=(ap_vad_module_impl_t*)module;ap_vad_result_t r;if(!m||!samples||!result||(frame_samples!=80u&&frame_samples!=160u)||frame_samples>AP_INTERNAL_FRAME_MAX||!isfinite(upstream)||upstream<0.0f||upstream>1.0f)return AP_EINVAL;ap_vad_process(&m->state,samples,(uint32_t)frame_samples,upstream,use_upstream,&r);result->probability=r.probability;result->active=r.active;return AP_OK;}
