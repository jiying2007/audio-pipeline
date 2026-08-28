#define _GNU_SOURCE
#include "audio_pipeline/audio_runtime.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <semaphore.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

#define AP_RT_DEPTH AP_BUILD_RUNTIME_QUEUE_DEPTH
#define AP_RT_MASK (AP_RT_DEPTH-1u)
#define AP_RT_COMMAND_MASK (AP_RUNTIME_COMMAND_QUEUE_DEPTH-1u)
#define AP_RT_EVENT_MASK (AP_RUNTIME_EVENT_QUEUE_DEPTH-1u)
#define AP_RT_MAX_CAPTURE (AP_BUILD_IO_FRAME_MAX*AP_BUILD_MAX_MIC_CHANNELS)
#define AP_DUMP_ENDIAN_TAG 0x01020304u

_Static_assert(ATOMIC_INT_LOCK_FREE==2,"Linux runtime requires lock-free 32-bit atomics");
_Static_assert((AP_RT_DEPTH&(AP_RT_DEPTH-1u))==0u,"runtime queue depth must be power of two");
_Static_assert((AP_RUNTIME_COMMAND_QUEUE_DEPTH&(AP_RUNTIME_COMMAND_QUEUE_DEPTH-1u))==0u,
               "command queue depth must be power of two");
_Static_assert((AP_RUNTIME_EVENT_QUEUE_DEPTH&(AP_RUNTIME_EVENT_QUEUE_DEPTH-1u))==0u,
               "event queue depth must be power of two");
_Static_assert((AP_RUNTIME_STATE_ALIGNMENT&(AP_RUNTIME_STATE_ALIGNMENT-1u))==0u,
               "runtime alignment must be power of two");

typedef struct ap_counter64 {
    atomic_uint seq;
    atomic_uint lo;
    atomic_uint hi;
} ap_counter64_t;

typedef struct ap_rt_input {
    int16_t mic[AP_RT_MAX_CAPTURE];
#if AP_HAVE_MODULE_SYNC
    int16_t render[AP_BUILD_IO_FRAME_MAX];
#endif
    ap_frame_metadata_t metadata;
    uint8_t has_metadata;
    uint8_t has_render;
} ap_rt_input_t;

typedef struct ap_rt_output {
    int16_t audio[AP_BUILD_IO_FRAME_MAX];
    ap_metrics_t metrics;
} ap_rt_output_t;

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
    uint32_t post_remaining;
    uint32_t trigger_event;
    uint8_t triggered;
    uint8_t frozen;
    uint8_t reserved[2];
    unsigned char slots[];
};

struct ap_runtime {
    ap_pipeline_t *pipeline;
    ap_runtime_config_t cfg;
    ap_runtime_options_t options;
    pthread_t thread;
    sem_t wake;
    atomic_uint running;
    atomic_uint in_head,in_tail,out_head,out_tail;
    atomic_uint command_head,command_tail,event_head,event_tail;
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
    atomic_uint input_queue_high_water;
    atomic_uint output_queue_high_water;
    atomic_uint last_dsp_us,max_dsp_us,quality;
    atomic_uint latency_hist[AP_RUNTIME_LATENCY_BUCKETS];
    atomic_int actual_cpu,actual_policy,actual_priority;
    ap_rt_input_t in[AP_RT_DEPTH];
    ap_rt_output_t out[AP_RT_DEPTH];
    ap_runtime_command_t commands[AP_RUNTIME_COMMAND_QUEUE_DEPTH];
    ap_event_t events[AP_RUNTIME_EVENT_QUEUE_DEPTH];
    int16_t discard_audio[AP_BUILD_IO_FRAME_MAX];
    ap_flight_recorder_t *recorder;
    uint32_t io_frames,mic_channels,overload_streak,healthy_streak;
    uint64_t worker_sequence;
    uint64_t last_render_underruns,last_delay_jumps,last_aec_resets;
    float last_valid_erle;
    uint8_t last_aec_converged;
    uint8_t uses_render;
};

_Static_assert(sizeof(struct ap_runtime)<=AP_RUNTIME_STATE_MAX_BYTES,
               "runtime state exceeded public ceiling");

static uint64_t now_ns(void){
    struct timespec ts;
    (void)clock_gettime(CLOCK_MONOTONIC,&ts);
    return(uint64_t)ts.tv_sec*1000000000ull+(uint64_t)ts.tv_nsec;
}

static size_t align_up_size(size_t value,size_t alignment){
    return (value+alignment-1u)&~(alignment-1u);
}

static void counter64_init(ap_counter64_t*c){
    atomic_init(&c->seq,0u);atomic_init(&c->lo,0u);atomic_init(&c->hi,0u);
}

static void counter64_add(ap_counter64_t*c,uint64_t delta){
    uint32_t lo,hi,new_lo;
    atomic_fetch_add_explicit(&c->seq,1u,memory_order_acq_rel);
    lo=atomic_load_explicit(&c->lo,memory_order_relaxed);
    hi=atomic_load_explicit(&c->hi,memory_order_relaxed);
    new_lo=lo+(uint32_t)delta;
    hi+=(uint32_t)(delta>>32u);
    if(new_lo<lo)hi++;
    atomic_store_explicit(&c->lo,new_lo,memory_order_relaxed);
    atomic_store_explicit(&c->hi,hi,memory_order_relaxed);
    atomic_fetch_add_explicit(&c->seq,1u,memory_order_release);
}

static uint64_t counter64_read(const ap_counter64_t*c){
    for(;;){
        unsigned s0=atomic_load_explicit(&c->seq,memory_order_acquire);
        unsigned lo,hi,s1;
        if(s0&1u)continue;
        lo=atomic_load_explicit(&c->lo,memory_order_relaxed);
        hi=atomic_load_explicit(&c->hi,memory_order_relaxed);
        s1=atomic_load_explicit(&c->seq,memory_order_acquire);
        if(s0==s1)return((uint64_t)hi<<32u)|(uint64_t)lo;
    }
}

