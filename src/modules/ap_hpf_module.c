#include "audio_pipeline/audio_modules.h"
#include "frontend/ap_frontend.h"
#include "ap_limits.h"
#include <stdint.h>
typedef struct ap_hpf_module_impl { ap_hpf_state_t state; uint32_t rate,channels; } ap_hpf_module_impl_t;
static int aligned16(const void*p){return ((uintptr_t)p&(AP_MODULE_STATE_ALIGNMENT-1u))==0u;}
size_t ap_module_hpf_state_size(void){return sizeof(ap_hpf_module_impl_t);}
ap_status_t ap_module_hpf_init(void*memory,size_t memory_size,uint32_t rate,uint32_t channels,ap_hpf_module_t**out){ap_hpf_module_impl_t*m;if(!memory||!out||!aligned16(memory))return AP_EINVAL;*out=NULL;if(memory_size<sizeof(*m))return AP_ENOMEM;if((rate!=8000u&&rate!=16000u)||rate>AP_BUILD_MAX_INTERNAL_RATE_HZ||channels<1u||channels>AP_BUILD_MAX_MIC_CHANNELS)return AP_EINVAL;m=(ap_hpf_module_impl_t*)memory;m->rate=rate;m->channels=channels;ap_hpf_init(&m->state,rate,channels);*out=(ap_hpf_module_t*)m;return AP_OK;}
void ap_module_hpf_reset(ap_hpf_module_t*module){ap_hpf_module_impl_t*m=(ap_hpf_module_impl_t*)module;if(m)ap_hpf_init(&m->state,m->rate,m->channels);}
ap_status_t ap_module_hpf_process(ap_hpf_module_t*module,float*samples,size_t frame_samples,uint32_t channel){ap_hpf_module_impl_t*m=(ap_hpf_module_impl_t*)module;if(!m||!samples||frame_samples!=m->rate/100u||channel>=m->channels)return AP_EINVAL;ap_hpf_process(&m->state,samples,(uint32_t)frame_samples,channel);return AP_OK;}
