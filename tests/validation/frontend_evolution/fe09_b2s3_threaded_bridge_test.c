#define _POSIX_C_SOURCE 200809L
/* #762: real pthread, frozen S1/S2 and private transactional S3 bridge.
 * All source PCM here is synthetic. Any timing is HOSTED, never SSC305.
 */
#include "fe09_b2s3_private_bridge.h"
#include <inttypes.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define QUEUE_CAP 65536u
#define WORK_CAP 65536u
#define DIRECT_CAP 16384u
#define DIRECT_WORK_CAP 32768u
#define WINDOW 4u
#define LONG_FRAMES 100000u
#define SPIN_CAP 10000000u
#define FNV0 UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

typedef struct {
    const char *name;
    uint32_t mics, slots[4], circle;
} scene_t;
static const scene_t SCENES[4] = {
    {"C1_BASELINE",1u,{0u,0u,0u,0u},0u},
    {"C2_ULA",2u,{1u,0u,0u,0u},0u},
    {"C4_ULA",4u,{2u,0u,3u,1u},0u},
    {"C4_UCA",4u,{3u,2u,1u,0u},1u}
};
static const uint32_t RATES[3] = {16000u,32000u,48000u};

typedef struct {
    fe_b2s1_config config;
    fe_b2s1_queue *queue;
    fe_b1b1 *direct;
    fe_s2_writer recorder;
    fe_s3_bridge bridge;
    const scene_t *scene;
    uint32_t rate, render, depth, frames, with_record;
    atomic_uint acknowledged, capture_published, render_published, failed;
    uint64_t beam_hash, apx_hash, ns[100];
    uint32_t captured, accepted, full_retries, empty_retries;
    _Alignas(16) uint8_t qstate[QUEUE_CAP], work[WORK_CAP];
    _Alignas(16) uint8_t dstate[DIRECT_CAP], dwork[DIRECT_WORK_CAP];
    int16_t capture[WINDOW][1920], reference[WINDOW][480];
    uint8_t record[FE_S2_MAX_BYTES], shadow[FE_S2_MAX_BYTES];
    uint8_t snapshot[FE_S2_MAX_BYTES], q_snapshot[QUEUE_CAP];
} test_t;
static test_t T;

typedef struct {test_t *t; uint32_t render;} producer_arg;
typedef struct {test_t *t; uint32_t index;} replay_arg;

