#define _GNU_SOURCE
#include "audio_pipeline/audio_runtime.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <pthread.h>
#include <sched.h>
#include <semaphore.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

#define AP_RT_DEPTH AP_BUILD_RUNTIME_QUEUE_DEPTH
#define AP_RT_MASK (AP_RT_DEPTH - 1u)
#define AP_RT_COMMAND_MASK (AP_RUNTIME_COMMAND_QUEUE_DEPTH - 1u)
#define AP_RT_EVENT_MASK (AP_RUNTIME_EVENT_QUEUE_DEPTH - 1u)
#define AP_RT_MAX_CAPTURE (AP_BUILD_IO_FRAME_MAX * AP_BUILD_MAX_MIC_CHANNELS)
#define AP_DUMP_ENDIAN_TAG 0x01020304u

_Static_assert(ATOMIC_INT_LOCK_FREE == 2,
               "Linux runtime requires lock-free 32-bit atomics");
_Static_assert((AP_RT_DEPTH & (AP_RT_DEPTH - 1u)) == 0u,
               "runtime queue depth must be power of two");
_Static_assert((AP_RUNTIME_COMMAND_QUEUE_DEPTH &
                (AP_RUNTIME_COMMAND_QUEUE_DEPTH - 1u)) == 0u,
               "command queue depth must be power of two");
_Static_assert((AP_RUNTIME_EVENT_QUEUE_DEPTH &
                (AP_RUNTIME_EVENT_QUEUE_DEPTH - 1u)) == 0u,
               "event queue depth must be power of two");
_Static_assert((AP_RUNTIME_STATE_ALIGNMENT &
                (AP_RUNTIME_STATE_ALIGNMENT - 1u)) == 0u,
               "runtime alignment must be power of two");

typedef struct ap_counter64 {
    atomic_uint seq;
    atomic_uint lo;
    atomic_uint hi;
} ap_counter64_t;

typedef struct ap_rt_metadata {
    uint64_t stream_sequence;
    uint64_t capture_timestamp_ns;
    uint64_t render_timestamp_ns;
    uint32_t flags;
    uint32_t lost_capture_frames;
    uint32_t lost_render_frames;
} ap_rt_metadata_t;

typedef struct ap_rt_input {
    int16_t mic[AP_RT_MAX_CAPTURE];
#if AP_HAVE_MODULE_SYNC
    int16_t render[AP_BUILD_IO_FRAME_MAX];
#endif
    ap_rt_metadata_t metadata;
    uint8_t has_metadata;
    uint8_t has_render;
} ap_rt_input_t;

typedef struct ap_rt_output {
    int16_t audio[AP_BUILD_IO_FRAME_MAX];
    ap_metrics_t metrics;
    ap_status_t status;
} ap_rt_output_t;

typedef struct ap_rt_tuning {
    ap_tuning_mask_t mask;
    float aec_mu;
    float ns_floor;
    float agc_target_dbfs;
    float limiter_dbfs;
} ap_rt_tuning_t;

typedef struct ap_rt_command {
    uint32_t kind;
    union {
        struct {
            ap_discontinuity_flags_t flags;
            uint32_t lost_frames;
        } discontinuity;
        ap_quality_t quality;
        ap_rt_tuning_t tuning;
    } data;
} ap_rt_command_t;

typedef struct ap_rt_event {
    uint64_t frame_sequence;
    uint64_t timestamp_ns;
    uint32_t kind;
    int32_t arg0;
    int32_t arg1;
    uint32_t count;
    uint8_t severity;
    uint8_t flags;
    uint16_t reserved;
} ap_rt_event_t;

typedef struct ap_rt_options {
    size_t dsp_stack_bytes;
    uint8_t lock_memory;
    uint8_t set_thread_name;
    char thread_name[16];
} ap_rt_options_t;

typedef struct ap_dump_file_header {
    uint32_t magic;
    uint32_t format_version;
    uint32_t header_size;
    uint32_t endian_tag;
    uint32_t io_sample_rate_hz;
    uint32_t mic_channels;
    uint32_t frame_samples;
    uint32_t record_mask;
    uint32_t record_stride;
    uint32_t frame_count;
    uint32_t trigger_event;
    uint32_t module_mask;
    char version[24];
    char aec_backend[12];
    char ns_estimator[12];
    char simd_backend[12];
    char resampler_mode[16];
} ap_dump_file_header_t;

typedef struct ap_dump_record_header {
    uint64_t frame_sequence;
    uint64_t capture_timestamp_ns;
    uint64_t render_timestamp_ns;
    uint32_t metadata_flags;
    uint32_t trigger_event;
} ap_dump_record_header_t;

struct ap_flight_recorder {
    ap_flight_recorder_config_t cfg;
    uint32_t capacity;
    uint32_t slot_stride;
    uint32_t count;
    uint32_t head;
    atomic_uint post_remaining;
    atomic_uint trigger_event;
    atomic_uint triggered;
    atomic_uint frozen;
    unsigned char slots[];
};

struct ap_runtime {
    ap_pipeline_t *pipeline;
    ap_runtime_config_t cfg;
    ap_rt_options_t options;
    pthread_t thread;
    sem_t wake;
    atomic_uint running;
    atomic_uint in_head;
    atomic_uint in_tail;
    atomic_uint out_head;
    atomic_uint out_tail;
    atomic_uint command_head;
    atomic_uint command_tail;
    atomic_uint event_head;
    atomic_uint event_tail;
    atomic_uint pending_input_full;
    ap_counter64_t submitted_frames;
    ap_counter64_t processed_frames;
    ap_counter64_t input_full_events;
    ap_counter64_t output_drop_events;
    ap_counter64_t dsp_overruns;
    ap_counter64_t command_full_events;
    ap_counter64_t event_drop_events;
    ap_counter64_t stream_discontinuities;
    ap_counter64_t capture_gap_frames;
    ap_counter64_t render_gap_frames;
    ap_counter64_t timestamp_frames;
    ap_counter64_t scheduler_bind_failures;
    ap_counter64_t memory_lock_failures;
    atomic_uint failed_frames;
    atomic_uint render_push_failures;
    atomic_uint capture_process_failures;
    atomic_uint observed_cpu_changes;
    atomic_uint critical_events;
    atomic_uint input_queue_high_water;
    atomic_uint output_queue_high_water;
    atomic_uint last_dsp_us;
    atomic_uint max_dsp_us;
    atomic_uint quality;
    atomic_uint latency_hist[AP_RUNTIME_LATENCY_BUCKETS];
    atomic_int actual_cpu;
    atomic_int actual_policy;
    atomic_int actual_priority;
    atomic_int last_pipeline_error;
    atomic_uint critical_seq;
    atomic_uint critical_frame_lo;
    atomic_uint critical_frame_hi;
    atomic_uint critical_kind;
    atomic_uint critical_severity;
    atomic_int critical_arg0;
    atomic_int critical_arg1;
    ap_rt_input_t in[AP_RT_DEPTH];
    ap_rt_output_t out[AP_RT_DEPTH];
    ap_rt_command_t commands[AP_RUNTIME_COMMAND_QUEUE_DEPTH];
    ap_rt_event_t events[AP_RUNTIME_EVENT_QUEUE_DEPTH];
    ap_flight_recorder_t *recorder;
    uint32_t io_frames;
    uint32_t mic_channels;
    uint32_t overload_streak;
    uint32_t healthy_streak;
    uint64_t worker_sequence;
    uint32_t cpu_sample_countdown;
    uint64_t last_render_underruns;
    uint64_t last_delay_jumps;
    uint64_t last_aec_resets;
    float last_valid_erle;
    uint8_t last_aec_converged;
    uint8_t uses_render;
};

_Static_assert(sizeof(struct ap_runtime) <= AP_RUNTIME_STATE_MAX_BYTES,
               "runtime state exceeded public ceiling");

