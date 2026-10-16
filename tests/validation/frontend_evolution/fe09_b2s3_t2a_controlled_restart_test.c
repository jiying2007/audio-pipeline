/* FE09 #769: real source/worker pthreads + cold epoch restart;
 * PRIVATE control-only test. Preserve old S1/T1/S2 bytes on all rejects.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t2a_controlled_restart.h"
#define main fe_s3_t0_reference_main_unused
#include "fe09_b2s3_threaded_bridge_test.c"
#undef main

#include <inttypes.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

static test_t A, B;
static fe_s3_t1_source_witness WA, WB, old_copy;
static fe_t2a_gate G;
static fe_t2a_receipt R;

typedef struct {
    test_t *t;
    fe_s3_t1_source_witness *w;
    fe_t2a_gate *g;
    uint64_t generation;
    atomic_uint first_done, second_start, second_done, processed, mismatch;
    atomic_uint allow_worker_ack;
    uint32_t render, negative_checks;
} context_t;
static context_t C;

static void wait_u32(atomic_uint *value, uint32_t minval, const char *reason) {
    uint32_t i;
    for (i=0u;i<SPIN_CAP;++i) {
        if (atomic_load_explicit(value,memory_order_acquire)>=minval)
            return;
        sched_yield();
    }
    must(0,reason);
}
static void wait_stopping(fe_t2a_gate *gate) {
    uint32_t i;
    for(i=0u;i<SPIN_CAP;++i) {
        if(atomic_load_explicit(&gate->phase,memory_order_acquire)==
           FE_T2A_STOPPING) return;
        sched_yield();
    }
    must(0,"T2A_OWNER_NOT_STOPPED");
}
typedef struct {
    context_t *c;
    uint32_t owner, role_bit;
    fe_t2a_status ack;
} owner_t;
static void *source_owner(void *opaque) {
    owner_t *o=(owner_t *)opaque;
    context_t *c=o->c;
    test_t *t=c->t;
    fe_s3_t1_source_witness *session;
    size_t n=(size_t)(t->rate/100u);
    fe_s3_t1_status result;
    session=fe_t2a_session(c->g,c->generation);
    must(session==c->w,"T2A_SOURCE_SESSION");
    result=o->owner==FE_T2A_RENDER_OWNER ?
        fe_s3_t1_render_submit(session,1u,0u,t->reference[0],n) :
        fe_s3_t1_capture_submit(session,1u,0u,t->capture[0],
                                n*t->scene->mics);
    must(result==FE_T1_OK,"T2A_REAL_INITIAL_SOURCE");
    atomic_fetch_or_explicit(&c->first_done,o->role_bit,memory_order_release);
    wait_u32(&c->second_start,1u,"T2A_SOURCE_SECOND_START");
    session=fe_t2a_session(c->g,c->generation);
    must(session==c->w,"T2A_SECOND_SOURCE_SESSION");
    result=o->owner==FE_T2A_RENDER_OWNER ?
        fe_s3_t1_render_submit(session,3u,FE_B1B0_RENDER_GAP,
                               t->reference[1],n) :
        fe_s3_t1_capture_submit(session,2u,0u,t->capture[1],
                                n*t->scene->mics);
    must(result==FE_T1_OK,"T2A_REAL_PENDING_SOURCE");
    atomic_fetch_or_explicit(&c->second_done,o->role_bit,memory_order_release);
    wait_stopping(c->g);
    /* All actual source submissions have returned before own ACK. */
    o->ack=fe_t2a_ack_stopped(c->g,c->generation,o->owner);
    return NULL;
}
static void *worker_owner(void *opaque) {
    owner_t *o=(owner_t *)opaque;
    context_t *c=o->c;
    test_t *t=c->t;
    fe_s2_frame f;
    float beam[160], ref[160];
    uint32_t roles=FE_T2A_CAPTURE_OWNER |
        (c->render?FE_T2A_RENDER_OWNER:0u);
    wait_u32(&c->first_done,roles,"T2A_FIRST_PUBLISH");
    must(fe_t2a_session(c->g,c->generation)==c->w,
         "T2A_WORKER_SESSION");
    build_frame(t,1u,&f);
    must(fe_s3_t1_step(c->w,&f,beam,160u,c->render?ref:NULL,
                        (size_t)160u*c->render,t->work,
                        fe_b2s1_work_bytes(&t->config))==FE_T1_OK,
         "T2A_OLD_FIRST_PARTY_FRAME");
    atomic_store_explicit(&c->processed,1u,memory_order_release);
    wait_u32(&c->second_done,roles,"T2A_SECOND_PUBLISH");
    build_frame(t,2u,&f);
    f.render_flags=c->render?FE_B1B0_RENDER_GAP:0u;
    f.render_epoch=c->render?2u:0u;
    /* In render mode the second actual render has seq3, not seq2.
     * In capture-only mode this candidate has a fake capture gap.
     */
    if(!c->render) f.capture_flags=FE_B1B0_CAPTURE_GAP;
    must(fe_s3_t1_step(c->w,&f,beam,160u,c->render?ref:NULL,
                        (size_t)160u*c->render,t->work,
                        fe_b2s1_work_bytes(&t->config))==FE_T1_EFRAME,
         "T2A_MISMATCH_FALSELY_CONSUMED");
    atomic_store_explicit(&c->mismatch,1u,memory_order_release);
    wait_stopping(c->g);
    /* Hold the last required ACK until supervisor tests early restart. */
    wait_u32(&c->allow_worker_ack,1u,"T2A_WORKER_ACK_RELEASE");
    o->ack=fe_t2a_ack_stopped(c->g,c->generation,FE_T2A_WORKER_OWNER);
    return NULL;
}
static void new_source_frame(test_t *t, fe_s3_t1_source_witness *w,
                             uint32_t k) {
    fe_s2_frame frame;
    float beam[160], ref[160], db[160], dr[160];
    size_t n=(size_t)(t->rate/100u);
    fe_b1b1_status direct_status;
    const uint32_t index=k-1u;
    must(fe_t2a_session(&G,2u)==w,"T2A_NEXT_SESSION_ACCESS");
    produce_pcm(t->scene,t->rate,k,t->capture[index],
                t->render?t->reference[index]:NULL);
    must(fe_s3_t1_capture_submit(w,k,0u,t->capture[index],
                                n*t->scene->mics)==FE_T1_OK,
         "T2A_FRESH_CAPTURE_SUBMITTED");
    if(t->render)
        must(fe_s3_t1_render_submit(w,k,0u,t->reference[index],n)==
             FE_T1_OK,"T2A_FRESH_RENDER_SUBMITTED");
    build_frame(t,k,&frame);
    must(fe_s3_t1_step(w,&frame,beam,160u,t->render?ref:NULL,
                       (size_t)160u*t->render,t->work,
                       fe_b2s1_work_bytes(&t->config))==FE_T1_OK,
         "T2A_FRESH_SOURCE_NOT_PROCESSED");
    direct_status=fe_b1b1_process(t->direct,
        frame.capture,frame.capture_count,frame.render,frame.render_count,
        db,160u,t->render?dr:NULL,(size_t)160u*t->render,
        t->dwork,fe_b1b1_work_bytes(&t->config.pipeline));
    must(direct_status==FE_B1B1_OK &&
         memcmp(beam,db,sizeof(db))==0 &&
         (!t->render || memcmp(ref,dr,sizeof(dr))==0),
         "T2A_POST_CUTOVER_FIRST_PARTY_BF_NOT_EQUAL");
}
static uint64_t one_profile(const scene_t *sc,uint32_t rate,
                            uint32_t render,uint32_t depth,
                            uint32_t *negative_checks) {
    owner_t cap={&C,FE_T2A_CAPTURE_OWNER,FE_T2A_CAPTURE_OWNER,FE_T2A_DENIED};
    owner_t ref={&C,FE_T2A_RENDER_OWNER,FE_T2A_RENDER_OWNER,FE_T2A_DENIED};
    owner_t worker={&C,FE_T2A_WORKER_OWNER,0u,FE_T2A_DENIED};
    pthread_t ct,rt,wt;
    fe_s2_config config;
    fe_b2s1_info qold,qnew;
    fe_s2_stream stream;
    size_t finished=0u;
    uint64_t digest=FNV0;
    size_t state_size;
    uint32_t required=FE_T2A_CAPTURE_OWNER | FE_T2A_WORKER_OWNER |
        (render?FE_T2A_RENDER_OWNER:0u);
    memset(&WA,0,sizeof(WA));
    memset(&WB,0,sizeof(WB));
    init(&A,sc,rate,render,depth,2u);
    init(&B,sc,rate,render,depth,2u);
    config=record_config(&B);
    config.capture_source_id+=10000u;
    if(render) config.render_source_id+=10000u;
    must(fe_s2_writer_begin(&B.recorder,B.record,sizeof(B.record),
                            &config,2u)==FE_S2_OK,"T2A_NEW_WRITER");
    must(fe_s3_bridge_init(&B.bridge,B.queue,&B.recorder,
                           B.shadow,sizeof(B.shadow))==FE_S3_OK,
         "T2A_NEW_BRIDGE");
    must(fe_s3_t1_bind(&WA,&A.bridge)==FE_T1_OK &&
         fe_s3_t1_bind(&WB,&B.bridge)==FE_T1_OK,"T2A_T1_EXCLUSIVE_BIND");
    must(fe_t2a_init(&G,&WA,1u)==FE_T2A_OK,"T2A_INIT");
    must(fe_t2a_session(&G,1u)==&WA,"T2A_INITIAL_ACCESS");
    must(fe_t2a_session(&G,0u)==NULL,"T2A_ZERO_GENERATION_ACCESS"); ++*negative_checks;
    must(fe_t2a_session(&G,2u)==NULL,"T2A_FUTURE_GENERATION_ACCESS"); ++*negative_checks;
    must(fe_t2a_request_stop(&G,1u,(fe_t2a_reason)0)==FE_T2A_DENIED,
         "T2A_REASON_ZERO"); ++*negative_checks;
    must(fe_t2a_request_stop(&G,2u,FE_T2A_REASON_XRUN)==FE_T2A_DENIED,
         "T2A_FUTURE_STOP"); ++*negative_checks;
    must(fe_t2a_ack_stopped(&G,1u,FE_T2A_WORKER_OWNER)==FE_T2A_DENIED,
         "T2A_ACK_BEFORE_STOP"); ++*negative_checks;
    must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_DENIED,
         "T2A_RESTART_WHILE_ACTIVE"); ++*negative_checks;
    memset(&C,0,sizeof(C)); C.t=&A; C.w=&WA; C.g=&G; C.generation=1u;
    C.render=render;
    atomic_init(&C.first_done,0u);
    atomic_init(&C.second_start,0u);
    atomic_init(&C.second_done,0u);
    atomic_init(&C.processed,0u);
    atomic_init(&C.mismatch,0u);
    atomic_init(&C.allow_worker_ack,0u);
    produce_pcm(sc,rate,1u,A.capture[0],render?A.reference[0]:NULL);
    produce_pcm(sc,rate,2u,A.capture[1],render?A.reference[1]:NULL);
    must(pthread_create(&ct,NULL,source_owner,&cap)==0,"T2A_CAPTURE_THREAD");
    if(render)
        must(pthread_create(&rt,NULL,source_owner,&ref)==0,
             "T2A_RENDER_THREAD");
    must(pthread_create(&wt,NULL,worker_owner,&worker)==0,
         "T2A_WORKER_THREAD");
    wait_u32(&C.processed,1u,"T2A_OLD_PAIR_PROGRESS");
    atomic_store_explicit(&C.second_start,1u,memory_order_release);
    wait_u32(&C.mismatch,1u,"T2A_OLD_MISMATCH");
    must(A.recorder.appended==1u && A.bridge.processed==1u,
         "T2A_MISMATCH_ALREADY_COMMITTED");
    state_size=fe_b2s1_state_bytes(&A.config);
    must(state_size>0u && state_size<=sizeof(A.q_snapshot),
         "T2A_CAPTURE_SNAPSHOT_BOUND");
    memcpy(A.q_snapshot,A.qstate,state_size);
    memcpy(A.snapshot,A.record,A.recorder.total_bytes);
    memcpy(&old_copy,&WA,sizeof(WA));
    must(fe_t2a_request_stop(&G,1u,
         render?FE_T2A_REASON_SOURCE_MISMATCH:
                FE_T2A_REASON_CAPTURE_RESET)==FE_T2A_OK,
         "T2A_CONTROL_STOP_REQUEST");
    must(fe_t2a_session(&G,1u)==NULL,"T2A_STOPPED_OLD_SESSION");
    ++*negative_checks;
    must(fe_t2a_request_stop(&G,1u,FE_T2A_REASON_XRUN)==FE_T2A_DENIED,
         "T2A_DOUBLE_STOP"); ++*negative_checks;
    /* Worker still has not acknowledged; no cutover may occur. */
    must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_DENIED,
         "T2A_PREMATURE_CUTOVER"); ++*negative_checks;
    atomic_store_explicit(&C.allow_worker_ack,1u,memory_order_release);
    must(pthread_join(ct,NULL)==0,"T2A_CAPTURE_JOIN");
    if(render) must(pthread_join(rt,NULL)==0,"T2A_RENDER_JOIN");
    must(pthread_join(wt,NULL)==0,"T2A_WORKER_JOIN");
    must(cap.ack==FE_T2A_OK && worker.ack==FE_T2A_OK &&
         (!render||ref.ack==FE_T2A_OK),"T2A_ROLE_ACK_MISSING");
    must(atomic_load_explicit(&G.acknowledgments,memory_order_acquire)==
         required,"T2A_REQUIRED_OWNERS_NOT_ACKED");
    must(memcmp(A.q_snapshot,A.qstate,state_size)==0 &&
         memcmp(A.snapshot,A.record,A.recorder.total_bytes)==0 &&
         memcmp(&old_copy,&WA,sizeof(WA))==0,
         "T2A_OLD_BF_OR_RECORDER_MUTATED_DURING_STOP");
    must(fe_t2a_ack_stopped(&G,1u,FE_T2A_CAPTURE_OWNER)==FE_T2A_DENIED,
         "T2A_DUPLICATE_CAPTURE_ACK"); ++*negative_checks;
    must(fe_t2a_ack_stopped(&G,2u,FE_T2A_WORKER_OWNER)==FE_T2A_DENIED,
         "T2A_STALE_GENERATION_ACK"); ++*negative_checks;
    must(fe_t2a_ack_stopped(&G,1u,3u)==FE_T2A_DENIED,
         "T2A_MULTI_ROLE_ACK"); ++*negative_checks;
    if(!render) {
        must(fe_t2a_ack_stopped(&G,1u,FE_T2A_RENDER_OWNER)==FE_T2A_DENIED,
             "T2A_PHANTOM_RENDER_OWNER"); ++*negative_checks;
    }
    must(fe_t2a_restart(&G,2u,&WB,&R)==FE_T2A_DENIED,
         "T2A_FUTURE_RESTART"); ++*negative_checks;
    must(fe_t2a_restart(&G,1u,&WA,&R)==FE_T2A_DENIED,
         "T2A_REUSE_OLD_STATE"); ++*negative_checks;
    B.recorder.config.capture_source_id=A.recorder.config.capture_source_id;
    must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_DENIED,
         "T2A_SOURCE_ID_REUSE"); ++*negative_checks;
    B.recorder.config.capture_source_id=config.capture_source_id;
    if(render) {
        /* Greater than old Capture but below old Render: would permit
         * cross-domain source ID recycling without a GLOBAL monotone floor. */
        B.recorder.config.capture_source_id=
            A.recorder.config.render_source_id-1u;
        B.bridge.capture_source_id=B.recorder.config.capture_source_id;
        must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_DENIED,
             "T2A_CROSS_DOMAIN_SOURCE_ID_REUSE"); ++*negative_checks;
        B.recorder.config.capture_source_id=config.capture_source_id;
        B.bridge.capture_source_id=config.capture_source_id;
    }
    B.bridge.capture_source_id=0u;
    must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_DENIED,
         "T2A_BRIDGE_SOURCE_AUTHORITY_DRIFT"); ++*negative_checks;
    B.bridge.capture_source_id=config.capture_source_id;
    B.recorder.target_frames=0u;
    must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_DENIED,
         "T2A_ZERO_RECORDING_TARGET"); ++*negative_checks;
    B.recorder.target_frames=2u;
    WB.cap_last=2u;
    must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_DENIED,
         "T2A_NONFRESH_WITNESS"); ++*negative_checks;
    WB.cap_last=0u;
    must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_OK,
         "T2A_ACTUAL_INDEPENDENT_EPOCH_RESTART");
    must(R.schema_version==1u && R.owner_acks==required &&
         R.old_generation==1u && R.new_generation==2u &&
         R.old_capture_source_id==A.recorder.config.capture_source_id &&
         R.new_capture_source_id==config.capture_source_id &&
         R.old_recorder_committed==1u && R.old_recorder_target==2u &&
         R.old_recorder_quarantined==1u &&
         R.mic_bf_history_preserved==0u && R.public_sdk_admitted==0u &&
         R.old_processed==1u &&
         R.old_capture_queued==1u &&
         R.old_render_queued==render &&
         R.fresh_capture_epoch==1u &&
         R.fresh_render_epoch==render,
         "T2A_RECEIPT_MISATTRIBUTES_BF_HISTORY");
    must(fe_t2a_session(&G,1u)==NULL && fe_t2a_session(&G,2u)==&WB,
         "T2A_EPOCH_ACCESS_ALIAS"); ++*negative_checks;
    must(fe_t2a_ack_stopped(&G,1u,FE_T2A_CAPTURE_OWNER)==FE_T2A_DENIED,
         "T2A_POSTRESTART_STALE_ACK"); ++*negative_checks;
    must(fe_t2a_restart(&G,1u,&WB,&R)==FE_T2A_DENIED,
         "T2A_DOUBLE_RESTART"); ++*negative_checks;
    must(memcmp(A.q_snapshot,A.qstate,state_size)==0 &&
         memcmp(A.snapshot,A.record,A.recorder.total_bytes)==0 &&
         memcmp(&old_copy,&WA,sizeof(WA))==0,
         "T2A_OLD_SOURCE_MUTATED_AFTER_CUTOVER");
    must(fe_b2s1_get_info(B.queue,&qnew)==FE_B2S1_OK &&
         qnew.processed==0u && qnew.capture_queued==0u,
         "T2A_NEW_SOURCE_NOT_FRESH");
    must(fe_b2s1_get_info(A.queue,&qold)==FE_B2S1_OK &&
         qold.processed==1u,"T2A_OLD_SOURCE_RESET");
    must(fe_s3_t1_capture_submit(&WB,2u,0u,B.capture[0],
                  (size_t)(rate/100u)*sc->mics)==FE_T1_EINVAL,
         "T2A_FRESH_SEQUENCE_SKIP_ACCEPTED"); ++*negative_checks;
    new_source_frame(&B,&WB,1u);
    new_source_frame(&B,&WB,2u);
    must(fe_s3_bridge_finish(&B.bridge,&finished)==FE_S3_OK &&
         finished>FE_S2_HEADER_BYTES,
         "T2A_FRESH_APX3_FINISH");
    must(fe_s2_decode(B.record,finished,&stream)==FE_S2_OK &&
         stream.frames==2u &&
         stream.config.capture_source_id==config.capture_source_id &&
         stream.config.render_source_id==config.render_source_id,
         "T2A_WRONG_NEXT_APX3_SOURCE");
    must(fe_s2_replay(B.record,finished,visitor,&B,NULL)==FE_S2_OK,
         "T2A_REAL_PCM_REPLAY_DIFFERENT");
    must(memcmp(A.q_snapshot,A.qstate,state_size)==0 &&
         memcmp(A.snapshot,A.record,A.recorder.total_bytes)==0,
         "T2A_OLD_APX3_MODIFIED_BY_NEW_SESSION");
    digest=hash(digest,&R.schema_version,sizeof(R.schema_version));
    digest=hash(digest,&R.reason,sizeof(R.reason));
    digest=hash(digest,&R.owner_acks,sizeof(R.owner_acks));
    digest=hash(digest,&R.old_capture_source_id,sizeof(R.old_capture_source_id));
    digest=hash(digest,&R.new_capture_source_id,sizeof(R.new_capture_source_id));
    digest=hash(digest,&R.old_recorder_committed,sizeof(R.old_recorder_committed));
    digest=hash(digest,&R.old_generation,sizeof(R.old_generation));
    digest=hash(digest,&R.new_generation,sizeof(R.new_generation));
    digest=hash(digest,&R.old_processed,sizeof(R.old_processed));
    digest=hash(digest,&rate,sizeof(rate));
    digest=hash(digest,&render,sizeof(render));
    digest=hash(digest,&depth,sizeof(depth));
    digest=hash(digest,&sc->mics,sizeof(sc->mics));
    return digest;
}
int main(void) {
    uint32_t scene, rate, depth, render, profiles=0u, negatives=0u;
    uint64_t result=FNV0;
    printf("{\"schema_version\":1,\"decision\":\"FE09_S3_T2A_NONSEAMLESS_RESTART_CONTROL_ONLY\",\"source_role\":\"first-party-synthetic\",\"actual_postrestart_bf\":true,\"bf_continuity_preserved\":false,\"device_qualified\":false,\"public_sdk_admitted\":false,\"cases\":[");
    for(scene=0u;scene<4u;++scene)
        for(rate=0u;rate<3u;++rate)
            for(render=0u;render<2u;++render)
                for(depth=2u;depth<=4u;depth+=2u) {
                    uint64_t one=one_profile(&SCENES[scene],RATES[rate],
                                             render,depth,&negatives);
                    if(profiles) putchar(',');
                    result^=one;
                    result*=FNV_PRIME;
                    printf("{\"scene\":\"%s\",\"rate\":%u,\"render\":%u,\"depth\":%u,\"control_hash\":\"%016" PRIx64 "\"}",
                           SCENES[scene].name,RATES[rate],render,depth,one);
                    ++profiles;
                }
    must(profiles==48u && negatives>=600u,
         "T2A_CONTROL_NEGATIVE_MATRIX_INCOMPLETE");
    printf("],\"profile_count\":%u,\"negative_checks\":%u,\"digest\":\"%016" PRIx64 "\"}\n",
           profiles,negatives,result);
    return 0;
}
