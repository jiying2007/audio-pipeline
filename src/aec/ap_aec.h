#ifndef AUDIO_PIPELINE_AP_AEC_H
#define AUDIO_PIPELINE_AP_AEC_H

#include "audio_pipeline/audio_pipeline_build.h"
#include "arch/ap_kernels.h"
#include "dsp/ap_dsp.h"
#include <stdint.h>

#define AP_AEC_CAP AP_BUILD_AEC_CAP
#define AP_AEC_SUBBLOCKS_PER_FRAME 5u
#define AP_AEC_BLOCK_MAX (AP_BUILD_INTERNAL_FRAME_MAX / AP_AEC_SUBBLOCKS_PER_FRAME)
#define AP_AEC_FFT_MAX (AP_AEC_BLOCK_MAX * 2u)
#define AP_AEC_BINS_MAX (AP_AEC_FFT_MAX / 2u + 1u)
#define AP_AEC_PARTITIONS_MAX AP_BUILD_AEC_PARTITIONS_MAX

typedef enum ap_aec_kind { AP_AEC_KIND_MDF = 0, AP_AEC_KIND_NLMS = 1 } ap_aec_kind_t;

#if defined(AP_BUILD_AEC_MDF)
typedef struct ap_mdf_state {
    uint32_t block, nfft, bins, partitions, active_partitions;
    uint32_t x_head, constrain_partition, adapt_phase;
    float prev_ref[AP_AEC_BLOCK_MAX];
    float x_power_sum[AP_AEC_BINS_MAX];
    float x_power_total;
    ap_complex_t x_history[AP_AEC_PARTITIONS_MAX][AP_AEC_BINS_MAX];
    ap_complex_t weights[AP_AEC_PARTITIONS_MAX][AP_AEC_BINS_MAX];
    ap_complex_t fft[AP_AEC_FFT_MAX];
    ap_complex_t acc[AP_AEC_FFT_MAX];
} ap_mdf_state_t;
#endif

typedef struct ap_aec_state {
    uint32_t taps, active_taps, active_adapt_stride;
#if defined(AP_BUILD_AEC_MDF)
    ap_mdf_state_t backend;
#elif defined(AP_BUILD_AEC_NLMS)
    float history[AP_AEC_CAP * 2u];
    float weights[AP_AEC_CAP];
    uint32_t pos, adapt_phase;
#else
#error "Exactly one AEC backend must be selected"
#endif
} ap_aec_state_t;

typedef struct ap_aec_result { float echo_energy; } ap_aec_result_t;
typedef struct ap_aec_status {
    ap_aec_kind_t kind;
    uint32_t active_taps, active_adapt_stride, active_partitions, block_samples;
} ap_aec_status_t;

void ap_aec_backend_init(ap_aec_state_t *, uint32_t, uint32_t, uint32_t);
void ap_aec_backend_reset(ap_aec_state_t *);
void ap_aec_backend_set_active(ap_aec_state_t *, uint32_t, uint32_t);
void ap_aec_backend_process(ap_aec_state_t *, int, float, uint32_t,
                            const float *, const float *, float *, float *,
                            int, int, ap_aec_result_t *);
void ap_aec_backend_get_status(const ap_aec_state_t *, ap_aec_status_t *);

#endif
