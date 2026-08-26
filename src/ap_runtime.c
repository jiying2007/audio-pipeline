#define _GNU_SOURCE
#include "audio_pipeline/audio_runtime.h"
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <semaphore.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#define AP_RT_DEPTH 8u
#define AP_RT_MASK (AP_RT_DEPTH - 1u)
#define AP_RT_MAX_CAPTURE (AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS)

typedef struct ap_rt_input {
    int16_t mic[AP_RT_MAX_CAPTURE];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
} ap_rt_input_t;

typedef struct ap_rt_output {
    int16_t audio[AP_MAX_IO_FRAME_SAMPLES];
    ap_metrics_t metrics;
} ap_rt_output_t;

struct ap_runtime {
    ap_pipeline_t *pipeline;
    ap_runtime_config_t cfg;
    pthread_t thread;
    sem_t wake;
    atomic_uint running, in_head, in_tail, out_head, out_tail;
    atomic_uint_fast64_t submitted_frames, processed_frames;
    atomic_uint_fast64_t input_full_events, output_drop_events, dsp_overruns;
    atomic_uint last_dsp_us, max_dsp_us;
    ap_rt_input_t in[AP_RT_DEPTH];
    ap_rt_output_t out[AP_RT_DEPTH];
    uint32_t io_frames, mic_channels;
    uint32_t overload_streak, healthy_streak;
};

static uint64_t ap_now_ns(void) {
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

int ap_runtime_bind_current_thread(int cpu, int fifo_priority) {
    int rc = 0;
    if (cpu >= 0) {
        cpu_set_t set;
        CPU_ZERO(&set);
        CPU_SET(cpu, &set);
        if (pthread_setaffinity_np(pthread_self(), sizeof(set), &set) != 0) rc = -1;
    }
    if (fifo_priority > 0) {
        struct sched_param sp;
        memset(&sp, 0, sizeof(sp));
        sp.sched_priority = fifo_priority > 99 ? 99 : fifo_priority;
        if (pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp) != 0) rc = -1;
    }
    return rc;
}

ap_runtime_config_t ap_runtime_config_default(void) {
    ap_runtime_config_t c;
    c.dsp_cpu = 1;
    c.dsp_priority = 20;
    c.overload_us = 9000u;
    c.recover_frames = 1000u;
    return c;
}

size_t ap_runtime_state_size(void) { return sizeof(ap_runtime_t); }

ap_status_t ap_runtime_init(void *memory, size_t memory_size, ap_pipeline_t *pipeline,
                            const ap_runtime_config_t *config, ap_runtime_t **out) {
    ap_runtime_t *r;
    if (!memory || memory_size < sizeof(ap_runtime_t) || !pipeline || !config || !out) return AP_ENOMEM;
    r = (ap_runtime_t *)memory;
    memset(r, 0, sizeof(*r));
    r->pipeline = pipeline;
    r->cfg = *config;
    r->io_frames = (uint32_t)ap_pipeline_frame_samples(pipeline);
    r->mic_channels = ap_pipeline_mic_channels(pipeline);
    if (!r->io_frames || r->io_frames > AP_MAX_IO_FRAME_SAMPLES ||
        !r->mic_channels || r->mic_channels > AP_MAX_MIC_CHANNELS) return AP_EINVAL;
    if (sem_init(&r->wake, 0, 0) != 0) return AP_ESTATE;
    atomic_init(&r->running, 0u);
    atomic_init(&r->in_head, 0u);
    atomic_init(&r->in_tail, 0u);
    atomic_init(&r->out_head, 0u);
    atomic_init(&r->out_tail, 0u);
    atomic_init(&r->submitted_frames, 0u);
    atomic_init(&r->processed_frames, 0u);
    atomic_init(&r->input_full_events, 0u);
    atomic_init(&r->output_drop_events, 0u);
    atomic_init(&r->dsp_overruns, 0u);
    atomic_init(&r->last_dsp_us, 0u);
    atomic_init(&r->max_dsp_us, 0u);
    *out = r;
    return AP_OK;
}

