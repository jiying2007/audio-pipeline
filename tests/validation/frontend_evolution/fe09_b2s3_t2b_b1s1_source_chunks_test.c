/* FE09 B1-S1 #778: genuine original APX3 C codec+replay for each
 * source-owned Capture frame; canonical SHA256 manifest chain, no dummy
 * Render PCM, actual pthread Capture/Render owners, no durable disk I/O.
 * Inputs are FIRST-PARTY SYNTHETIC, not physical ADC source authority.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t2b_b1s1_source_chunks.h"
/* Include only the frozen S3 test geometry/oracle utilities. The
 * predecessor B1-S0 test includes nested #undef main and has a separate
 * complete main(); including that test would define main twice. We reuse
 * the exact frozen *test-only* owner fixture and helper logic below,
 * not any duplicated shipping resampler/BF/codec implementation.
 */
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

static fe_b1s1_store STORE;
static uint32_t NEGATIVES;
static uint64_t CONTROL,FIR_HASH;
static uint8_t SOURCE_SAMPLE[FE_B1S1_MAX_CHUNK_BYTES];
static uint8_t MANIFEST_SAMPLE[FE_B1S1_ROW_BYTES];
static size_t SOURCE_SAMPLE_BYTES;
static void print_hex(const uint8_t *p,size_t n) {
    static const char *digits="0123456789abcdef";
    size_t i;
    for(i=0u;i<n;++i) {
        putchar(digits[p[i]>>4u]);
        putchar(digits[p[i]&15u]);
    }
}

