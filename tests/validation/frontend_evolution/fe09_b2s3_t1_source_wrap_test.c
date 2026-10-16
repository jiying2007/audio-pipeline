/* #764 noninstalled exact-source identity and actual pthread modulo-wrap.
 * Compile frozen S1 implementation as a PRIVATE white-box translation unit
 * only for the near-UINT32_MAX test. No installed S1 ABI/control extension.
 * Reuse frozen T0 deterministic C1/C2/C4 direct BF and APX3 oracle fixture.
 */
/* Set glibc feature flags BEFORE including any frozen source/header. T0's
 * own _POSIX_C_SOURCE declaration would otherwise come after stdint.h. */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s1_private_queue.c"
#define main fe_s3_t0_unused_entry
#include "fe09_b2s3_threaded_bridge_test.c"
#undef main
#include "fe09_b2s3_t1_source_witness.h"

static fe_s3_t1_source_witness T1;
static unsigned t1_failures, t1_tamper_cases;

static void *t1_producer(void *payload) {
    producer_arg *arg=(producer_arg *)payload;
    test_t *t=arg->t;
    uint32_t k, count=t->rate/100u;
    for(k=1u;k<=t->frames;++k) {
        uint32_t i, published=0u, index=(k-1u)%t->depth;
        int16_t *pcm;
        for(i=0u;i<SPIN_CAP;++i) {
            uint32_t done=atomic_load_explicit(&t->acknowledged,
                                                memory_order_acquire);
            if(atomic_load_explicit(&t->failed,memory_order_acquire))
                return NULL;
            if(k<=done+t->depth) break;
            sched_yield();
        }
        if(i==SPIN_CAP) {
            atomic_store_explicit(&t->failed,101u,memory_order_release);
            return NULL;
        }
        if(arg->render) {
            pcm=t->reference[index];
            produce_pcm(t->scene,t->rate,k,NULL,pcm);
        } else {
            pcm=t->capture[index];
            produce_pcm(t->scene,t->rate,k,pcm,NULL);
        }
        for(i=0u;i<SPIN_CAP;++i) {
            fe_s3_t1_status status=arg->render ?
              fe_s3_t1_render_submit(&T1,k,render_flags(k),pcm,count) :
              fe_s3_t1_capture_submit(&T1,k,cap_flags(k),pcm,
                                      (size_t)count*t->scene->mics);
            if(status==FE_T1_OK){published=1u;break;}
            if(status!=FE_T1_EFULL ||
               atomic_load_explicit(&t->failed,memory_order_acquire))
                break;
            sched_yield();
        }
        if(!published) {
            atomic_store_explicit(&t->failed,102u,memory_order_release);
            return NULL;
        }
        atomic_store_explicit(arg->render?&t->render_published:
                              &t->capture_published,k,memory_order_release);
    }
    return NULL;
}
static void *t1_consumer(void *payload) {
    test_t *t=(test_t *)payload;
    uint32_t k;
    float beam[160],reference[160],direct_beam[160],direct_ref[160];
    for(k=1u;k<=t->frames;++k) {
        fe_s2_frame frame;
        fe_s3_t1_status result;
        uint32_t gap=0u;
        fe_b1b1_status d;
        if(!spin_until(t,&t->capture_published,k) ||
           (t->render&&!spin_until(t,&t->render_published,k)))
            return NULL;
        build_frame(t,k,&frame);
        result=fe_s3_t1_step(&T1,&frame,beam,160u,
                            t->render?reference:NULL,(size_t)160u*t->render,
                            t->work,fe_b2s1_work_bytes(&t->config));
        if(result!=FE_T1_OK) {
            atomic_store_explicit(&t->failed,103u,memory_order_release);
            return NULL;
        }
        if(frame.capture_flags&(FE_B1B0_CAPTURE_GAP|FE_B2S1_XRUN))
            gap|=FE_B1B0_CAPTURE_GAP;
        if(frame.render_flags&(FE_B1B0_RENDER_GAP|FE_B2S1_XRUN))
            gap|=FE_B1B0_RENDER_GAP;
        if(frame.capture_flags&FE_B1B0_CLOCK_RESET)
            gap=FE_B1B0_CLOCK_RESET;
        if(gap && fe_b1b1_notify_gap(t->direct,gap)!=FE_B1B1_OK) {
            atomic_store_explicit(&t->failed,104u,memory_order_release);
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
            atomic_store_explicit(&t->failed,105u,memory_order_release);
            return NULL;
        }
        t->beam_hash=hash(t->beam_hash,beam,sizeof(beam));
        if(t->render)
            t->beam_hash=hash(t->beam_hash,reference,sizeof(reference));
        t->accepted=k;
        atomic_store_explicit(&t->acknowledged,k,memory_order_release);
    }
    return NULL;
}
static uint64_t t1_execute_witness(test_t *t) {
    pthread_t capture, render, consumer;
    producer_arg ca={t,0u},ra={t,1u};
    fe_s2_stream stream,out;
    fe_b2s1_info qi;
    size_t bytes=0u;
    must(pthread_create(&capture,NULL,t1_producer,&ca)==0,
         "T1_CREATE_CAPTURE");
    if(t->render)
        must(pthread_create(&render,NULL,t1_producer,&ra)==0,
             "T1_CREATE_RENDER");
    must(pthread_create(&consumer,NULL,t1_consumer,t)==0,
         "T1_CREATE_CONSUMER");
    must(pthread_join(capture,NULL)==0,"T1_CAPTURE_JOIN");
    if(t->render)must(pthread_join(render,NULL)==0,"T1_RENDER_JOIN");
    must(pthread_join(consumer,NULL)==0,"T1_WORKER_JOIN");
    must(atomic_load_explicit(&t->failed,memory_order_acquire)==0u,
         "T1_REAL_THREAD_EXECUTION_FAILED");
    must(t->accepted==t->frames,"T1_MISSING_FRAMES");
    must(fe_b2s1_get_info(t->queue,&qi)==FE_B2S1_OK &&
         qi.processed==t->frames && qi.capture_queued==0u &&
         qi.render_queued==0u && qi.capture_submitted==t->frames &&
         qi.render_submitted==(uint64_t)t->frames*t->render,
         "T1_QUIESCENT_SOURCE_OWNERSHIP");
    must(atomic_load_explicit(&T1.cap_head,memory_order_acquire)==
         atomic_load_explicit(&T1.cap_tail,memory_order_acquire) &&
         atomic_load_explicit(&T1.ref_head,memory_order_acquire)==
         atomic_load_explicit(&T1.ref_tail,memory_order_acquire),
         "T1_WITNESS_RING_NOT_DRAINED");
    must(fe_s3_bridge_finish(&t->bridge,&bytes)==FE_S3_OK &&
         bytes<=FE_S2_MAX_BYTES,"T1_COMPLETE_APX3");
    must(fe_s2_decode(t->record,bytes,&stream)==FE_S2_OK &&
         stream.frames==t->frames,"T1_APX3_FORMAT");
    must(fe_s2_replay(t->record,bytes,visitor,t,&out)==FE_S2_OK &&
         out.frames==t->frames,"T1_APX3_EXACT_COPIED_PCM_REPLAY");
    t->apx_hash=hash(FNV0,t->record,bytes);
    return t->apx_hash;
}
static unsigned t1_negative_source(void) {
    fe_s2_frame original, altered;
    fe_s2_writer prior;
    float beam[160],reference[160],before_beam[160],before_ref[160];
    fe_b2s1_info info;
    size_t qbytes, recbytes, i;
    unsigned count=0u;
    uint16_t bits;
    init(&T,&SCENES[1],16000u,1u,2u,2u);
    must(fe_s3_t1_bind(&T1,&T.bridge)==FE_T1_OK,
         "T1_NEG_BIND");
    produce_pcm(T.scene,T.rate,1u,T.capture[0],T.reference[0]);
    build_frame(&T,1u,&original);
    must(fe_s3_t1_capture_submit(&T1,1u,0u,
         original.capture,original.capture_count)==FE_T1_OK,
         "T1_NEG_CAPTURE_SUBMITTED");
    must(fe_s3_t1_render_submit(&T1,1u,0u,
         original.render,original.render_count)==FE_T1_OK,
         "T1_NEG_RENDER_SUBMITTED");
    prior=T.recorder;
    qbytes=fe_b2s1_state_bytes(&T.config);
    recbytes=T.recorder.total_bytes;
    memcpy(T.q_snapshot,T.qstate,qbytes);
    memcpy(T.snapshot,T.record,recbytes);
    memset(beam,0x5a,sizeof(beam));
    memset(reference,0x45,sizeof(reference));
    memcpy(before_beam,beam,sizeof(beam));
    memcpy(before_ref,reference,sizeof(reference));
    /* A malicious output buffer inside the immutable witness must be
     * rejected before BF can overwrite source identity bytes.
     */
    must(fe_s3_t1_step(&T1,&original,
            (float *)(void *)T1.cap[0].witness,160u,
            reference,160u,T.work,
            fe_b2s1_work_bytes(&T.config))==FE_T1_EINVAL,
         "T1_OUTPUT_ALIAS_WITNESS_ADMITTED");
    must(memcmp(T.q_snapshot,T.qstate,qbytes)==0 &&
         memcmp(T.snapshot,T.record,recbytes)==0 &&
         memcmp(&prior,&T.recorder,sizeof(prior))==0 &&
         memcmp(T1.cap[0].witness,original.capture,
                original.capture_count*sizeof(int16_t))==0,
         "T1_OUTPUT_ALIAS_CORRUPTED_SOURCE");
    ++count;
    for(i=0u;i<128u;++i) {
        altered=original;
        bits=0u;
        switch(i%8u) {
        case 0u:
            bits=(uint16_t)T.capture[0][i%original.capture_count];
            T.capture[0][i%original.capture_count]=(int16_t)(T.capture[0][i%original.capture_count]^1);
            break;
        case 1u:
            bits=(uint16_t)T.reference[0][i%original.render_count];
            T.reference[0][i%original.render_count]=(int16_t)(T.reference[0][i%original.render_count]^1);
            break;
        case 2u: altered.sequence+=(uint64_t)i+1u; break;
        case 3u: altered.capture_flags=FE_B1B0_CAPTURE_GAP; break;
        case 4u: altered.render_flags=FE_B1B0_RENDER_GAP; break;
        case 5u: altered.capture_epoch=2u; break;
        case 6u: altered.render_epoch=2u; break;
        default: altered.capture_timestamp_valid=1u; break;
        }
        must(fe_s3_t1_step(&T1,&altered,beam,160u,reference,160u,
                 T.work,fe_b2s1_work_bytes(&T.config))!=FE_T1_OK,
             "T1_TAMPER_ADMITTED");
        must(memcmp(T.q_snapshot,T.qstate,qbytes)==0 &&
             memcmp(T.snapshot,T.record,recbytes)==0 &&
             memcmp(&prior,&T.recorder,sizeof(prior))==0 &&
             memcmp(beam,before_beam,sizeof(beam))==0 &&
             memcmp(reference,before_ref,sizeof(reference))==0,
             "T1_TAMPER_CHANGED_EXTERNAL_OR_S1_STATE");
        if(i%8u==0u)
            T.capture[0][i%original.capture_count]=(int16_t)bits;
        if(i%8u==1u)
            T.reference[0][i%original.render_count]=(int16_t)bits;
        ++count;
    }
    must(fe_s3_t1_step(&T1,&original,beam,160u,reference,160u,
            T.work,fe_b2s1_work_bytes(&T.config))==FE_T1_OK,
         "T1_REAL_MATCH_NOT_CONSUMED");
    must(T.recorder.appended==1u,"T1_COMMIT_COUNT_DRIFT");
    must(fe_b2s1_get_info(T.queue,&info)==FE_B2S1_OK &&
         info.processed==1u && info.capture_queued==0u &&
         info.render_queued==0u,"T1_MATCH_FINAL_QUEUE");
    ++count;
    /* The facade cannot bless an outsider who directly writes frozen S1.
     * Such frames are rejected rather than assigning them an APX3 identity.
     */
    init(&T,&SCENES[1],16000u,1u,2u,2u);
    must(fe_s3_t1_bind(&T1,&T.bridge)==FE_T1_OK,"T1_OUTSIDER_BIND");
    produce_pcm(T.scene,T.rate,1u,T.capture[0],T.reference[0]);
    build_frame(&T,1u,&original);
    must(fe_b2s1_submit_capture(T.queue,1u,0u,original.capture,320u)==
         FE_B2S1_OK,"T1_OUTSIDER_S1");
    must(fe_b2s1_submit_render(T.queue,1u,0u,original.render,160u)==
         FE_B2S1_OK,"T1_OUTSIDER_S1_RENDER");
    must(fe_s3_t1_step(&T1,&original,beam,160u,reference,160u,
            T.work,fe_b2s1_work_bytes(&T.config))==FE_T1_EEMPTY &&
         T.recorder.appended==0u,"T1_OUTSIDER_PROMOTED");
    ++count;
    t1_tamper_cases=count;
    return count;
}
static uint64_t t1_wrap(test_t *t,const scene_t *sc,uint32_t rate,
                        uint32_t render,uint32_t depth) {
    const uint32_t near=UINT32_MAX-2u;
    /* TEST-ONLY privileged seeding of S1's exact internal atomic indexes.
     * A clean empty queue and actual producer/consumer threads start at
     * near UINT32_MAX. Frozen S1 source is not modified or copied.
     */
    init(t,sc,rate,render,depth,100u);
    atomic_store_explicit(&t->queue->capture_head,near,memory_order_relaxed);
    atomic_store_explicit(&t->queue->capture_tail,near,memory_order_relaxed);
    if(render){
        atomic_store_explicit(&t->queue->render_head,near,memory_order_relaxed);
        atomic_store_explicit(&t->queue->render_tail,near,memory_order_relaxed);
    }
    {
        uint64_t result=execute(t);
        fe_b2s1_info qi;
        must(fe_b2s1_get_info(t->queue,&qi)==FE_B2S1_OK &&
             qi.capture_queued==0u && qi.render_queued==0u &&
             qi.capture_submitted==100u &&
             qi.render_submitted==(uint64_t)100u*render,
             "T1_UINT32_WRAP_QUEUE_STATE");
        must(atomic_load_explicit(&t->queue->capture_head,
                    memory_order_acquire)==near+100u &&
             atomic_load_explicit(&t->queue->capture_tail,
                    memory_order_acquire)==near+100u &&
             (!render ||
              atomic_load_explicit(&t->queue->render_head,
                    memory_order_acquire)==near+100u),
             "T1_REAL_UINT32_WRAP_MISSING");
        return result;
    }
}
int main(int argc,char **argv) {
    uint32_t s,r,render,depth;
    unsigned profiles=0u,wrap_profiles=0u;
    uint64_t digest=FNV0,wrap_digest=FNV0;
    if(argc!=1 || !argv) {
        fprintf(stderr,"T1 invalid arguments\n");
        return 2;
    }
    must(sizeof(unsigned int)==4u,"ATOMIC_UINT_IS_NOT_UINT32");
    printf("{\"schema_version\":1,\"decision\":\"FE09_R2B2_S3_T1_EXACT_SOURCE_WRAP_RESEARCH_ONLY_NO_PUBLIC_ABI\",\"source_role\":\"first-party-synthetic\",\"public_sdk_installed\":false,\"physical_clock_qualified\":false,\"ssc305_dut_qualified\":false,\"actual_threaded_fixture\":true,\"profiles\":[");
    for(s=0u;s<4u;++s)for(r=0u;r<3u;++r)
        for(render=0u;render<2u;++render)
            for(depth=2u;depth<=4u;depth+=2u) {
                uint64_t file_hash;
                if(profiles)putchar(',');
                init(&T,&SCENES[s],RATES[r],render,depth,100u);
                must(fe_s3_t1_bind(&T1,&T.bridge)==FE_T1_OK,
                     "T1_EXCLUSIVE_FACADE_INIT");
                file_hash=t1_execute_witness(&T);
                digest^=file_hash;digest*=FNV_PRIME;
                printf("{\"scene\":\"%s\",\"rate\":%u,\"mics\":%u,\"render\":%u,\"depth\":%u,\"frames\":%u,\"apx_hash\":\"%016" PRIx64 "\"}",
                       SCENES[s].name,RATES[r],SCENES[s].mics,render,depth,
                       T.accepted,file_hash);
                ++profiles;
            }
    printf("],\"wrap_profiles\":[");
    for(s=0u;s<4u;++s)for(r=0u;r<3u;++r)
        for(render=0u;render<2u;++render)
            for(depth=2u;depth<=4u;depth+=2u) {
                uint64_t file_hash;
                if(wrap_profiles)putchar(',');
                file_hash=t1_wrap(&T,&SCENES[s],RATES[r],render,depth);
                wrap_digest^=file_hash;wrap_digest*=FNV_PRIME;
                printf("{\"scene\":\"%s\",\"rate\":%u,\"mics\":%u,\"render\":%u,\"depth\":%u,\"frames\":%u,\"apx_hash\":\"%016" PRIx64 "\"}",
                      SCENES[s].name,RATES[r],SCENES[s].mics,render,depth,
                      T.accepted,file_hash);
                ++wrap_profiles;
            }
    t1_failures=t1_negative_source();
    printf("],\"profile_count\":%u,\"wrap_profile_count\":%u,\"total_frames\":%u,\"negative_cases\":%u,\"source_digest\":\"%016" PRIx64 "\",\"wrap_digest\":\"%016" PRIx64 "\"}\n",
           profiles,wrap_profiles,(profiles+wrap_profiles)*100u,t1_failures,
           digest,wrap_digest);
    must(profiles==48u&&wrap_profiles==48u&&t1_failures>=130u,
         "T1_SOURCE_WRAP_MATRIX_INCOMPLETE");
    return 0;
}