static void ap_update_max(atomic_uint *dst, uint32_t value) {
    unsigned cur = atomic_load_explicit(dst, memory_order_relaxed);
    while (value > cur &&
           !atomic_compare_exchange_weak_explicit(dst, &cur, value,
                                                  memory_order_relaxed,
                                                  memory_order_relaxed)) {
    }
}

static void ap_adjust_quality(ap_runtime_t *r, uint64_t elapsed_ns) {
    const uint64_t limit = (uint64_t)r->cfg.overload_us * 1000ull;
    ap_metrics_t m;
    ap_pipeline_get_metrics(r->pipeline, &m);
    if (elapsed_ns > limit) {
        r->healthy_streak = 0u;
        atomic_fetch_add_explicit(&r->dsp_overruns, 1u, memory_order_relaxed);
        if (++r->overload_streak >= 3u) {
            if (m.quality == AP_QUALITY_FULL) (void)ap_pipeline_set_quality(r->pipeline, AP_QUALITY_LITE);
            else if (m.quality == AP_QUALITY_LITE) (void)ap_pipeline_set_quality(r->pipeline, AP_QUALITY_SAFE);
            r->overload_streak = 0u;
        }
    } else {
        r->overload_streak = 0u;
        if (++r->healthy_streak >= r->cfg.recover_frames) {
            if (m.quality == AP_QUALITY_SAFE) (void)ap_pipeline_set_quality(r->pipeline, AP_QUALITY_LITE);
            else if (m.quality == AP_QUALITY_LITE) (void)ap_pipeline_set_quality(r->pipeline, AP_QUALITY_FULL);
            r->healthy_streak = 0u;
        }
    }
}

static int ap_wait_for_work(ap_runtime_t *r) {
    int rc;
    do {
        rc = sem_wait(&r->wake);
    } while (rc != 0 && errno == EINTR);
    return rc;
}

static void *ap_worker(void *arg) {
    ap_runtime_t *r = (ap_runtime_t *)arg;
    (void)ap_runtime_bind_current_thread(r->cfg.dsp_cpu, r->cfg.dsp_priority);
    for (;;) {
        unsigned tail, head;
        if (ap_wait_for_work(r) != 0) continue;
        if (!atomic_load_explicit(&r->running, memory_order_acquire)) break;
        tail = atomic_load_explicit(&r->in_tail, memory_order_relaxed);
        head = atomic_load_explicit(&r->in_head, memory_order_acquire);
        if (tail == head) continue;
        {
            const unsigned oh = atomic_load_explicit(&r->out_head, memory_order_relaxed);
            const unsigned ot = atomic_load_explicit(&r->out_tail, memory_order_acquire);
            ap_rt_input_t *in = &r->in[tail & AP_RT_MASK];
            ap_rt_output_t *out;
            uint64_t t0, t1;
            uint32_t elapsed_us;
            if (oh - ot >= AP_RT_DEPTH) {
                atomic_fetch_add_explicit(&r->output_drop_events, 1u, memory_order_relaxed);
                atomic_store_explicit(&r->in_tail, tail + 1u, memory_order_release);
                continue;
            }
            out = &r->out[oh & AP_RT_MASK];
            t0 = ap_now_ns();
            if (ap_pipeline_push_render(r->pipeline, in->render, r->io_frames) != AP_OK ||
                ap_pipeline_process_capture(r->pipeline, in->mic, r->io_frames, out->audio) != AP_OK) {
                atomic_store_explicit(&r->in_tail, tail + 1u, memory_order_release);
                continue;
            }
            t1 = ap_now_ns();
            elapsed_us = (uint32_t)((t1 - t0 + 999ull) / 1000ull);
            atomic_store_explicit(&r->last_dsp_us, elapsed_us, memory_order_relaxed);
            ap_update_max(&r->max_dsp_us, elapsed_us);
            ap_adjust_quality(r, t1 - t0);
            ap_pipeline_get_metrics(r->pipeline, &out->metrics);
            atomic_fetch_add_explicit(&r->processed_frames, 1u, memory_order_relaxed);
            atomic_store_explicit(&r->out_head, oh + 1u, memory_order_release);
            atomic_store_explicit(&r->in_tail, tail + 1u, memory_order_release);
        }
    }
    return NULL;
}