static void update_max(atomic_uint*dst,uint32_t value){
    unsigned cur=atomic_load_explicit(dst,memory_order_relaxed);
    while(value>cur&&!atomic_compare_exchange_weak_explicit(
        dst,&cur,value,memory_order_relaxed,memory_order_relaxed)){}
}

static void copy_text(char*dst,size_t cap,const char*src){
    size_t n=0u;
    if(!cap)return;
    if(src){while(n+1u<cap&&src[n]){dst[n]=src[n];n++;}}
    dst[n]='\0';
}

static size_t recorder_slot_stride(const ap_flight_recorder_config_t*c){
    size_t bytes=sizeof(ap_dump_record_header_t);
    if(c->record_mask&AP_DIAG_RECORD_METRICS)bytes+=sizeof(ap_metrics_t);
    if(c->record_mask&AP_DIAG_RECORD_MIC)
        bytes+=(size_t)c->frame_samples*c->mic_channels*sizeof(int16_t);
    if(c->record_mask&AP_DIAG_RECORD_RENDER)
        bytes+=(size_t)c->frame_samples*sizeof(int16_t);
    if(c->record_mask&AP_DIAG_RECORD_OUTPUT)
        bytes+=(size_t)c->frame_samples*sizeof(int16_t);
    return align_up_size(bytes,8u);
}

ap_flight_recorder_config_t ap_flight_recorder_config_default(uint32_t rate,uint32_t channels){
    ap_flight_recorder_config_t c;
    memset(&c,0,sizeof(c));
    c.struct_size=sizeof(c);c.api_version=AP_DIAG_API_VERSION;
    c.io_sample_rate_hz=rate;c.mic_channels=channels;c.frame_samples=rate/100u;
    c.pre_roll_frames=500u;c.post_roll_frames=100u;
    c.record_mask=AP_DIAG_RECORD_ALL;c.trigger_severity=AP_EVENT_ERROR;
    return c;
}

size_t ap_flight_recorder_state_size(const ap_flight_recorder_config_t*c){
    size_t capacity,stride;
    if(!c||c->struct_size<sizeof(*c)||c->api_version!=AP_DIAG_API_VERSION||
       !c->frame_samples||!c->mic_channels||c->mic_channels>2u||
       (c->record_mask&~AP_DIAG_RECORD_ALL)!=0u)return 0u;
    capacity=(size_t)c->pre_roll_frames+(size_t)c->post_roll_frames+1u;
    stride=recorder_slot_stride(c);
    if(!capacity||stride>SIZE_MAX/capacity)return 0u;
    if(sizeof(ap_flight_recorder_t)>SIZE_MAX-capacity*stride)return 0u;
    return sizeof(ap_flight_recorder_t)+capacity*stride;
}

size_t ap_flight_recorder_state_alignment(void){return AP_FLIGHT_RECORDER_STATE_ALIGNMENT;}

ap_status_t ap_flight_recorder_init(void*memory,size_t memory_size,
                                    const ap_flight_recorder_config_t*c,
                                    ap_flight_recorder_t**out){
    size_t need;
    ap_flight_recorder_t*r;
    if(!memory||!c||!out)return AP_EINVAL;
    *out=NULL;need=ap_flight_recorder_state_size(c);if(!need)return AP_EINVAL;
    if(memory_size<need)return AP_ENOMEM;
    if(((uintptr_t)memory&(AP_FLIGHT_RECORDER_STATE_ALIGNMENT-1u))!=0u)return AP_EINVAL;
    memset(memory,0,need);r=(ap_flight_recorder_t*)memory;r->cfg=*c;
    r->capacity=c->pre_roll_frames+c->post_roll_frames+1u;
    r->slot_stride=(uint32_t)recorder_slot_stride(c);*out=r;return AP_OK;
}

void ap_flight_recorder_reset(ap_flight_recorder_t*r){
    if(!r)return;r->count=0u;r->head=0u;r->post_remaining=0u;r->trigger_event=0u;
    r->triggered=0u;r->frozen=0u;
}

ap_status_t ap_flight_recorder_trigger(ap_flight_recorder_t*r,
                                       ap_event_kind_t kind,
                                       ap_event_severity_t severity){
    if(!r)return AP_EINVAL;
    if(r->frozen||r->triggered)return AP_OK;
    if(severity<r->cfg.trigger_severity)return AP_OK;
    r->triggered=1u;r->trigger_event=(uint32_t)kind;
    r->post_remaining=r->cfg.post_roll_frames+1u;
    return AP_OK;
}

ap_status_t ap_flight_recorder_record(ap_flight_recorder_t*r,const ap_diag_frame_t*f){
    unsigned char*p;
    ap_dump_record_header_t h;
    size_t mic_bytes;
    if(!r||!f||f->struct_size<sizeof(*f)||f->api_version!=AP_DIAG_API_VERSION)
        return AP_EINVAL;
    if(r->frozen)return AP_ESTATE;
    p=r->slots+(size_t)r->head*r->slot_stride;memset(p,0,r->slot_stride);
    memset(&h,0,sizeof(h));h.frame_sequence=f->frame_sequence;
    h.capture_timestamp_ns=f->capture_timestamp_ns;h.render_timestamp_ns=f->render_timestamp_ns;
    h.metadata_flags=f->metadata_flags;h.trigger_event=f->trigger_event;
    memcpy(p,&h,sizeof(h));p+=sizeof(h);
    if(r->cfg.record_mask&AP_DIAG_RECORD_METRICS){
        if(f->metrics)memcpy(p,f->metrics,sizeof(*f->metrics));
        p+=sizeof(ap_metrics_t);
    }
    mic_bytes=(size_t)r->cfg.frame_samples*r->cfg.mic_channels*sizeof(int16_t);
    if(r->cfg.record_mask&AP_DIAG_RECORD_MIC){
        if(f->mic_interleaved)memcpy(p,f->mic_interleaved,mic_bytes);p+=mic_bytes;
    }
    if(r->cfg.record_mask&AP_DIAG_RECORD_RENDER){
        const size_t n=(size_t)r->cfg.frame_samples*sizeof(int16_t);
        if(f->render)memcpy(p,f->render,n);p+=n;
    }
    if(r->cfg.record_mask&AP_DIAG_RECORD_OUTPUT){
        const size_t n=(size_t)r->cfg.frame_samples*sizeof(int16_t);
        if(f->output)memcpy(p,f->output,n);p+=n;
    }
    r->head=(r->head+1u)%r->capacity;if(r->count<r->capacity)r->count++;
    if(r->triggered&&r->post_remaining){
        r->post_remaining--;if(r->post_remaining==0u)r->frozen=1u;
    }
    return AP_OK;
}

