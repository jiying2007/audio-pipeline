#ifndef AUDIO_PIPELINE_AUDIO_RUNTIME_H
#define AUDIO_PIPELINE_AUDIO_RUNTIME_H

#include "audio_pipeline/audio_diag.h"
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AP_RUNTIME_STATE_MAX_BYTES (64u * 1024u)
#define AP_RUNTIME_STATE_ALIGNMENT 16u
#define AP_RUNTIME_CONTROL_API_VERSION 2u
#define AP_RUNTIME_COMMAND_QUEUE_DEPTH 4u
#define AP_RUNTIME_EVENT_QUEUE_DEPTH 4u
#define AP_RUNTIME_LATENCY_BUCKETS 12u

typedef struct ap_runtime ap_runtime_t;

typedef struct ap_runtime_config {
    int dsp_cpu;              /* -1: do not pin; default */
    int dsp_priority;         /* 0: SCHED_OTHER; default */
    uint32_t overload_us;     /* default 9000 for a 10 ms frame */
    uint32_t recover_frames;  /* sustained healthy frames before upgrade */
} ap_runtime_config_t;

typedef struct ap_runtime_options {
    uint32_t struct_size;
    uint32_t api_version;
    size_t dsp_stack_bytes;   /* 0: pthread default */
    uint8_t lock_memory;      /* best-effort mlockall; failure is observable */
    uint8_t set_thread_name;
    uint8_t reserved8[6];
    char thread_name[16];
    uint32_t reserved[8];
} ap_runtime_options_t;

typedef uint32_t ap_frame_metadata_flags_t;
enum {
    AP_FRAME_CAPTURE_TIMESTAMP_VALID = 1u << 0,
    AP_FRAME_RENDER_TIMESTAMP_VALID = 1u << 1,
    AP_FRAME_CAPTURE_DISCONTINUITY = 1u << 2,
    AP_FRAME_RENDER_DISCONTINUITY = 1u << 3,
    AP_FRAME_CLOCK_RESET = 1u << 4,
    AP_FRAME_XRUN = 1u << 5,
    AP_FRAME_CODEC_REOPEN = 1u << 6
};

typedef struct ap_frame_metadata {
    uint32_t struct_size;
    uint32_t api_version;
    ap_frame_metadata_flags_t flags;
    uint32_t reserved0;
    uint64_t stream_sequence;
    uint64_t capture_timestamp_ns;
    uint64_t render_timestamp_ns;
    uint32_t lost_capture_frames;
    uint32_t lost_render_frames;
    uint32_t reserved[6];
} ap_frame_metadata_t;

typedef enum ap_runtime_command_kind {
    AP_RUNTIME_COMMAND_ECHO_PATH_CHANGE = 1,
    AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY = 2,
    AP_RUNTIME_COMMAND_RESET = 3,
    AP_RUNTIME_COMMAND_SET_QUALITY = 4,
    AP_RUNTIME_COMMAND_SET_TUNING = 5
} ap_runtime_command_kind_t;

typedef struct ap_runtime_command {
    uint32_t struct_size;
    uint32_t api_version;
    uint32_t kind;
    uint32_t reserved0;
    union {
        struct {
            ap_discontinuity_flags_t flags;
            uint32_t lost_frames;
        } discontinuity;
        struct {
            ap_quality_t quality;
            uint32_t reserved;
        } set_quality;
        ap_tuning_t tuning;
    } data;
} ap_runtime_command_t;

typedef struct ap_runtime_metrics {
    uint64_t submitted_frames;
    uint64_t processed_frames;
    uint64_t input_full_events;
    uint64_t output_drop_events;
    uint64_t dsp_overruns;
    uint32_t last_dsp_us;
    uint32_t max_dsp_us;
    ap_quality_t quality;
} ap_runtime_metrics_t;

typedef struct ap_runtime_metrics_v2 {
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
} ap_runtime_metrics_v2_t;

ap_runtime_config_t ap_runtime_config_default(void);
ap_runtime_options_t ap_runtime_options_default(void);
size_t ap_runtime_state_size(void);
size_t ap_runtime_state_alignment(void);

ap_status_t ap_runtime_init(void *memory,
                            size_t memory_size,
                            ap_pipeline_t *pipeline,
                            const ap_runtime_config_t *config,
                            ap_runtime_t **out_runtime);
ap_status_t ap_runtime_init_ex(void *memory,
                               size_t memory_size,
                               ap_pipeline_t *pipeline,
                               const ap_runtime_config_t *config,
                               const ap_runtime_options_t *options,
                               ap_runtime_t **out_runtime);
ap_status_t ap_runtime_start(ap_runtime_t *runtime);
void ap_runtime_stop(ap_runtime_t *runtime);
void ap_runtime_deinit(ap_runtime_t *runtime);

/* SPSC producer. Submission never waits; AP_EFULL exposes backpressure. */
ap_status_t ap_runtime_submit(ap_runtime_t *runtime,
                              const int16_t *mic_interleaved,
                              const int16_t *render_or_null);
ap_status_t ap_runtime_submit_ex(ap_runtime_t *runtime,
                                 const int16_t *mic_interleaved,
                                 const int16_t *render_or_null,
                                 const ap_frame_metadata_t *metadata_or_null);

/* Single control producer -> DSP worker command queue. Commands are applied only
 * at frame boundaries, preserving worker ownership of the live pipeline. */
ap_status_t ap_runtime_command(ap_runtime_t *runtime,
                               const ap_runtime_command_t *command);

/* SPSC consumer. */
ap_status_t ap_runtime_receive(ap_runtime_t *runtime,
                               int16_t *output,
                               ap_metrics_t *metrics_or_null);
ap_status_t ap_runtime_receive_event(ap_runtime_t *runtime,
                                     ap_event_t *event);

/* Attach before start. Recorder memory remains caller-owned; the worker only
 * writes its in-memory ring and never performs file I/O. */
ap_status_t ap_runtime_attach_flight_recorder(ap_runtime_t *runtime,
                                              ap_flight_recorder_t *recorder);

/* Queue depth is a build capability: AP_BUILD_RUNTIME_QUEUE_DEPTH. */
void ap_runtime_get_metrics(const ap_runtime_t *runtime,
                            ap_runtime_metrics_t *metrics);
ap_status_t ap_runtime_get_metrics_v2(const ap_runtime_t *runtime,
                                      ap_runtime_metrics_v2_t *metrics);

/* Optional Linux helper. Affinity/FIFO failure is non-fatal to DSP correctness. */
int ap_runtime_bind_current_thread(int cpu, int fifo_priority);

#ifdef __cplusplus
}
#endif

#endif
