#ifndef AUDIO_PIPELINE_AP_PIPELINE_INTERNAL_H
#define AUDIO_PIPELINE_AP_PIPELINE_INTERNAL_H

#include "audio_pipeline/audio_pipeline.h"
#include "ap_limits.h"
#include "frontend/ap_resampler.h"
#include "enhance/ap_enhance.h"
#include <stdint.h>

#if AP_BUILD_STAGE_HPF || AP_BUILD_STAGE_BF
#include "frontend/ap_frontend.h"
#endif
#if AP_BUILD_STAGE_SYNC
#include "sync/ap_sync.h"
#endif
#if AP_BUILD_ACTIVITY
#include "activity/ap_activity.h"
#endif
#if AP_BUILD_STAGE_AEC
#include "aec/ap_aec.h"
#endif

#define AP_ANY_DSP_STAGE (AP_BUILD_STAGE_HPF || AP_BUILD_STAGE_BF || AP_BUILD_STAGE_SYNC || AP_BUILD_STAGE_AEC || AP_BUILD_STAGE_RES || AP_BUILD_STAGE_NS || AP_BUILD_STAGE_AGC || AP_BUILD_STAGE_VAD)

struct ap_pipeline {
    ap_config_t cfg;
    ap_metrics_t metrics;
    uint32_t io_frame;
    uint32_t internal_frame;
    ap_resampler_state_t resampler;

#if AP_BUILD_STAGE_HPF
    ap_hpf_state_t hpf;
#endif
#if AP_BUILD_STAGE_BF
    ap_beamformer_state_t beamformer;
#endif
#if AP_BUILD_STAGE_SYNC
    ap_sync_state_t sync;
#endif
#if AP_BUILD_ACTIVITY
    ap_activity_state_t activity;
#endif
#if AP_BUILD_STAGE_AEC
    ap_aec_state_t aec;
#endif
#if AP_BUILD_STAGE_RES
    ap_res_state_t res;
#endif
#if AP_BUILD_STAGE_NS
    ap_ns_state_t ns;
#endif
#if AP_BUILD_STAGE_AGC
    ap_agc_state_t agc;
#endif
#if AP_BUILD_STAGE_VAD
    ap_vad_state_t vad;
#endif

#if AP_ANY_DSP_STAGE
    union {
        float mic0[AP_INTERNAL_FRAME_MAX];
        float reference[AP_INTERNAL_FRAME_MAX];
        float work[AP_INTERNAL_FRAME_MAX];
    };
    union {
        float mic1[AP_INTERNAL_FRAME_MAX];
        float aec_out[AP_INTERNAL_FRAME_MAX];
    };
    union {
        float mono[AP_INTERNAL_FRAME_MAX];
        float processed[AP_INTERNAL_FRAME_MAX];
    };
#if AP_BUILD_STAGE_AEC
    float echo_estimate[AP_INTERNAL_FRAME_MAX];
#endif
#else
    float raw_scratch[AP_INTERNAL_FRAME_MAX];
#endif

    ap_quality_t quality;
    uint32_t aec_convergence_frames;
};

_Static_assert((AP_PIPELINE_STATE_ALIGNMENT & (AP_PIPELINE_STATE_ALIGNMENT - 1u)) == 0u,
               "pipeline state alignment must remain power of two");
_Static_assert(sizeof(struct ap_pipeline) <= AP_PIPELINE_STATE_MAX_BYTES,
               "pipeline resident state exceeded public ceiling");

#endif