static uint64_t now_ns(void) {
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static size_t align_up_size(size_t value, size_t alignment) {
    return (value + alignment - 1u) & ~(alignment - 1u);
}

static void counter64_init(ap_counter64_t *counter) {
    atomic_init(&counter->seq, 0u);
    atomic_init(&counter->lo, 0u);
    atomic_init(&counter->hi, 0u);
}

static void counter64_add(ap_counter64_t *counter, uint64_t delta) {
    uint32_t lo;
    uint32_t hi;
    uint32_t new_lo;
    atomic_fetch_add_explicit(&counter->seq, 1u, memory_order_acq_rel);
    lo = atomic_load_explicit(&counter->lo, memory_order_relaxed);
    hi = atomic_load_explicit(&counter->hi, memory_order_relaxed);
    new_lo = lo + (uint32_t)delta;
    hi += (uint32_t)(delta >> 32u);
    if (new_lo < lo) hi++;
    atomic_store_explicit(&counter->lo, new_lo, memory_order_relaxed);
    atomic_store_explicit(&counter->hi, hi, memory_order_relaxed);
    atomic_fetch_add_explicit(&counter->seq, 1u, memory_order_release);
}

static uint64_t counter64_read(const ap_counter64_t *counter) {
    for (;;) {
        unsigned seq0 = atomic_load_explicit(&counter->seq, memory_order_acquire);
        unsigned lo;
        unsigned hi;
        unsigned seq1;
        if (seq0 & 1u) continue;
        lo = atomic_load_explicit(&counter->lo, memory_order_relaxed);
        hi = atomic_load_explicit(&counter->hi, memory_order_relaxed);
        seq1 = atomic_load_explicit(&counter->seq, memory_order_acquire);
        if (seq0 == seq1)
            return ((uint64_t)hi << 32u) | (uint64_t)lo;
    }
}

static void update_max(atomic_uint *dst, uint32_t value) {
    unsigned current = atomic_load_explicit(dst, memory_order_relaxed);
    while (value > current &&
           !atomic_compare_exchange_weak_explicit(dst,
                                                  &current,
                                                  value,
                                                  memory_order_relaxed,
                                                  memory_order_relaxed)) {
    }
}

static void counter32_inc_sat(atomic_uint *counter) {
    unsigned current = atomic_load_explicit(counter, memory_order_relaxed);
    while (current != UINT32_MAX &&
           !atomic_compare_exchange_weak_explicit(counter,
                                                  &current,
                                                  current + 1u,
                                                  memory_order_relaxed,
                                                  memory_order_relaxed)) {
    }
}

static void copy_text(char *dst, size_t capacity, const char *src) {
    size_t n = 0u;
    if (!capacity) return;
    if (src) {
        while (n + 1u < capacity && src[n]) {
            dst[n] = src[n];
            n++;
        }
    }
    dst[n] = '\0';
}

static size_t recorder_slot_stride(const ap_flight_recorder_config_t *config) {
    size_t bytes = sizeof(ap_dump_record_header_t);
    if (config->record_mask & AP_DIAG_RECORD_METRICS)
        bytes += sizeof(ap_metrics_t);
    if (config->record_mask & AP_DIAG_RECORD_MIC)
        bytes += (size_t)config->frame_samples * config->mic_channels * sizeof(int16_t);
    if (config->record_mask & AP_DIAG_RECORD_RENDER)
        bytes += (size_t)config->frame_samples * sizeof(int16_t);
    if (config->record_mask & AP_DIAG_RECORD_OUTPUT)
        bytes += (size_t)config->frame_samples * sizeof(int16_t);
    return align_up_size(bytes, 8u);
}

ap_flight_recorder_config_t ap_flight_recorder_config_default(uint32_t rate,
                                                               uint32_t channels) {
    ap_flight_recorder_config_t config;
    memset(&config, 0, sizeof(config));
    config.struct_size = sizeof(config);
    config.api_version = AP_DIAG_API_VERSION;
    config.io_sample_rate_hz = rate;
    config.mic_channels = channels;
    config.frame_samples = rate / 100u;
    config.pre_roll_frames = 500u;
    config.post_roll_frames = 100u;
    config.record_mask = AP_DIAG_RECORD_METRICS;
    config.trigger_severity = AP_EVENT_ERROR;
    return config;
}

static int recorder_rate_supported(uint32_t rate) {
    return rate == 8000u || rate == 16000u || rate == 24000u ||
           rate == 32000u || rate == 48000u;
}

static int recorder_config_valid(const ap_flight_recorder_config_t *config) {
    size_t capacity;
    size_t stride;
    if (!config || config->struct_size < sizeof(*config) ||
        config->api_version != AP_DIAG_API_VERSION ||
        !recorder_rate_supported(config->io_sample_rate_hz) ||
        config->frame_samples != config->io_sample_rate_hz / 100u ||
        !config->mic_channels || config->mic_channels > 2u ||
        (config->record_mask & ~AP_DIAG_RECORD_ALL) != 0u)
        return 0;
    capacity = (size_t)config->pre_roll_frames +
               (size_t)config->post_roll_frames + 1u;
    if (!capacity || capacity > UINT32_MAX) return 0;
    stride = recorder_slot_stride(config);
    if (!stride || stride > UINT32_MAX || stride > SIZE_MAX / capacity) return 0;
    if (sizeof(ap_flight_recorder_t) > SIZE_MAX - capacity * stride) return 0;
    return 1;
}

size_t ap_flight_recorder_state_size(const ap_flight_recorder_config_t *config) {
    size_t capacity;
    size_t stride;
    if (!recorder_config_valid(config)) return 0u;
    capacity = (size_t)config->pre_roll_frames +
               (size_t)config->post_roll_frames + 1u;
    stride = recorder_slot_stride(config);
    return sizeof(ap_flight_recorder_t) + capacity * stride;
}

size_t ap_flight_recorder_state_alignment(void) {
    return AP_FLIGHT_RECORDER_STATE_ALIGNMENT;
}

ap_status_t ap_flight_recorder_init(void *memory,
                                    size_t memory_size,
                                    const ap_flight_recorder_config_t *config,
                                    ap_flight_recorder_t **out_recorder) {
    size_t need;
    ap_flight_recorder_t *recorder;
    if (!memory || !config || !out_recorder) return AP_EINVAL;
    *out_recorder = NULL;
    need = ap_flight_recorder_state_size(config);
    if (!need) return AP_EINVAL;
    if (memory_size < need) return AP_ENOMEM;
    if (((uintptr_t)memory & (AP_FLIGHT_RECORDER_STATE_ALIGNMENT - 1u)) != 0u)
        return AP_EINVAL;
    memset(memory, 0, need);
    recorder = (ap_flight_recorder_t *)memory;
    recorder->cfg = *config;
    recorder->capacity = config->pre_roll_frames + config->post_roll_frames + 1u;
    recorder->slot_stride = (uint32_t)recorder_slot_stride(config);
    atomic_init(&recorder->post_remaining, 0u);
    atomic_init(&recorder->trigger_event, 0u);
    atomic_init(&recorder->triggered, 0u);
    atomic_init(&recorder->frozen, 0u);
    *out_recorder = recorder;
    return AP_OK;
}

void ap_flight_recorder_reset(ap_flight_recorder_t *recorder) {
    if (!recorder) return;
    recorder->count = 0u;
    recorder->head = 0u;
    atomic_store_explicit(&recorder->post_remaining, 0u, memory_order_relaxed);
    atomic_store_explicit(&recorder->trigger_event, 0u, memory_order_relaxed);
    atomic_store_explicit(&recorder->triggered, 0u, memory_order_release);
    atomic_store_explicit(&recorder->frozen, 0u, memory_order_release);
}

ap_status_t ap_flight_recorder_trigger(ap_flight_recorder_t *recorder,
                                       ap_event_kind_t kind,
                                       ap_event_severity_t severity) {
    unsigned expected = 0u;
    if (!recorder) return AP_EINVAL;
    if (severity < recorder->cfg.trigger_severity) return AP_OK;
    if (atomic_load_explicit(&recorder->frozen, memory_order_acquire)) return AP_OK;
    if (!atomic_compare_exchange_strong_explicit(&recorder->triggered,
                                                  &expected,
                                                  1u,
                                                  memory_order_acq_rel,
                                                  memory_order_acquire))
        return AP_OK;
    atomic_store_explicit(&recorder->trigger_event,
                          (unsigned)kind,
                          memory_order_relaxed);
    atomic_store_explicit(&recorder->post_remaining,
                          recorder->cfg.post_roll_frames + 1u,
                          memory_order_release);
    return AP_OK;
}

ap_status_t ap_flight_recorder_record(ap_flight_recorder_t *recorder,
                                      const ap_diag_frame_t *frame) {
    unsigned char *p;
    ap_dump_record_header_t header;
    size_t mic_bytes;
    if (!recorder || !frame || frame->struct_size < sizeof(*frame) ||
        frame->api_version != AP_DIAG_API_VERSION)
        return AP_EINVAL;
    if (atomic_load_explicit(&recorder->frozen, memory_order_acquire))
        return AP_ESTATE;

    p = recorder->slots + (size_t)recorder->head * recorder->slot_stride;
    memset(p, 0, recorder->slot_stride);
    memset(&header, 0, sizeof(header));
    header.frame_sequence = frame->frame_sequence;
    header.capture_timestamp_ns = frame->capture_timestamp_ns;
    header.render_timestamp_ns = frame->render_timestamp_ns;
    header.metadata_flags = frame->metadata_flags;
    header.trigger_event = frame->trigger_event;
    memcpy(p, &header, sizeof(header));
    p += sizeof(header);

    if (recorder->cfg.record_mask & AP_DIAG_RECORD_METRICS) {
        if (frame->metrics) memcpy(p, frame->metrics, sizeof(*frame->metrics));
        p += sizeof(ap_metrics_t);
    }
    mic_bytes = (size_t)recorder->cfg.frame_samples *
                recorder->cfg.mic_channels * sizeof(int16_t);
    if (recorder->cfg.record_mask & AP_DIAG_RECORD_MIC) {
        if (frame->mic_interleaved)
            memcpy(p, frame->mic_interleaved, mic_bytes);
        p += mic_bytes;
    }
    if (recorder->cfg.record_mask & AP_DIAG_RECORD_RENDER) {
        const size_t bytes = (size_t)recorder->cfg.frame_samples * sizeof(int16_t);
        if (frame->render) memcpy(p, frame->render, bytes);
        p += bytes;
    }
    if (recorder->cfg.record_mask & AP_DIAG_RECORD_OUTPUT) {
        const size_t bytes = (size_t)recorder->cfg.frame_samples * sizeof(int16_t);
        if (frame->output) memcpy(p, frame->output, bytes);
        p += bytes;
    }

    recorder->head = (recorder->head + 1u) % recorder->capacity;
    if (recorder->count < recorder->capacity) recorder->count++;
    if (atomic_load_explicit(&recorder->triggered, memory_order_acquire)) {
        unsigned remaining = atomic_load_explicit(&recorder->post_remaining,
                                                  memory_order_acquire);
        if (remaining > 0u) {
            remaining = atomic_fetch_sub_explicit(&recorder->post_remaining,
                                                  1u,
                                                  memory_order_acq_rel);
            if (remaining == 1u)
                atomic_store_explicit(&recorder->frozen, 1u, memory_order_release);
        }
    }
    return AP_OK;
}

int ap_flight_recorder_is_frozen(const ap_flight_recorder_t *recorder) {
    if (!recorder) return 0;
    return atomic_load_explicit(&recorder->frozen, memory_order_acquire) != 0u;
}

size_t ap_flight_recorder_export_size(const ap_flight_recorder_t *recorder) {
    if (!recorder || !ap_flight_recorder_is_frozen(recorder)) return 0u;
    return sizeof(ap_dump_file_header_t) +
           (size_t)recorder->count * recorder->slot_stride;
}

ap_status_t ap_flight_recorder_export(const ap_flight_recorder_t *recorder,
                                      void *dst,
                                      size_t dst_size,
                                      size_t *written) {
    ap_dump_file_header_t header;
    unsigned char *out = (unsigned char *)dst;
    uint32_t i;
    uint32_t oldest;
    size_t need;
    const ap_build_info_t *build;
    if (!recorder || !dst || !written) return AP_EINVAL;
    *written = 0u;
    if (!ap_flight_recorder_is_frozen(recorder)) return AP_ESTATE;
    need = ap_flight_recorder_export_size(recorder);
    if (dst_size < need) return AP_ENOMEM;

    memset(&header, 0, sizeof(header));
    header.magic = AP_DUMP_MAGIC;
    header.format_version = AP_DUMP_FORMAT_VERSION;
    header.header_size = sizeof(header);
    header.endian_tag = AP_DUMP_ENDIAN_TAG;
    header.io_sample_rate_hz = recorder->cfg.io_sample_rate_hz;
    header.mic_channels = recorder->cfg.mic_channels;
    header.frame_samples = recorder->cfg.frame_samples;
    header.record_mask = recorder->cfg.record_mask;
    header.record_stride = recorder->slot_stride;
    header.frame_count = recorder->count;
    header.trigger_event = atomic_load_explicit(&recorder->trigger_event,
                                                memory_order_acquire);
    build = ap_build_info();
    if (build) {
        header.module_mask = build->module_mask;
        copy_text(header.version, sizeof(header.version), build->version);
        copy_text(header.aec_backend, sizeof(header.aec_backend), build->aec_backend);
        copy_text(header.ns_estimator, sizeof(header.ns_estimator), build->ns_estimator);
        copy_text(header.simd_backend, sizeof(header.simd_backend), build->simd_backend);
        copy_text(header.resampler_mode, sizeof(header.resampler_mode), build->resampler_mode);
    }
    memcpy(out, &header, sizeof(header));
    out += sizeof(header);
    oldest = (recorder->head + recorder->capacity - recorder->count) %
             recorder->capacity;
    for (i = 0u; i < recorder->count; ++i) {
        const uint32_t index = (oldest + i) % recorder->capacity;
        memcpy(out,
               recorder->slots + (size_t)index * recorder->slot_stride,
               recorder->slot_stride);
        out += recorder->slot_stride;
    }
    *written = need;
    return AP_OK;
}

int ap_runtime_bind_current_thread(int cpu, int fifo_priority) {
    int result = 0;
    if (cpu >= 0) {
        cpu_set_t set;
        if (cpu >= CPU_SETSIZE) return -1;
        CPU_ZERO(&set);
        CPU_SET(cpu, &set);
        if (pthread_setaffinity_np(pthread_self(), sizeof(set), &set) != 0)
            result = -1;
    }
    if (fifo_priority > 0) {
        struct sched_param sp;
        memset(&sp, 0, sizeof(sp));
        sp.sched_priority = fifo_priority > 99 ? 99 : fifo_priority;
        if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp) != 0)
            result = -1;
    }
    return result;
}