int ap_flight_recorder_is_frozen(const ap_flight_recorder_t*r){return r?r->frozen:0;}

size_t ap_flight_recorder_export_size(const ap_flight_recorder_t*r){
    if(!r)return 0u;return sizeof(ap_dump_file_header_t)+(size_t)r->count*r->slot_stride;
}

ap_status_t ap_flight_recorder_export(const ap_flight_recorder_t*r,void*dst,size_t dst_size,size_t*written){
    ap_dump_file_header_t h;
    unsigned char*out=(unsigned char*)dst;
    uint32_t i,oldest;
    size_t need;
    const ap_build_info_t*b;
    if(!r||!dst||!written)return AP_EINVAL;*written=0u;
    need=ap_flight_recorder_export_size(r);if(dst_size<need)return AP_ENOMEM;
    memset(&h,0,sizeof(h));h.magic=AP_DUMP_MAGIC;h.format_version=AP_DUMP_FORMAT_VERSION;
    h.header_size=sizeof(h);h.endian_tag=AP_DUMP_ENDIAN_TAG;
    h.io_sample_rate_hz=r->cfg.io_sample_rate_hz;h.mic_channels=r->cfg.mic_channels;
    h.frame_samples=r->cfg.frame_samples;h.record_mask=r->cfg.record_mask;
    h.record_stride=r->slot_stride;h.frame_count=r->count;h.trigger_event=r->trigger_event;
    b=ap_build_info();if(b){h.module_mask=b->module_mask;copy_text(h.version,sizeof(h.version),b->version);
        copy_text(h.aec_backend,sizeof(h.aec_backend),b->aec_backend);
        copy_text(h.ns_estimator,sizeof(h.ns_estimator),b->ns_estimator);
        copy_text(h.simd_backend,sizeof(h.simd_backend),b->simd_backend);
        copy_text(h.resampler_mode,sizeof(h.resampler_mode),b->resampler_mode);}
    memcpy(out,&h,sizeof(h));out+=sizeof(h);
    oldest=(r->head+r->capacity-r->count)%r->capacity;
    for(i=0u;i<r->count;++i){uint32_t idx=(oldest+i)%r->capacity;
        memcpy(out,r->slots+(size_t)idx*r->slot_stride,r->slot_stride);out+=r->slot_stride;}
    *written=need;return AP_OK;
}

int ap_runtime_bind_current_thread(int cpu,int fifo){
    int rc=0;
    if(cpu>=0){
        cpu_set_t set;if(cpu>=CPU_SETSIZE)return-1;CPU_ZERO(&set);CPU_SET(cpu,&set);
        if(pthread_setaffinity_np(pthread_self(),sizeof(set),&set)!=0)rc=-1;
    }
    if(fifo>0){
        struct sched_param sp;memset(&sp,0,sizeof(sp));sp.sched_priority=fifo>99?99:fifo;
        if(pthread_setschedparam(pthread_self(),SCHED_FIFO,&sp)!=0)rc=-1;
    }
    return rc;
}

ap_runtime_config_t ap_runtime_config_default(void){
    ap_runtime_config_t c;c.dsp_cpu=-1;c.dsp_priority=0;c.overload_us=9000u;c.recover_frames=1000u;return c;
}

ap_runtime_options_t ap_runtime_options_default(void){
    ap_runtime_options_t o;memset(&o,0,sizeof(o));o.struct_size=sizeof(o);
    o.api_version=AP_RUNTIME_CONTROL_API_VERSION;o.set_thread_name=1u;
    copy_text(o.thread_name,sizeof(o.thread_name),"ap-dsp");return o;
}

size_t ap_runtime_state_size(void){return sizeof(ap_runtime_t);}
size_t ap_runtime_state_alignment(void){return AP_RUNTIME_STATE_ALIGNMENT;}

static void init_runtime_atomics(ap_runtime_t*r){
    uint32_t i;
    atomic_init(&r->running,0u);atomic_init(&r->in_head,0u);atomic_init(&r->in_tail,0u);
    atomic_init(&r->out_head,0u);atomic_init(&r->out_tail,0u);
    atomic_init(&r->command_head,0u);atomic_init(&r->command_tail,0u);
    atomic_init(&r->event_head,0u);atomic_init(&r->event_tail,0u);
    atomic_init(&r->pending_input_full,0u);
    counter64_init(&r->submitted_frames);counter64_init(&r->processed_frames);
    counter64_init(&r->input_full_events);counter64_init(&r->output_drop_events);
    counter64_init(&r->dsp_overruns);counter64_init(&r->command_full_events);
    counter64_init(&r->event_drop_events);counter64_init(&r->stream_discontinuities);
    counter64_init(&r->capture_gap_frames);counter64_init(&r->render_gap_frames);
    counter64_init(&r->timestamp_frames);counter64_init(&r->scheduler_bind_failures);
    counter64_init(&r->memory_lock_failures);
    atomic_init(&r->input_queue_high_water,0u);atomic_init(&r->output_queue_high_water,0u);
    atomic_init(&r->last_dsp_us,0u);atomic_init(&r->max_dsp_us,0u);
    atomic_init(&r->quality,(unsigned)AP_QUALITY_FULL);
    for(i=0u;i<AP_RUNTIME_LATENCY_BUCKETS;++i)atomic_init(&r->latency_hist[i],0u);
    atomic_init(&r->actual_cpu,-1);atomic_init(&r->actual_policy,SCHED_OTHER);atomic_init(&r->actual_priority,0);
}

