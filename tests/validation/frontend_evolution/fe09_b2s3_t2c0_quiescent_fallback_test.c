/* #784 first-party real Capture BF/APX3 before and after logical ACK gate.
 * Hosted first-party synthetic only. No physical stopped-owner proof.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t2c0_quiescent_fallback.h"
#define main fe_s3_t0_reference_main_unused
#include "fe09_b2s3_threaded_bridge_test.c"
#undef main

#include <inttypes.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define B1_STATE 16384u
#define B1_WORK 32768u

/* Test-only independently calculated LE PCM source witness. */
static uint64_t expected_pcm_hash(const int16_t *pcm, size_t samples) {
    uint64_t out = UINT64_C(14695981039346656037);
    size_t i;
    for (i = 0u; i < samples; ++i) {
        uint16_t bits = (uint16_t)pcm[i];
        out = (out ^ (uint8_t)bits) * UINT64_C(1099511628211);
        out = (out ^ (uint8_t)(bits >> 8u)) * UINT64_C(1099511628211);
    }
    return out;
}

typedef struct {
    fe_b1s0_state q;
    fe_b1s0_config cfg;
    fe_t2b_b0 adapter;
    fe_b1b1 *core;
    _Alignas(16) uint8_t core_state[B1_STATE], work[B1_WORK];
    fe_b1s1_store archive;
    fe_t2c0_session session;
} t2c0_fixture;

static t2c0_fixture OLD, FRESH;
static fe_t2c0_gate GATE;
static uint32_t BAD_CASES;
static _Alignas(16) uint8_t ORACLE_STATE[B1_STATE], ORACLE_WORK[B1_WORK];