ap_runtime_config_t ap_runtime_config_default(void) {
    ap_runtime_config_t config;
    config.dsp_cpu = -1;
    config.dsp_priority = 0;
    config.overload_us = 9000u;
    config.recover_frames = 1000u;
    return config;
}

ap_runtime_options_t ap_runtime_options_default(void) {
    ap_runtime_options_t options;
    memset(&options, 0, sizeof(options));
    options.struct_size = sizeof(options);
    options.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    options.set_thread_name = 1u;
    copy_text(options.thread_name, sizeof(options.thread_name), "ap-dsp");
    return options;
}

size_t ap_runtime_state_size(void) {
    return sizeof(ap_runtime_t);
}

size_t ap_runtime_state_alignment(void) {
    return AP_RUNTIME_STATE_ALIGNMENT;
}

static void init_runtime_atomics(ap_runtime_t *runtime) {
    uint32_t i;
    atomic_init(&runtime->running, 0u);
    atomic_init(&runtime->in_head, 0u);
    atomic_init(&runtime->in_tail, 0u);
    atomic_init(&runtime->out_head, 0u);
    atomic_init(&runtime->out_tail, 0u);
    atomic_init(&runtime->command_head, 0u);
    atomic_init(&runtime->command_tail, 0u);
    atomic_init(&runtime->event_head, 0u);
    atomic_init(&runtime->event_tail, 0u);
    atomic_init(&runtime->pending_input_full, 0u);
    counter64_init(&runtime->submitted_frames);
    counter64_init(&runtime->processed_frames);
    counter64_init(&runtime->input_full_events);
    counter64_init(&runtime->output_drop_events);
    counter64_init(&runtime->dsp_overruns);
    counter64_init(&runtime->command_full_events);
    counter64_init(&runtime->event_drop_events);
    counter64_init(&runtime->stream_discontinuities);
    counter64_init(&runtime->capture_gap_frames);
    counter64_init(&runtime->render_gap_frames);
    counter64_init(&runtime->timestamp_frames);
    counter64_init(&runtime->scheduler_bind_failures);
    counter64_init(&runtime->memory_lock_failures);
    atomic_init(&runtime->failed_frames, 0u);
    atomic_init(&runtime->render_push_failures, 0u);
    atomic_init(&runtime->capture_process_failures, 0u);
    atomic_init(&runtime->observed_cpu_changes, 0u);
    atomic_init(&runtime->critical_events, 0u);
    atomic_init(&runtime->input_queue_high_water, 0u);
    atomic_init(&runtime->output_queue_high_water, 0u);
    atomic_init(&runtime->last_dsp_us, 0u);
    atomic_init(&runtime->max_dsp_us, 0u);
    atomic_init(&runtime->quality, (unsigned)AP_QUALITY_FULL);
    for (i = 0u; i < AP_RUNTIME_LATENCY_BUCKETS; ++i)
        atomic_init(&runtime->latency_hist[i], 0u);
    atomic_init(&runtime->actual_cpu, -1);
    atomic_init(&runtime->actual_policy, SCHED_OTHER);
    atomic_init(&runtime->actual_priority, 0);
    atomic_init(&runtime->last_pipeline_error, AP_OK);
    atomic_init(&runtime->critical_seq, 0u);
    atomic_init(&runtime->critical_frame_lo, 0u);
    atomic_init(&runtime->critical_frame_hi, 0u);
    atomic_init(&runtime->critical_kind, 0u);
    atomic_init(&runtime->critical_severity, 0u);
    atomic_init(&runtime->critical_arg0, 0);
    atomic_init(&runtime->critical_arg1, 0);
}

ap_status_t ap_runtime_init_ex(void *memory,
                               size_t memory_size,
                               ap_pipeline_t *pipeline,
                               const ap_runtime_config_t *config,
                               const ap_runtime_options_t *options,
                               ap_runtime_t **out_runtime) {
    ap_runtime_t *runtime;
    if (!memory || !pipeline || !config || !options || !out_runtime)
        return AP_EINVAL;
    *out_runtime = NULL;
    if (memory_size < sizeof(ap_runtime_t)) return AP_ENOMEM;
    if (((uintptr_t)memory & (AP_RUNTIME_STATE_ALIGNMENT - 1u)) != 0u)
        return AP_EINVAL;
    if (config->recover_frames == 0u) return AP_EINVAL;
    if (config->dsp_cpu < -1 || config->dsp_cpu >= CPU_SETSIZE) return AP_EINVAL;
    if (config->dsp_priority < 0 || config->dsp_priority > 99) return AP_EINVAL;
    if (options->struct_size < sizeof(*options) ||
        options->api_version != AP_RUNTIME_CONTROL_API_VERSION)
        return AP_EINVAL;

    runtime = (ap_runtime_t *)memory;
    memset(runtime, 0, sizeof(*runtime));
    runtime->pipeline = pipeline;
    runtime->cfg = *config;
    runtime->options.dsp_stack_bytes = options->dsp_stack_bytes;
    runtime->options.lock_memory = options->lock_memory;
    runtime->options.set_thread_name = options->set_thread_name;
    copy_text(runtime->options.thread_name,
              sizeof(runtime->options.thread_name),
              options->thread_name);
    runtime->io_frames = (uint32_t)ap_pipeline_frame_samples(pipeline);
    runtime->mic_channels = ap_pipeline_mic_channels(pipeline);
    runtime->uses_render =
        (uint8_t)((ap_pipeline_stages(pipeline) & AP_STAGE_SYNC) != 0u);
    if (!runtime->io_frames || runtime->io_frames > AP_BUILD_IO_FRAME_MAX ||
        !runtime->mic_channels || runtime->mic_channels > AP_BUILD_MAX_MIC_CHANNELS)
        return AP_EINVAL;
    if (sem_init(&runtime->wake, 0, 0) != 0) return AP_ESTATE;
    init_runtime_atomics(runtime);
    *out_runtime = runtime;
    return AP_OK;
}