ap_status_t ap_runtime_init_ex(void*memory,size_t memory_size,ap_pipeline_t*pipeline,
                               const ap_runtime_config_t*c,const ap_runtime_options_t*o,
                               ap_runtime_t**out){
    ap_runtime_t*r;
    if(!memory||!pipeline||!c||!o||!out)return AP_EINVAL;*out=NULL;
    if(memory_size<sizeof(ap_runtime_t))return AP_ENOMEM;
    if(((uintptr_t)memory&(AP_RUNTIME_STATE_ALIGNMENT-1u))!=0u)return AP_EINVAL;
    if(c->recover_frames==0u)return AP_EINVAL;
    if(c->dsp_cpu>=CPU_SETSIZE)return AP_EINVAL;
    if(c->dsp_priority<0||c->dsp_priority>99)return AP_EINVAL;
    if(o->struct_size<sizeof(*o)||o->api_version!=AP_RUNTIME_CONTROL_API_VERSION)return AP_EINVAL;
    r=(ap_runtime_t*)memory;memset(r,0,sizeof(*r));r->pipeline=pipeline;r->cfg=*c;r->options=*o;
    r->io_frames=(uint32_t)ap_pipeline_frame_samples(pipeline);r->mic_channels=ap_pipeline_mic_channels(pipeline);
    r->uses_render=(uint8_t)((ap_pipeline_stages(pipeline)&AP_STAGE_SYNC)!=0u);
    if(!r->io_frames||r->io_frames>AP_BUILD_IO_FRAME_MAX||!r->mic_channels||
       r->mic_channels>AP_BUILD_MAX_MIC_CHANNELS)return AP_EINVAL;
    if(sem_init(&r->wake,0,0)!=0)return AP_ESTATE;init_runtime_atomics(r);*out=r;return AP_OK;
}

ap_status_t ap_runtime_init(void*memory,size_t memory_size,ap_pipeline_t*pipeline,
                            const ap_runtime_config_t*c,ap_runtime_t**out){
    ap_runtime_options_t o=ap_runtime_options_default();
    return ap_runtime_init_ex(memory,memory_size,pipeline,c,&o,out);
}

static void runtime_emit_event(ap_runtime_t*r,ap_event_kind_t kind,ap_event_severity_t severity,
                               int32_t arg0,int32_t arg1,uint32_t count){
    unsigned head=atomic_load_explicit(&r->event_head,memory_order_relaxed);
    unsigned tail=atomic_load_explicit(&r->event_tail,memory_order_acquire);
    ap_event_t*e;
    if(head-tail>=AP_RUNTIME_EVENT_QUEUE_DEPTH){counter64_add(&r->event_drop_events,1u);return;}
    e=&r->events[head&AP_RT_EVENT_MASK];memset(e,0,sizeof(*e));e->struct_size=sizeof(*e);
    e->api_version=AP_DIAG_API_VERSION;e->frame_sequence=r->worker_sequence;e->timestamp_ns=now_ns();
    e->kind=(uint32_t)kind;e->severity=(uint8_t)severity;e->arg0=arg0;e->arg1=arg1;e->count=count;
    atomic_store_explicit(&r->event_head,head+1u,memory_order_release);
    if(r->recorder)(void)ap_flight_recorder_trigger(r->recorder,kind,severity);
}

static uint32_t latency_bucket(uint32_t us){
    static const uint32_t limits[AP_RUNTIME_LATENCY_BUCKETS-1u]={250u,500u,1000u,1500u,2000u,3000u,4000u,5000u,6000u,7000u,9000u};
    uint32_t i;for(i=0u;i<AP_RUNTIME_LATENCY_BUCKETS-1u;++i)if(us<=limits[i])return i;
    return AP_RUNTIME_LATENCY_BUCKETS-1u;
}

static uint32_t latency_bucket_upper(uint32_t bucket){
    static const uint32_t limits[AP_RUNTIME_LATENCY_BUCKETS]={250u,500u,1000u,1500u,2000u,3000u,4000u,5000u,6000u,7000u,9000u,UINT32_MAX};
    return limits[bucket<AP_RUNTIME_LATENCY_BUCKETS?bucket:AP_RUNTIME_LATENCY_BUCKETS-1u];
}

static void apply_quality_transition(ap_runtime_t*r,ap_quality_t next){
    ap_metrics_t m;ap_quality_t old;
    ap_pipeline_get_metrics(r->pipeline,&m);old=m.quality;if(old==next)return;
    if(ap_pipeline_set_quality(r->pipeline,next)!=AP_OK)return;
    atomic_store_explicit(&r->quality,(unsigned)next,memory_order_release);
    if(old==AP_QUALITY_FULL&&next==AP_QUALITY_LITE)
        runtime_emit_event(r,AP_EVENT_QUALITY_FULL_TO_LITE,AP_EVENT_WARN,(int32_t)old,(int32_t)next,1u);
    else if(old==AP_QUALITY_LITE&&next==AP_QUALITY_SAFE)
        runtime_emit_event(r,AP_EVENT_QUALITY_LITE_TO_SAFE,AP_EVENT_ERROR,(int32_t)old,(int32_t)next,1u);
    else runtime_emit_event(r,AP_EVENT_QUALITY_RECOVERED,AP_EVENT_INFO,(int32_t)old,(int32_t)next,1u);
}