static void must_sha_vector(const uint8_t *bytes,size_t count,
                            const uint8_t expected[32]) {
    uint8_t result[32];
    must(fe_b1s1_sha256(bytes,count,result)==0 &&
         memcmp(result,expected,32u)==0,
         "B1S1_SHA256_FIPS1804_VECTOR_WRONG");
    ++NEGATIVES;
}
static void sha_vectors(void) {
    static const uint8_t empty[32]={
        0xe3,0xb0,0xc4,0x42,0x98,0xfc,0x1c,0x14,
        0x9a,0xfb,0xf4,0xc8,0x99,0x6f,0xb9,0x24,
        0x27,0xae,0x41,0xe4,0x64,0x9b,0x93,0x4c,
        0xa4,0x95,0x99,0x1b,0x78,0x52,0xb8,0x55
    };
    static const uint8_t abc[32]={
        0xba,0x78,0x16,0xbf,0x8f,0x01,0xcf,0xea,
        0x41,0x41,0x40,0xde,0x5d,0xae,0x22,0x23,
        0xb0,0x03,0x61,0xa3,0x96,0x17,0x7a,0x9c,
        0xb4,0x10,0xff,0x61,0xf2,0x00,0x15,0xad
    };
    static const uint8_t text[3]={'a','b','c'};
    uint8_t digest[32];
    must_sha_vector(NULL,0u,empty);
    must_sha_vector(text,sizeof(text),abc);
    must(fe_b1s1_sha256(NULL,1u,digest)!=0 &&
         fe_b1s1_sha256(text,1048577u,digest)!=0 &&
         fe_b1s1_sha256(text,1u,NULL)!=0,
         "B1S1_SHA256_BOUND_OR_NULL_ACCEPTED");
    NEGATIVES+=3u;
}
static void *chunk_worker(void *unused) {
    uint32_t k;
    float beam[160],reference[160],direct[160],reforacle[160];
    _Alignas(16) uint8_t work[B1_WORK];
    (void)unused;
    for(k=1u;k<=B1_FRAMES;++k) {
        int16_t cap[1920],ref[480];
        fe_b1s0_receipt receipt;
        uint32_t spin=0u;
        fe_b1s1_status status;
        size_t n=(size_t)(P.rate/100u)*P.scene->mics;
        uint32_t actual=P.render&&!absent_at(k);
        produce_pcm(P.scene,P.rate,k,cap,ref);
        for(;;) {
            for(size_t i=0u;i<160u;++i) reference[i]=-193.0f;
            memset(&receipt,0x59,sizeof(receipt));
            status=fe_b1s1_append_one(&STORE,beam,160u,
                      P.render?reference:NULL,P.render?160u:0u,
                      work,sizeof(work),&receipt);
            if(status==FE_B1S1_OK) break;
            if(status!=FE_B1S1_PENDING||++spin>=B1_WAIT) {
                atomic_store_explicit(&P.failed,20u,memory_order_release);
                return NULL;
            }
            sched_yield();
        }
        if(STORE.committed!=k||STORE.last_global_capture!=k||
           P.q.processed!=k||receipt.capture_sequence!=k||
           receipt.capture_pcm_hash!=expected_pcm_hash(cap,n)||
           receipt.source_generation!=P.cfg.source_generation||
           receipt.reference_actual_pcm!=actual||
           receipt.recorder_qualified||receipt.source_clock_known ||
           receipt.device_qualified||receipt.public_sdk_qualified) {
            atomic_store_explicit(&P.failed,21u,memory_order_release);
            return NULL;
        }
        if(fe_b1b1_process(P.oracle,cap,n,NULL,0u,
             direct,160u,NULL,0u,P.oracle_work,sizeof(P.oracle_work))!=
             FE_B1B1_OK||memcmp(beam,direct,sizeof(direct))!=0) {
            atomic_store_explicit(&P.failed,22u,memory_order_release);
            return NULL;
        }
        FIR_HASH=hash(FIR_HASH,beam,sizeof(beam));
        if(P.render) {
            if(actual) {
                uint32_t gap=0u;
                if(P.actual_reference_ordinal&&k>1u&&absent_at(k-1u))
                    gap=1u;
                if(gap) ap_resampler_reset(&P.expected_reference);
                ap_resample_input_channel(&P.expected_reference,0u,
                     ref,P.rate/100u,1u,0u,reforacle,160u);
                ++P.actual_reference_ordinal;
                if(receipt.render_event!=FE_B1S0_RENDER_PRESENT ||
                   receipt.render_pcm_hash!=
                        expected_pcm_hash(ref,(size_t)P.rate/100u)||
                   memcmp(reference,reforacle,sizeof(reference))!=0) {
                    atomic_store_explicit(&P.failed,23u,memory_order_release);
                    return NULL;
                }
            } else {
                if(receipt.render_event!=FE_B1S0_RENDER_ABSENT||
                   receipt.render_reason!=FE_B1S0_ABSENT_SOURCE_REPORTED||
                   receipt.render_pcm_hash) {
                    atomic_store_explicit(&P.failed,24u,memory_order_release);
                    return NULL;
                }
                for(size_t i=0u;i<160u;++i)
                    if(reference[i]!=-193.0f) {
                        atomic_store_explicit(&P.failed,25u,memory_order_release);
                        return NULL;
                    }
            }
        } else if(receipt.render_event!=FE_B1S0_RENDER_DISABLED||
                  receipt.render_pcm_hash) {
            atomic_store_explicit(&P.failed,26u,memory_order_release);
            return NULL;
        }
        CONTROL=hash(CONTROL,&receipt.capture_sequence,
                      sizeof(receipt.capture_sequence));
        CONTROL=hash(CONTROL,&receipt.render_event,
                      sizeof(receipt.render_event));
        CONTROL=hash(CONTROL,STORE.manifest[k-1u]+
                      FE_B1S1_ROW_DIGEST_OFFSET,32u);
        atomic_store_explicit(&P.processed,k,memory_order_release);
    }
    return NULL;
}
static void tamper_one(uint8_t *field,uint8_t mask) {
    uint8_t old=*field;
    uint32_t checked=UINT32_C(0x89abcdef);
    *field^=mask;
    must(fe_b1s1_verify(&STORE,&checked)==FE_B1S1_TAMPER &&
         checked==UINT32_C(0x89abcdef),
         "B1S1_TAMPER_OR_PARTIAL_VERIFICATION_PROMOTED");
    *field=old;
    ++NEGATIVES;
}
static void negative_replay_matrix(void) {
    uint32_t verified=0u;
    uint32_t last=STORE.committed-1u;
    uint32_t first=0u;
    uint32_t old_length=STORE.chunk_bytes[0];
    uint64_t old_seq=STORE.last_global_capture;
    uint32_t old_count=STORE.committed;
    must(fe_b1s1_verify(&STORE,&verified)==FE_B1S1_OK &&
         verified==B1_FRAMES,"B1S1_ORIGINAL_APX3_REPLAY_FAIL");
    tamper_one(&STORE.chunks[first][0],0x01u); /* APX3 header + CRC */
    tamper_one(&STORE.chunks[last][STORE.chunk_bytes[last]-1u],0x01u);
    tamper_one(&STORE.chunks[last][FE_S2_HEADER_BYTES+
          FE_S2_RECORD_META_BYTES+4u],0x80u); /* actual first-party PCM */
    tamper_one(&STORE.manifest[first][0],0x01u); /* Magic */
    tamper_one(&STORE.manifest[first][48u],0x01u); /* Global seq mapping */
    tamper_one(&STORE.manifest[last][56u],0x04u); /* APX3 local seq */
    tamper_one(&STORE.manifest[last][88u],0x04u); /* Slot identity */
    tamper_one(&STORE.manifest[last][104u],0x04u); /* Chunk digest */
    tamper_one(&STORE.manifest[last][136u],0x04u); /* Previous row link */
    tamper_one(&STORE.manifest[last][168u],0x04u); /* Own row SHA */
    tamper_one(&STORE.manifest[last][44u],0x04u); /* Source reason */
    tamper_one(&STORE.manifest[last][80u],0x04u); /* Real Render hash */
    STORE.chunk_bytes[0]=old_length-1u;
    verified=0x89abcdefu;
    must(fe_b1s1_verify(&STORE,&verified)==FE_B1S1_TAMPER &&
         verified==0x89abcdefu,"B1S1_TRUNCATION_ACCEPTED");
    STORE.chunk_bytes[0]=old_length;++NEGATIVES;
    STORE.last_global_capture=UINT64_MAX;
    must(fe_b1s1_verify(&STORE,&verified)==FE_B1S1_REJECT,
         "B1S1_GLOBAL_SEQUENCE_OVERFLOW_ACCEPTED");
    STORE.last_global_capture=old_seq;++NEGATIVES;
    STORE.committed=old_count-1u;
    must(fe_b1s1_verify(&STORE,&verified)==FE_B1S1_REJECT,
         "B1S1_MISSING_LAST_CHUNK_ACCEPTED");
    STORE.committed=old_count;++NEGATIVES;
    /* Adversarial coordinated rollback of BOTH sidecar high-water fields
     * must not make the source's already committed 24th BF/PCM disappear.
     */
    STORE.committed=old_count-1u;
    STORE.last_global_capture=old_seq-1u;
    verified=UINT32_C(0x89abcdef);
    must(fe_b1s1_verify(&STORE,&verified)==FE_B1S1_REJECT &&
         verified==UINT32_C(0x89abcdef),
         "B1S1_COORDINATED_ROLLBACK_FALSE_COMPLETE");
    STORE.committed=old_count;
    STORE.last_global_capture=old_seq;
    ++NEGATIVES;
    must(fe_b1s1_verify(&STORE,&verified)==FE_B1S1_OK &&
         verified==old_count,
         "B1S1_TAMPER_RECOVERY_NO_ORIGINAL_REPLAY");
}
static uint32_t faulted_first_party_capture_is_atomic(void) {
    uint8_t prior_manifest[FE_B1S1_ROW_BYTES];
    uint8_t prior_chunk[FE_B1S1_MAX_CHUNK_BYTES];
    uint32_t slots[4]={1u,0u,UINT32_MAX,UINT32_MAX};
    int16_t cap[1920],refpcm[480];
    float beam[160],reference[160],beam_before[160],ref_before[160];
    fe_b1s0_receipt receipt,prior_receipt;
    fe_t2b_b0 adapter_before;
    uint8_t core_before[B1_STATE];
    uint32_t k;
    _Alignas(16) uint8_t work[B1_WORK];
    memset(&P,0,sizeof(P));
    first_party_oracle_init(&SCENES[1],16000u,2u,1u);
    must(fe_b1s1_init(&STORE,&P.q,slots)==FE_B1S1_OK,
         "B1S1_FAULT_FIXTURE_SINK_INIT");
    produce_pcm(P.scene,P.rate,1u,cap,refpcm);
    must(fe_b1s0_capture_submit(&P.q,P.cfg.capture_source_id,
         P.cfg.source_generation,1u,cap,320u)==FE_B1S0_OK &&
         fe_b1s0_render_present(&P.q,P.cfg.render_source_id,
         P.cfg.source_generation,1u,1u,0u,refpcm,160u)==FE_B1S0_OK,
         "B1S1_FAULT_FIXTURE_REAL_OWNER_PCM");
    memcpy(prior_manifest,STORE.manifest[0],sizeof(prior_manifest));
    memcpy(prior_chunk,STORE.chunks[0],sizeof(prior_chunk));
    adapter_before=P.adapter;
    memset(beam,0x4a,sizeof(beam));
    memset(reference,0x4b,sizeof(reference));
    memset(&receipt,0x4c,sizeof(receipt));
    memcpy(beam_before,beam,sizeof(beam));
    memcpy(ref_before,reference,sizeof(reference));
    memcpy(&prior_receipt,&receipt,sizeof(receipt));
    P.core_state[0]^=0x49u;
    memcpy(core_before,P.core_state,sizeof(core_before));
    must(fe_b1s1_append_one(&STORE,beam,160u,reference,160u,
          work,sizeof(work),&receipt)==FE_B1S1_CORE &&
         STORE.committed==0u&&STORE.last_global_capture==0u &&
         P.q.processed==0u&&P.adapter.accepted_capture==0u &&
         P.adapter.accepted_render==0u &&
         memcmp(prior_manifest,STORE.manifest[0],sizeof(prior_manifest))==0 &&
         memcmp(prior_chunk,STORE.chunks[0],sizeof(prior_chunk))==0 &&
         memcmp(&adapter_before,&P.adapter,sizeof(adapter_before))==0 &&
         memcmp(core_before,P.core_state,sizeof(core_before))==0 &&
         memcmp(beam_before,beam,sizeof(beam))==0 &&
         memcmp(ref_before,reference,sizeof(reference))==0 &&
         memcmp(&prior_receipt,&receipt,sizeof(receipt))==0,
         "B1S1_FAILED_CORE_PARTIALLY_COMMITTED_RECORD");
    P.core_state[0]^=0x49u;
    must(fe_b1s1_append_one(&STORE,beam,160u,reference,160u,
          work,sizeof(work),&receipt)==FE_B1S1_OK &&
         STORE.committed==1u&&P.q.processed==1u,
         "B1S1_RECOVERY_OF_EXACT_SOURCE_AFTER_CORE_FAULT");
    must(fe_b1s1_verify(&STORE,&k)==FE_B1S1_OK&&k==1u,
         "B1S1_RECOVERED_RECORD_NOT_EXACT_APX3");
    return 1u;
}
static uint64_t one(const scene_t *sc,uint32_t rate,
                    uint32_t depth,uint32_t render,uint64_t *beam_digest) {
    uint32_t slots[4],k,negative_start=NEGATIVES;
    uint64_t digest;
    pthread_t capture,ref,worker;
    owner_arg ca={0u},ra={1u};
    _Alignas(16) uint8_t work[B1_WORK];
    float beam[160],refout[160];
    fe_b1s0_receipt receipt;
    (void)work;
    memset(&P,0,sizeof(P));
    first_party_oracle_init(sc,rate,depth,render);
    for(k=0u;k<4u;++k)
        slots[k]=k<sc->mics?sc->slots[k]:UINT32_MAX;
    must(fe_b1s1_init(&STORE,&P.q,slots)==FE_B1S1_OK,
         "B1S1_EXACT_PHYSICAL_SLOT_BIND");
    /* Actual producer-owned source frames are in queues, not regenerated
     * by the APX3 sink; this is only the independent BF test oracle.
     */
    must(pthread_create(&capture,NULL,source_thread,&ca)==0,
         "B1S1_CAPTURE_PTHREAD_STARTED");
    wait_counter(&P.cap_full,1u,"B1S1_CAPTURE_RING_FULL_BACKPRESSURE");
    if(render) {
        uint8_t before[B1_STATE];
        memcpy(before,P.core_state,sizeof(before));
        memset(beam,0x24,sizeof(beam));
        memset(refout,0x25,sizeof(refout));
        memset(&receipt,0x26,sizeof(receipt));
        must(fe_b1s1_append_one(&STORE,beam,160u,refout,160u,
              work,sizeof(work),&receipt)==FE_B1S1_PENDING &&
             STORE.committed==0u&&P.q.processed==0u &&
             memcmp(before,P.core_state,sizeof(before))==0,
             "B1S1_PENDING_RENDER_MISCLASSIFIED_AS_ABSENT");
        ++NEGATIVES;
        must(pthread_create(&ref,NULL,source_thread,&ra)==0,
             "B1S1_RENDER_EVENT_OWNER_PTHREAD");
        wait_counter(&P.ref_full,1u,"B1S1_RENDER_OWNER_QUEUE_NOT_FULL");
    }
    CONTROL=FNV0;FIR_HASH=FNV0;
    must(pthread_create(&worker,NULL,chunk_worker,NULL)==0,
         "B1S1_APX3_WORKER_PTHREAD");
    must(pthread_join(capture,NULL)==0,"B1S1_CAPTURE_JOIN");
    if(render)must(pthread_join(ref,NULL)==0,"B1S1_RENDER_JOIN");
    must(pthread_join(worker,NULL)==0,"B1S1_WORKER_JOIN");
    must(atomic_load_explicit(&P.failed,memory_order_acquire)==0u &&
         P.q.processed==B1_FRAMES && STORE.committed==B1_FRAMES &&
         STORE.last_global_capture==B1_FRAMES &&
         P.adapter.accepted_capture==B1_FRAMES &&
         P.adapter.accepted_render==P.q.actual_render_frames,
         "B1S1_REAL_OWNER_PCMC_BF_CHUNKS_NOT_CONCURRENT");
    negative_replay_matrix();
    digest=CONTROL;
    digest=hash(digest,&rate,sizeof(rate));
    digest=hash(digest,&depth,sizeof(depth));
    digest=hash(digest,&render,sizeof(render));
    digest=hash(digest,&sc->mics,sizeof(sc->mics));
    digest=hash(digest,STORE.manifest[B1_FRAMES-1u]+
                FE_B1S1_ROW_DIGEST_OFFSET,32u);
    *beam_digest=FIR_HASH;
    must(NEGATIVES>=negative_start+15u,
         "B1S1_TRUE_NEGATIVE_CONTROLS_INCOMPLETE");
    return digest;
}
int main(void) {
    uint32_t i,j,d,r,profiles=0u;
    uint64_t digest=FNV0;
    sha_vectors();
    NEGATIVES+=faulted_first_party_capture_is_atomic();
    printf("{\"schema_version\":1,\"decision\":\"FE09_T2B_B1S1_SOURCE_EXACT_ONE_FRAME_APX3_CHUNKS_NO_DURABILITY\",\"source_role\":\"first-party-synthetic\",\"real_original_s2_codec\":true,\"real_capture_source_before_queue_tail\":true,\"chunk_hash_chain_verified\":true,\"apx3_chunks_replayed\":true,\"physical_clock_qualified\":false,\"durable_io_qualified\":false,\"ssc305_device_qualified\":false,\"public_sdk_installed\":false,\"profiles\":[");
    for(i=0u;i<4u;++i)for(j=0u;j<3u;++j)
      for(d=2u;d<=4u;d+=2u)for(r=0u;r<2u;++r) {
        uint64_t bh=0u;
        uint64_t one_hash=one(&SCENES[i],RATES[j],d,r,&bh);
        if(i==3u&&j==2u&&d==4u&&r==1u) {
            SOURCE_SAMPLE_BYTES=STORE.chunk_bytes[B1_FRAMES-1u];
            must(SOURCE_SAMPLE_BYTES>0u&&
                 SOURCE_SAMPLE_BYTES<=FE_B1S1_MAX_CHUNK_BYTES,
                 "B1S1_SAMPLE_BOUNDS");
            memcpy(SOURCE_SAMPLE,STORE.chunks[B1_FRAMES-1u],
                   SOURCE_SAMPLE_BYTES);
            memcpy(MANIFEST_SAMPLE,STORE.manifest[B1_FRAMES-1u],
                   FE_B1S1_ROW_BYTES);
        }
        if(profiles) putchar(',');
        digest=(digest^one_hash)*FNV_PRIME;
        printf("{\"scene\":\"%s\",\"rate\":%u,\"render_enabled\":%u,\"depth\":%u,\"frames\":%u,\"chunk_count\":%u,\"control_hash\":\"%016" PRIx64 "\",\"bf_hash\":\"%016" PRIx64 "\"}",
             SCENES[i].name,RATES[j],r,d,B1_FRAMES,STORE.committed,
             one_hash,bh);
        ++profiles;
      }
    must(profiles==48u&&NEGATIVES>=720u,
         "B1S1_REAL_CODEC_REPLAY_NEGATIVE_MATRIX_NOT_COMPLETE");
    must(SOURCE_SAMPLE_BYTES>0u,"B1S1_C_SAMPLE_NOT_CAPTURED");
    printf("],\"profile_count\":%u,\"negative_checks\":%u,\"control_digest\":\"%016" PRIx64 "\",\"source_chunk_hex\":\"",
           profiles,NEGATIVES,digest);
    print_hex(SOURCE_SAMPLE,SOURCE_SAMPLE_BYTES);
    printf("\",\"source_manifest_hex\":\"");
    print_hex(MANIFEST_SAMPLE,FE_B1S1_ROW_BYTES);
    printf("\"}\n");
    return 0;
}