ap_status_t ap_runtime_init(void *memory,
                            size_t memory_size,
                            ap_pipeline_t *pipeline,
                            const ap_runtime_config_t *config,
                            ap_runtime_t **out_runtime) {
    const ap_runtime_options_t options = ap_runtime_options_default();
    return ap_runtime_init_ex(memory,
                              memory_size,
                              pipeline,
                              config,
                              &options,
                              out_runtime);
}

static void runtime_latch_critical(ap_runtime_t *runtime,
                                   ap_event_kind_t kind,
                                   ap_event_severity_t severity,
                                   int32_t arg0,
                                   int32_t arg1) {
    uint64_t frame;
    if (severity < AP_EVENT_ERROR) return;
    frame = runtime->worker_sequence;
    counter32_inc_sat(&runtime->critical_events);
    atomic_fetch_add_explicit(&runtime->critical_seq, 1u, memory_order_acq_rel);
    atomic_store_explicit(&runtime->critical_frame_lo, (uint32_t)frame, memory_order_relaxed);
    atomic_store_explicit(&runtime->critical_frame_hi, (uint32_t)(frame >> 32u), memory_order_relaxed);
    atomic_store_explicit(&runtime->critical_kind, (unsigned)kind, memory_order_relaxed);
    atomic_store_explicit(&runtime->critical_severity, (unsigned)severity, memory_order_relaxed);
    atomic_store_explicit(&runtime->critical_arg0, arg0, memory_order_relaxed);
    atomic_store_explicit(&runtime->critical_arg1, arg1, memory_order_relaxed);
    atomic_fetch_add_explicit(&runtime->critical_seq, 1u, memory_order_release);
}

static void runtime_emit_event(ap_runtime_t *runtime,
                               ap_event_kind_t kind,
                               ap_event_severity_t severity,
                               int32_t arg0,
                               int32_t arg1,
                               uint32_t count) {
    const unsigned head =
        atomic_load_explicit(&runtime->event_head, memory_order_relaxed);
    const unsigned tail =
        atomic_load_explicit(&runtime->event_tail, memory_order_acquire);
    ap_rt_event_t *event;

    runtime_latch_critical(runtime, kind, severity, arg0, arg1);
    if (runtime->recorder)
        (void)ap_flight_recorder_trigger(runtime->recorder, kind, severity);

    if (head - tail >= AP_RUNTIME_EVENT_QUEUE_DEPTH) {
        counter64_add(&runtime->event_drop_events, 1u);
        return;
    }
    event = &runtime->events[head & AP_RT_EVENT_MASK];
    memset(event, 0, sizeof(*event));
    event->frame_sequence = runtime->worker_sequence;
    event->timestamp_ns = now_ns();
    event->kind = (uint32_t)kind;
    event->severity = (uint8_t)severity;
    event->arg0 = arg0;
    event->arg1 = arg1;
    event->count = count;
    atomic_store_explicit(&runtime->event_head, head + 1u, memory_order_release);
}

static uint32_t latency_bucket(uint32_t us) {
    static const uint32_t limits[AP_RUNTIME_LATENCY_BUCKETS - 1u] = {
        250u, 500u, 1000u, 1500u, 2000u, 3000u,
        4000u, 5000u, 6000u, 7000u, 9000u
    };
    uint32_t i;
    for (i = 0u; i < AP_RUNTIME_LATENCY_BUCKETS - 1u; ++i) {
        if (us <= limits[i]) return i;
    }
    return AP_RUNTIME_LATENCY_BUCKETS - 1u;
}

static uint32_t latency_bucket_upper(uint32_t bucket) {
    static const uint32_t limits[AP_RUNTIME_LATENCY_BUCKETS] = {
        250u, 500u, 1000u, 1500u, 2000u, 3000u,
        4000u, 5000u, 6000u, 7000u, 9000u, UINT32_MAX
    };
    if (bucket >= AP_RUNTIME_LATENCY_BUCKETS)
        bucket = AP_RUNTIME_LATENCY_BUCKETS - 1u;
    return limits[bucket];
}

static void apply_quality_transition(ap_runtime_t *runtime, ap_quality_t next) {
    ap_metrics_t metrics;
    ap_quality_t old;
    ap_pipeline_get_metrics(runtime->pipeline, &metrics);
    old = metrics.quality;
    if (old == next) return;
    if (ap_pipeline_set_quality(runtime->pipeline, next) != AP_OK) return;
    atomic_store_explicit(&runtime->quality, (unsigned)next, memory_order_release);
    if (old == AP_QUALITY_FULL && next == AP_QUALITY_LITE) {
        runtime_emit_event(runtime,
                           AP_EVENT_QUALITY_FULL_TO_LITE,
                           AP_EVENT_WARN,
                           (int32_t)old,
                           (int32_t)next,
                           1u);
    } else if (old == AP_QUALITY_LITE && next == AP_QUALITY_SAFE) {
        runtime_emit_event(runtime,
                           AP_EVENT_QUALITY_LITE_TO_SAFE,
                           AP_EVENT_ERROR,
                           (int32_t)old,
                           (int32_t)next,
                           1u);
    } else {
        runtime_emit_event(runtime,
                           AP_EVENT_QUALITY_RECOVERED,
                           AP_EVENT_INFO,
                           (int32_t)old,
                           (int32_t)next,
                           1u);
    }
}

static void adjust_quality(ap_runtime_t *runtime, uint64_t elapsed_ns) {
    const uint64_t limit = (uint64_t)runtime->cfg.overload_us * 1000ull;
    ap_metrics_t metrics;
    ap_pipeline_get_metrics(runtime->pipeline, &metrics);
    if (elapsed_ns > limit) {
        runtime->healthy_streak = 0u;
        counter64_add(&runtime->dsp_overruns, 1u);
        runtime_emit_event(runtime,
                           AP_EVENT_DSP_DEADLINE_MISS,
                           AP_EVENT_ERROR,
                           (int32_t)(elapsed_ns / 1000ull),
                           (int32_t)runtime->cfg.overload_us,
                           1u);
        if (++runtime->overload_streak >= 3u) {
            if (metrics.quality == AP_QUALITY_FULL)
                apply_quality_transition(runtime, AP_QUALITY_LITE);
            else if (metrics.quality == AP_QUALITY_LITE)
                apply_quality_transition(runtime, AP_QUALITY_SAFE);
            runtime->overload_streak = 0u;
        }
    } else {
        runtime->overload_streak = 0u;
        if (++runtime->healthy_streak >= runtime->cfg.recover_frames) {
            if (metrics.quality == AP_QUALITY_SAFE)
                apply_quality_transition(runtime, AP_QUALITY_LITE);
            else if (metrics.quality == AP_QUALITY_LITE)
                apply_quality_transition(runtime, AP_QUALITY_FULL);
            runtime->healthy_streak = 0u;
        }
    }
}

static void runtime_note_discontinuity(ap_runtime_t *runtime,
                                       ap_discontinuity_flags_t flags,
                                       uint32_t lost) {
    if (ap_pipeline_notify_stream_discontinuity(runtime->pipeline, flags, lost) != AP_OK)
        return;
    counter64_add(&runtime->stream_discontinuities, 1u);
    if (flags & AP_DISCONTINUITY_CAPTURE_GAP)
        counter64_add(&runtime->capture_gap_frames, lost ? lost : 1u);
    if (flags & AP_DISCONTINUITY_RENDER_GAP)
        counter64_add(&runtime->render_gap_frames, lost ? lost : 1u);
    runtime_emit_event(runtime,
                       AP_EVENT_STREAM_DISCONTINUITY,
                       AP_EVENT_WARN,
                       (int32_t)flags,
                       (int32_t)lost,
                       1u);
}