static void adjust_quality(ap_runtime_t*r,uint64_t elapsed_ns){
    uint64_t limit=(uint64_t)r->cfg.overload_us*1000ull;ap_metrics_t m;
    ap_pipeline_get_metrics(r->pipeline,&m);
    if(elapsed_ns>limit){
        r->healthy_streak=0u;counter64_add(&r->dsp_overruns,1u);
        runtime_emit_event(r,AP_EVENT_DSP_DEADLINE_MISS,AP_EVENT_ERROR,(int32_t)(elapsed_ns/1000ull),
                           (int32_t)r->cfg.overload_us,1u);
        if(++r->overload_streak>=3u){
            if(m.quality==AP_QUALITY_FULL)apply_quality_transition(r,AP_QUALITY_LITE);
            else if(m.quality==AP_QUALITY_LITE)apply_quality_transition(r,AP_QUALITY_SAFE);
            r->overload_streak=0u;
        }
    }else{
        r->overload_streak=0u;
        if(++r->healthy_streak>=r->cfg.recover_frames){
            if(m.quality==AP_QUALITY_SAFE)apply_quality_transition(r,AP_QUALITY_LITE);
            else if(m.quality==AP_QUALITY_LITE)apply_quality_transition(r,AP_QUALITY_FULL);
            r->healthy_streak=0u;
        }
    }
}

static void runtime_note_discontinuity(ap_runtime_t*r,ap_discontinuity_flags_t flags,uint32_t lost){
    if(ap_pipeline_notify_stream_discontinuity(r->pipeline,flags,lost)==AP_OK){
        counter64_add(&r->stream_discontinuities,1u);
        if(flags&AP_DISCONTINUITY_CAPTURE_GAP)counter64_add(&r->capture_gap_frames,lost?lost:1u);
        if(flags&AP_DISCONTINUITY_RENDER_GAP)counter64_add(&r->render_gap_frames,lost?lost:1u);
        runtime_emit_event(r,AP_EVENT_STREAM_DISCONTINUITY,AP_EVENT_WARN,(int32_t)flags,(int32_t)lost,1u);
    }
}

static void runtime_apply_command(ap_runtime_t*r,const ap_runtime_command_t*c){
    ap_metrics_t m;
    if(c->struct_size<sizeof(*c)||c->api_version!=AP_RUNTIME_CONTROL_API_VERSION)return;
    switch((ap_runtime_command_kind_t)c->kind){
    case AP_RUNTIME_COMMAND_ECHO_PATH_CHANGE:
        if(ap_pipeline_notify_echo_path_change(r->pipeline)==AP_OK)
            runtime_emit_event(r,AP_EVENT_ECHO_PATH_CHANGE,AP_EVENT_WARN,0,0,1u);
        break;
    case AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY:
        runtime_note_discontinuity(r,c->data.discontinuity.flags,c->data.discontinuity.lost_frames);
        break;
    case AP_RUNTIME_COMMAND_RESET:
        ap_pipeline_reset(r->pipeline);runtime_emit_event(r,AP_EVENT_AEC_RESET,AP_EVENT_WARN,0,0,1u);break;
    case AP_RUNTIME_COMMAND_SET_QUALITY:
        apply_quality_transition(r,c->data.set_quality.quality);break;
    case AP_RUNTIME_COMMAND_SET_TUNING:
        (void)ap_pipeline_apply_tuning(r->pipeline,&c->data.tuning);break;
    default:break;
    }
    ap_pipeline_get_metrics(r->pipeline,&m);atomic_store_explicit(&r->quality,(unsigned)m.quality,memory_order_release);
}

static void runtime_drain_commands(ap_runtime_t*r){
    for(;;){
        unsigned tail=atomic_load_explicit(&r->command_tail,memory_order_relaxed);
        unsigned head=atomic_load_explicit(&r->command_head,memory_order_acquire);
        if(tail==head)break;runtime_apply_command(r,&r->commands[tail&AP_RT_COMMAND_MASK]);
        atomic_store_explicit(&r->command_tail,tail+1u,memory_order_release);
    }
}

static void runtime_apply_metadata(ap_runtime_t*r,const ap_rt_input_t*in){
    const ap_frame_metadata_t*m=&in->metadata;ap_discontinuity_flags_t flags=0u;uint32_t lost=0u;
    if(!in->has_metadata)return;
    if(m->flags&AP_FRAME_CAPTURE_DISCONTINUITY){flags|=AP_DISCONTINUITY_CAPTURE_GAP;lost=m->lost_capture_frames;}
    if(m->flags&AP_FRAME_RENDER_DISCONTINUITY){flags|=AP_DISCONTINUITY_RENDER_GAP;
        if(m->lost_render_frames>lost)lost=m->lost_render_frames;}
    if(m->flags&AP_FRAME_CLOCK_RESET)flags|=AP_DISCONTINUITY_CLOCK_RESET;
    if(m->flags&AP_FRAME_XRUN)flags|=AP_DISCONTINUITY_XRUN;
    if(m->flags&AP_FRAME_CODEC_REOPEN)flags|=AP_DISCONTINUITY_CODEC_REOPEN;
    if(flags)runtime_note_discontinuity(r,flags,lost);
    if((m->flags&(AP_FRAME_CAPTURE_TIMESTAMP_VALID|AP_FRAME_RENDER_TIMESTAMP_VALID))==
       (AP_FRAME_CAPTURE_TIMESTAMP_VALID|AP_FRAME_RENDER_TIMESTAMP_VALID)){
        if(ap_pipeline_observe_io_timestamps(r->pipeline,m->capture_timestamp_ns,m->render_timestamp_ns)==AP_OK)
            counter64_add(&r->timestamp_frames,1u);
    }
}

