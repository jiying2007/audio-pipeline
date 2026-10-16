/* FE09 B1-S0 #776: actual pthread Capture/Render producers and BF worker,
 * source PCM is strictly FIRST-PARTY SYNTHETIC. No APX3 or physical timebase.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t2b_b1s0_owner_spsc.h"
#define main fe_s3_t0_reference_main_unused
#include "fe09_b2s3_threaded_bridge_test.c"
#undef main

#include <inttypes.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define B1_FRAMES 24u
#define B1_STATE 16384u
#define B1_WORK 32768u
#define B1_WAIT 10000000u

typedef struct {
    fe_b1s0_state q;
    fe_b1s0_config cfg;
    fe_t2b_b0 adapter;
    fe_b1b1 *core, *oracle;
    const scene_t *scene;
    uint32_t rate, depth, render, negative;
    _Alignas(16) uint8_t core_state[B1_STATE], core_work[B1_WORK];
    _Alignas(16) uint8_t oracle_state[B1_STATE], oracle_work[B1_WORK];
    atomic_uint cap_full, ref_full, failed, processed;
    uint64_t control_hash, beam_hash;
    ap_resampler_state_t expected_reference;
    uint64_t actual_reference_ordinal;
} b1_fixture;
static b1_fixture P;

static uint64_t expected_pcm_hash(const int16_t *pcm,size_t count) {
    size_t i;
    uint64_t h=FNV0;
    for(i=0u;i<count;++i) {
        uint16_t bits=(uint16_t)pcm[i];
        h=(h^(uint8_t)bits)*FNV_PRIME;
        h=(h^(uint8_t)(bits>>8u))*FNV_PRIME;
    }
    return h;
}
static uint32_t absent_at(uint32_t k) {
    return k%8u==3u || k%8u==4u;
}
static void wait_counter(const atomic_uint *value, uint32_t min,
                         const char *error) {
    uint32_t i;
    for(i=0u;i<B1_WAIT;++i) {
        if(atomic_load_explicit(value,memory_order_acquire)>=min) return;
        if(atomic_load_explicit(&P.failed,memory_order_acquire))
            must(0,"B1_THREAD_FAILURE");
        sched_yield();
    }
    must(0,error);
}
static void first_party_oracle_init(const scene_t *sc,uint32_t rate,
                                    uint32_t depth,uint32_t render) {
    fe_b1b1_config cfg=config_for(sc,rate,0u,depth).pipeline;
    size_t state=fe_b1b1_state_bytes(&cfg);
    size_t work=fe_b1b1_work_bytes(&cfg);
    P.rate=rate;P.depth=depth;P.render=render;P.scene=sc;
    must(state>0u&&state<=B1_STATE&&work>0u&&work<=B1_WORK,
         "B1_MIC_BF_ALLOCATION_BOUND");
    must(fe_b1b1_init(P.core_state,state,&cfg,&P.core)==FE_B1B1_OK &&
         fe_b1b1_init(P.oracle_state,state,&cfg,&P.oracle)==FE_B1B1_OK &&
         P.core && P.oracle && P.core!=P.oracle,
         "B1_REAL_FIRST_PARTY_BF_INIT");
    must(fe_t2b_b0_bind(&P.adapter,P.core,rate,sc->mics)==FE_T2B_B0_OK,
         "B1_FROZEN_B0_BIND");
    memset(&P.cfg,0,sizeof(P.cfg));
    P.cfg.depth=depth;P.cfg.input_hz=rate;
    P.cfg.physical_mics=sc->mics;P.cfg.render_enabled=render;
    P.cfg.capture_source_id=101u+sc->mics;
    P.cfg.render_source_id=render?201u+sc->mics:0u;
    P.cfg.source_generation=UINT64_C(900001);
    must(fe_b1s0_init(&P.q,&P.cfg,&P.adapter)==FE_B1S0_OK,
         "B1_SOURCE_OWNER_BIND");
    must(fe_b1s0_seed_wrap_before_start(&P.q,UINT32_MAX-2u)==FE_B1S0_OK,
         "B1_ACTUAL_UINT32_NEAR_WRAP_INIT");
    ap_resampler_init(&P.expected_reference);
    atomic_init(&P.cap_full,0u);
    atomic_init(&P.ref_full,0u);
    atomic_init(&P.failed,0u);
    atomic_init(&P.processed,0u);
    P.control_hash=FNV0;
    P.beam_hash=FNV0;
}
static void assert_atomic_reject(fe_b1s0_status expected,fe_b1s0_status got,
                                  const char *reason,
                                  const fe_b1s0_state *before) {
    must(got==expected && memcmp(before,&P.q,sizeof(P.q))==0,reason);
    ++P.negative;
}
static void initial_negatives(void) {
    fe_b1s0_state before;
    float beam[160],ref[160];
    fe_b1s0_receipt receipt;
    _Alignas(16) uint8_t work[B1_WORK];
    int16_t cap[1920],render[480];
    size_t n=(size_t)(P.rate/100u)*P.scene->mics;
    produce_pcm(P.scene,P.rate,1u,cap,render);
    memcpy(&before,&P.q,sizeof(before));
    assert_atomic_reject(FE_B1S0_REJECT,
        fe_b1s0_capture_submit(&P.q,0u,P.cfg.source_generation,1u,cap,n),
        "B1_CAP_WRONG_OWNER", &before);
    assert_atomic_reject(FE_B1S0_REJECT,
        fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
                               P.cfg.source_generation+1u,1u,cap,n),
        "B1_CAP_WRONG_GENERATION", &before);
    assert_atomic_reject(FE_B1S0_REJECT,
        fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
                               P.cfg.source_generation,2u,cap,n),
        "B1_CAP_UNAUTHORIZED_GAP", &before);
    assert_atomic_reject(FE_B1S0_REJECT,
        fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
                               P.cfg.source_generation,1u,cap,n-1u),
        "B1_CAP_WRONG_COUNT", &before);
    assert_atomic_reject(FE_B1S0_REJECT,
        fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
                               P.cfg.source_generation,0u,cap,n),
        "B1_CAP_ZERO_SEQUENCE", &before);
    assert_atomic_reject(FE_B1S0_REJECT,
        fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
                               P.cfg.source_generation,1u,NULL,n),
        "B1_CAP_NULL_PCM", &before);
    assert_atomic_reject(FE_B1S0_REJECT,
        fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
                               P.cfg.source_generation,1u,
                               (const int16_t *)(const void *)&P.q,n),
        "B1_CAP_ALIAS_QUEUE", &before);
    if(P.render) {
        assert_atomic_reject(FE_B1S0_REJECT,
            fe_b1s0_render_absent(&P.q,P.cfg.render_source_id,
                                  P.cfg.source_generation,1u,1u,0u),
            "B1_REJECT_UNAUTHORIZED_ABSENCE", &before);
        assert_atomic_reject(FE_B1S0_REJECT,
            fe_b1s0_render_present(&P.q,P.cfg.render_source_id,
                                   P.cfg.source_generation,2u,1u,0u,
                                   render,(size_t)P.rate/100u),
            "B1_REJECT_RENDER_SEQUENCE_GAP", &before);
        assert_atomic_reject(FE_B1S0_REJECT,
            fe_b1s0_render_present(&P.q,P.cfg.capture_source_id,
                                   P.cfg.source_generation,1u,1u,0u,
                                   render,(size_t)P.rate/100u),
            "B1_REJECT_CROSS_DOMAIN_SOURCE", &before);
    } else {
        assert_atomic_reject(FE_B1S0_REJECT,
            fe_b1s0_render_absent(&P.q,0u,P.cfg.source_generation,1u,1u,
                                 FE_B1S0_ABSENT_SOURCE_REPORTED),
            "B1_RENDER_DISABLED_SOURCE_TOKEN", &before);
    }
    memset(beam,0xa6,sizeof(beam));
    memset(ref,0x9b,sizeof(ref));
    memset(&receipt,0x86,sizeof(receipt));
    must(fe_b1s0_process_one(&P.q,beam,160u,P.render?ref:NULL,
          P.render?160u:0u,work,sizeof(work),&receipt)==FE_B1S0_EMPTY &&
         memcmp(&before,&P.q,sizeof(before))==0,
         "B1_EMPTY_QUEUE_CANNOT_PROGRESS");
    ++P.negative;
}
typedef struct {uint32_t render;} owner_arg;
static void *source_thread(void *ctx) {
    owner_arg *arg=(owner_arg *)ctx;
    uint32_t k,prior_absent=0u,epoch=1u;
    for(k=1u;k<=B1_FRAMES;++k) {
        uint32_t attempts;
        fe_b1s0_status rc=FE_B1S0_FULL;
        int16_t cap[1920],ref[480];
        produce_pcm(P.scene,P.rate,k,cap,ref);
        if(arg->render && k>1u && prior_absent && !absent_at(k))
            ++epoch;
        for(attempts=0u;attempts<B1_WAIT;++attempts) {
            if(arg->render) {
                if(absent_at(k))
                    rc=fe_b1s0_render_absent(&P.q,P.cfg.render_source_id,
                        P.cfg.source_generation,k,epoch,
                        FE_B1S0_ABSENT_SOURCE_REPORTED);
                else
                    rc=fe_b1s0_render_present(&P.q,P.cfg.render_source_id,
                        P.cfg.source_generation,k,epoch,
                        prior_absent?FE_B1S0_RENDER_GAP:0u,
                        ref,(size_t)P.rate/100u);
            } else {
                rc=fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
                    P.cfg.source_generation,k,cap,
                    (size_t)(P.rate/100u)*P.scene->mics);
            }
            if(rc==FE_B1S0_OK) break;
            if(rc!=FE_B1S0_FULL) {
                atomic_store_explicit(&P.failed,1u,memory_order_release);
                return NULL;
            }
            atomic_fetch_add_explicit(arg->render?&P.ref_full:&P.cap_full,
                                      1u,memory_order_relaxed);
            if(atomic_load_explicit(&P.failed,memory_order_acquire))
                return NULL;
            sched_yield();
        }
        if(attempts==B1_WAIT || rc!=FE_B1S0_OK) {
            atomic_store_explicit(&P.failed,2u,memory_order_release);
            return NULL;
        }
        if(arg->render)
            prior_absent=absent_at(k);
    }
    return NULL;
}
static void *worker_thread(void *unused) {
    uint32_t k;
    float beam[160],reference[160],oraclebeam[160],reforacle[160];
    _Alignas(16) uint8_t work[B1_WORK];
    (void)unused;
    for(k=1u;k<=B1_FRAMES;++k) {
        fe_b1s0_status rc=FE_B1S0_EMPTY;
        fe_b1s0_receipt receipt;
        int16_t cap[1920],ref[480];
        uint32_t n;
        size_t capn=(size_t)(P.rate/100u)*P.scene->mics;
        const uint32_t actual=P.render&&!absent_at(k);
        produce_pcm(P.scene,P.rate,k,cap,ref);
        for(n=0u;n<B1_WAIT;++n) {
            for(size_t i=0u;i<160u;++i) reference[i]=-113.0f;
            memset(&receipt,0xbe,sizeof(receipt));
            rc=fe_b1s0_process_one(&P.q,beam,160u,
                P.render?reference:NULL,P.render?160u:0u,
                work,sizeof(work),&receipt);
            if(rc==FE_B1S0_OK) break;
            if(rc!=FE_B1S0_EMPTY) {
                atomic_store_explicit(&P.failed,3u,memory_order_release);
                return NULL;
            }
            sched_yield();
        }
        if(n==B1_WAIT || rc!=FE_B1S0_OK ||
           receipt.capture_sequence!=k ||
           receipt.source_generation!=P.cfg.source_generation ||
           receipt.capture_source_id!=P.cfg.capture_source_id ||
           receipt.capture_pcm_hash!=expected_pcm_hash(cap,capn) ||
           receipt.mic_bf_progressed!=1u || receipt.source_clock_known ||
           receipt.recorder_qualified || receipt.public_sdk_qualified ||
           receipt.device_qualified ||
           receipt.reference_actual_pcm!=actual) {
            atomic_store_explicit(&P.failed,4u,memory_order_release);
            return NULL;
        }
        if(fe_b1b1_process(P.oracle,cap,capn,NULL,0u,
              oraclebeam,160u,NULL,0u,P.oracle_work,sizeof(P.oracle_work))
              !=FE_B1B1_OK ||
           memcmp(beam,oraclebeam,sizeof(beam))!=0) {
            atomic_store_explicit(&P.failed,5u,memory_order_release);
            return NULL;
        }
        P.beam_hash=hash(P.beam_hash,beam,sizeof(beam));
        if(P.render) {
            if(actual) {
                uint32_t gap=0u;
                if(P.actual_reference_ordinal &&
                   (k>1u && absent_at(k-1u)))
                    gap=1u;
                if(gap) ap_resampler_reset(&P.expected_reference);
                ap_resample_input_channel(&P.expected_reference,0u,
                    ref,P.rate/100u,1u,0u,reforacle,160u);
                ++P.actual_reference_ordinal;
                if(memcmp(reference,reforacle,sizeof(reforacle))!=0 ||
                   receipt.render_event!=FE_B1S0_RENDER_PRESENT ||
                   receipt.render_pcm_hash!=
                       expected_pcm_hash(ref,(size_t)P.rate/100u)) {
                    atomic_store_explicit(&P.failed,6u,memory_order_release);
                    return NULL;
                }
            } else {
                for(size_t i=0u;i<160u;++i)
                    if(reference[i]!=-113.0f) {
                        atomic_store_explicit(&P.failed,7u,memory_order_release);
                        return NULL;
                    }
                if(receipt.render_event!=FE_B1S0_RENDER_ABSENT ||
                   receipt.render_reason!=FE_B1S0_ABSENT_SOURCE_REPORTED ||
                   receipt.render_pcm_hash) {
                    atomic_store_explicit(&P.failed,8u,memory_order_release);
                    return NULL;
                }
            }
        } else if(receipt.render_event!=FE_B1S0_RENDER_DISABLED ||
                  receipt.render_pcm_hash || receipt.render_reason)
            return NULL;
        P.control_hash=hash(P.control_hash,&receipt.capture_sequence,
                            sizeof(receipt.capture_sequence));
        P.control_hash=hash(P.control_hash,&receipt.render_event,
                            sizeof(receipt.render_event));
        P.control_hash=hash(P.control_hash,&receipt.render_epoch,
                            sizeof(receipt.render_epoch));
        atomic_store_explicit(&P.processed,k,memory_order_release);
    }
    return NULL;
}
static uint64_t profile(const scene_t *sc,uint32_t rate,
                        uint32_t render,uint32_t depth,
                        uint32_t *negatives,uint64_t *bfhash) {
    pthread_t capthread,refthread,workerthread;
    owner_arg cap={0u},ref={1u};
    _Alignas(16) uint8_t work[B1_WORK];
    fe_b1s0_receipt receipt;
    float beam[160],refout[160];
    uint32_t seed=UINT32_MAX-2u;
    uint64_t id;
    memset(&P,0,sizeof(P));
    first_party_oracle_init(sc,rate,depth,render);
    initial_negatives();
    must(pthread_create(&capthread,NULL,source_thread,&cap)==0,
         "B1_CAPTURE_PTHREAD_CREATED");
    wait_counter(&P.cap_full,1u,"B1_CAPTURE_FULL_NOT_ACTUALLY_EXERCISED");
    if(render) {
        /* Real queued Capture without a Render OWNER event must remain
         * EMPTY. It is not a source-attested missing Render token.
         */
        float before_beam[160],before_ref[160];
        uint8_t before_core[B1_STATE];
        fe_t2b_b0 before_adapter=P.adapter;
        memset(beam,0x88,sizeof(beam));
        memset(refout,0x77,sizeof(refout));
        memset(&receipt,0x22,sizeof(receipt));
        memcpy(before_beam,beam,sizeof(beam));
        memcpy(before_ref,refout,sizeof(refout));
        memcpy(before_core,P.core_state,sizeof(before_core));
        must(fe_b1s0_process_one(&P.q,beam,160u,refout,160u,work,
              sizeof(work),&receipt)==FE_B1S0_EMPTY &&
             memcmp(before_beam,beam,sizeof(beam))==0 &&
             memcmp(before_ref,refout,sizeof(refout))==0 &&
             memcmp(before_core,P.core_state,sizeof(before_core))==0 &&
             memcmp(&before_adapter,&P.adapter,sizeof(before_adapter))==0,
             "B1_PENDING_RENDER_FALSIFIED_AS_ABSENT");
        ++P.negative;
        must(pthread_create(&refthread,NULL,source_thread,&ref)==0,
             "B1_RENDER_PTHREAD_CREATED");
        wait_counter(&P.ref_full,1u,"B1_RENDER_FULL_NOT_EXERCISED");
    }
    must(pthread_create(&workerthread,NULL,worker_thread,NULL)==0,
         "B1_ACTUAL_WORKER_PTHREAD");
    must(pthread_join(capthread,NULL)==0,"B1_CAPTURE_JOIN");
    if(render) must(pthread_join(refthread,NULL)==0,"B1_RENDER_JOIN");
    must(pthread_join(workerthread,NULL)==0,"B1_WORKER_JOIN");
    must(!atomic_load_explicit(&P.failed,memory_order_acquire) &&
         P.q.processed==B1_FRAMES &&
         atomic_load_explicit(&P.processed,memory_order_acquire)==B1_FRAMES &&
         P.adapter.accepted_capture==B1_FRAMES &&
         P.adapter.accepted_render==P.q.actual_render_frames &&
         P.q.cap_last==B1_FRAMES &&
         P.q.ref_last==(render?B1_FRAMES:0u),
         "B1_ACTUAL_CONCURRENT_SOURCE_PROGRESS");
    must(atomic_load_explicit(&P.q.cap_head,memory_order_acquire)==
         (uint32_t)(seed+B1_FRAMES) &&
         atomic_load_explicit(&P.q.cap_tail,memory_order_acquire)==
         (uint32_t)(seed+B1_FRAMES) &&
         atomic_load_explicit(&P.q.ref_head,memory_order_acquire)==
         (uint32_t)(seed+(render?B1_FRAMES:0u)) &&
         atomic_load_explicit(&P.q.ref_tail,memory_order_acquire)==
         (uint32_t)(seed+(render?B1_FRAMES:0u)),
         "B1_ACTUAL_UINT32_SPSC_WRAP_OR_DRAIN");
    must(fe_b1s0_seed_wrap_before_start(&P.q,0u)==FE_B1S0_REJECT,
         "B1_REJECT_POST_START_COUNTER_RESEED");++P.negative;
    /* Negative inputs on truly drained actual queues; no data races. */
    for(uint32_t i=0u;i<12u;++i) {
        fe_b1s0_state snapshot=P.q;
        fe_b1s0_status status;
        int16_t cap_pcm_buf[1920],ref_pcm_buf[480];
        produce_pcm(sc,rate,B1_FRAMES+1u,cap_pcm_buf,ref_pcm_buf);
        switch(i%4u) {
        case 0u: status=fe_b1s0_capture_submit(&P.q,0u,
                        P.cfg.source_generation,B1_FRAMES+1u,cap_pcm_buf,
                        (size_t)(rate/100u)*sc->mics);break;
        case 1u: status=fe_b1s0_capture_submit(&P.q,
                        P.cfg.capture_source_id,P.cfg.source_generation+1u,
                        B1_FRAMES+1u,cap_pcm_buf,
                        (size_t)(rate/100u)*sc->mics);break;
        case 2u: status=fe_b1s0_capture_submit(&P.q,
                        P.cfg.capture_source_id,P.cfg.source_generation,
                        B1_FRAMES+3u,cap_pcm_buf,
                        (size_t)(rate/100u)*sc->mics);break;
        default: status=fe_b1s0_render_absent(&P.q,P.cfg.render_source_id,
                        P.cfg.source_generation,B1_FRAMES+1u,1u,0u);break;
        }
        must(status==FE_B1S0_REJECT &&
             memcmp(&snapshot,&P.q,sizeof(snapshot))==0,
             "B1_DRAINED_INVALID_RETRY_MUTATED_QUEUES");
        ++P.negative;
    }
    memset(beam,0x33,sizeof(beam));memset(refout,0x48,sizeof(refout));
    memset(&receipt,0xb8,sizeof(receipt));
    must(fe_b1s0_process_one(&P.q,beam,160u,render?refout:NULL,
                            render?160u:0u,work,sizeof(work),&receipt)
         ==FE_B1S0_EMPTY,"B1_DRAINED_NO_GHOST_FRAME");
    ++P.negative;
    id=P.control_hash;
    id=hash(id,&rate,sizeof(rate));
    id=hash(id,&depth,sizeof(depth));
    id=hash(id,&render,sizeof(render));
    id=hash(id,&sc->mics,sizeof(sc->mics));
    *bfhash=P.beam_hash;
    *negatives+=P.negative;
    return id;
}
/* Force an actual post-Render, pre-Capture DSP validation failure.
 * A successful temporary reference resample must NOT leak into the adapter,
 * queue, BF core, user beam/ref or receipt when Capture fails atomically.
 * Corruption is injected ONLY in this noninstalled test before worker call.
 */