static void runtime_apply_command(ap_runtime_t *runtime,
                                  const ap_rt_command_t *command) {
    ap_metrics_t metrics;
    switch ((ap_runtime_command_kind_t)command->kind) {
    case AP_RUNTIME_COMMAND_ECHO_PATH_CHANGE:
        if (ap_pipeline_notify_echo_path_change(runtime->pipeline) == AP_OK)
            runtime_emit_event(runtime,
                               AP_EVENT_ECHO_PATH_CHANGE,
                               AP_EVENT_WARN,
                               0,
                               0,
                               1u);
        break;
    case AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY:
        runtime_note_discontinuity(runtime,
                                   command->data.discontinuity.flags,
                                   command->data.discontinuity.lost_frames);
        break;
    case AP_RUNTIME_COMMAND_RESET:
        ap_pipeline_reset(runtime->pipeline);
        runtime_emit_event(runtime, AP_EVENT_AEC_RESET, AP_EVENT_WARN, 0, 0, 1u);
        break;
    case AP_RUNTIME_COMMAND_SET_QUALITY:
        apply_quality_transition(runtime, command->data.quality);
        break;
    case AP_RUNTIME_COMMAND_SET_TUNING: {
        ap_tuning_t tuning;
        memset(&tuning, 0, sizeof(tuning));
        tuning.struct_size = sizeof(tuning);
        tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
        tuning.mask = command->data.tuning.mask;
        tuning.aec_mu = command->data.tuning.aec_mu;
        tuning.ns_floor = command->data.tuning.ns_floor;
        tuning.agc_target_dbfs = command->data.tuning.agc_target_dbfs;
        tuning.limiter_dbfs = command->data.tuning.limiter_dbfs;
        if (ap_pipeline_apply_tuning(runtime->pipeline, &tuning) != AP_OK)
            runtime_emit_event(runtime,
                               AP_EVENT_COMMAND_REJECTED,
                               AP_EVENT_WARN,
                               (int32_t)command->kind,
                               AP_EINVAL,
                               1u);
        break;
    }
    default:
        break;
    }
    ap_pipeline_get_metrics(runtime->pipeline, &metrics);
    atomic_store_explicit(&runtime->quality,
                          (unsigned)metrics.quality,
                          memory_order_release);
}

static void runtime_drain_commands(ap_runtime_t *runtime) {
    for (;;) {
        const unsigned tail =
            atomic_load_explicit(&runtime->command_tail, memory_order_relaxed);
        const unsigned head =
            atomic_load_explicit(&runtime->command_head, memory_order_acquire);
        if (tail == head) break;
        runtime_apply_command(runtime,
                              &runtime->commands[tail & AP_RT_COMMAND_MASK]);
        atomic_store_explicit(&runtime->command_tail,
                              tail + 1u,
                              memory_order_release);
    }
}

static void runtime_apply_metadata(ap_runtime_t *runtime,
                                   const ap_rt_input_t *input) {
    const ap_rt_metadata_t *metadata = &input->metadata;
    ap_discontinuity_flags_t flags = 0u;
    uint32_t lost = 0u;
    if (!input->has_metadata) return;
    if (metadata->flags & AP_FRAME_CAPTURE_DISCONTINUITY) {
        flags |= AP_DISCONTINUITY_CAPTURE_GAP;
        lost = metadata->lost_capture_frames;
    }
    if (metadata->flags & AP_FRAME_RENDER_DISCONTINUITY) {
        flags |= AP_DISCONTINUITY_RENDER_GAP;
        if (metadata->lost_render_frames > lost)
            lost = metadata->lost_render_frames;
    }
    if (metadata->flags & AP_FRAME_CLOCK_RESET)
        flags |= AP_DISCONTINUITY_CLOCK_RESET;
    if (metadata->flags & AP_FRAME_XRUN)
        flags |= AP_DISCONTINUITY_XRUN;
    if (metadata->flags & AP_FRAME_CODEC_REOPEN)
        flags |= AP_DISCONTINUITY_CODEC_REOPEN;
    if (flags) runtime_note_discontinuity(runtime, flags, lost);
    if ((metadata->flags &
         (AP_FRAME_CAPTURE_TIMESTAMP_VALID | AP_FRAME_RENDER_TIMESTAMP_VALID)) ==
        (AP_FRAME_CAPTURE_TIMESTAMP_VALID | AP_FRAME_RENDER_TIMESTAMP_VALID)) {
        if (ap_pipeline_observe_io_timestamps(runtime->pipeline,
                                              metadata->capture_timestamp_ns,
                                              metadata->render_timestamp_ns) == AP_OK)
            counter64_add(&runtime->timestamp_frames, 1u);
    }
}

static void runtime_note_pipeline_events(ap_runtime_t *runtime,
                                         const ap_metrics_t *metrics) {
    if (metrics->render_underruns > runtime->last_render_underruns) {
        runtime_emit_event(runtime,
                           AP_EVENT_RENDER_UNDERRUN,
                           AP_EVENT_WARN,
                           0,
                           0,
                           (uint32_t)(metrics->render_underruns -
                                      runtime->last_render_underruns));
        runtime->last_render_underruns = metrics->render_underruns;
    }
    if (metrics->delay_jumps > runtime->last_delay_jumps) {
        runtime_emit_event(runtime,
                           AP_EVENT_DELAY_JUMP,
                           AP_EVENT_WARN,
                           metrics->delay_error_samples,
                           (int32_t)metrics->estimated_delay_ms,
                           (uint32_t)(metrics->delay_jumps -
                                      runtime->last_delay_jumps));
        runtime->last_delay_jumps = metrics->delay_jumps;
    }
    if (metrics->aec_resets > runtime->last_aec_resets) {
        runtime_emit_event(runtime,
                           AP_EVENT_AEC_RESET,
                           AP_EVENT_WARN,
                           0,
                           0,
                           (uint32_t)(metrics->aec_resets - runtime->last_aec_resets));
        runtime->last_aec_resets = metrics->aec_resets;
    }
    if (metrics->aec_converged && !runtime->last_aec_converged)
        runtime_emit_event(runtime,
                           AP_EVENT_AEC_CONVERGED,
                           AP_EVENT_INFO,
                           (int32_t)metrics->aec_convergence_frames,
                           0,
                           1u);
    runtime->last_aec_converged = metrics->aec_converged;
    if (metrics->erle_valid) {
        if (runtime->last_valid_erle > 8.0f &&
            metrics->erle_db + 6.0f < runtime->last_valid_erle)
            runtime_emit_event(runtime,
                               AP_EVENT_ERLE_COLLAPSE,
                               AP_EVENT_WARN,
                               (int32_t)runtime->last_valid_erle,
                               (int32_t)metrics->erle_db,
                               1u);
        runtime->last_valid_erle = metrics->erle_db;
    }
}

static void runtime_record_frame(ap_runtime_t *runtime,
                                 const ap_rt_input_t *input,
                                 const int16_t *output,
                                 const ap_metrics_t *metrics) {
    ap_diag_frame_t frame;
    if (!runtime->recorder) return;
    memset(&frame, 0, sizeof(frame));
    frame.struct_size = sizeof(frame);
    frame.api_version = AP_DIAG_API_VERSION;
    frame.frame_sequence = runtime->worker_sequence;
    frame.mic_interleaved = input->mic;
#if AP_HAVE_MODULE_SYNC
    frame.render = input->has_render ? input->render : NULL;
#else
    frame.render = NULL;
#endif
    frame.output = output;
    frame.metrics = metrics;
    if (input->has_metadata) {
        frame.capture_timestamp_ns = input->metadata.capture_timestamp_ns;
        frame.render_timestamp_ns = input->metadata.render_timestamp_ns;
        frame.metadata_flags = input->metadata.flags;
    }
    (void)ap_flight_recorder_record(runtime->recorder, &frame);
}

static int wait_work(ap_runtime_t *runtime) {
    int rc;
    do {
        rc = sem_wait(&runtime->wake);
    } while (rc != 0 && errno == EINTR);
    return rc;
}

static void runtime_setup_thread(ap_runtime_t *runtime) {
    int policy = SCHED_OTHER;
    struct sched_param sp;
    memset(&sp, 0, sizeof(sp));
    if (runtime->options.set_thread_name && runtime->options.thread_name[0])
        (void)pthread_setname_np(pthread_self(), runtime->options.thread_name);
    if (runtime->cfg.dsp_cpu >= 0) {
        cpu_set_t set;
        const int cpu = runtime->cfg.dsp_cpu;
        int rc;
        CPU_ZERO(&set);
        CPU_SET(cpu, &set);
        rc = pthread_setaffinity_np(pthread_self(), sizeof(set), &set);
        if (rc != 0) {
            counter64_add(&runtime->scheduler_bind_failures, 1u);
            runtime_emit_event(runtime,
                               AP_EVENT_RT_AFFINITY_FAILED,
                               AP_EVENT_WARN,
                               cpu,
                               rc,
                               1u);
        }
    }
    if (runtime->cfg.dsp_priority > 0) {
        int rc;
        sp.sched_priority = runtime->cfg.dsp_priority;
        rc = pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
        if (rc != 0) {
            counter64_add(&runtime->scheduler_bind_failures, 1u);
            runtime_emit_event(runtime,
                               AP_EVENT_RT_PRIORITY_FAILED,
                               AP_EVENT_WARN,
                               runtime->cfg.dsp_priority,
                               rc,
                               1u);
        }
    }
    if (runtime->options.lock_memory && mlockall(MCL_CURRENT | MCL_FUTURE) != 0) {
        counter64_add(&runtime->memory_lock_failures, 1u);
        runtime_emit_event(runtime,
                           AP_EVENT_RT_MLOCK_FAILED,
                           AP_EVENT_WARN,
                           errno,
                           0,
                           1u);
    }
    atomic_store_explicit(&runtime->actual_cpu, sched_getcpu(), memory_order_release);
    if (pthread_getschedparam(pthread_self(), &policy, &sp) == 0) {
        atomic_store_explicit(&runtime->actual_policy, policy, memory_order_release);
        atomic_store_explicit(&runtime->actual_priority,
                              sp.sched_priority,
                              memory_order_release);
    }
}

