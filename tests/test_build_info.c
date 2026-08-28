#include "audio_pipeline/audio_types.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    const ap_build_info_t *info = ap_build_info();
    assert(info != NULL);
    assert(info->version_major == AP_VERSION_MAJOR);
    assert(info->version_minor == AP_VERSION_MINOR);
    assert(info->version_patch == AP_VERSION_PATCH);
    assert(strcmp(info->version, AP_VERSION_STRING) == 0);
    assert(info->max_io_rate_hz == AP_BUILD_MAX_IO_RATE_HZ);
    assert(info->max_internal_rate_hz == AP_BUILD_MAX_INTERNAL_RATE_HZ);
    assert(info->max_mic_channels == AP_BUILD_MAX_MIC_CHANNELS);
    assert(info->max_delay_ms == AP_BUILD_MAX_DELAY_MS);
    assert(info->max_aec_tail_ms == AP_BUILD_MAX_AEC_TAIL_MS);
    assert(info->runtime_queue_depth == AP_BUILD_RUNTIME_QUEUE_DEPTH);
    assert(info->has_pipeline == AP_HAVE_PIPELINE);
    assert(info->has_linux_runtime == AP_HAVE_LINUX_RUNTIME);
    assert(info->fast_math == AP_BUILD_FAST_MATH);
#if AP_HAVE_MODULE_AEC
    assert(info->aec_backend != NULL && info->aec_backend[0] != '\0');
#endif
#if AP_HAVE_MODULE_NS
    assert(info->ns_estimator != NULL && info->ns_estimator[0] != '\0');
#endif
    assert(info->simd_backend != NULL && info->simd_backend[0] != '\0');
#if AP_HAVE_MODULE_RESAMPLER
    assert(info->resampler_mode != NULL && info->resampler_mode[0] != '\0');
#endif
    puts("audio-pipeline build info contract: OK");
    return 0;
}