static uint32_t render_then_capture_core_failure_negative(void) {
    int16_t cap[1920],refpcm[480];
    fe_b1s0_receipt receipt, prior_receipt;
    fe_b1s0_state prior_queue;
    fe_t2b_b0 prior_adapter;
    uint8_t prior_bf[B1_STATE];
    float beam[160],ref[160],prior_beam[160],prior_ref[160];
    _Alignas(16) uint8_t work[B1_WORK];
    uint32_t k;
    memset(&P,0,sizeof(P));
    first_party_oracle_init(&SCENES[1],16000u,2u,1u);
    produce_pcm(P.scene,P.rate,1u,cap,refpcm);
    must(fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
        P.cfg.source_generation,1u,cap,320u)==FE_B1S0_OK &&
         fe_b1s0_render_present(&P.q,P.cfg.render_source_id,
        P.cfg.source_generation,1u,1u,0u,refpcm,160u)==FE_B1S0_OK,
         "B1_FAULT_FIXTURE_REAL_SOURCE_SUBMISSION");
    prior_queue=P.q;
    prior_adapter=P.adapter;
    for(k=0u;k<160u;++k) { beam[k]=-55.0f;ref[k]=-66.0f; }
    memset(&receipt,0x96,sizeof(receipt));
    memcpy(prior_beam,beam,sizeof(beam));
    memcpy(prior_ref,ref,sizeof(ref));
    memcpy(&prior_receipt,&receipt,sizeof(receipt));
    P.core_state[0]^=(uint8_t)0x49u;
    memcpy(prior_bf,P.core_state,sizeof(prior_bf));
    must(fe_b1s0_process_one(&P.q,beam,160u,ref,160u,
             work,sizeof(work),&receipt)==FE_B1S0_CORE &&
         memcmp(&prior_queue,&P.q,sizeof(P.q))==0 &&
         memcmp(&prior_adapter,&P.adapter,sizeof(P.adapter))==0 &&
         memcmp(prior_bf,P.core_state,sizeof(prior_bf))==0 &&
         memcmp(prior_beam,beam,sizeof(beam))==0 &&
         memcmp(prior_ref,ref,sizeof(ref))==0 &&
         memcmp(&prior_receipt,&receipt,sizeof(receipt))==0,
         "B1_POST_RENDER_DSP_FAILURE_NOT_ATOMIC");
    P.core_state[0]^=(uint8_t)0x49u;
    must(fe_b1s0_process_one(&P.q,beam,160u,ref,160u,
             work,sizeof(work),&receipt)==FE_B1S0_OK &&
         receipt.capture_sequence==1u &&
         receipt.reference_actual_pcm==1u &&
         P.q.processed==1u && P.q.actual_render_frames==1u,
         "B1_SOURCE_RECOVERY_AFTER_REJECT");
    return 1u;
}
int main(void) {
    uint32_t i,j,d,r,profiles=0u,negatives=0u;
    uint64_t digest=FNV0;
    negatives+=render_then_capture_core_failure_negative();
    printf("{\"schema_version\":1,\"decision\":\"FE09_T2B_B1S0_OWNER_WITNESS_SPSC_CAPTURE_BF_NO_RECORDER\",\"source_role\":\"first-party-synthetic\",\"real_pthread_source_owners\":true,\"capture_bf_continuity_software\":true,\"source_absence_physical_verified\":false,\"apx3_recording_qualified\":false,\"device_qualified\":false,\"public_sdk_installed\":false,\"profiles\":[");
    for(i=0u;i<4u;++i) for(j=0u;j<3u;++j)
      for(d=2u;d<=4u;d+=2u) for(r=0u;r<2u;++r) {
        uint64_t bh=0u;
        uint64_t h=profile(&SCENES[i],RATES[j],r,d,&negatives,&bh);
        if(profiles) putchar(',');
        digest=(digest^h)*FNV_PRIME;
        printf("{\"scene\":\"%s\",\"rate\":%u,\"render_enabled\":%u,\"depth\":%u,\"frames\":%u,\"control_hash\":\"%016" PRIx64 "\",\"bf_hash\":\"%016" PRIx64 "\"}",
                SCENES[i].name,RATES[j],r,d,B1_FRAMES,h,bh);
        ++profiles;
      }
    must(profiles==48u && negatives>=600u,
         "B1_INCOMPLETE_OWNER_SPSC_NEGATIVE_MATRIX");
    printf("],\"profile_count\":%u,\"negative_checks\":%u,\"control_digest\":\"%016" PRIx64 "\"}\n",
           profiles,negatives,digest);
    return 0;
}