static void runtime_sample_cpu(ap_runtime_t *runtime) {
    int cpu;
    int old;
    if (runtime->cpu_sample_countdown) {
        runtime->cpu_sample_countdown--;
        return;
    }
    runtime->cpu_sample_countdown = 63u;
    cpu = sched_getcpu();
    if (cpu < 0) return;
    old = atomic_load_explicit(&runtime->actual_cpu, memory_order_relaxed);
    if (old >= 0 && old != cpu) {
        counter32_inc_sat(&runtime->observed_cpu_changes);
        runtime_emit_event(runtime, AP_EVENT_CPU_MIGRATION, AP_EVENT_INFO, old, cpu, 1u);
    }
    atomic_store_explicit(&runtime->actual_cpu, cpu, memory_order_release);
}

static void runtime_publish_failure(ap_runtime_t *runtime,
                                    ap_rt_input_t *input,
                                    int publish,
                                    ap_rt_output_t *slot,
                                    unsigned out_head,
                                    unsigned out_tail,
                                    int16_t *audio,
                                    ap_status_t status,
                                    int stage) {
    ap_metrics_t metrics;
    memset(audio, 0, (size_t)runtime->io_frames * sizeof(int16_t));
    counter32_inc_sat(&runtime->failed_frames);
    if (stage == 1) counter32_inc_sat(&runtime->render_push_failures);
    if (stage == 2) counter32_inc_sat(&runtime->capture_process_failures);
    atomic_store_explicit(&runtime->last_pipeline_error, status, memory_order_release);
    runtime_emit_event(runtime, AP_EVENT_PIPELINE_ERROR, AP_EVENT_ERROR, stage, status, 1u);
    ap_pipeline_get_metrics(runtime->pipeline, &metrics);
    runtime_record_frame(runtime, input, audio, &metrics);
    if (publish) {
        slot->metrics = metrics;
        slot->status = status;
        atomic_store_explicit(&runtime->out_head, out_head + 1u, memory_order_release);
        update_max(&runtime->output_queue_high_water, out_head + 1u - out_tail);
    } else {
        counter64_add(&runtime->output_drop_events, 1u);
        runtime_emit_event(runtime, AP_EVENT_OUTPUT_DROPPED, AP_EVENT_WARN, 0, 0, 1u);
    }
}

static void *worker(void *arg) {
    ap_runtime_t *runtime = (ap_runtime_t *)arg;
    int16_t discard_audio[AP_BUILD_IO_FRAME_MAX];
    runtime_setup_thread(runtime);
    runtime_emit_event(runtime, AP_EVENT_RUNTIME_STARTED, AP_EVENT_INFO, 0, 0, 1u);
    for (;;) {
        unsigned tail;
        unsigned head;
        if (wait_work(runtime) != 0) continue;
        if (!atomic_load_explicit(&runtime->running, memory_order_acquire)) break;
        runtime_drain_commands(runtime);
        {
            const unsigned pending =
                atomic_exchange_explicit(&runtime->pending_input_full,
                                         0u,
                                         memory_order_acq_rel);
            if (pending)
                runtime_emit_event(runtime,
                                   AP_EVENT_INPUT_QUEUE_FULL,
                                   AP_EVENT_WARN,
                                   0,
                                   0,
                                   pending);
        }
        tail = atomic_load_explicit(&runtime->in_tail, memory_order_relaxed);
        head = atomic_load_explicit(&runtime->in_head, memory_order_acquire);
        if (tail == head) continue;
        {
            ap_rt_input_t *input = &runtime->in[tail & AP_RT_MASK];
            const unsigned out_head =
                atomic_load_explicit(&runtime->out_head, memory_order_relaxed);
            const unsigned out_tail =
                atomic_load_explicit(&runtime->out_tail, memory_order_acquire);
            const int publish = out_head - out_tail < AP_RT_DEPTH;
            ap_rt_output_t *slot =
                publish ? &runtime->out[out_head & AP_RT_MASK] : NULL;
            int16_t *audio = publish ? slot->audio : discard_audio;
            ap_metrics_t metrics;
            uint64_t t0;
            uint64_t t1;
            uint32_t us;

            if (input->has_metadata && input->metadata.stream_sequence)
                runtime->worker_sequence = input->metadata.stream_sequence;
            else
                runtime->worker_sequence++;
            runtime_apply_metadata(runtime, input);
            runtime_sample_cpu(runtime);
            t0 = now_ns();
#if AP_HAVE_MODULE_SYNC
            if (runtime->uses_render) {
                if (!input->has_render)
                    runtime_emit_event(runtime,
                                       AP_EVENT_RENDER_MISSING,
                                       AP_EVENT_WARN,
                                       0,
                                       0,
                                       1u);
                {
                    const ap_status_t status = ap_pipeline_push_render(runtime->pipeline,
                                                                       input->render,
                                                                       runtime->io_frames);
                    if (status != AP_OK) {
                        runtime_publish_failure(runtime, input, publish, slot, out_head,
                                                out_tail, audio, status, 1);
                        atomic_store_explicit(&runtime->in_tail, tail + 1u, memory_order_release);
                        continue;
                    }
                }
            }
#endif
            {
                const ap_status_t status = ap_pipeline_process_capture(runtime->pipeline,
                                                                       input->mic,
                                                                       runtime->io_frames,
                                                                       audio);
                if (status != AP_OK) {
                    runtime_publish_failure(runtime, input, publish, slot, out_head,
                                            out_tail, audio, status, 2);
                    atomic_store_explicit(&runtime->in_tail, tail + 1u, memory_order_release);
                    continue;
                }
            }
            t1 = now_ns();
            us = (uint32_t)((t1 - t0 + 999ull) / 1000ull);
            atomic_store_explicit(&runtime->last_dsp_us, us, memory_order_relaxed);
            update_max(&runtime->max_dsp_us, us);
            atomic_fetch_add_explicit(&runtime->latency_hist[latency_bucket(us)],
                                      1u,
                                      memory_order_relaxed);
            adjust_quality(runtime, t1 - t0);
            ap_pipeline_get_metrics(runtime->pipeline, &metrics);
            atomic_store_explicit(&runtime->quality,
                                  (unsigned)metrics.quality,
                                  memory_order_release);
            runtime_note_pipeline_events(runtime, &metrics);
            runtime_record_frame(runtime, input, audio, &metrics);
            counter64_add(&runtime->processed_frames, 1u);
            if (publish) {
                slot->metrics = metrics;
                slot->status = AP_OK;
                atomic_store_explicit(&runtime->out_head,
                                      out_head + 1u,
                                      memory_order_release);
                update_max(&runtime->output_queue_high_water,
                           out_head + 1u - out_tail);
            } else {
                counter64_add(&runtime->output_drop_events, 1u);
                runtime_emit_event(runtime,
                                   AP_EVENT_OUTPUT_DROPPED,
                                   AP_EVENT_WARN,
                                   0,
                                   0,
                                   1u);
            }
            atomic_store_explicit(&runtime->in_tail,
                                  tail + 1u,
                                  memory_order_release);
        }
    }
    runtime_emit_event(runtime, AP_EVENT_RUNTIME_STOPPED, AP_EVENT_INFO, 0, 0, 1u);
    return NULL;
}

ap_status_t ap_runtime_start(ap_runtime_t *runtime) {
    pthread_attr_t attr;
    int use_attr = 0;
    int rc;
    if (!runtime) return AP_EINVAL;
    if (atomic_exchange_explicit(&runtime->running, 1u, memory_order_acq_rel))
        return AP_ESTATE;
    if (pthread_attr_init(&attr) == 0) {
        use_attr = 1;
        if (runtime->options.dsp_stack_bytes &&
            pthread_attr_setstacksize(&attr,
                                      runtime->options.dsp_stack_bytes) != 0) {
            pthread_attr_destroy(&attr);
            atomic_store_explicit(&runtime->running, 0u, memory_order_release);
            return AP_EINVAL;
        }
    }
    rc = pthread_create(&runtime->thread,
                        use_attr ? &attr : NULL,
                        worker,
                        runtime);
    if (use_attr) pthread_attr_destroy(&attr);
    if (rc != 0) {
        atomic_store_explicit(&runtime->running, 0u, memory_order_release);
        return AP_ESTATE;
    }
    return AP_OK;
}

void ap_runtime_stop(ap_runtime_t *runtime) {
    if (!runtime) return;
    if (atomic_exchange_explicit(&runtime->running, 0u, memory_order_acq_rel)) {
        (void)sem_post(&runtime->wake);
        (void)pthread_join(runtime->thread, NULL);
    }
}

void ap_runtime_deinit(ap_runtime_t *runtime) {
    if (!runtime) return;
    ap_runtime_stop(runtime);
    (void)sem_destroy(&runtime->wake);
}

