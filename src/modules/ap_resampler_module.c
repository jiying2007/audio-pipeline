#include "audio_pipeline/audio_modules.h"
#include "frontend/ap_resampler.h"
#include "ap_limits.h"
#include <stdint.h>

typedef struct ap_resampler_module_impl { ap_resampler_state_t state; } ap_resampler_module_impl_t;
static int aligned16(const void *p){return ((uintptr_t)p&(AP_MODULE_STATE_ALIGNMENT-1u))==0u;}
static int io_frame_ok(size_t frames) {
    return frames <= AP_IO_FRAME_MAX &&
           (frames == 80u || frames == 160u || frames == 240u ||
            frames == 320u || frames == 480u);
}
static int internal_frame_ok(size_t frames) {
    return frames <= AP_INTERNAL_FRAME_MAX && (frames == 80u || frames == 160u);
}
size_t ap_module_resampler_state_size(void){return sizeof(ap_resampler_module_impl_t);}
ap_status_t ap_module_resampler_init(void *memory,size_t memory_size,ap_resampler_module_t **out){ap_resampler_module_impl_t *m;if(!memory||!out||!aligned16(memory))return AP_EINVAL;*out=NULL;if(memory_size<sizeof(*m))return AP_ENOMEM;m=(ap_resampler_module_impl_t*)memory;ap_resampler_init(&m->state);*out=(ap_resampler_module_t*)m;return AP_OK;}
void ap_module_resampler_reset(ap_resampler_module_t *module){ap_resampler_module_impl_t*m=(ap_resampler_module_impl_t*)module;if(m)ap_resampler_reset(&m->state);}
ap_status_t ap_module_resampler_input_s16(ap_resampler_module_t *module,
                                         const int16_t *input, size_t input_frames,
                                         uint32_t channels, uint32_t channel,
                                         float *output, size_t output_frames) {
    ap_resampler_module_impl_t *m = (ap_resampler_module_impl_t *)module;
    if (!m || !input || !output || !io_frame_ok(input_frames) ||
        !internal_frame_ok(output_frames) || channels < 1u ||
        channels > AP_BUILD_MIC_CHANNEL_MAX || channel >= channels)
        return AP_EINVAL;
    ap_resample_input_channel(&m->state, channel, input, (uint32_t)input_frames,
                              channels, channel, output, (uint32_t)output_frames);
    return AP_OK;
}
ap_status_t ap_module_resampler_output_s16(ap_resampler_module_t *module,
                                          const float *input, size_t input_frames,
                                          int16_t *output, size_t output_frames) {
    ap_resampler_module_impl_t *m = (ap_resampler_module_impl_t *)module;
    if (!m || !input || !output || !internal_frame_ok(input_frames) ||
        !io_frame_ok(output_frames))
        return AP_EINVAL;
    ap_resample_output(&m->state, input, (uint32_t)input_frames,
                       output, (uint32_t)output_frames);
    return AP_OK;
}
uint32_t ap_module_resampler_filter_delay_samples(uint32_t input_rate_hz,
                                                  uint32_t output_rate_hz) {
    const uint32_t input_frames = input_rate_hz / 100u;
    const uint32_t output_frames = output_rate_hz / 100u;
    if (input_rate_hz % 100u != 0u || output_rate_hz % 100u != 0u ||
        !((io_frame_ok(input_frames) && internal_frame_ok(output_frames)) ||
          (internal_frame_ok(input_frames) && io_frame_ok(output_frames))))
        return 0u;
    return ap_resampler_filter_delay_samples(input_frames, output_frames);
}