static void must(int cond, const char *text) {
    if (!cond) {
        fprintf(stderr, "FE09_B2S3_FAIL reason=%s\n", text);
        exit(1);
    }
}
static uint64_t hash(uint64_t base, const void *ptr, size_t n) {
    const uint8_t *p = (const uint8_t *)ptr;
    size_t i;
    for (i = 0u; i < n; ++i)
        base = (base ^ (uint64_t)p[i]) * FNV_PRIME;
    return base;
}
static uint64_t nano(void) {
    struct timespec ts;
    must(clock_gettime(CLOCK_MONOTONIC, &ts) == 0, "CLOCK_READ");
    return (uint64_t)ts.tv_sec*UINT64_C(1000000000) +
           (uint64_t)ts.tv_nsec;
}
static int16_t cap_pcm(uint32_t mic, uint32_t sample, uint32_t frame) {
    uint32_t x = (frame*337u + sample*73u + mic*1931u)&65535u;
    return (int16_t)((int32_t)x - 32768);
}
static int16_t ref_pcm(uint32_t sample, uint32_t frame) {
    uint32_t x = (frame*233u + sample*229u)&65535u;
    return (int16_t)((int32_t)x - 32768);
}
static void produce_pcm(const scene_t *sc, uint32_t rate, uint32_t frame,
                        int16_t *capture, int16_t *render) {
    uint32_t sample, mic, n = rate/100u;
    for (sample = 0u; sample < n; ++sample) {
        for (mic = 0u; mic < sc->mics; ++mic)
            if (capture)
                capture[(size_t)sample*sc->mics + sc->slots[mic]] =
                    cap_pcm(mic,sample,frame);
        if (render) render[sample] = ref_pcm(sample,frame);
    }
}
static fe_b2s1_config config_for(const scene_t *sc, uint32_t rate,
                                uint32_t render, uint32_t depth) {
    fe_b2s1_config c;
    static const double square[4][2] = {
        {0.03,0.00},{0.00,0.03},{-0.03,0.00},{0.00,-0.03}
    };
    uint32_t i;
    memset(&c,0,sizeof(c));
    c.depth = depth;
    c.pipeline.ingress.struct_size = (uint32_t)sizeof(c.pipeline.ingress);
    c.pipeline.ingress.api_version = FE_B1B0_VERSION;
    c.pipeline.ingress.capture_and_render_rate_hz = rate;
    c.pipeline.ingress.frame_ms = 10u;
    c.pipeline.ingress.physical_mics = sc->mics;
    c.pipeline.ingress.render_channels = render;
    c.pipeline.ingress.active_mic_mask = (1u<<sc->mics)-1u;
    c.pipeline.array.sample_rate_hz = 16000u;
    c.pipeline.array.mic_count = sc->mics;
    c.pipeline.array.reference_mic = 0u;
    c.pipeline.array.active_mask = c.pipeline.ingress.active_mic_mask;
    c.pipeline.array.interpolation = FE_ARRAY_FIR33_HANN;
    c.pipeline.array.direction[0] = 1.0;
    for (i=0u;i<sc->mics;++i) {
        c.pipeline.ingress.physical_to_capture_slot[i] = sc->slots[i];
        c.pipeline.array.microphones[i].input_channel = i;
        c.pipeline.array.microphones[i].gain = 1.0;
        if (sc->circle) {
            c.pipeline.array.microphones[i].position_m[0] = square[i][0];
            c.pipeline.array.microphones[i].position_m[1] = square[i][1];
        } else {
            c.pipeline.array.microphones[i].position_m[0] = 0.035*(double)i;
        }
    }
    return c;
}
static fe_s2_config record_config(const test_t *t) {
    fe_s2_config c;
    uint32_t i;
    memset(&c,0,sizeof(c));
    c.rate_hz = t->rate;
    c.physical_mics = t->scene->mics;
    c.render_channels = t->render;
    c.capture_source_id = 120u+t->scene->mics;
    c.render_source_id = t->render ? 220u+t->scene->mics : 0u;
    c.capture_epoch=1u;
    c.render_epoch=t->render ? 1u : 0u;
    for(i=0u;i<4u;++i)
        c.physical_to_capture_slot[i] =
            i<t->scene->mics ? t->scene->slots[i] : UINT32_MAX;
    return c;
}
static uint32_t cap_flags(uint32_t k) {
    if(k==15u) return FE_B1B0_CAPTURE_GAP;
    if(k==60u) return FE_B1B0_CLOCK_RESET;
    if(k==80u) return FE_B2S1_XRUN;
    return 0u;
}
static uint32_t render_flags(uint32_t k) {
    if(k==25u) return FE_B1B0_RENDER_GAP;
    if(k==60u) return FE_B1B0_CLOCK_RESET;
    if(k==81u) return FE_B2S1_XRUN;
    return 0u;
}
static uint32_t cap_epoch(uint32_t k) {
    return 1u + (uint32_t)(k>=15u) + (uint32_t)(k>=60u) +
           (uint32_t)(k>=80u);
}
static uint32_t ref_epoch(uint32_t k, uint32_t enabled) {
    return enabled ? 1u + (uint32_t)(k>=25u) +
           (uint32_t)(k>=60u) + (uint32_t)(k>=81u) : 0u;
}
static int spin_until(test_t *t, const atomic_uint *value, uint32_t k) {
    uint32_t n;
    for(n=0u;n<SPIN_CAP;++n) {
        if(atomic_load_explicit(&t->failed,memory_order_acquire))
            return 0;
        if(atomic_load_explicit(value,memory_order_acquire)>=k) return 1;
        sched_yield(); /* synthetic harness only, never S1/S2 frame path */
    }
    atomic_store_explicit(&t->failed,1u,memory_order_release);
    return 0;
}
static void *producer(void *payload) {
    producer_arg *a=(producer_arg *)payload;
    test_t *t=a->t;
    uint32_t k,n=t->rate/100u;
    for(k=1u;k<=t->frames;++k) {
        int16_t *slot;
        uint32_t attempts,result=0u;
        const uint32_t idx=(k-1u)%t->depth;
        /* The worker releases mirror ownership only AFTER APX3 commit.
         * This prevents both overwrite and cross-thread data races.
         */
        for(attempts=0u;attempts<SPIN_CAP;++attempts) {
            uint32_t done=atomic_load_explicit(&t->acknowledged,memory_order_acquire);
            if(atomic_load_explicit(&t->failed,memory_order_acquire)) return NULL;
            if(k<=done+t->depth) break;
            sched_yield();
        }
        if(attempts==SPIN_CAP) {
            atomic_store_explicit(&t->failed,2u,memory_order_release);
            return NULL;
        }
        if(a->render) {
            slot=t->reference[idx];
            produce_pcm(t->scene,t->rate,k,NULL,slot);
        } else {
            slot=t->capture[idx];
            produce_pcm(t->scene,t->rate,k,slot,NULL);
        }
        for(attempts=0u;attempts<SPIN_CAP;++attempts) {
            fe_b2s1_status st=a->render ?
                fe_b2s1_submit_render(t->queue,k,render_flags(k),
                                      slot,(size_t)n) :
                fe_b2s1_submit_capture(t->queue,k,cap_flags(k),
                                       slot,(size_t)n*t->scene->mics);
            if(st==FE_B2S1_OK){result=1u;break;}
            if(st!=FE_B2S1_EFULL) break;
            if(atomic_load_explicit(&t->failed,memory_order_acquire))
                return NULL;
            sched_yield();
        }
        if(!result) {
            atomic_store_explicit(&t->failed,3u,memory_order_release);
            return NULL;
        }
        atomic_store_explicit(a->render?&t->render_published:
                             &t->capture_published,k,memory_order_release);
    }
    return NULL;
}
static void build_frame(test_t *t,uint32_t k,fe_s2_frame *frame) {
    const uint32_t idx=(k-1u)%t->depth;
    memset(frame,0,sizeof(*frame));
    frame->sequence=k;
    frame->capture_flags=cap_flags(k);
    frame->render_flags=t->render?render_flags(k):0u;
    frame->capture_epoch=cap_epoch(k);
    frame->render_epoch=ref_epoch(k,t->render);
    frame->capture=t->capture[idx];
    frame->capture_count=(size_t)(t->rate/100u)*t->scene->mics;
    frame->render=t->render?t->reference[idx]:NULL;
    frame->render_count=(size_t)(t->rate/100u)*t->render;
}
static void *consumer(void *payload) {
    test_t *t=(test_t *)payload;
    uint32_t k;
    float beam[160],reference[160],direct_beam[160],direct_ref[160];
    for(k=1u;k<=t->frames;++k) {
        fe_s2_frame frame;
        fe_s3_status step=FE_S3_EEMPTY;
        fe_b1b1_status d;
        uint32_t gap,tries;
        uint64_t before=0u,after=0u;
        if(!spin_until(t,&t->capture_published,k) ||
           (t->render&&!spin_until(t,&t->render_published,k)))
            return NULL;
        build_frame(t,k,&frame);
        if(t->with_record) before=nano();
        for(tries=0u;tries<SPIN_CAP;++tries) {
            if(t->with_record) {
                step=fe_s3_bridge_step(&t->bridge,&frame,beam,160u,
                      t->render?reference:NULL,(size_t)160u*t->render,
                      t->work,fe_b2s1_work_bytes(&t->config));
            } else {
                fe_b2s1_status status=fe_b2s1_process_one(t->queue,
                      beam,160u,t->render?reference:NULL,
                      (size_t)160u*t->render,t->work,
                      fe_b2s1_work_bytes(&t->config));
                step=status==FE_B2S1_OK?FE_S3_OK:
                     status==FE_B2S1_EEMPTY?FE_S3_EEMPTY:FE_S3_ECORE;
            }
            if(step==FE_S3_OK) break;
            if(step!=FE_S3_EEMPTY) break;
            sched_yield();
        }
        if(step!=FE_S3_OK) {
            atomic_store_explicit(&t->failed,4u,memory_order_release);
            return NULL;
        }
        if(t->with_record) {
            after=nano();
            t->ns[k-1u]=after>=before?after-before:0u;
        }
        gap=0u;
        if(frame.capture_flags&(FE_B1B0_CAPTURE_GAP|FE_B2S1_XRUN))
            gap|=FE_B1B0_CAPTURE_GAP;
        if(frame.render_flags&(FE_B1B0_RENDER_GAP|FE_B2S1_XRUN))
            gap|=FE_B1B0_RENDER_GAP;
        if(frame.capture_flags&FE_B1B0_CLOCK_RESET)
            gap=FE_B1B0_CLOCK_RESET;
        if(gap&&fe_b1b1_notify_gap(t->direct,gap)!=FE_B1B1_OK) {
            atomic_store_explicit(&t->failed,5u,memory_order_release);
            return NULL;
        }
        d=fe_b1b1_process(t->direct,frame.capture,frame.capture_count,
                          frame.render,frame.render_count,
                          direct_beam,160u,t->render?direct_ref:NULL,
                          (size_t)160u*t->render,t->dwork,
                          fe_b1b1_work_bytes(&t->config.pipeline));
        if(d!=FE_B1B1_OK ||
           memcmp(beam,direct_beam,sizeof(beam))!=0 ||
           (t->render&&memcmp(reference,direct_ref,sizeof(reference))!=0)) {
            atomic_store_explicit(&t->failed,6u,memory_order_release);
            return NULL;
        }
        t->beam_hash=hash(t->beam_hash,beam,sizeof(beam));
        if(t->render) t->beam_hash=hash(t->beam_hash,reference,sizeof(reference));
        t->accepted=k;
        atomic_store_explicit(&t->acknowledged,k,memory_order_release);
    }
    return NULL;
}
static int visitor(const fe_s2_stream *s,uint32_t index,uint64_t seq,
    uint32_t cf,uint32_t rf,const uint8_t *cap,size_t cb,
    const uint8_t *ref,size_t rb,void *opaque) {
    test_t *t=(test_t *)opaque;
    const uint32_t k=index+1u;
    int16_t expected[1920],expected_ref[480];
    size_t i;
    if(!s||!t||seq!=k||s->config.rate_hz!=t->rate||
       s->config.physical_mics!=t->scene->mics||
       s->config.render_channels!=t->render||
       cf!=cap_flags(k)||rf!=(t->render?render_flags(k):0u)||
       cb!=(size_t)(t->rate/100u)*t->scene->mics*2u||
       rb!=(size_t)(t->rate/100u)*t->render*2u||
       !cap||(t->render&&!ref)||(!t->render&&ref)) return -1;
    produce_pcm(t->scene,t->rate,k,expected,
                t->render?expected_ref:NULL);
    for(i=0u;i<cb/2u;++i) {
        uint16_t bits=(uint16_t)((uint16_t)cap[2u*i]|
                                ((uint16_t)cap[2u*i+1u]<<8u));
        if(bits!=(uint16_t)expected[i]) return -1;
    }
    for(i=0u;i<rb/2u;++i) {
        uint16_t bits=(uint16_t)((uint16_t)ref[2u*i]|
                                ((uint16_t)ref[2u*i+1u]<<8u));
        if(bits!=(uint16_t)expected_ref[i]) return -1;
    }
    return 0;
}
static int cmp64(const void *aa,const void *bb) {
    const uint64_t a=*(const uint64_t *)aa,b=*(const uint64_t *)bb;
    return a<b?-1:a>b?1:0;
}
static void init(test_t *t,const scene_t *sc,uint32_t rate,
                 uint32_t render,uint32_t depth,uint32_t frames) {
    const size_t qs=fe_b2s1_state_bytes(&(fe_b2s1_config){0});
    size_t state_bytes,direct_bytes,work_bytes,dirwork;
    fe_s2_config rec;
    (void)qs;
    memset(t,0,sizeof(*t));
    t->scene=sc;t->rate=rate;t->render=render;t->depth=depth;
    t->frames=frames;t->with_record=(uint32_t)(frames<=100u);
    t->beam_hash=FNV0;
    t->config=config_for(sc,rate,render,depth);
    state_bytes=fe_b2s1_state_bytes(&t->config);
    work_bytes=fe_b2s1_work_bytes(&t->config);
    direct_bytes=fe_b1b1_state_bytes(&t->config.pipeline);
    dirwork=fe_b1b1_work_bytes(&t->config.pipeline);
    must(state_bytes&&state_bytes<=QUEUE_CAP&&work_bytes<=WORK_CAP&&
         direct_bytes&&direct_bytes<=DIRECT_CAP&&dirwork<=DIRECT_WORK_CAP,
         "BOUNDED_FIRST_PARTY_ARENAS");
    must(fe_b2s1_init(t->qstate,state_bytes,&t->config,&t->queue)==FE_B2S1_OK,
         "S1_INIT");
    must(fe_b1b1_init(t->dstate,direct_bytes,&t->config.pipeline,
                      &t->direct)==FE_B1B1_OK,"DIRECT_INIT");
    if(t->with_record) {
        rec=record_config(t);
        must(fe_s2_writer_begin(&t->recorder,t->record,sizeof(t->record),
                                &rec,frames)==FE_S2_OK,"S2_INIT");
        must(fe_s3_bridge_init(&t->bridge,t->queue,&t->recorder,
                               t->shadow,sizeof(t->shadow))==FE_S3_OK,
                               "S3_INIT");
    }
    atomic_init(&t->acknowledged,0u);
    atomic_init(&t->capture_published,0u);
    atomic_init(&t->render_published,0u);
    atomic_init(&t->failed,0u);
}
static uint64_t execute(test_t *t) {
    pthread_t cap_thread,ref_thread,worker_thread;
    producer_arg cap={t,0u},ref={t,1u};
    fe_b2s1_info info;
    fe_s2_stream stream,observed;
    size_t file_bytes=0u;
    must(pthread_create(&cap_thread,NULL,producer,&cap)==0,"CAP_THREAD");
    if(t->render)
        must(pthread_create(&ref_thread,NULL,producer,&ref)==0,"RENDER_THREAD");
    must(pthread_create(&worker_thread,NULL,consumer,t)==0,"WORKER_THREAD");
    must(pthread_join(cap_thread,NULL)==0,"CAP_JOIN");
    if(t->render) must(pthread_join(ref_thread,NULL)==0,"RENDER_JOIN");
    must(pthread_join(worker_thread,NULL)==0,"WORKER_JOIN");
    must(atomic_load_explicit(&t->failed,memory_order_acquire)==0u,
         "ACTUAL_THREADED_PIPELINE");
    must(t->accepted==t->frames,"INCOMPLETE_SPSC_FRAMES");
    must(fe_b2s1_get_info(t->queue,&info)==FE_B2S1_OK &&
         info.processed==t->frames &&
         info.capture_queued==0u && info.render_queued==0u &&
         info.capture_submitted==t->frames &&
         info.render_submitted==(uint64_t)t->frames*t->render,
         "SPSC_DRAINED_STATE");
    if(!t->with_record) return UINT64_C(0);
    must(fe_s3_bridge_finish(&t->bridge,&file_bytes)==FE_S3_OK &&
         file_bytes>FE_S2_HEADER_BYTES&&file_bytes<=FE_S2_MAX_BYTES,
         "S3_FINISH");
    must(fe_s2_decode(t->record,file_bytes,&stream)==FE_S2_OK &&
         stream.frames==t->frames,"APX3_STRICT_DECODE");
    must(fe_s2_replay(t->record,file_bytes,visitor,t,&observed)==FE_S2_OK &&
         observed.frames==t->frames,"APX3_EXACT_PCM_REPLAY");
    qsort(t->ns,100u,sizeof(t->ns[0]),cmp64);
    fprintf(stderr,
      "FE09_B2S3_HOSTED_ONLY_RATE_%u_MICS_%u_RENDER_%u_DEPTH_%u p95_ns=%" PRIu64 " p99_ns=%" PRIu64 " NOT_SSC305\n",
      t->rate,t->scene->mics,t->render,t->depth,t->ns[94],t->ns[98]);
    t->apx_hash=hash(FNV0,t->record,file_bytes);
    return t->apx_hash;
}
static unsigned negatives(test_t *t) {
    fe_s2_frame valid;
    fe_s2_writer before_writer;
    fe_b2s1_queue *q;
    fe_s2_config rec;
    uint32_t i;
    size_t total=0u;
    float beam[160],ref[160];
    unsigned count=0u;
    init(t,&SCENES[1],16000u,1u,2u,2u);
    rec=record_config(t);
    q=t->queue;
    produce_pcm(t->scene,t->rate,1u,t->capture[0],t->reference[0]);
    build_frame(t,1u,&valid);
    before_writer=t->recorder;
    memcpy(t->q_snapshot,t->qstate,fe_b2s1_state_bytes(&t->config));
    memcpy(t->snapshot,t->record,t->recorder.total_bytes);
    for(i=0u;i<96u;++i) {
        fe_s2_frame bad=valid;
        switch(i%8u) {
        case 0u: bad.sequence=0u;break;
        case 1u: bad.sequence=2u+i;break;
        case 2u: bad.capture_flags=16u+i*16u;break;
        case 3u: bad.render_flags=16u+i*16u;break;
        case 4u: bad.capture_count+=1u+(size_t)i;break;
        case 5u: bad.render_count+=1u+(size_t)i;break;
        case 6u: bad.capture_epoch+=1u+i;break;
        default: bad.render_epoch+=1u+i;break;
        }
        memset(beam,0xa5,sizeof(beam));
        memset(ref,0xa5,sizeof(ref));
        must(fe_s3_bridge_step(&t->bridge,&bad,beam,160u,ref,160u,
                 t->work,fe_b2s1_work_bytes(&t->config))==FE_S3_EINVAL,
                 "INVALID_FRAME_ADMITTED");
        must(memcmp(t->q_snapshot,t->qstate,
                    fe_b2s1_state_bytes(&t->config))==0 &&
             memcmp(t->snapshot,t->record,t->recorder.total_bytes)==0 &&
             memcmp(&before_writer,&t->recorder,sizeof(before_writer))==0,
             "BAD_FRAME_MODIFIED_ARENAS");
        ++count;
    }
    must(fe_s3_bridge_step(&t->bridge,&valid,beam,160u,ref,160u,
              t->work,fe_b2s1_work_bytes(&t->config))==FE_S3_EEMPTY,
              "EMPTY_QUEUE_NOT_FAIL_CLOSED");
    must(t->recorder.appended==0u,"EMPTY_COMMITTED_RECORD");
    ++count;
    must(fe_b2s1_submit_capture(q,1u,0u,t->capture[0],160u*2u)==FE_B2S1_OK,
         "MISMATCH_CAPTURE_SUBMIT");
    must(fe_b2s1_submit_render(q,2u,FE_B1B0_RENDER_GAP,
                               t->reference[0],160u)==FE_B2S1_OK,
         "MISMATCH_RENDER_SUBMIT");
    must(fe_s3_bridge_step(&t->bridge,&valid,beam,160u,ref,160u,
              t->work,fe_b2s1_work_bytes(&t->config))==FE_S3_EMISMATCH,
              "MISMATCH_INCORRECTLY_CONSUMED");
    must(t->recorder.appended==0u &&
         memcmp(t->snapshot,t->record,t->recorder.total_bytes)==0,
         "MISMATCH_COMMITTED_APX3");
    ++count;
    /* Full source-owner restart is allowed ONLY after producer quiescence.
     * A lost render frame is NOT magically replaced by silence; all BF
     * histories are discarded here, never advertised as seamless recovery.
     */
    must(fe_b2s1_init(t->qstate,fe_b2s1_state_bytes(&t->config),
                       &t->config,&q)==FE_B2S1_OK,"QUIESCENT_FULL_RESTART");
    t->queue=q;
    must(fe_s3_bridge_init(&t->bridge,q,&t->recorder,
                           t->shadow,sizeof(t->shadow))==FE_S3_OK,
                           "RESTART_BRIDGE");
    must(fe_b2s1_submit_capture(q,1u,0u,t->capture[0],320u)==FE_B2S1_OK &&
         fe_b2s1_submit_render(q,1u,0u,t->reference[0],160u)==FE_B2S1_OK,
         "RESTART_MATCHED_SOURCES");
    must(fe_s3_bridge_step(&t->bridge,&valid,beam,160u,ref,160u,
              t->work,fe_b2s1_work_bytes(&t->config))==FE_S3_OK &&
         t->recorder.appended==1u,"RESTART_RECORD_NOT_COMMITTED");
    must(fe_s3_bridge_finish(&t->bridge,&total)==FE_S3_EINVAL,
         "INCOMPLETE_APX3_INCORRECTLY_FINISHED");
    ++count;
    (void)rec;
    return count;
}
int main(int argc,char **argv) {
    uint32_t s,r,render,depth;
    uint64_t digest=FNV0,pre;
    unsigned profiles=0u,negative_cases=0u;
    if(argc==2&&strcmp(argv[1],"--long")==0) {
        init(&T,&SCENES[0],16000u,1u,4u,LONG_FRAMES);
        (void)execute(&T);
        must(T.accepted==LONG_FRAMES,"LONG_100K_NOT_QUALIFIED");
        printf("{\"schema_version\":1,\"decision\":\"S3_NATIVE_HOSTED_STRESS_ONLY_NOT_DEVICE\",\"accepted_frames\":%u,\"actual_threads\":3,\"real_clock_measured\":false}\n",T.accepted);
        return 0;
    }
    must(argc==1,"UNSUPPORTED_CLI");
    printf("{\"schema_version\":1,\"decision\":\"FE09_R2B2_S3_PRIVATE_THREADED_BRIDGE_RESEARCH_ONLY_NO_PUBLIC_ABI\",\"source_role\":\"first-party-synthetic\",\"physical_clock_qualified\":false,\"ssc305_dut_qualified\":false,\"public_sdk_installed\":false,\"actual_pthread_producers\":true,\"profiles\":[");
    for(s=0u;s<4u;++s)
        for(r=0u;r<3u;++r)
            for(render=0u;render<2u;++render)
                for(depth=2u;depth<=4u;depth+=2u) {
                    if(profiles) putchar(',');
                    init(&T,&SCENES[s],RATES[r],render,depth,100u);
                    pre=execute(&T);
                    digest^=pre;digest*=FNV_PRIME;
                    printf("{\"scene\":\"%s\",\"rate\":%u,\"mics\":%u,\"render\":%u,\"depth\":%u,\"frames\":%u,\"apx_hash\":\"%016" PRIx64 "\"}",
                           SCENES[s].name,RATES[r],SCENES[s].mics,render,
                           depth,T.accepted,pre);
                    ++profiles;
                }
    negative_cases=negatives(&T);
    printf("],\"profile_count\":%u,\"total_frames\":%u,\"negative_cases\":%u,\"source_only_digest\":\"%016" PRIx64 "\"}\n",
           profiles,profiles*100u,negative_cases,digest);
    must(profiles==48u&&negative_cases>=99u,
         "THREADED_CASE_COUNT_DRIFT");
    return 0;
}