ap_status_t ap_runtime_submit_ex(ap_runtime_t *runtime,
                                 const int16_t *mic,
                                 const int16_t *render,
                                 const ap_frame_metadata_t *metadata) {
    unsigned head;
    unsigned tail;
    ap_rt_input_t *dst;
    size_t mic_samples;
    if (!runtime || !mic) return AP_EINVAL;
    if (metadata &&
        (metadata->struct_size < sizeof(*metadata) ||
         metadata->api_version != AP_RUNTIME_CONTROL_API_VERSION))
        return AP_EINVAL;
    head = atomic_load_explicit(&runtime->in_head, memory_order_relaxed);
    tail = atomic_load_explicit(&runtime->in_tail, memory_order_acquire);
    if (head - tail >= AP_RT_DEPTH) {
        counter64_add(&runtime->input_full_events, 1u);
        atomic_fetch_add_explicit(&runtime->pending_input_full,
                                  1u,
                                  memory_order_relaxed);
        (void)sem_post(&runtime->wake);
        return AP_EFULL;
    }
    dst = &runtime->in[head & AP_RT_MASK];
    mic_samples = (size_t)runtime->io_frames * runtime->mic_channels;
    memcpy(dst->mic, mic, mic_samples * sizeof(int16_t));
    dst->has_metadata = (uint8_t)(metadata != NULL);
    dst->has_render = (uint8_t)(render != NULL);
    memset(&dst->metadata, 0, sizeof(dst->metadata));
    if (metadata) {
        dst->metadata.stream_sequence = metadata->stream_sequence;
        dst->metadata.capture_timestamp_ns = metadata->capture_timestamp_ns;
        dst->metadata.render_timestamp_ns = metadata->render_timestamp_ns;
        dst->metadata.flags = metadata->flags;
        dst->metadata.lost_capture_frames = metadata->lost_capture_frames;
        dst->metadata.lost_render_frames = metadata->lost_render_frames;
    }
#if AP_HAVE_MODULE_SYNC
    if (runtime->uses_render) {
        if (render)
            memcpy(dst->render,
                   render,
                   (size_t)runtime->io_frames * sizeof(int16_t));
        else
            memset(dst->render,
                   0,
                   (size_t)runtime->io_frames * sizeof(int16_t));
    }
#else
    (void)render;
#endif
    atomic_store_explicit(&runtime->in_head, head + 1u, memory_order_release);
    counter64_add(&runtime->submitted_frames, 1u);
    update_max(&runtime->input_queue_high_water, head + 1u - tail);
    (void)sem_post(&runtime->wake);
    return AP_OK;
}

ap_status_t ap_runtime_submit(ap_runtime_t *runtime,
                              const int16_t *mic,
                              const int16_t *render) {
    return ap_runtime_submit_ex(runtime, mic, render, NULL);
}

static ap_status_t runtime_validate_command(const ap_runtime_command_t *command) {
    const ap_discontinuity_flags_t discontinuity_all =
        AP_DISCONTINUITY_CAPTURE_GAP | AP_DISCONTINUITY_RENDER_GAP |
        AP_DISCONTINUITY_CLOCK_RESET | AP_DISCONTINUITY_XRUN |
        AP_DISCONTINUITY_CODEC_REOPEN | AP_DISCONTINUITY_ROUTE_CHANGE;
    const ap_tuning_mask_t tuning_all =
        AP_TUNING_AEC_MU | AP_TUNING_NS_FLOOR |
        AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER;
    if (!command || command->struct_size < sizeof(*command) ||
        command->api_version != AP_RUNTIME_CONTROL_API_VERSION)
        return AP_EINVAL;
    switch ((ap_runtime_command_kind_t)command->kind) {
    case AP_RUNTIME_COMMAND_ECHO_PATH_CHANGE:
    case AP_RUNTIME_COMMAND_RESET:
        return AP_OK;
    case AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY:
        if (command->data.discontinuity.flags == 0u ||
            (command->data.discontinuity.flags & ~discontinuity_all) != 0u)
            return AP_EINVAL;
        return AP_OK;
    case AP_RUNTIME_COMMAND_SET_QUALITY:
        if (command->data.set_quality.quality < AP_QUALITY_SAFE ||
            command->data.set_quality.quality > AP_QUALITY_FULL)
            return AP_EINVAL;
        return AP_OK;
    case AP_RUNTIME_COMMAND_SET_TUNING: {
        const ap_tuning_t *t = &command->data.tuning;
        if (t->struct_size < sizeof(*t) ||
            t->api_version != AP_PIPELINE_CONTROL_API_VERSION ||
            t->mask == 0u || (t->mask & ~tuning_all) != 0u)
            return AP_EINVAL;
        if ((t->mask & AP_TUNING_AEC_MU) &&
            (!isfinite(t->aec_mu) || t->aec_mu <= 0.0f || t->aec_mu > 1.0f))
            return AP_EINVAL;
        if ((t->mask & AP_TUNING_NS_FLOOR) &&
            (!isfinite(t->ns_floor) || t->ns_floor < 0.02f || t->ns_floor > 1.0f))
            return AP_EINVAL;
        if ((t->mask & AP_TUNING_AGC_TARGET) &&
            (!isfinite(t->agc_target_dbfs) || t->agc_target_dbfs < -60.0f ||
             t->agc_target_dbfs > -1.0f))
            return AP_EINVAL;
        if ((t->mask & AP_TUNING_LIMITER) &&
            (!isfinite(t->limiter_dbfs) || t->limiter_dbfs < -20.0f ||
             t->limiter_dbfs > -0.1f))
            return AP_EINVAL;
        if ((t->mask & (AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER)) ==
            (AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER) &&
            t->agc_target_dbfs >= t->limiter_dbfs)
            return AP_EINVAL;
        return AP_OK;
    }
    default:
        return AP_EINVAL;
    }
}

ap_status_t ap_runtime_command(ap_runtime_t *runtime,
                               const ap_runtime_command_t *command) {
    unsigned head;
    unsigned tail;
    ap_rt_command_t *dst;
    if (!runtime || runtime_validate_command(command) != AP_OK)
        return AP_EINVAL;
    head = atomic_load_explicit(&runtime->command_head, memory_order_relaxed);
    tail = atomic_load_explicit(&runtime->command_tail, memory_order_acquire);
    if (head - tail >= AP_RUNTIME_COMMAND_QUEUE_DEPTH) {
        counter64_add(&runtime->command_full_events, 1u);
        return AP_EFULL;
    }
    dst = &runtime->commands[head & AP_RT_COMMAND_MASK];
    memset(dst, 0, sizeof(*dst));
    dst->kind = command->kind;
    switch ((ap_runtime_command_kind_t)command->kind) {
    case AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY:
        dst->data.discontinuity.flags = command->data.discontinuity.flags;
        dst->data.discontinuity.lost_frames =
            command->data.discontinuity.lost_frames;
        break;
    case AP_RUNTIME_COMMAND_SET_QUALITY:
        dst->data.quality = command->data.set_quality.quality;
        break;
    case AP_RUNTIME_COMMAND_SET_TUNING:
        dst->data.tuning.mask = command->data.tuning.mask;
        dst->data.tuning.aec_mu = command->data.tuning.aec_mu;
        dst->data.tuning.ns_floor = command->data.tuning.ns_floor;
        dst->data.tuning.agc_target_dbfs = command->data.tuning.agc_target_dbfs;
        dst->data.tuning.limiter_dbfs = command->data.tuning.limiter_dbfs;
        break;
    default:
        break;
    }
    atomic_store_explicit(&runtime->command_head, head + 1u, memory_order_release);
    (void)sem_post(&runtime->wake);
    return AP_OK;
}

ap_status_t ap_runtime_receive(ap_runtime_t *runtime,
                               int16_t *output,
                               ap_metrics_t *metrics) {
    unsigned head;
    unsigned tail;
    ap_rt_output_t *src;
    if (!runtime || !output) return AP_EINVAL;
    tail = atomic_load_explicit(&runtime->out_tail, memory_order_relaxed);
    head = atomic_load_explicit(&runtime->out_head, memory_order_acquire);
    if (tail == head) return AP_EEMPTY;
    src = &runtime->out[tail & AP_RT_MASK];
    memcpy(output,
           src->audio,
           (size_t)runtime->io_frames * sizeof(int16_t));
    if (metrics) *metrics = src->metrics;
    atomic_store_explicit(&runtime->out_tail, tail + 1u, memory_order_release);
    return src->status;
}

ap_status_t ap_runtime_receive_event(ap_runtime_t *runtime, ap_event_t *event) {
    unsigned head;
    unsigned tail;
    const ap_rt_event_t *src;
    if (!runtime || !event) return AP_EINVAL;
    tail = atomic_load_explicit(&runtime->event_tail, memory_order_relaxed);
    head = atomic_load_explicit(&runtime->event_head, memory_order_acquire);
    if (tail == head) return AP_EEMPTY;
    src = &runtime->events[tail & AP_RT_EVENT_MASK];
    memset(event, 0, sizeof(*event));
    event->struct_size = sizeof(*event);
    event->api_version = AP_DIAG_API_VERSION;
    event->frame_sequence = src->frame_sequence;
    event->timestamp_ns = src->timestamp_ns;
    event->kind = src->kind;
    event->severity = src->severity;
    event->flags = src->flags;
    event->arg0 = src->arg0;
    event->arg1 = src->arg1;
    event->count = src->count;
    atomic_store_explicit(&runtime->event_tail, tail + 1u, memory_order_release);
    return AP_OK;
}