static void runtime_note_pipeline_events(ap_runtime_t*r,const ap_metrics_t*m){
    if(m->render_underruns>r->last_render_underruns){
        runtime_emit_event(r,AP_EVENT_RENDER_UNDERRUN,AP_EVENT_WARN,0,0,
                           (uint32_t)(m->render_underruns-r->last_render_underruns));
        r->last_render_underruns=m->render_underruns;
    }
    if(m->delay_jumps>r->last_delay_jumps){
        runtime_emit_event(r,AP_EVENT_DELAY_JUMP,AP_EVENT_WARN,m->delay_error_samples,
                           (int32_t)m->estimated_delay_ms,
                           (uint32_t)(m->delay_jumps-r->last_delay_jumps));
        r->last_delay_jumps=m->delay_jumps;
    }
    if(m->aec_resets>r->last_aec_resets){
        runtime_emit_event(r,AP_EVENT_AEC_RESET,AP_EVENT_WARN,0,0,
                           (uint32_t)(m->aec_resets-r->last_aec_resets));
        r->last_aec_resets=m->aec_resets;
    }
    if(m->aec_converged&&!r->last_aec_converged)
        runtime_emit_event(r,AP_EVENT_AEC_CONVERGED,AP_EVENT_INFO,(int32_t)m->aec_convergence_frames,0,1u);
    r->last_aec_converged=m->aec_converged;
    if(m->erle_valid){
        if(r->last_valid_erle>8.0f&&m->erle_db+6.0f<r->last_valid_erle)
            runtime_emit_event(r,AP_EVENT_ERLE_COLLAPSE,AP_EVENT_WARN,(int32_t)r->last_valid_erle,(int32_t)m->erle_db,1u);
        r->last_valid_erle=m->erle_db;
    }
}

static void runtime_record_frame(ap_runtime_t*r,const ap_rt_input_t*in,const int16_t*out,const ap_metrics_t*m){
    ap_diag_frame_t f;if(!r->recorder)return;memset(&f,0,sizeof(f));f.struct_size=sizeof(f);
    f.api_version=AP_DIAG_API_VERSION;f.frame_sequence=r->worker_sequence;f.mic_interleaved=in->mic;
#if AP_HAVE_MODULE_SYNC
    f.render=in->has_render?in->render:NULL;
#else
    f.render=NULL;
#endif
    f.output=out;f.metrics=m;
    if(in->has_metadata){f.capture_timestamp_ns=in->metadata.capture_timestamp_ns;
        f.render_timestamp_ns=in->metadata.render_timestamp_ns;f.metadata_flags=in->metadata.flags;}
    (void)ap_flight_recorder_record(r->recorder,&f);
}

static int wait_work(ap_runtime_t*r){int rc;do{rc=sem_wait(&r->wake);}while(rc!=0&&errno==EINTR);return rc;}

static void runtime_setup_thread(ap_runtime_t*r){
    int policy=SCHED_OTHER;struct sched_param sp;memset(&sp,0,sizeof(sp));
    if(r->options.set_thread_name&&r->options.thread_name[0])
        (void)pthread_setname_np(pthread_self(),r->options.thread_name);
    if(r->cfg.dsp_cpu>=0){
        cpu_set_t set;int rc;CPU_ZERO(&set);CPU_SET(r->cfg.dsp_cpu,&set);
        rc=pthread_setaffinity_np(pthread_self(),sizeof(set),&set);
        if(rc!=0){counter64_add(&r->scheduler_bind_failures,1u);
            runtime_emit_event(r,AP_EVENT_RT_AFFINITY_FAILED,AP_EVENT_WARN,r->cfg.dsp_cpu,rc,1u);}
    }
    if(r->cfg.dsp_priority>0){
        sp.sched_priority=r->cfg.dsp_priority;
        if(pthread_setschedparam(pthread_self(),SCHED_FIFO,&sp)!=0){
            counter64_add(&r->scheduler_bind_failures,1u);
            runtime_emit_event(r,AP_EVENT_RT_PRIORITY_FAILED,AP_EVENT_WARN,r->cfg.dsp_priority,errno,1u);}
    }
    if(r->options.lock_memory&&mlockall(MCL_CURRENT|MCL_FUTURE)!=0){
        counter64_add(&r->memory_lock_failures,1u);
        runtime_emit_event(r,AP_EVENT_RT_MLOCK_FAILED,AP_EVENT_WARN,errno,0,1u);
    }
    atomic_store_explicit(&r->actual_cpu,sched_getcpu(),memory_order_release);
    if(pthread_getschedparam(pthread_self(),&policy,&sp)==0){
        atomic_store_explicit(&r->actual_policy,policy,memory_order_release);
        atomic_store_explicit(&r->actual_priority,sp.sched_priority,memory_order_release);
    }
}

