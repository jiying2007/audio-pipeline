#ifndef AUDIO_PIPELINE_AUDIO_DIAG_H
#define AUDIO_PIPELINE_AUDIO_DIAG_H

#include "audio_pipeline/audio_pipeline.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AP_DIAG_API_VERSION 1u
#define AP_FLIGHT_RECORDER_STATE_ALIGNMENT 16u
#define AP_DUMP_MAGIC 0x32445041u /* "APD2" little-endian */
#define AP_DUMP_FORMAT_VERSION 1u

typedef enum ap_event_severity {
    AP_EVENT_DEBUG = 0,
    AP_EVENT_INFO = 1,
    AP_EVENT_WARN = 2,
    AP_EVENT_ERROR = 3,
    AP_EVENT_FATAL = 4
} ap_event_severity_t;

typedef enum ap_event_kind {
    AP_EVENT_RUNTIME_STARTED = 1,
    AP_EVENT_RUNTIME_STOPPED = 2,
    AP_EVENT_RT_AFFINITY_FAILED = 3,
    AP_EVENT_RT_PRIORITY_FAILED = 4,
    AP_EVENT_RT_MLOCK_FAILED = 5,
    AP_EVENT_INPUT_QUEUE_HIGH = 10,
    AP_EVENT_INPUT_QUEUE_FULL = 11,
    AP_EVENT_OUTPUT_DROPPED = 12,
    AP_EVENT_DSP_DEADLINE_MISS = 13,
    AP_EVENT_RENDER_MISSING = 20,
    AP_EVENT_RENDER_UNDERRUN = 21,
    AP_EVENT_DELAY_JUMP = 22,
    AP_EVENT_STREAM_DISCONTINUITY = 23,
    AP_EVENT_ECHO_PATH_CHANGE = 24,
    AP_EVENT_AEC_RESET = 30,
    AP_EVENT_AEC_CONVERGED = 31,
    AP_EVENT_ERLE_COLLAPSE = 32,
    AP_EVENT_QUALITY_FULL_TO_LITE = 40,
    AP_EVENT_QUALITY_LITE_TO_SAFE = 41,
    AP_EVENT_QUALITY_RECOVERED = 42,
    AP_EVENT_DIAG_TRIGGERED = 50
} ap_event_kind_t;

typedef struct ap_event {
    uint32_t struct_size;
    uint32_t api_version;
    uint64_t frame_sequence;
    uint64_t timestamp_ns;
    uint32_t kind;
    uint8_t severity;
    uint8_t flags;
    uint16_t reserved0;
    int32_t arg0;
    int32_t arg1;
    uint32_t count;
    uint32_t reserved1;
} ap_event_t;

typedef uint32_t ap_diag_record_mask_t;
enum {
    AP_DIAG_RECORD_MIC = 1u << 0,
    AP_DIAG_RECORD_RENDER = 1u << 1,
    AP_DIAG_RECORD_OUTPUT = 1u << 2,
    AP_DIAG_RECORD_METRICS = 1u << 3,
    AP_DIAG_RECORD_ALL = (1u << 4) - 1u
};

typedef struct ap_flight_recorder_config {
    uint32_t struct_size;
    uint32_t api_version;
    uint32_t io_sample_rate_hz;
    uint32_t mic_channels;
    uint32_t frame_samples;
    uint32_t pre_roll_frames;
    uint32_t post_roll_frames;
    ap_diag_record_mask_t record_mask;
    ap_event_severity_t trigger_severity;
    uint32_t reserved[7];
} ap_flight_recorder_config_t;

typedef struct ap_diag_frame {
    uint32_t struct_size;
    uint32_t api_version;
    uint64_t frame_sequence;
    uint64_t capture_timestamp_ns;
    uint64_t render_timestamp_ns;
    uint32_t metadata_flags;
    uint32_t trigger_event;
    const int16_t *mic_interleaved;
    const int16_t *render;
    const int16_t *output;
    const ap_metrics_t *metrics;
} ap_diag_frame_t;

typedef struct ap_flight_recorder ap_flight_recorder_t;

ap_flight_recorder_config_t ap_flight_recorder_config_default(uint32_t io_sample_rate_hz,
                                                               uint32_t mic_channels);
size_t ap_flight_recorder_state_size(const ap_flight_recorder_config_t *config);
size_t ap_flight_recorder_state_alignment(void);
ap_status_t ap_flight_recorder_init(void *memory,
                                    size_t memory_size,
                                    const ap_flight_recorder_config_t *config,
                                    ap_flight_recorder_t **out_recorder);
void ap_flight_recorder_reset(ap_flight_recorder_t *recorder);
ap_status_t ap_flight_recorder_record(ap_flight_recorder_t *recorder,
                                      const ap_diag_frame_t *frame);
ap_status_t ap_flight_recorder_trigger(ap_flight_recorder_t *recorder,
                                       ap_event_kind_t event_kind,
                                       ap_event_severity_t severity);
int ap_flight_recorder_is_frozen(const ap_flight_recorder_t *recorder);
size_t ap_flight_recorder_export_size(const ap_flight_recorder_t *recorder);
ap_status_t ap_flight_recorder_export(const ap_flight_recorder_t *recorder,
                                      void *dst,
                                      size_t dst_size,
                                      size_t *written);

#ifdef __cplusplus
}
#endif

#endif