ap_status_t ap_runtime_attach_flight_recorder(ap_runtime_t *runtime,
                                              ap_flight_recorder_t *recorder) {
    if (!runtime) return AP_EINVAL;
    if (atomic_load_explicit(&runtime->running, memory_order_acquire))
        return AP_ESTATE;
    if (recorder &&
        (recorder->cfg.frame_samples != runtime->io_frames ||
         recorder->cfg.mic_channels != runtime->mic_channels ||
         recorder->cfg.io_sample_rate_hz != runtime->io_frames * 100u))
        return AP_EINVAL;
    runtime->recorder = recorder;
    return AP_OK;
}

void ap_runtime_get_metrics(const ap_runtime_t *runtime,
                            ap_runtime_metrics_t *metrics) {
    if (!runtime || !metrics) return;
    metrics->submitted_frames = counter64_read(&runtime->submitted_frames);
    metrics->processed_frames = counter64_read(&runtime->processed_frames);
    metrics->input_full_events = counter64_read(&runtime->input_full_events);
    metrics->output_drop_events = counter64_read(&runtime->output_drop_events);
    metrics->dsp_overruns = counter64_read(&runtime->dsp_overruns);
    metrics->last_dsp_us =
        atomic_load_explicit(&runtime->last_dsp_us, memory_order_relaxed);
    metrics->max_dsp_us =
        atomic_load_explicit(&runtime->max_dsp_us, memory_order_relaxed);
    metrics->quality =
        (ap_quality_t)atomic_load_explicit(&runtime->quality,
                                           memory_order_acquire);
}

static uint32_t percentile_us(const ap_runtime_t *runtime,
                              uint32_t numerator,
                              uint32_t denominator) {
    uint64_t total = 0u;
    uint64_t target;
    uint64_t cumulative = 0u;
    uint32_t i;
    for (i = 0u; i < AP_RUNTIME_LATENCY_BUCKETS; ++i)
        total += atomic_load_explicit(&runtime->latency_hist[i],
                                      memory_order_relaxed);
    if (!total) return 0u;
    target = (total * numerator + denominator - 1u) / denominator;
    for (i = 0u; i < AP_RUNTIME_LATENCY_BUCKETS; ++i) {
        cumulative += atomic_load_explicit(&runtime->latency_hist[i],
                                           memory_order_relaxed);
        if (cumulative >= target) return latency_bucket_upper(i);
    }
    return UINT32_MAX;
}

ap_status_t ap_runtime_get_metrics_v2(const ap_runtime_t *runtime,
                                      ap_runtime_metrics_v2_t *metrics) {
    if (!runtime || !metrics || metrics->struct_size < sizeof(*metrics) ||
        metrics->api_version != AP_RUNTIME_CONTROL_API_VERSION)
        return AP_EINVAL;
    metrics->submitted_frames = counter64_read(&runtime->submitted_frames);
    metrics->processed_frames = counter64_read(&runtime->processed_frames);
    metrics->input_full_events = counter64_read(&runtime->input_full_events);
    metrics->output_drop_events = counter64_read(&runtime->output_drop_events);
    metrics->dsp_overruns = counter64_read(&runtime->dsp_overruns);
    metrics->command_full_events = counter64_read(&runtime->command_full_events);
    metrics->event_drop_events = counter64_read(&runtime->event_drop_events);
    metrics->stream_discontinuities =
        counter64_read(&runtime->stream_discontinuities);
    metrics->capture_gap_frames = counter64_read(&runtime->capture_gap_frames);
    metrics->render_gap_frames = counter64_read(&runtime->render_gap_frames);
    metrics->timestamp_frames = counter64_read(&runtime->timestamp_frames);
    metrics->scheduler_bind_failures =
        counter64_read(&runtime->scheduler_bind_failures);
    metrics->memory_lock_failures =
        counter64_read(&runtime->memory_lock_failures);
    metrics->input_queue_high_water =
        atomic_load_explicit(&runtime->input_queue_high_water,
                             memory_order_relaxed);
    metrics->output_queue_high_water =
        atomic_load_explicit(&runtime->output_queue_high_water,
                             memory_order_relaxed);
    metrics->last_dsp_us =
        atomic_load_explicit(&runtime->last_dsp_us, memory_order_relaxed);
    metrics->max_dsp_us =
        atomic_load_explicit(&runtime->max_dsp_us, memory_order_relaxed);
    metrics->p50_dsp_us = percentile_us(runtime, 50u, 100u);
    metrics->p95_dsp_us = percentile_us(runtime, 95u, 100u);
    metrics->p99_dsp_us = percentile_us(runtime, 99u, 100u);
    metrics->actual_cpu =
        atomic_load_explicit(&runtime->actual_cpu, memory_order_acquire);
    metrics->actual_policy =
        atomic_load_explicit(&runtime->actual_policy, memory_order_acquire);
    metrics->actual_priority =
        atomic_load_explicit(&runtime->actual_priority, memory_order_acquire);
    metrics->quality =
        (ap_quality_t)atomic_load_explicit(&runtime->quality,
                                           memory_order_acquire);
    return AP_OK;
}

ap_status_t ap_runtime_get_metrics_v3(const ap_runtime_t *runtime,
                                      ap_runtime_metrics_v3_t *metrics) {
    ap_runtime_metrics_v2_t v2;
    if (!runtime || !metrics || metrics->struct_size < sizeof(*metrics) ||
        metrics->api_version != AP_RUNTIME_METRICS_V3_API_VERSION)
        return AP_EINVAL;
    memset(&v2, 0, sizeof(v2));
    v2.struct_size = sizeof(v2);
    v2.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    if (ap_runtime_get_metrics_v2(runtime, &v2) != AP_OK) return AP_ESTATE;
    metrics->submitted_frames = v2.submitted_frames;
    metrics->processed_frames = v2.processed_frames;
    metrics->failed_frames = (uint64_t)atomic_load_explicit(&runtime->failed_frames, memory_order_acquire);
    metrics->input_full_events = v2.input_full_events;
    metrics->output_drop_events = v2.output_drop_events;
    metrics->dsp_overruns = v2.dsp_overruns;
    metrics->command_full_events = v2.command_full_events;
    metrics->event_drop_events = v2.event_drop_events;
    metrics->stream_discontinuities = v2.stream_discontinuities;
    metrics->capture_gap_frames = v2.capture_gap_frames;
    metrics->render_gap_frames = v2.render_gap_frames;
    metrics->timestamp_frames = v2.timestamp_frames;
    metrics->scheduler_bind_failures = v2.scheduler_bind_failures;
    metrics->memory_lock_failures = v2.memory_lock_failures;
    metrics->render_push_failures = (uint64_t)atomic_load_explicit(&runtime->render_push_failures, memory_order_acquire);
    metrics->capture_process_failures = (uint64_t)atomic_load_explicit(&runtime->capture_process_failures, memory_order_acquire);
    metrics->observed_cpu_changes = (uint64_t)atomic_load_explicit(&runtime->observed_cpu_changes, memory_order_acquire);
    metrics->critical_events = (uint64_t)atomic_load_explicit(&runtime->critical_events, memory_order_acquire);
    metrics->input_queue_high_water = v2.input_queue_high_water;
    metrics->output_queue_high_water = v2.output_queue_high_water;
    metrics->last_dsp_us = v2.last_dsp_us;
    metrics->max_dsp_us = v2.max_dsp_us;
    metrics->p50_dsp_us = v2.p50_dsp_us;
    metrics->p95_dsp_us = v2.p95_dsp_us;
    metrics->p99_dsp_us = v2.p99_dsp_us;
    metrics->actual_cpu = v2.actual_cpu;
    metrics->actual_policy = v2.actual_policy;
    metrics->actual_priority = v2.actual_priority;
    metrics->last_pipeline_error = atomic_load_explicit(&runtime->last_pipeline_error, memory_order_acquire);
    metrics->quality = v2.quality;
    return AP_OK;
}

ap_status_t ap_runtime_get_critical_state(const ap_runtime_t *runtime,
                                          ap_runtime_critical_state_t *state) {
    unsigned seq0 = 0u;
    unsigned seq1 = 0u;
    unsigned lo = 0u;
    unsigned hi = 0u;
    if (!runtime || !state || state->struct_size < sizeof(*state) ||
        state->api_version != AP_RUNTIME_CRITICAL_STATE_API_VERSION)
        return AP_EINVAL;
    do {
        seq0 = atomic_load_explicit(&runtime->critical_seq, memory_order_acquire);
        if (seq0 & 1u) continue;
        lo = atomic_load_explicit(&runtime->critical_frame_lo, memory_order_relaxed);
        hi = atomic_load_explicit(&runtime->critical_frame_hi, memory_order_relaxed);
        state->kind = atomic_load_explicit(&runtime->critical_kind, memory_order_relaxed);
        state->severity = (uint8_t)atomic_load_explicit(&runtime->critical_severity, memory_order_relaxed);
        state->arg0 = atomic_load_explicit(&runtime->critical_arg0, memory_order_relaxed);
        state->arg1 = atomic_load_explicit(&runtime->critical_arg1, memory_order_relaxed);
        seq1 = atomic_load_explicit(&runtime->critical_seq, memory_order_acquire);
    } while (seq0 != seq1);
    state->frame_sequence = ((uint64_t)hi << 32u) | lo;
    state->total_events = (uint64_t)atomic_load_explicit(&runtime->critical_events, memory_order_acquire);
    return AP_OK;
}