static void*worker(void*arg){
    ap_runtime_t*r=(ap_runtime_t*)arg;runtime_setup_thread(r);
    runtime_emit_event(r,AP_EVENT_RUNTIME_STARTED,AP_EVENT_INFO,0,0,1u);
    for(;;){
        unsigned tail,head;
        if(wait_work(r)!=0)continue;
        if(!atomic_load_explicit(&r->running,memory_order_acquire))break;
        runtime_drain_commands(r);
        {
            unsigned pending=atomic_exchange_explicit(&r->pending_input_full,0u,memory_order_acq_rel);
            if(pending)runtime_emit_event(r,AP_EVENT_INPUT_QUEUE_FULL,AP_EVENT_WARN,0,0,pending);
        }
        tail=atomic_load_explicit(&r->in_tail,memory_order_relaxed);
        head=atomic_load_explicit(&r->in_head,memory_order_acquire);
        if(tail==head)continue;
        {
            ap_rt_input_t*in=&r->in[tail&AP_RT_MASK];
            unsigned oh=atomic_load_explicit(&r->out_head,memory_order_relaxed);
            unsigned ot=atomic_load_explicit(&r->out_tail,memory_order_acquire);
            int publish=(oh-ot<AP_RT_DEPTH);
            ap_rt_output_t*slot=publish?&r->out[oh&AP_RT_MASK]:NULL;
            int16_t*audio=publish?slot->audio:r->discard_audio;
            ap_metrics_t metrics;
            uint64_t t0,t1;uint32_t us;
            r->worker_sequence=in->has_metadata&&in->metadata.stream_sequence?
                               in->metadata.stream_sequence:r->worker_sequence+1u;
            runtime_apply_metadata(r,in);
            t0=now_ns();
#if AP_HAVE_MODULE_SYNC
            if(r->uses_render){
                if(!in->has_render)runtime_emit_event(r,AP_EVENT_RENDER_MISSING,AP_EVENT_WARN,0,0,1u);
                if(ap_pipeline_push_render(r->pipeline,in->render,r->io_frames)!=AP_OK){
                    atomic_store_explicit(&r->in_tail,tail+1u,memory_order_release);continue;
                }
            }
#endif
            if(ap_pipeline_process_capture(r->pipeline,in->mic,r->io_frames,audio)!=AP_OK){
                atomic_store_explicit(&r->in_tail,tail+1u,memory_order_release);continue;
            }
            t1=now_ns();us=(uint32_t)((t1-t0+999ull)/1000ull);
            atomic_store_explicit(&r->last_dsp_us,us,memory_order_relaxed);update_max(&r->max_dsp_us,us);
            atomic_fetch_add_explicit(&r->latency_hist[latency_bucket(us)],1u,memory_order_relaxed);
            adjust_quality(r,t1-t0);ap_pipeline_get_metrics(r->pipeline,&metrics);
            atomic_store_explicit(&r->quality,(unsigned)metrics.quality,memory_order_release);
            runtime_note_pipeline_events(r,&metrics);runtime_record_frame(r,in,audio,&metrics);
            counter64_add(&r->processed_frames,1u);
            if(publish){
                slot->metrics=metrics;atomic_store_explicit(&r->out_head,oh+1u,memory_order_release);
                update_max(&r->output_queue_high_water,oh+1u-ot);
            }else{
                counter64_add(&r->output_drop_events,1u);
                runtime_emit_event(r,AP_EVENT_OUTPUT_DROPPED,AP_EVENT_WARN,0,0,1u);
            }
            atomic_store_explicit(&r->in_tail,tail+1u,memory_order_release);
        }
    }
    runtime_emit_event(r,AP_EVENT_RUNTIME_STOPPED,AP_EVENT_INFO,0,0,1u);return NULL;
}

ap_status_t ap_runtime_start(ap_runtime_t*r){
    pthread_attr_t attr;int use_attr=0,rc;
    if(!r)return AP_EINVAL;if(atomic_exchange_explicit(&r->running,1u,memory_order_acq_rel))return AP_ESTATE;
    if(pthread_attr_init(&attr)==0){
        use_attr=1;
        if(r->options.dsp_stack_bytes&&pthread_attr_setstacksize(&attr,r->options.dsp_stack_bytes)!=0){
            pthread_attr_destroy(&attr);atomic_store(&r->running,0u);return AP_EINVAL;
        }
    }
    rc=pthread_create(&r->thread,use_attr?&attr:NULL,worker,r);if(use_attr)pthread_attr_destroy(&attr);
    if(rc!=0){atomic_store(&r->running,0u);return AP_ESTATE;}return AP_OK;
}

void ap_runtime_stop(ap_runtime_t*r){
    if(!r)return;if(atomic_exchange_explicit(&r->running,0u,memory_order_acq_rel)){
        (void)sem_post(&r->wake);(void)pthread_join(r->thread,NULL);}
}

void ap_runtime_deinit(ap_runtime_t*r){if(!r)return;ap_runtime_stop(r);(void)sem_destroy(&r->wake);}

ap_status_t ap_runtime_submit_ex(ap_runtime_t*r,const int16_t*mic,const int16_t*render,
                                 const ap_frame_metadata_t*m){
    unsigned head,tail;ap_rt_input_t*dst;size_t mic_samples;
    if(!r||!mic)return AP_EINVAL;
    if(m&&(m->struct_size<sizeof(*m)||m->api_version!=AP_RUNTIME_CONTROL_API_VERSION))return AP_EINVAL;
    head=atomic_load_explicit(&r->in_head,memory_order_relaxed);
    tail=atomic_load_explicit(&r->in_tail,memory_order_acquire);
    if(head-tail>=AP_RT_DEPTH){
        counter64_add(&r->input_full_events,1u);atomic_fetch_add_explicit(&r->pending_input_full,1u,memory_order_relaxed);
        (void)sem_post(&r->wake);return AP_EFULL;
    }
    dst=&r->in[head&AP_RT_MASK];mic_samples=(size_t)r->io_frames*r->mic_channels;
    memcpy(dst->mic,mic,mic_samples*sizeof(int16_t));dst->has_metadata=(uint8_t)(m!=NULL);dst->has_render=(uint8_t)(render!=NULL);
    if(m)dst->metadata=*m;else memset(&dst->metadata,0,sizeof(dst->metadata));
#if AP_HAVE_MODULE_SYNC
    if(r->uses_render){if(render)memcpy(dst->render,render,(size_t)r->io_frames*sizeof(int16_t));
        else memset(dst->render,0,(size_t)r->io_frames*sizeof(int16_t));}
#else
    (void)render;
#endif
    atomic_store_explicit(&r->in_head,head+1u,memory_order_release);counter64_add(&r->submitted_frames,1u);
    update_max(&r->input_queue_high_water,head+1u-tail);(void)sem_post(&r->wake);return AP_OK;
}

ap_status_t ap_runtime_submit(ap_runtime_t*r,const int16_t*mic,const int16_t*render){
    return ap_runtime_submit_ex(r,mic,render,NULL);
}

