#ifndef AUDIO_PIPELINE_AUDIO_TYPES_H
#define AUDIO_PIPELINE_AUDIO_TYPES_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AP_FRAME_MS 10u
#define AP_MAX_MIC_CHANNELS 2u
#define AP_MAX_IO_RATE_HZ 48000u
#define AP_MAX_IO_FRAME_SAMPLES (AP_MAX_IO_RATE_HZ / 100u)

typedef enum ap_status {
    AP_OK = 0,
    AP_EINVAL = -1,
    AP_ENOMEM = -2,
    AP_ESTATE = -3,
    AP_EFULL = -4,
    AP_EEMPTY = -5
} ap_status_t;

typedef enum ap_quality {
    AP_QUALITY_SAFE = 0,
    AP_QUALITY_LITE = 1,
    AP_QUALITY_FULL = 2
} ap_quality_t;

typedef enum ap_aec_backend {
    AP_AEC_BACKEND_MDF = 0,
    AP_AEC_BACKEND_NLMS = 1
} ap_aec_backend_t;

#ifdef __cplusplus
}
#endif

#endif
