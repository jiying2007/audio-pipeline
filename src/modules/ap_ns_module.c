#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "ap_limits.h"
#include <math.h>
#include <stdint.h>
#include <string.h>
typedef struct ap_ns_module_impl { ap_ns_state_t state; float floor_gain; uint32_t frame_samples; } ap_ns_module_impl_t;
static int aligned16(const void*p){return ((uintptr_t)p&(AP_MODULE_STATE_ALIGNMENT-1u))==0u;}
static ap_enhance_mode_t mode(ap_quality_t q){return q==AP_QUALITY_FULL?AP_ENHANCE_FULL:(q==AP_QUALITY_LITE?AP_ENHANCE_LITE:AP_ENHANCE_SAFE);}
size_t ap_module_ns_state_size(void){return sizeof(ap_ns_module_impl_t);}
ap_status_t ap_module_ns_init(void*memory,size_t memory_size,const ap_module_ns_config_t*c,ap_ns_module_t**out){ap_ns_module_impl_t*m;if(!memory||!c||!out||!aligned16(memory))return AP_EINVAL;*out=NULL;if(memory_size<sizeof(*m))return AP_ENOMEM;if((c->sample_rate_hz!=8000u&&c->sample_rate_hz!=16000u)||c->sample_rate_hz>AP_BUILD_MAX_INTERNAL_RATE_HZ||!isfinite(c->floor_gain)||c->floor_gain<0.02f||c->floor_gain>1.0f)return AP_EINVAL;m=(ap_ns_module_impl_t*)memory;memset(m,0,sizeof(*m));m->frame_samples=c->sample_rate_hz/100u;m->floor_gain=c->floor_gain;ap_ns_init(&m->state,m->frame_samples);*out=(ap_ns_module_t*)m;return AP_OK;}
void ap_module_ns_reset(ap_ns_module_t*module){ap_ns_module_impl_t*m=(ap_ns_module_impl_t*)module;if(m)ap_ns_init(&m->state,m->frame_samples);}
ap_status_t ap_module_ns_process(ap_ns_module_t*module,ap_quality_t quality,const float*input,const float*predicted_echo,float*output,size_t frame_samples,int freq,int far,int dt,ap_module_ns_result_t*result){ap_ns_module_impl_t*m=(ap_ns_module_impl_t*)module;ap_ns_result_t r;if(!m||!input||!output||!result||frame_samples!=m->frame_samples||quality<AP_QUALITY_SAFE||quality>AP_QUALITY_FULL)return AP_EINVAL;
#if !AP_BUILD_STAGE_RES
if(freq)return AP_ESTATE;
#else
if(freq&&!predicted_echo)return AP_EINVAL;
#endif
ap_ns_process(&m->state,mode(quality),m->floor_gain,input,predicted_echo,output,m->frame_samples,freq,far,dt,&r);result->noise_rms_dbfs=r.noise_rms_dbfs;result->speech_probability=r.speech_probability;result->residual_echo_gain=r.residual_echo_gain;result->frequency_res_active=r.frequency_res_active;return AP_OK;}