static void build(t2c0_fixture *f, const scene_t *sc, uint32_t rate,
                  uint32_t depth, uint32_t render, uint64_t generation,
                  uint32_t cap_id, uint32_t ref_id) {
    fe_b1b1_config bc = config_for(sc, rate, 0u, depth).pipeline;
    uint32_t slots[4], k;
    size_t state = fe_b1b1_state_bytes(&bc);
    memset(f, 0, sizeof(*f));
    must(state > 0u && state <= B1_STATE &&
         fe_b1b1_work_bytes(&bc) <= B1_WORK &&
         fe_b1b1_init(f->core_state, state, &bc, &f->core)
         == FE_B1B1_OK, "T2C0_FIRST_PARTY_BF_INIT");
    must(fe_t2b_b0_bind(&f->adapter, f->core, rate, sc->mics)
         == FE_T2B_B0_OK, "T2C0_REAL_B0_BIND");
    f->cfg.depth = depth;
    f->cfg.physical_mics = sc->mics;
    f->cfg.input_hz = rate;
    f->cfg.render_enabled = render;
    f->cfg.capture_source_id = cap_id;
    f->cfg.render_source_id = ref_id;
    f->cfg.source_generation = generation;
    must(fe_b1s0_init(&f->q, &f->cfg, &f->adapter) == FE_B1S0_OK,
         "T2C0_REAL_OWNER_QUEUE_INIT");
    for (k = 0u; k < 4u; ++k)
        slots[k] = k < sc->mics ? sc->slots[k] : UINT32_MAX;
    must(fe_b1s1_init(&f->archive, &f->q, slots) == FE_B1S1_OK,
         "T2C0_ORIGINAL_APX3_SINK_INIT");
    f->session.source = &f->q;
    f->session.archive = &f->archive;
}
static void real_frame(t2c0_fixture *f, const scene_t *sc,
                       uint32_t rate, uint64_t seq, float *beam) {
    int16_t capture[1920], render[480];
    float reference[160];
    fe_b1s0_receipt actual;
    uint32_t verified = 0u;
    produce_pcm(sc, rate, (uint32_t)seq, capture, render);
    must(fe_b1s0_capture_submit(&f->q, f->cfg.capture_source_id,
         f->cfg.source_generation, seq, capture,
         (size_t)(rate/100u)*sc->mics) == FE_B1S0_OK,
         "T2C0_ACTUAL_CAPTURE_SOURCE");
    if (f->cfg.render_enabled)
        must(fe_b1s0_render_present(&f->q, f->cfg.render_source_id,
             f->cfg.source_generation, seq, 1u, 0u,
             render, (size_t)rate/100u) == FE_B1S0_OK,
             "T2C0_REAL_RENDER_SOURCE");
    must(fe_b1s1_append_one(&f->archive, beam, 160u,
         f->cfg.render_enabled ? reference : NULL,
         f->cfg.render_enabled ? 160u : 0u,
         f->work, sizeof(f->work), &actual) == FE_B1S1_OK,
         "T2C0_ORIGINAL_BF_APX3_COMMIT");
    must(actual.capture_sequence == seq &&
         actual.source_generation == f->cfg.source_generation &&
         actual.capture_pcm_hash == expected_pcm_hash(
             capture, (size_t)(rate/100u)*sc->mics) &&
         actual.mic_bf_progressed == 1u &&
         actual.source_clock_known == 0u &&
         actual.recorder_qualified == 0u &&
         actual.device_qualified == 0u &&
         actual.public_sdk_qualified == 0u &&
         fe_b1s1_verify(&f->archive, &verified) == FE_B1S1_OK &&
         verified == (uint32_t)seq, "T2C0_SOURCE_REPLAY_EXACT");
}
static void must_denied(fe_t2c0_status status, const char *why) {
    must(status != FE_T2C0_OK, why);
    ++BAD_CASES;
}
typedef struct {
    uint64_t gen;
    uint32_t owner;
    fe_t2c0_status result;
} ack_t;
static void *ack_worker(void *opaque) {
    ack_t *arg = (ack_t *)opaque;
    arg->result = fe_t2c0_ack(&GATE, arg->gen, arg->owner);
    return NULL;
}
static uint64_t one(const scene_t *sc, uint32_t rate,
                    uint32_t depth, uint32_t next_render,
                    uint64_t *beam_hash) {
    const uint64_t generation = UINT64_C(900001);
    const uint32_t old_cap = 101u+sc->mics, old_ref = 201u+sc->mics;
    const uint32_t new_cap = 301u+sc->mics;
    const uint32_t new_ref = next_render ? (401u+sc->mics):0u;
    fe_t2c0_receipt rec;
    uint8_t oldq[32], oldstore[32], oldbf[32], now[32];
    fe_b1b1_config cfg = config_for(sc, rate, 0u, depth).pipeline;
    fe_b1b1 *oracle = NULL;
    float before[160], after[160], direct[160];
    int16_t cap[1920], ref[480];
    fe_b1s0_receipt fake;
    ack_t args[3];
    pthread_t threads[3];
    uint32_t k, prior = BAD_CASES;
    uint64_t h = FNV0;
    build(&OLD, sc, rate, depth, 1u, generation, old_cap, old_ref);
    real_frame(&OLD, sc, rate, 1u, before);
    /* Frozen source emits a real second Capture, but no Render event:
     * B1 must remain PENDING, and cannot fill or commit fake audio.
     */
    produce_pcm(sc, rate, 2u, cap, ref);
    must(fe_b1s0_capture_submit(&OLD.q, old_cap, generation, 2u, cap,
         (size_t)(rate/100u)*sc->mics) == FE_B1S0_OK,
         "T2C0_OLD_SECOND_CAPTURE_REALLY_PENDING");
    must(fe_b1s1_append_one(&OLD.archive, before, 160u, direct, 160u,
         OLD.work, sizeof(OLD.work), &fake) == FE_B1S1_PENDING &&
         OLD.q.processed == 1u && OLD.archive.committed == 1u,
         "T2C0_NO_TOKEN_CANNOT_FAKE_RENDER_ABSENT");
    ++BAD_CASES;
    build(&FRESH, sc, rate, depth, next_render, generation+1u,
          new_cap, new_ref);
    must(fe_t2c0_init(&GATE, &OLD.session) == FE_T2C0_OK &&
         fe_t2c0_current(&GATE, generation) == &OLD.session,
         "T2C0_NEW_GATE_INITIAL_SESSION");
    memset(&rec, 0xa5, sizeof(rec));
    must_denied(fe_t2c0_restart(&GATE, generation, &FRESH.session, &rec),
                "T2C0_RESTART_WITHOUT_STOP");
    must_denied(fe_t2c0_request_stop(&GATE, generation+1u,
                 FE_T2C0_REASON_RENDER_OWNER_UNAVAILABLE),
                "T2C0_WRONG_GENERATION_STOP");
    must(fe_t2c0_request_stop(&GATE, generation,
         FE_T2C0_REASON_RENDER_OWNER_UNAVAILABLE) == FE_T2C0_OK &&
         fe_t2c0_current(&GATE, generation) == NULL,
         "T2C0_STOP_INVALIDATES_OLD_PUBLIC_SESSION");
    must_denied(fe_t2c0_request_stop(&GATE, generation,
                 FE_T2C0_REASON_RENDER_OWNER_UNAVAILABLE),
                "T2C0_DUPLICATE_STOP");
    must_denied(fe_t2c0_ack(&GATE, generation+1u,
                 FE_T2C0_CAPTURE_OWNER), "T2C0_WRONG_GENERATION_ACK");
    must_denied(fe_t2c0_ack(&GATE, generation, 8u),
                "T2C0_UNAUTHORIZED_OWNER_ACK");
    must_denied(fe_t2c0_ack(&GATE, generation, 0u),
                "T2C0_ZERO_OWNER_ACK");
    must_denied(fe_t2c0_ack(&GATE, generation,
                 FE_T2C0_CAPTURE_OWNER | FE_T2C0_WORKER_OWNER),
                "T2C0_MULTIPLE_OWNER_SPOOF");
    must_denied(fe_t2c0_restart(&GATE, generation, &FRESH.session, &rec),
                "T2C0_MISSING_ACK_BLOCKS_RECOVERY");
    for (k = 0u; k < 3u; ++k) {
        args[k].gen = generation;
        args[k].owner = (1u << k);
        args[k].result = FE_T2C0_DENIED;
        must(pthread_create(&threads[k], NULL, ack_worker, &args[k]) == 0,
             "T2C0_OWNER_ACK_THREAD_STARTED");
    }
    for (k = 0u; k < 3u; ++k) {
        must(pthread_join(threads[k], NULL) == 0 &&
             args[k].result == FE_T2C0_OK,
             "T2C0_THREE_ATOMIC_OWNER_ACKS");
    }
    must_denied(fe_t2c0_ack(&GATE, generation, FE_T2C0_RENDER_OWNER),
                "T2C0_DUPLICATE_ACK");
    must_denied(fe_t2c0_restart(&GATE, generation, &OLD.session, &rec),
                "T2C0_IN_PLACE_OLD_SESSION_RESTART");
    must_denied(fe_t2c0_restart(&GATE, generation+1u,
                 &FRESH.session, &rec), "T2C0_WRONG_RESTART_GENERATION");
    ++FRESH.q.cfg.source_generation;
    must_denied(fe_t2c0_restart(&GATE, generation, &FRESH.session, &rec),
                "T2C0_NONCONSECUTIVE_GENERATION");
    --FRESH.q.cfg.source_generation;
    FRESH.q.cfg.capture_source_id = old_cap;
    must_denied(fe_t2c0_restart(&GATE, generation, &FRESH.session, &rec),
                "T2C0_REUSED_SOURCE_ID");
    FRESH.q.cfg.capture_source_id = new_cap;
    FRESH.archive.physical_to_slot[0] = UINT32_MAX;
    must_denied(fe_t2c0_restart(&GATE, generation, &FRESH.session, &rec),
                "T2C0_CHANGED_PHYSICAL_TO_PCM_SLOT");
    FRESH.archive.physical_to_slot[0] = sc->slots[0];
    FRESH.q.cap_last = 1u;
    must_denied(fe_t2c0_restart(&GATE, generation, &FRESH.session, &rec),
                "T2C0_DIRTY_NEXT_SOURCE");
    FRESH.q.cap_last = 0u;
    must(fe_b1s1_sha256((const uint8_t *)&OLD.q, sizeof(OLD.q), oldq) == 0 &&
         fe_b1s1_sha256((const uint8_t *)&OLD.archive, sizeof(OLD.archive), oldstore) == 0 &&
         fe_b1s1_sha256(OLD.core_state, sizeof(OLD.core_state), oldbf) == 0,
         "T2C0_OLD_SOURCE_HASH_BEFORE_COMMIT");
    must(fe_t2c0_restart(&GATE, generation,
         &FRESH.session, &rec) == FE_T2C0_OK &&
         rec.schema_version == 1u &&
         rec.reason == FE_T2C0_REASON_RENDER_OWNER_UNAVAILABLE &&
         rec.owners_acknowledged == 7u &&
         rec.old_generation == generation &&
         rec.new_generation == generation+1u &&
         rec.old_processed_capture == 1u &&
         rec.old_source_capture_submitted == 2u &&
         rec.old_render_source_submitted == 1u &&
         rec.old_completed_apx3_chunks == 1u &&
         rec.quarantined_capture_frames == 1u &&
         rec.quarantined_render_events == 0u &&
         rec.lost_capture_start == 2u && rec.lost_capture_end == 2u &&
         rec.old_archival_durable == 0u &&
         rec.physical_clock_known == 0u &&
         rec.capture_bf_history_preserved == 0u &&
         rec.public_sdk_admitted == 0u &&
         rec.new_render_enabled == next_render &&
         rec.new_capture_source_id == new_cap &&
         rec.new_render_source_id == new_ref &&
         memcmp(rec.previous_committed_row_sha256,
                OLD.archive.manifest[0]+FE_B1S1_ROW_DIGEST_OFFSET,32u)==0,
         "T2C0_NON_SEAMLESS_RECOVERY_LOSS_RECEIPT");
    must(fe_t2c0_current(&GATE, generation) == NULL &&
         fe_t2c0_current(&GATE, generation+1u) == &FRESH.session,
         "T2C0_ATOMIC_NEW_GENERATION_PUBLICATION");
    must_denied(fe_t2c0_ack(&GATE, generation, FE_T2C0_CAPTURE_OWNER),
                "T2C0_OLD_GENERATION_ACK_CANNOT_RESUME");
    must(fe_b1s1_sha256((const uint8_t *)&OLD.q, sizeof(OLD.q), now) == 0 &&
         memcmp(now,oldq,32u)==0 &&
         fe_b1s1_sha256((const uint8_t *)&OLD.archive, sizeof(OLD.archive), now)==0 &&
         memcmp(now,oldstore,32u)==0 &&
         fe_b1s1_sha256(OLD.core_state,sizeof(OLD.core_state),now)==0 &&
         memcmp(now,oldbf,32u)==0,
         "T2C0_RESTART_MUTATED_FROZEN_OLD_SOURCE");
    real_frame(&FRESH, sc, rate, 1u, after);
    produce_pcm(sc, rate, 1u, cap, ref);
    must(fe_b1b1_init(ORACLE_STATE, fe_b1b1_state_bytes(&cfg),
                      &cfg, &oracle) == FE_B1B1_OK &&
         fe_b1b1_process(oracle, cap,
             (size_t)(rate/100u)*sc->mics, NULL, 0u,
             direct, 160u, NULL, 0u, ORACLE_WORK,
             sizeof(ORACLE_WORK)) == FE_B1B1_OK &&
         memcmp(after,direct,sizeof(after))==0,
         "T2C0_RESTART_FRESH_REAL_FIRST_PARTY_MIC_BF_NOT_EQUIVALENT");
    must(fe_b1s1_verify(&FRESH.archive,&k)==FE_B1S1_OK && k==1u &&
         fe_b1s1_verify(&OLD.archive,&k)==FE_B1S1_OK && k==1u,
         "T2C0_OLD_AND_FRESH_SOURCE_APX3_REPLAY_FAIL");
    h = hash(h, &rec.old_generation, sizeof(rec.old_generation));
    h = hash(h, &rec.new_generation, sizeof(rec.new_generation));
    h = hash(h, &rec.quarantined_capture_frames,
             sizeof(rec.quarantined_capture_frames));
    h = hash(h, &rec.old_capture_source_id,
             sizeof(rec.old_capture_source_id));
    h = hash(h, &rec.new_capture_source_id,
             sizeof(rec.new_capture_source_id));
    h = hash(h, &next_render, sizeof(next_render));
    h = hash(h, FRESH.archive.manifest[0]+FE_B1S1_ROW_DIGEST_OFFSET,32u);
    *beam_hash = hash(FNV0, after, sizeof(after));
    must(BAD_CASES>=prior+13u, "T2C0_INSUFFICIENT_EXECUTED_NEGATIVES");
    return h;
}
int main(void) {
    uint32_t i,j,d,r,count=0u;
    uint64_t digest=FNV0;
    printf("{\"schema_version\":1,\"decision\":\"FE09_T2C0_LOGICAL_OWNER_ACK_NONSEAMLESS_FALLBACK_NO_PHYSICAL_AUTHORITY\","
           "\"source_role\":\"first-party-synthetic\",\"real_first_party_bf_and_apx3\":true,"
           "\"logical_owner_ack_qualified\":true,\"physical_owner_stop_verified\":false,"
           "\"capture_bf_history_preserved\":false,\"durable_archive_qualified\":false,"
           "\"ssc305_device_qualified\":false,\"public_sdk_installed\":false,\"profiles\":[");
    for(i=0u;i<4u;++i)for(j=0u;j<3u;++j)
      for(d=2u;d<=4u;d+=2u)for(r=0u;r<2u;++r) {
        uint64_t beam=0u,h=one(&SCENES[i],RATES[j],d,r,&beam);
        if(count)putchar(',');
        digest=(digest^h)*FNV_PRIME;
        printf("{\"scene\":\"%s\",\"rate\":%u,\"depth\":%u,"
               "\"new_render\":%u,\"old_apx3\":1,\"fresh_apx3\":1,"
               "\"quarantined_capture\":1,\"control_hash\":\"%016" PRIx64 "\","
               "\"beam_hash\":\"%016" PRIx64 "\"}",
               SCENES[i].name,RATES[j],d,r,h,beam);
        ++count;
      }
    must(count==48u && BAD_CASES>=624u,
         "T2C0_SOURCE_OWNER_GATES_OR_PROFILE_MATRIX_NOT_EXECUTED");
    printf("],\"profile_count\":%u,\"negative_checks\":%u,"
           "\"control_digest\":\"%016" PRIx64 "\"}\n",
           count,BAD_CASES,digest);
    return 0;
}