ap_status_t ap_runtime_command(ap_runtime_t*r,const ap_runtime_command_t*c){
    unsigned head,tail;
    if(!r||!c||c->struct_size<sizeof(*c)||c->api_version!=AP_RUNTIME_CONTROL_API_VERSION)return AP_EINVAL;
    head=atomic_load_explicit(&r->command_head,memory_order_relaxed);
    tail=atomic_load_explicit(&r->command_tail,memory_order_acquire);
    if(head-tail>=AP_RUNTIME_COMMAND_QUEUE_DEPTH){counter64_add(&r->command_full_events,1u);return AP_EFULL;}
    r->commands[head&AP_RT_COMMAND_MASK]=*c;atomic_store_explicit(&r->command_head,head+1u,memory_order_release);
    (void)sem_post(&r->wake);return AP_OK;
}

ap_status_t ap_runtime_receive(ap_runtime_t*r,int16_t*output,ap_metrics_t*metrics){
    unsigned head,tail;ap_rt_output_t*src;if(!r||!output)return AP_EINVAL;
    tail=atomic_load_explicit(&r->out_tail,memory_order_relaxed);head=atomic_load_explicit(&r->out_head,memory_order_acquire);
    if(tail==head)return AP_EEMPTY;src=&r->out[tail&AP_RT_MASK];
    memcpy(output,src->audio,(size_t)r->io_frames*sizeof(int16_t));if(metrics)*metrics=src->metrics;
    atomic_store_explicit(&r->out_tail,tail+1u,memory_order_release);return AP_OK;
}

ap_status_t ap_runtime_receive_event(ap_runtime_t*r,ap_event_t*event){
    unsigned head,tail;if(!r||!event)return AP_EINVAL;
    tail=atomic_load_explicit(&r->event_tail,memory_order_relaxed);head=atomic_load_explicit(&r->event_head,memory_order_acquire);
    if(tail==head)return AP_EEMPTY;*event=r->events[tail&AP_RT_EVENT_MASK];
    atomic_store_explicit(&r->event_tail,tail+1u,memory_order_release);return AP_OK;
}

ap_status_t ap_runtime_attach_flight_recorder(ap_runtime_t*r,ap_flight_recorder_t*recorder){
    if(!r)return AP_EINVAL;if(atomic_load_explicit(&r->running,memory_order_acquire))return AP_ESTATE;
    r->recorder=recorder;return AP_OK;
}

void ap_runtime_get_metrics(const ap_runtime_t*r,ap_runtime_metrics_t*m){
    if(!r||!m)return;m->submitted_frames=counter64_read(&r->submitted_frames);
    m->processed_frames=counter64_read(&r->processed_frames);m->input_full_events=counter64_read(&r->input_full_events);
    m->output_drop_events=counter64_read(&r->output_drop_events);m->dsp_overruns=counter64_read(&r->dsp_overruns);
    m->last_dsp_us=atomic_load_explicit(&r->last_dsp_us,memory_order_relaxed);
    m->max_dsp_us=atomic_load_explicit(&r->max_dsp_us,memory_order_relaxed);
    m->quality=(ap_quality_t)atomic_load_explicit(&r->quality,memory_order_acquire);
}

static uint32_t percentile_us(const ap_runtime_t*r,uint32_t numerator,uint32_t denominator){
    uint64_t total=0u,target,cumulative=0u;uint32_t i;
    for(i=0u;i<AP_RUNTIME_LATENCY_BUCKETS;++i)total+=atomic_load_explicit(&r->latency_hist[i],memory_order_relaxed);
    if(!total)return 0u;target=(total*numerator+denominator-1u)/denominator;
    for(i=0u;i<AP_RUNTIME_LATENCY_BUCKETS;++i){cumulative+=atomic_load_explicit(&r->latency_hist[i],memory_order_relaxed);
        if(cumulative>=target)return latency_bucket_upper(i);}return UINT32_MAX;
}

ap_status_t ap_runtime_get_metrics_v2(const ap_runtime_t*r,ap_runtime_metrics_v2_t*m){
    if(!r||!m||m->struct_size<sizeof(*m)||m->api_version!=AP_RUNTIME_CONTROL_API_VERSION)return AP_EINVAL;
    m->submitted_frames=counter64_read(&r->submitted_frames);m->processed_frames=counter64_read(&r->processed_frames);
    m->input_full_events=counter64_read(&r->input_full_events);m->output_drop_events=counter64_read(&r->output_drop_events);
    m->dsp_overruns=counter64_read(&r->dsp_overruns);m->command_full_events=counter64_read(&r->command_full_events);
    m->event_drop_events=counter64_read(&r->event_drop_events);m->stream_discontinuities=counter64_read(&r->stream_discontinuities);
    m->capture_gap_frames=counter64_read(&r->capture_gap_frames);m->render_gap_frames=counter64_read(&r->render_gap_frames);
    m->timestamp_frames=counter64_read(&r->timestamp_frames);m->scheduler_bind_failures=counter64_read(&r->scheduler_bind_failures);
    m->memory_lock_failures=counter64_read(&r->memory_lock_failures);
    m->input_queue_high_water=atomic_load_explicit(&r->input_queue_high_water,memory_order_relaxed);
    m->output_queue_high_water=atomic_load_explicit(&r->output_queue_high_water,memory_order_relaxed);
    m->last_dsp_us=atomic_load_explicit(&r->last_dsp_us,memory_order_relaxed);
    m->max_dsp_us=atomic_load_explicit(&r->max_dsp_us,memory_order_relaxed);
    m->p50_dsp_us=percentile_us(r,50u,100u);m->p95_dsp_us=percentile_us(r,95u,100u);m->p99_dsp_us=percentile_us(r,99u,100u);
    m->actual_cpu=atomic_load_explicit(&r->actual_cpu,memory_order_acquire);
    m->actual_policy=atomic_load_explicit(&r->actual_policy,memory_order_acquire);
    m->actual_priority=atomic_load_explicit(&r->actual_priority,memory_order_acquire);
    m->quality=(ap_quality_t)atomic_load_explicit(&r->quality,memory_order_acquire);return AP_OK;
}
