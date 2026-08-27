#ifndef AUDIO_PIPELINE_AP_PIPELINE_INTERNAL_H
#define AUDIO_PIPELINE_AP_PIPELINE_INTERNAL_H

#include "audio_pipeline/audio_pipeline.h"
#include "aec/ap_aec.h"
#include "ap_limits.h"
#include "enhance/ap_enhance.h"
#include "frontend/ap_frontend.h"
#include "sync/ap_sync.h"

#include <stdint.h>

struct ap_pipeline {
    ap_config_t cfg;
    ap_metrics_t metrics;
    uint32_t io_frame;
    uint32_t internal_frame;

    ap_frontend_state_t frontend;

    /* Strictly sequential frame stages share storage. */
    union {
        float mic0[AP_INTERNAL_FRAME_MAX];
        float reference[AP_INTERNAL_FRAME_MAX];
    };
    union {
        float mic1[AP_INTERNAL_FRAME_MAX];
        float aec_out[AP_INTERNAL_FRAME_MAX];
    };
    union {
        float mono[AP_INTERNAL_FRAME_MAX];
        float ns_out[AP_INTERNAL_FRAME_MAX];
    };
    float echo_estimate[AP_INTERNAL_FRAME_MAX];
    float work[AP_INTERNAL_FRAME_MAX];

    ap_sync_state_t sync;
    ap_aec_state_t aec;
    ap_enhance_state_t enhance;
    ap_quality_t quality;
    uint32_t double_talk_hangover;
};

_Static_assert((AP_PIPELINE_STATE_ALIGNMENT & (AP_PIPELINE_STATE_ALIGNMENT - 1u)) == 0u,
               "pipeline state alignment must remain power of two");
_Static_assert(sizeof(struct ap_pipeline) <= AP_PIPELINE_STATE_MAX_BYTES,
               "pipeline resident state exceeded the public static-state ceiling");

#endif
