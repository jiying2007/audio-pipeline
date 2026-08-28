#ifndef AUDIO_PIPELINE_AUDIO_RUNTIME_H
#define AUDIO_PIPELINE_AUDIO_RUNTIME_H

#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AP_RUNTIME_STATE_MAX_BYTES (64u * 1024u)
#define AP_RUNTIME_STATE_ALIGNMENT 16u

typedef struct ap_runtime ap_runtime_t;

typedef struct ap_runtime_config {
    int dsp_cpu;              /* -1: do not pin; default */
    int dsp_priority;         /* 0: SCHED_OTHER; default */
    uint32_t overload_us;     /* default 9000 for a 10 ms frame */
    uint32_t recover_frames;  /* sustained healthy frames before upgrade */
} ap_runtime_config_t;

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

ap_runtime_config_t ap_runtime_config_default(void);
size_t ap_runtime_state_size(void);
size_t ap_runtime_state_alignment(void);

ap_status_t ap_runtime_init(void *memory,
                            size_t memory_size,
                            ap_pipeline_t *pipeline,
                            const ap_runtime_config_t *config,
                            ap_runtime_t **out_runtime);
ap_status_t ap_runtime_start(ap_runtime_t *runtime);
void ap_runtime_stop(ap_runtime_t *runtime);
void ap_runtime_deinit(ap_runtime_t *runtime);

/* SPSC producer. Submission never waits; AP_EFULL exposes backpressure. */
ap_status_t ap_runtime_submit(ap_runtime_t *runtime,
                              const int16_t *mic_interleaved,
                              const int16_t *render_or_null);

/* SPSC consumer. */
ap_status_t ap_runtime_receive(ap_runtime_t *runtime,
                               int16_t *output,
                               ap_metrics_t *metrics_or_null);

/* Queue depth is a build capability: AP_BUILD_RUNTIME_QUEUE_DEPTH. */
void ap_runtime_get_metrics(const ap_runtime_t *runtime,
                            ap_runtime_metrics_t *metrics);

/* Optional Linux helper. Affinity/FIFO failure is non-fatal to DSP correctness. */
int ap_runtime_bind_current_thread(int cpu, int fifo_priority);

#ifdef __cplusplus
}
#endif

#endif