ap_status_t ap_runtime_start(ap_runtime_t *r) {
    if (!r) return AP_EINVAL;
    if (atomic_exchange_explicit(&r->running, 1u, memory_order_acq_rel)) return AP_ESTATE;
    if (pthread_create(&r->thread, NULL, ap_worker, r) != 0) {
        atomic_store(&r->running, 0u);
        return AP_ESTATE;
    }
    return AP_OK;
}

void ap_runtime_stop(ap_runtime_t *r) {
    if (!r) return;
    if (atomic_exchange_explicit(&r->running, 0u, memory_order_acq_rel)) {
        (void)sem_post(&r->wake);
        (void)pthread_join(r->thread, NULL);
    }
}

void ap_runtime_deinit(ap_runtime_t *r) {
    if (!r) return;
    ap_runtime_stop(r);
    (void)sem_destroy(&r->wake);
}

ap_status_t ap_runtime_submit(ap_runtime_t *r, const int16_t *mic, const int16_t *render) {
    unsigned head, tail;
    ap_rt_input_t *dst;
    size_t mic_samples, render_samples;
    if (!r || !mic) return AP_EINVAL;
    head = atomic_load_explicit(&r->in_head, memory_order_relaxed);
    tail = atomic_load_explicit(&r->in_tail, memory_order_acquire);
    if (head - tail >= AP_RT_DEPTH) {
        atomic_fetch_add_explicit(&r->input_full_events, 1u, memory_order_relaxed);
        return AP_EFULL;
    }
    dst = &r->in[head & AP_RT_MASK];
    mic_samples = (size_t)r->io_frames * r->mic_channels;
    render_samples = r->io_frames;
    memcpy(dst->mic, mic, mic_samples * sizeof(int16_t));
    if (render) memcpy(dst->render, render, render_samples * sizeof(int16_t));
    else memset(dst->render, 0, render_samples * sizeof(int16_t));
    atomic_store_explicit(&r->in_head, head + 1u, memory_order_release);
    atomic_fetch_add_explicit(&r->submitted_frames, 1u, memory_order_relaxed);
    (void)sem_post(&r->wake);
    return AP_OK;
}

ap_status_t ap_runtime_receive(ap_runtime_t *r, int16_t *output, ap_metrics_t *metrics) {
    unsigned head, tail;
    ap_rt_output_t *src;
    if (!r || !output) return AP_EINVAL;
    tail = atomic_load_explicit(&r->out_tail, memory_order_relaxed);
    head = atomic_load_explicit(&r->out_head, memory_order_acquire);
    if (tail == head) return AP_EEMPTY;
    src = &r->out[tail & AP_RT_MASK];
    memcpy(output, src->audio, (size_t)r->io_frames * sizeof(int16_t));
    if (metrics) *metrics = src->metrics;
    atomic_store_explicit(&r->out_tail, tail + 1u, memory_order_release);
    return AP_OK;
}

void ap_runtime_get_metrics(const ap_runtime_t *r, ap_runtime_metrics_t *m) {
    ap_metrics_t pm;
    if (!r || !m) return;
    m->submitted_frames = atomic_load_explicit(&r->submitted_frames, memory_order_relaxed);
    m->processed_frames = atomic_load_explicit(&r->processed_frames, memory_order_relaxed);
    m->input_full_events = atomic_load_explicit(&r->input_full_events, memory_order_relaxed);
    m->output_drop_events = atomic_load_explicit(&r->output_drop_events, memory_order_relaxed);
    m->dsp_overruns = atomic_load_explicit(&r->dsp_overruns, memory_order_relaxed);
    m->last_dsp_us = atomic_load_explicit(&r->last_dsp_us, memory_order_relaxed);
    m->max_dsp_us = atomic_load_explicit(&r->max_dsp_us, memory_order_relaxed);
    ap_pipeline_get_metrics(r->pipeline, &pm);
    m->quality = pm.quality;
}
