#ifndef AP_RUNTIME_IMPLEMENTATION_PRIVATE_H
#define AP_RUNTIME_IMPLEMENTATION_PRIVATE_H

/* This header is found only by src/platform/linux/ap_runtime.c because quoted
 * includes search the source directory first. It maps the existing proven
 * implementation bodies onto the v2 public names without exposing historical
 * API generations through the installed header or library symbol surface. */
#include "../../../../include/audio_pipeline/audio_runtime.h"

#define AP_RUNTIME_CONTROL_API_VERSION AP_RUNTIME_API_VERSION
#define AP_RUNTIME_METRICS_V3_API_VERSION AP_RUNTIME_API_VERSION
#define AP_RUNTIME_CRITICAL_STATE_API_VERSION AP_RUNTIME_API_VERSION

typedef struct ap_runtime_metrics_v2_internal {
    uint32_t struct_size;
    uint32_t api_version;
    uint64_t submitted_frames;
    uint64_t processed_frames;
    uint64_t input_full_events;
    uint64_t output_drop_events;
    uint64_t dsp_overruns;
    uint64_t command_full_events;
    uint64_t event_drop_events;
    uint64_t stream_discontinuities;
    uint64_t capture_gap_frames;
    uint64_t render_gap_frames;
    uint64_t timestamp_frames;
    uint64_t scheduler_bind_failures;
    uint64_t memory_lock_failures;
    uint32_t input_queue_high_water;
    uint32_t output_queue_high_water;
    uint32_t last_dsp_us;
    uint32_t max_dsp_us;
    uint32_t p50_dsp_us;
    uint32_t p95_dsp_us;
    uint32_t p99_dsp_us;
    int32_t actual_cpu;
    int32_t actual_policy;
    int32_t actual_priority;
    ap_quality_t quality;
    uint32_t reserved[8];
} ap_runtime_metrics_v2_internal_t;

#define ap_runtime_metrics_v2_t ap_runtime_metrics_v2_internal_t
#define ap_runtime_metrics_v3_t ap_runtime_metrics_t

#define ap_runtime_init_ex ap_runtime_open
#define ap_runtime_submit_ex ap_runtime_submit_frame
#define ap_runtime_get_metrics_v3 ap_runtime_read_metrics

#define ap_runtime_init static __attribute__((unused)) ap_internal_runtime_init_removed
#define ap_runtime_submit static __attribute__((unused)) ap_internal_runtime_submit_removed
#define ap_runtime_get_metrics static __attribute__((unused)) ap_internal_runtime_get_metrics_removed
#define ap_runtime_get_metrics_v2 static ap_internal_runtime_get_metrics_v2

#endif
