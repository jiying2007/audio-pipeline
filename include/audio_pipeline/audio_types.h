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
#define AP_BUILD_INFO_API_VERSION 1u

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

typedef uint32_t ap_module_mask_t;
enum {
    AP_MODULE_CAP_RESAMPLER = 1u << 0,
    AP_MODULE_CAP_HPF       = 1u << 1,
    AP_MODULE_CAP_BF        = 1u << 2,
    AP_MODULE_CAP_SYNC      = 1u << 3,
    AP_MODULE_CAP_ACTIVITY  = 1u << 4,
    AP_MODULE_CAP_AEC       = 1u << 5,
    AP_MODULE_CAP_RES       = 1u << 6,
    AP_MODULE_CAP_NS        = 1u << 7,
    AP_MODULE_CAP_AGC       = 1u << 8,
    AP_MODULE_CAP_VAD       = 1u << 9
};

typedef struct ap_build_info {
    uint32_t struct_size;
    uint32_t api_version;
    uint32_t version_major;
    uint32_t version_minor;
    uint32_t version_patch;
    ap_module_mask_t module_mask;
    uint32_t max_io_rate_hz;
    uint32_t max_internal_rate_hz;
    uint32_t max_mic_channels;
    uint32_t max_delay_ms;
    uint32_t max_aec_tail_ms;
    uint32_t runtime_queue_depth;
    uint8_t has_pipeline;
    uint8_t has_linux_runtime;
    uint8_t fast_math;
    uint8_t reserved8;
    const char *version;
    const char *aec_backend;
    const char *ns_estimator;
    const char *simd_backend;
    const char *resampler_mode;
    const char *source_revision;
    const char *compiler_id;
    const char *compiler_version;
    const char *target_triple;
    const char *build_type;
    const char *config_digest;
    uint32_t reserved[8];
} ap_build_info_t;

const ap_build_info_t *ap_build_info(void);

#ifdef __cplusplus
}
#endif

#endif
