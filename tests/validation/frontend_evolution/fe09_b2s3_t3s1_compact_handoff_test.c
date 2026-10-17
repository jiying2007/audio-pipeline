/* #789: first-party noninstalled S2 + BF + source SPSC + compact APX3.
 * True separate pthread Capture, optional Render, worker, outboard owner.
 * First-party synthetic PCM only. No product, memory-fit or durable claims.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s1_compact_handoff.h"
#include <inttypes.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define STATE_CAP 16384u
#define WORK_CAP 32768u
#define FRAMES 6u
#define SPIN_CAP 3000000u

typedef struct { const char *name; uint32_t mics,slots[4],circle; } scene_t;
static const scene_t SCENES[4]={
    {"C1_BASELINE",1u,{0u,0u,0u,0u},0u},
    {"C2_ULA",2u,{1u,0u,0u,0u},0u},
    {"C4_ULA",4u,{2u,0u,3u,1u},0u},
    {"C4_UCA",4u,{3u,2u,1u,0u},1u}
};
static const uint32_t RATES[3]={16000u,32000u,48000u};
typedef struct {
    const scene_t *scene;
    uint32_t rate,render,slot_count,depth;
    fe_b1s0_state source;
    fe_t2b_b0 adapter;
    fe_t3s1_ring ring;
    fe_t3s1_slot *physical_storage;
    fe_b1b1 *bf,*oracle;
    _Alignas(16) uint8_t state[STATE_CAP],work[WORK_CAP];
    _Alignas(16) uint8_t oracle_state[STATE_CAP],oracle_work[WORK_CAP];
    atomic_uint failed,capture_done,render_done,worker_done,sink_done;
    size_t actually_outboard_bytes;
    uint32_t external_failure_attempts,sink_mode;
    uint64_t beam_hash;
} fixture;
static fixture P;
static uint32_t NEGATIVES,PROFILES;

static void must(int pass,const char *why) {
    if(!pass) { fprintf(stderr,"FE09_T3S1_NOT_ADMITTED reason=%s\n",why); exit(1); }
}
static void reject(int ok,const char *why) { must(ok,why); ++NEGATIVES; }
static uint64_t beam_digest(uint64_t h,const float *p,size_t count) {
    const uint8_t *b=(const uint8_t *)p;
    size_t i;
    for(i=0u;i<count*sizeof(float);++i)
        h=(h^(uint64_t)b[i])*UINT64_C(1099511628211);
    return h;
}
static void pcm_for(const scene_t *sc,uint32_t rate,uint32_t frame,
                    int16_t capture[1920],int16_t render[480]) {
    uint32_t t,i,n=rate/100u;
    for(t=0u;t<n;++t) {
        for(i=0u;i<sc->mics;++i) {
            uint32_t v=(frame*337u+t*73u+i*1931u)&65535u;
            capture[(size_t)t*sc->mics+sc->slots[i]]=
                (int16_t)((int32_t)v-32768);
        }
        render[t]=(int16_t)((int32_t)((frame*233u+t*229u)&65535u)-32768);
    }
}
static fe_b1b1_config config_for(const scene_t *sc,uint32_t rate) {
    static const double xy[4][2]={
        {0.03,0.0},{0.0,0.03},{-0.03,0.0},{0.0,-0.03}
    };
    fe_b1b1_config c;
    uint32_t i;
    memset(&c,0,sizeof(c));
    c.ingress.struct_size=(uint32_t)sizeof(c.ingress);
    c.ingress.api_version=FE_B1B0_VERSION;
    c.ingress.capture_and_render_rate_hz=rate;
    c.ingress.frame_ms=10u;
    c.ingress.physical_mics=sc->mics;
    c.ingress.render_channels=0u;
    c.ingress.active_mic_mask=(1u<<sc->mics)-1u;
    c.array.sample_rate_hz=16000u;
    c.array.mic_count=sc->mics;
    c.array.reference_mic=0u;
    c.array.active_mask=c.ingress.active_mic_mask;
    c.array.interpolation=FE_ARRAY_FIR33_HANN;
    c.array.direction[0]=1.0;
    for(i=0u;i<sc->mics;++i) {
        c.ingress.physical_to_capture_slot[i]=sc->slots[i];
        c.array.microphones[i].input_channel=i;
        c.array.microphones[i].gain=1.0;
        if(sc->circle) {
            c.array.microphones[i].position_m[0]=xy[i][0];
            c.array.microphones[i].position_m[1]=xy[i][1];
        } else c.array.microphones[i].position_m[0]=0.035*(double)i;
    }
    return c;
}
static uint32_t absent(uint32_t k) { return k==2u||k==3u; }
static uint32_t ref_epoch(uint32_t k) { return k<=3u?1u:2u; }

static int outboard(const uint8_t *apx3,size_t len,
                    const uint8_t *row,size_t rowlen,
                    void *ctx,size_t *accounted) {
    fixture *p=(fixture *)ctx;
    fe_s2_stream decoded;
    if(!p||!apx3||!row||!accounted||rowlen!=FE_T3S1_ROW_BYTES||
       !len||len>FE_T3S1_CHUNK_BYTES||
       fe_s2_decode(apx3,len,&decoded)!=FE_S2_OK||
       decoded.frames!=1u||decoded.total_bytes!=len) return -1;
    if(p->sink_mode) {
        ++p->external_failure_attempts;
        *accounted=p->sink_mode==1u?len/2u:len;
        return p->sink_mode==1u?-1:0;
    }
    p->actually_outboard_bytes+=len+rowlen;
    *accounted=len+rowlen;
    return 0;
}
static int torn_sink(const uint8_t *apx3,size_t len,
                     const uint8_t *row,size_t rowlen,
                     void *ctx,size_t *accounted) {
    fixture *p=(fixture *)ctx;
    if(!apx3||!row||!len||rowlen!=FE_T3S1_ROW_BYTES||
       !p||!accounted) return -1;
    ++p->external_failure_attempts;
    *accounted=len/2u;
    return -1; /* An interrupted external transfer cannot ACK. */
}
static int short_ack(const uint8_t *apx3,size_t len,
                     const uint8_t *row,size_t rowlen,
                     void *ctx,size_t *accounted) {
    fixture *p=(fixture *)ctx;
    if(!apx3||!row||!len||!rowlen||!p||!accounted) return -1;
    ++p->external_failure_attempts;
    *accounted=len; /* Omitted real 200B canonical sidecar. */
    return 0;
}
static void setup(const scene_t *sc,uint32_t rate,
                  uint32_t render,uint32_t slots) {
    fe_b1b1_config bc=config_for(sc,rate);
    fe_b1s0_config q;
    size_t state=fe_b1b1_state_bytes(&bc),work=fe_b1b1_work_bytes(&bc);
    uint32_t mapping[4],badmap[4],i;
    memset(&P,0,sizeof(P));
    P.scene=sc;P.rate=rate;P.render=render;P.slot_count=slots;
    P.depth=slots==1u?2u:4u;
    must(state>0u&&state<=STATE_CAP&&work>0u&&work<=WORK_CAP,
         "COMPILER_TRUE_ORIGINAL_BF_ARENA_BOUND");
    must(fe_b1b1_init(P.state,state,&bc,&P.bf)==FE_B1B1_OK &&
         fe_b1b1_init(P.oracle_state,state,&bc,&P.oracle)==FE_B1B1_OK &&
         P.bf&&P.oracle&&P.bf!=P.oracle,
         "ACTUAL_FIRST_PARTY_BF_AND_ORACLE_INIT");
    must(fe_t2b_b0_bind(&P.adapter,P.bf,rate,sc->mics)==FE_T2B_B0_OK,
         "ACTUAL_B0_CAPTURE_ONLY_BIND");
    memset(&q,0,sizeof(q));
    q.depth=P.depth;q.physical_mics=sc->mics;q.input_hz=rate;
    q.render_enabled=render;q.capture_source_id=101u+sc->mics;
    q.render_source_id=render?201u+sc->mics:0u;
    q.source_generation=UINT64_C(900001);
    must(fe_b1s0_init(&P.source,&q,&P.adapter)==FE_B1S0_OK,
         "ACTUAL_SOURCE_QUEUE_INIT");
    must(fe_b1s0_seed_wrap_before_start(&P.source,UINT32_MAX-2u)==
         FE_B1S0_OK,"ORIGINAL_SOURCE_UINT32_WRAP_INIT");
    for(i=0u;i<4u;++i) mapping[i]=i<sc->mics?sc->slots[i]:UINT32_MAX;
    memcpy(badmap,mapping,sizeof(badmap));
    badmap[0]=UINT32_MAX;
    P.physical_storage=(fe_t3s1_slot *)calloc(
                              (size_t)slots,sizeof(fe_t3s1_slot));
    must(P.physical_storage!=NULL,"EXACT_PHYSICAL_SLOT_ALLOCATION");
    reject(fe_t3s1_init(NULL,&P.source,mapping,P.physical_storage,
            slots*sizeof(fe_t3s1_slot),slots,outboard,&P)==FE_T3S1_REJECT,
           "NULL_RING_ACCEPTED");
    reject(fe_t3s1_init(&P.ring,&P.source,mapping,P.physical_storage,
            slots*sizeof(fe_t3s1_slot),0u,outboard,&P)==FE_T3S1_REJECT,
           "ZERO_SLOT_BANK_ACCEPTED");
    reject(fe_t3s1_init(&P.ring,&P.source,mapping,P.physical_storage,
            slots*sizeof(fe_t3s1_slot),3u,outboard,&P)==FE_T3S1_REJECT,
           "THREE_SLOT_BANK_ACCEPTED");
    reject(fe_t3s1_init(&P.ring,&P.source,mapping,P.physical_storage,
            slots*sizeof(fe_t3s1_slot)-1u,slots,outboard,&P)==FE_T3S1_REJECT,
           "SHORT_PHYSICAL_ALLOCATION_ACCEPTED");
    reject(fe_t3s1_init(&P.ring,&P.source,badmap,P.physical_storage,
            slots*sizeof(fe_t3s1_slot),slots,outboard,&P)==FE_T3S1_REJECT,
           "INVALID_CAPTURE_SLOT_BIJECTION_ACCEPTED");
    must(fe_t3s1_init(&P.ring,&P.source,mapping,P.physical_storage,
           slots*sizeof(fe_t3s1_slot),slots,outboard,&P)==FE_T3S1_OK,
         "PHYSICALLY_ALLOCATED_ONLY_ONE_TWO_SLOTS");
    must(fe_t3s1_seed_wrap_before_start(&P.ring,UINT32_MAX-2u)==
         FE_T3S1_OK,"REAL_COMPACT_COUNTER_WRAP_INIT");
    must(P.ring.slot_allocation_bytes==slots*sizeof(fe_t3s1_slot)&&
         P.ring.slot==P.physical_storage,"HIDDEN_SECOND_SLOT_BANK");
    atomic_init(&P.failed,0u);
    atomic_init(&P.capture_done,0u);
    atomic_init(&P.render_done,0u);
    atomic_init(&P.worker_done,0u);
    atomic_init(&P.sink_done,0u);
    P.beam_hash=UINT64_C(14695981039346656037);
}
static void enqueue_capture(uint32_t k) {
    uint32_t attempts;
    int16_t cap[1920],ref[480];
    fe_b1s0_status rc=FE_B1S0_FULL;
    pcm_for(P.scene,P.rate,k,cap,ref);
    for(attempts=0u;attempts<SPIN_CAP;++attempts) {
        rc=fe_b1s0_capture_submit(&P.source,
             P.source.cfg.capture_source_id,P.source.cfg.source_generation,
             k,cap,(size_t)P.rate/100u*P.scene->mics);
        if(rc==FE_B1S0_OK) return;
        if(rc!=FE_B1S0_FULL||
           atomic_load_explicit(&P.failed,memory_order_acquire))break;
        sched_yield();
    }
    atomic_store_explicit(&P.failed,1u,memory_order_release);
}
static void enqueue_render(uint32_t k) {
    uint32_t attempts;
    int16_t cap[1920],ref[480];
    fe_b1s0_status rc=FE_B1S0_FULL;
    if(!P.render)return;
    pcm_for(P.scene,P.rate,k,cap,ref);
    for(attempts=0u;attempts<SPIN_CAP;++attempts) {
        if(absent(k))
            rc=fe_b1s0_render_absent(&P.source,
                P.source.cfg.render_source_id,P.source.cfg.source_generation,
                k,ref_epoch(k),FE_B1S0_ABSENT_SOURCE_REPORTED);
        else rc=fe_b1s0_render_present(&P.source,
                P.source.cfg.render_source_id,P.source.cfg.source_generation,
                k,ref_epoch(k),k==4u?FE_B1S0_RENDER_GAP:0u,
                ref,P.rate/100u);
        if(rc==FE_B1S0_OK)return;
        if(rc!=FE_B1S0_FULL||
           atomic_load_explicit(&P.failed,memory_order_acquire))break;
        sched_yield();
    }
    atomic_store_explicit(&P.failed,2u,memory_order_release);
}
static void *cap_thread(void *ignored) {
    uint32_t k;
    (void)ignored;
    for(k=1u;k<=FRAMES;++k) {
        enqueue_capture(k);
        if(atomic_load_explicit(&P.failed,memory_order_acquire))return NULL;
        atomic_fetch_add_explicit(&P.capture_done,1u,memory_order_release);
    }
    return NULL;
}
static void *ref_thread(void *ignored) {
    uint32_t k;
    (void)ignored;
    for(k=1u;k<=FRAMES;++k) {
        enqueue_render(k);
        if(atomic_load_explicit(&P.failed,memory_order_acquire))return NULL;
        atomic_fetch_add_explicit(&P.render_done,1u,memory_order_release);
    }
    return NULL;
}
static void *worker_thread(void *ignored) {
    uint32_t k;
    (void)ignored;
    for(k=1u;k<=FRAMES;++k) {
        uint32_t tries;
        fe_t3s1_status rc=FE_T3S1_PENDING;
        float beam[160],ref[160],direct[160];
        fe_b1s0_receipt receipt;
        int16_t pcm[1920],render[480];
        pcm_for(P.scene,P.rate,k,pcm,render);
        for(tries=0u;tries<SPIN_CAP;++tries) {
            rc=fe_t3s1_step(&P.ring,beam,160u,
                    P.render?ref:NULL,P.render?160u:0u,
                    P.work,sizeof(P.work),&receipt);
            if(rc==FE_T3S1_OK)break;
            if((rc!=FE_T3S1_PENDING&&rc!=FE_T3S1_FULL)||
               atomic_load_explicit(&P.failed,memory_order_acquire))break;
            sched_yield();
        }
        if(rc!=FE_T3S1_OK||tries==SPIN_CAP||
           receipt.capture_sequence!=k ||
           receipt.source_generation!=P.source.cfg.source_generation ||
           receipt.recorder_qualified||receipt.source_clock_known ||
           receipt.device_qualified||receipt.public_sdk_qualified ||
           fe_b1b1_process(P.oracle,pcm,
                  (size_t)P.rate/100u*P.scene->mics,NULL,0u,
                  direct,160u,NULL,0u,P.oracle_work,
                  sizeof(P.oracle_work))!=FE_B1B1_OK ||
           memcmp(beam,direct,sizeof(direct))!=0) {
            atomic_store_explicit(&P.failed,3u,memory_order_release);
            return NULL;
        }
        P.beam_hash=beam_digest(P.beam_hash,beam,160u);
        atomic_fetch_add_explicit(&P.worker_done,1u,memory_order_release);
    }
    return NULL;
}
static void *sink_thread(void *ignored) {
    uint32_t k;
    (void)ignored;
    for(k=1u;k<=FRAMES;++k) {
        fe_t3s1_drain_receipt r;
        fe_t3s1_status status=FE_T3S1_PENDING;
        uint32_t tries;
        for(tries=0u;tries<SPIN_CAP;++tries) {
            status=fe_t3s1_drain_one(&P.ring,outboard,&P,&r);
            if(status==FE_T3S1_OK)break;
            if(status!=FE_T3S1_PENDING||
               atomic_load_explicit(&P.failed,memory_order_acquire))break;
            sched_yield();
        }
        if(status!=FE_T3S1_OK||tries==SPIN_CAP||
           r.source_sequence!=k||r.hardware_qualified||
           r.durable_qualified||r.product_qualified||
           r.actually_accounted_bytes!=
                (size_t)r.apx3_bytes+FE_T3S1_ROW_BYTES) {
            atomic_store_explicit(&P.failed,4u,memory_order_release);
            return NULL;
        }
        atomic_fetch_add_explicit(&P.sink_done,1u,memory_order_release);
    }
    return NULL;
}
static void run_threads(void) {
    pthread_t cap,ref,worker,sink;
    must(pthread_create(&worker,NULL,worker_thread,NULL)==0&&
         pthread_create(&sink,NULL,sink_thread,NULL)==0&&
         pthread_create(&cap,NULL,cap_thread,NULL)==0,
         "REAL_CAPTURE_WORKER_OUTBOARD_THREADS");
    if(P.render)must(pthread_create(&ref,NULL,ref_thread,NULL)==0,
                     "INDEPENDENT_RENDER_PRODUCER");
    must(pthread_join(cap,NULL)==0,"CAPTURE_THREAD_JOIN");
    if(P.render)must(pthread_join(ref,NULL)==0,"RENDER_THREAD_JOIN");
    must(pthread_join(worker,NULL)==0&&pthread_join(sink,NULL)==0,
         "WORKER_OUTBOARD_THREAD_JOIN");
    must(atomic_load_explicit(&P.failed,memory_order_acquire)==0u &&
         atomic_load_explicit(&P.capture_done,memory_order_acquire)==FRAMES &&
         (!P.render||atomic_load_explicit(&P.render_done,
           memory_order_acquire)==FRAMES) &&
         atomic_load_explicit(&P.worker_done,memory_order_acquire)==FRAMES &&
         atomic_load_explicit(&P.sink_done,memory_order_acquire)==FRAMES &&
         P.ring.last_global_capture==FRAMES &&
         P.ring.drained_global_capture==FRAMES &&
         atomic_load_explicit(&P.ring.head,memory_order_acquire)==
         atomic_load_explicit(&P.ring.tail,memory_order_acquire),
         "PTHREAD_SOURCE_BF_OUTBOARD_PROGRESS_AND_ACK");
}
static void one_profile(const scene_t *sc,uint32_t rate,
                        uint32_t render,uint32_t slots) {
    uint32_t k,i,tail,neg0=NEGATIVES;
    float beam[160],ref[160];
    fe_b1s0_receipt wr;
    fe_t3s1_drain_receipt dr;
    fe_s2_config source_cfg;
    size_t one=0u,stride=0u;
    setup(sc,rate,render,slots);
    memset(&source_cfg,0,sizeof(source_cfg));
    source_cfg.rate_hz=rate;
    source_cfg.physical_mics=sc->mics;
    source_cfg.render_channels=render;
    source_cfg.capture_source_id=P.source.cfg.capture_source_id;
    source_cfg.render_source_id=P.source.cfg.render_source_id;
    source_cfg.capture_epoch=1u;
    source_cfg.render_epoch=render?1u:0u;
    for(i=0u;i<4u;++i)
        source_cfg.physical_to_capture_slot[i]=
            i<sc->mics?sc->slots[i]:UINT32_MAX;
    must(fe_s2_layout(&source_cfg,1u,&one,&stride)==FE_S2_OK&&
         one<=FE_T3S1_CHUNK_BYTES,
         "REAL_ORIGINAL_S2_ONE_FRAME_LAYOUT");
    for(i=0u;i<160u;++i)beam[i]=321.0f;
    memset(&wr,0x5a,sizeof(wr));
    reject(fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
             render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_PENDING,
           "EMPTY_CAPTURE_NOT_PENDING");
    reject(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==FE_T3S1_PENDING,
           "EMPTY_SINK_NOT_PENDING");
    reject(fe_t3s1_drain_one(&P.ring,NULL,&P,&dr)==FE_T3S1_REJECT,
           "NULL_SINK_ACCEPTED");
    reject(fe_t3s1_step(&P.ring,beam,159u,render?ref:NULL,
             render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_REJECT,
           "SHORT_BF_OUTPUT_ACCEPTED");
    reject(fe_t3s1_step(&P.ring,NULL,160u,render?ref:NULL,
             render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_REJECT,
           "NULL_BF_OUTPUT_ACCEPTED");
    reject(fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
             render?160u:0u,NULL,sizeof(P.work),&wr)==FE_T3S1_REJECT,
           "NULL_BF_ROLLBACK_ACCEPTED");
    reject(fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
             render?160u:0u,P.work,sizeof(P.work),NULL)==FE_T3S1_REJECT,
           "NULL_SOURCE_RECEIPT_ACCEPTED");
    reject(fe_t3s1_step(&P.ring,(float *)P.physical_storage,160u,
             render?ref:NULL,render?160u:0u,P.work,sizeof(P.work),
             &wr)==FE_T3S1_REJECT,"RING_SLOT_ALIAS_BF_OUTPUT_ACCEPTED");
    reject(fe_t3s1_drain_one(&P.ring,outboard,&P,
             (fe_t3s1_drain_receipt *)P.physical_storage)==FE_T3S1_REJECT,
           "RING_SLOT_ALIAS_DRAIN_RECEIPT_ACCEPTED");
    {
        uint64_t old_id=P.source.cfg.source_generation;
        P.source.cfg.source_generation=old_id+1u;
        reject(fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
              render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_REJECT,
              "STALE_OR_REBOUND_SOURCE_GENERATION_ADMITTED");
        P.source.cfg.source_generation=old_id;
    }
    {
        uint32_t old_id=P.source.cfg.capture_source_id;
        P.source.cfg.capture_source_id=old_id+1000u;
        reject(fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
              render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_REJECT,
              "SOURCE_CAPTURE_ID_CHANGED_AFTER_BIND");
        P.source.cfg.capture_source_id=old_id;
    }
    reject(beam[0]==321.0f&&P.source.processed==0u,
           "INVALID_OR_PENDING_MUTATED_OUTPUT");
    run_threads();
    reject(fe_t3s1_seed_wrap_before_start(&P.ring,0u)==FE_T3S1_REJECT,
           "LIVE_RING_RESEED_ACCEPTED");
    {
        uint64_t saved=P.source.cap_last;
        int16_t cap[1920],refpcm[480];
        pcm_for(P.scene,P.rate,7u,cap,refpcm);
        P.source.cap_last=UINT64_MAX; /* quiescent test-only state mutation */
        reject(fe_b1s0_capture_submit(&P.source,
               P.source.cfg.capture_source_id,
               P.source.cfg.source_generation,UINT64_MAX,cap,
               (size_t)P.rate/100u*P.scene->mics)==FE_B1S0_REJECT,
               "UINT64_SOURCE_SEQUENCE_OVERFLOW_ACCEPTED");
        P.source.cap_last=saved;
    }
    enqueue_capture(7u);enqueue_render(7u);
    must(atomic_load_explicit(&P.failed,memory_order_acquire)==0u&&
         fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
            render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_OK,
         "SEVENTH_ACTUAL_CAPTURE_COMMIT");
    tail=atomic_load_explicit(&P.ring.tail,memory_order_relaxed);
    P.physical_storage[tail%slots].canonical_row[104u]^=1u;
    reject(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==FE_T3S1_TAMPER,
           "CANONICAL_FILE_SHA_TAMPER_ADMITTED");
    P.physical_storage[tail%slots].canonical_row[104u]^=1u;
    {
        fe_t3s1_slot *record=&P.physical_storage[tail%slots];
        uint8_t original_row[FE_T3S1_ROW_BYTES],digest[32];
        uint32_t bytes=record->apx3_bytes;
        must(bytes>FE_S2_HEADER_BYTES&&bytes<=FE_T3S1_CHUNK_BYTES,
             "REAL_ORIGINAL_APX3_CRC_NEGATIVE_BYTE_COUNT");
        memcpy(original_row,record->canonical_row,sizeof(original_row));
        record->apx3[bytes-1u]^=1u; /* Original S2 final CRC byte. */
        must(fe_b1s1_sha256(record->apx3,bytes,digest)==0,
             "REAL_APX3_HASH_RECALC_NEGATIVE");
        memcpy(record->canonical_row+104u,digest,sizeof(digest));
        must(fe_b1s1_sha256(record->canonical_row,
             FE_B1S1_ROW_DIGEST_OFFSET,
             record->canonical_row+FE_B1S1_ROW_DIGEST_OFFSET)==0,
             "REAL_FBS1_CANONICAL_DIGEST_NEGATIVE");
        reject(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==FE_T3S1_TAMPER,
               "ORIGINAL_S2_CRC_CORRUPTION_WITH_VALID_ROW_SHA_ACCEPTED");
        record->apx3[bytes-1u]^=1u;
        memcpy(record->canonical_row,original_row,sizeof(original_row));
    }
    reject(fe_t3s1_drain_one(&P.ring,torn_sink,&P,&dr)==
           FE_T3S1_REJECT,"UNBOUND_OUTBOARD_CALLBACK_ACCEPTED");
    reject(fe_t3s1_drain_one(&P.ring,short_ack,&P,&dr)==
           FE_T3S1_REJECT,"DIFFERENT_OUTBOARD_CALLBACK_ACCEPTED");
    P.sink_mode=1u;
    reject(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==
           FE_T3S1_SINK_NOT_ADMITTED,"TORN_OUTBOARD_ACK_ADMITTED");
    P.sink_mode=2u;
    reject(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==
           FE_T3S1_SINK_NOT_ADMITTED,"SHORT_OUTBOARD_ACK_ADMITTED");
    P.sink_mode=0u;
    reject(P.ring.drained_global_capture==FRAMES &&
           atomic_load_explicit(&P.ring.tail,memory_order_relaxed)==tail,
           "FAILED_SINK_ADVANCED_CONSUMER_TAIL");
    must(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==FE_T3S1_OK&&
         dr.source_sequence==7u&&P.ring.drained_global_capture==7u,
         "RECOVERED_EXTERNAL_SINK_EXACT_BYTES");
    for(k=8u;k<8u+slots;++k) {
        enqueue_capture(k);enqueue_render(k);
        must(fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
                render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_OK,
             "EXACT_PHYSICAL_RECORDER_SLOT_RESERVATION");
    }
    k=8u+slots;
    enqueue_capture(k);enqueue_render(k);
    {
        uint64_t processed=P.source.processed;
        uint32_t head=atomic_load_explicit(&P.ring.head,
                                           memory_order_acquire);
        reject(fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
                  render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_FULL,
               "FULL_RECORDER_UNSAFE_BF_PROGRESS");
        reject(P.source.processed==processed&&
               P.ring.last_global_capture==processed&&
               atomic_load_explicit(&P.ring.head,memory_order_acquire)==head,
               "FULL_RECORDER_MUTATED_SOURCE_OR_BF");
    }
    must(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==FE_T3S1_OK,
         "OUTBOARD_ACK_FREES_CAPACITY");
    must(fe_t3s1_step(&P.ring,beam,160u,render?ref:NULL,
          render?160u:0u,P.work,sizeof(P.work),&wr)==FE_T3S1_OK,
         "HELD_CAPTURE_REPLAY_AFTER_ACK");
    for(i=0u;i<slots;++i)
        must(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==FE_T3S1_OK,
             "DRAIN_ALL_SOURCE_BOUND_CHUNKS");
    reject(fe_t3s1_drain_one(&P.ring,outboard,&P,&dr)==FE_T3S1_PENDING,
           "EMPTY_SINK_NOT_PENDING_POST_ACK");
    must(P.ring.last_global_capture==k&&
         P.ring.drained_global_capture==k&&
         atomic_load_explicit(&P.ring.head,memory_order_acquire)==
           atomic_load_explicit(&P.ring.tail,memory_order_acquire)&&
         P.external_failure_attempts==2u&&P.actually_outboard_bytes>0u,
         "FINAL_HANDOFF_SOURCE_HASH_OR_SINK_MISMATCH");
    if(PROFILES++)putchar(',');
    printf("{\"scene\":\"%s\",\"rate\":%" PRIu32
           ",\"render\":%" PRIu32 ",\"slots\":%" PRIu32
           ",\"source_depth\":%" PRIu32
           ",\"control_bytes\":%zu,\"slot_bytes\":%zu"
           ",\"stage_owned_bytes\":%zu,\"dual_stage_owned_bytes\":%zu"
           ",\"outboard_accounted_bytes\":%zu,\"stack_scratch_min\":%u"
           ",\"apx3_one_frame\":%zu"
           ",\"source_processed\":%" PRIu64
           ",\"negative_checks\":%" PRIu32 "}",
           sc->name,rate,render,slots,P.depth,
           sizeof(P.ring),sizeof(fe_t3s1_slot),
           sizeof(P.ring)+P.ring.slot_allocation_bytes,
           2u*(sizeof(P.ring)+P.ring.slot_allocation_bytes),
           P.actually_outboard_bytes,FE_T3S1_CHUNK_BYTES,
           one,P.ring.last_global_capture,
           NEGATIVES-neg0);
    free(P.physical_storage);
    P.physical_storage=NULL;
}
int main(void) {
    uint32_t i,j,r,k;
    must(sizeof(fe_t3s1_slot)==FE_T3S1_CHUNK_BYTES+
         FE_T3S1_ROW_BYTES+sizeof(uint32_t),
         "ACTUAL_COMPILED_SLOT_PADDING_NOT_ACCOUNTED");
    printf("{\"schema_version\":1,"
           "\"decision\":\"FE09_T3S1_TWO_SLOT_SOURCE_BF_HANDOFF_RESEARCH_ONLY\","
           "\"source_role\":\"first-party-synthetic\","
           "\"complete_device_memory_qualified\":false,"
           "\"physical_ssc305_qualified\":false,"
           "\"durable_rolling_recorder_qualified\":false,"
           "\"public_sdk_installed\":false,"
           "\"archive_power_loss_safe\":false,"
           "\"profile_rows\":[");
    for(i=0u;i<4u;++i)
      for(j=0u;j<3u;++j)
        for(r=0u;r<=1u;++r)
          for(k=1u;k<=2u;++k)
            one_profile(&SCENES[i],RATES[j],r,k);
    must(PROFILES==48u&&NEGATIVES>=500u,
         "C1_C2_C4_REAL_SOURCE_PTHREAD_MATRIX_100_PLUS_NEGATIVES");
    printf("],\"profile_count\":%" PRIu32
           ",\"negative_checks\":%" PRIu32 "}\n",PROFILES,NEGATIVES);
    return 0;
}
