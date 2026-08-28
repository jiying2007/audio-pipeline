#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "ap_limits.h"
#include <math.h>
#include <stdint.h>
static int aligned16(const void*p){return ((uintptr_t)p&(AP_MODULE_STATE_ALIGNMENT-1u))==0u;}
static ap_enhance_mode_t mode(ap_quality_t q){return q==AP_QUALITY_FULL?AP_ENHANCE_FULL:(q==AP_QUALITY_LITE?AP_ENHANCE_LITE:AP_ENHANCE_SAFE);}
size_t ap_module_res_state_size(void){return sizeof(ap_res_state_t);}
ap_status_t ap_module_res_init(void*memory,size_t memory_size,ap_res_module_t**out){if(!memory||!out||!aligned16(memory))return AP_EINVAL;*out=NULL;if(memory_size<sizeof(ap_res_state_t))return AP_ENOMEM;ap_res_init((ap_res_state_t*)memory);*out=(ap_res_module_t*)memory;return AP_OK;}
void ap_module_res_reset(ap_res_module_t*module){if(module)ap_res_init((ap_res_state_t*)module);}
ap_status_t ap_module_res_process(ap_res_module_t*module,ap_quality_t quality,float*samples,size_t frame_samples,float echo_energy,float residual_energy,int far,int dt,float*gain){if(!module||!samples||!gain||(frame_samples!=80u&&frame_samples!=160u)||frame_samples>AP_INTERNAL_FRAME_MAX||quality<AP_QUALITY_SAFE||quality>AP_QUALITY_FULL||!isfinite(echo_energy)||!isfinite(residual_energy)||echo_energy<0.0f||residual_energy<0.0f)return AP_EINVAL;*gain=ap_res_process((ap_res_state_t*)module,mode(quality),samples,(uint32_t)frame_samples,echo_energy,residual_energy,far,dt);return AP_OK;}
