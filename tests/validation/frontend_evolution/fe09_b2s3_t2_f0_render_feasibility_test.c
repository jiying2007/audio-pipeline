/* FE09 B2-S3 T2-F0 (#766): executable negative reachability audit.
 * Frozen S1 actual C is included only into this NONINSTALLED test unit.
 * No fake recovery success, no private S1 state mutations except its own
 * documented initialization / legitimate submit/consume functions.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s1_private_queue.c"
#define main fe_s3_t0_reference_main_unused
#include "fe09_b2s3_threaded_bridge_test.c"
#undef main

#include <inttypes.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    fe_b2s1_queue *q;
    uint64_t sequence;
    uint32_t flags;
    int render;
    const int16_t *pcm;
    size_t count;
    fe_b2s1_status outcome;
} f0_producer;

static void *submit_thread(void *context) {
    f0_producer *p = (f0_producer *)context;
    p->outcome = p->render ?
        fe_b2s1_submit_render(p->q, p->sequence, p->flags,
                             p->pcm, p->count) :
        fe_b2s1_submit_capture(p->q, p->sequence, p->flags,
                              p->pcm, p->count);
    return NULL;
}
static uint64_t f0_hash(uint64_t value, uint32_t scenario,
                        uint32_t rate, uint32_t depth, uint32_t mode) {
    uint32_t data[4] = {scenario, rate, depth, mode};
    return hash(value, data, sizeof(data));
}
static void source_pair_concurrently(fe_b2s1_queue *q,
    const int16_t *pcm, size_t samples,
    uint64_t cap_seq, uint32_t cap_flags,
    const int16_t *render, size_t ref_count,
    uint64_t ref_seq, uint32_t ref_flags) {
    pthread_t cthread, rthread;
    f0_producer cap = {q, cap_seq, cap_flags, 0, pcm, samples, FE_B2S1_ESTATE};
    f0_producer ref = {q, ref_seq, ref_flags, 1, render, ref_count, FE_B2S1_ESTATE};
    must(pthread_create(&cthread, NULL, submit_thread, &cap) == 0,
         "F0_CAPTURE_PTHREAD_CREATE");
    must(pthread_create(&rthread, NULL, submit_thread, &ref) == 0,
         "F0_RENDER_PTHREAD_CREATE");
    must(pthread_join(cthread, NULL) == 0, "F0_CAPTURE_PTHREAD_JOIN");
    must(pthread_join(rthread, NULL) == 0, "F0_RENDER_PTHREAD_JOIN");
    must(cap.outcome == FE_B2S1_OK && ref.outcome == FE_B2S1_OK,
         "F0_REAL_SOURCE_SUBMISSIONS");
}

static void reject_undocumented_capture_skip(
    fe_b2s1_queue *q, uint64_t next_seq,
    const int16_t *capture, size_t count, unsigned *violations) {
    size_t bytes = T.queue ? fe_b2s1_state_bytes(&T.config) : 0u;
    must(bytes > 0u && bytes <= sizeof(T.q_snapshot),
         "F0_NO_GAP_STATE_CAPACITY");
    memcpy(T.q_snapshot, T.qstate, bytes);
    must(fe_b2s1_submit_capture(q, next_seq, 0u,
                                capture, count) == FE_B2S1_EINVAL,
         "F0_MISSING_CAPTURE_GAP_WAS_ACCEPTED");
    must(memcmp(T.q_snapshot, T.qstate, bytes) == 0,
         "F0_MISSING_CAPTURE_GAP_MODIFIED_SOURCE");
    ++*violations;
}
static uint64_t bounded_negative(const scene_t *scene, uint32_t rate,
                                 uint32_t depth, uint32_t mode,
                                 unsigned *violations) {
    uint64_t id = UINT64_C(14695981039346656037);
    const size_t cap_count = (size_t)(rate / 100u) * scene->mics;
    const size_t ref_count = (size_t)(rate / 100u);
    const size_t queue_bytes = fe_b2s1_state_bytes(
        &(fe_b2s1_config){0});
    size_t real_bytes;
    fe_b2s1_info current, previous;
    fe_s2_writer writer_prior;
    fe_b2s1_status got;
    fe_s3_status bridge_status;
    int16_t capture_samples[1920], reference_samples[480];
    float out[160], ref_out[160];
    uint8_t saved_out[sizeof(out)], saved_ref[sizeof(ref_out)];
    unsigned round;
    (void)queue_bytes;
    init(&T, scene, rate, 1u, depth, 2u);
    real_bytes = fe_b2s1_state_bytes(&T.config);
    must(real_bytes > 0u && real_bytes <= sizeof(T.q_snapshot),
         "F0_QUEUE_CAPACITY");
    produce_pcm(scene, rate, 1u, capture_samples, reference_samples);
    if (mode == 2u) {
        /* One real matched frame has been consumed on S1, but S2 is
         * deliberately independent. Subsequent capture skips 2 -> 3
         * only under explicit CAPTURE_GAP; reference queues real seq 2.
         */
        must(fe_b2s1_submit_capture(T.queue, 1u, 0u,
                                   capture_samples, cap_count) == FE_B2S1_OK,
             "F0_INITIAL_CAPTURE");
        must(fe_b2s1_submit_render(T.queue, 1u, 0u,
                                  reference_samples, ref_count) == FE_B2S1_OK,
             "F0_INITIAL_RENDER");
        must(fe_b2s1_process_one(T.queue, out, 160u,
                                 ref_out, 160u, T.work,
                                 fe_b2s1_work_bytes(&T.config)) == FE_B2S1_OK,
             "F0_INITIAL_MATCHED_PROCESS");
        produce_pcm(scene, rate, 3u, capture_samples, reference_samples);
        reject_undocumented_capture_skip(T.queue, 3u, capture_samples,
                                          cap_count, violations);
        source_pair_concurrently(
            T.queue, capture_samples, cap_count, 3u, FE_B1B0_CAPTURE_GAP,
            reference_samples, ref_count, 2u, 0u);
    } else if (mode == 1u) {
        /* Render behind capture: the source continuity obligation was
         * already broken (first capture 2 explicitly CAPTURE_GAP).
         * Prove a false clean seq-2 is rejected before admitting it.
         */
        reject_undocumented_capture_skip(T.queue, 2u, capture_samples,
                                          cap_count, violations);
        source_pair_concurrently(
            T.queue, capture_samples, cap_count, 2u, FE_B1B0_CAPTURE_GAP,
            reference_samples, ref_count, 1u, 0u);
    } else if (mode == 0u) {
        /* Render ahead: missing render 1 cannot be synthesized. */
        source_pair_concurrently(
            T.queue, capture_samples, cap_count, 1u, 0u,
            reference_samples, ref_count, 2u, FE_B1B0_RENDER_GAP);
    } else {
        /* Explicitly missing Render => EEMPTY, never fabricate silence. */
        must(fe_b2s1_submit_capture(T.queue, 1u, 0u,
                                   capture_samples, cap_count) == FE_B2S1_OK,
             "F0_CAPTURE_WITHOUT_RENDER");
    }
    must(fe_b2s1_get_info(T.queue, &previous) == FE_B2S1_OK,
         "F0_PRE_REJECT_SOURCE_INFO");
    must(previous.capture_queued == 1u &&
         previous.render_queued == (mode == 3u ? 0u : 1u),
         "F0_PRE_REJECT_QUEUE_COUNTS");
    memcpy(T.q_snapshot, T.qstate, real_bytes);
    memcpy(T.snapshot, T.record, T.recorder.total_bytes);
    writer_prior = T.recorder;
    memset(out, 0xa7, sizeof(out));
    memset(ref_out, 0xbc, sizeof(ref_out));
    memcpy(saved_out, out, sizeof(out));
    memcpy(saved_ref, ref_out, sizeof(ref_out));
    for (round = 0u; round < 4u; ++round) {
        got = fe_b2s1_process_one(T.queue, out, 160u, ref_out, 160u,
                                  T.work, fe_b2s1_work_bytes(&T.config));
        must(got == (mode == 3u ? FE_B2S1_EEMPTY : FE_B2S1_EINVAL),
             "F0_MISMATCH_EITHER_PROGRESSED_OR_HIDDEN");
        must(memcmp(T.q_snapshot, T.qstate, real_bytes) == 0 &&
             memcmp(T.snapshot, T.record, T.recorder.total_bytes) == 0 &&
             memcmp(&writer_prior, &T.recorder, sizeof(writer_prior)) == 0 &&
             memcmp(saved_out, out, sizeof(out)) == 0 &&
             memcmp(saved_ref, ref_out, sizeof(ref_out)) == 0,
             "F0_REJECT_MODIFIED_BF_QUEUE_OR_APX3");
        ++*violations; /* actually executed reject, not a fake PASS */
    }
    must(fe_b2s1_get_info(T.queue, &current) == FE_B2S1_OK,
         "F0_POST_REJECT_SOURCE_INFO");
    must(current.processed == previous.processed &&
         current.capture_queued == previous.capture_queued &&
         current.render_queued == previous.render_queued &&
         current.capture_sequence == previous.capture_sequence &&
         current.render_sequence == previous.render_sequence,
         "F0_REJECT_SOURCE_PROGRESS_DRIFT");
    /* T0 bridge must also be noncommitting on missing/mismatched queues.
     * Provide S2 legal first sequence 1 so the new recorder preflight
     * cannot hide a real S1 mismatch by rejecting the candidate first.
     */
    if (mode != 2u) {
        fe_s2_frame frame;
        memset(&frame, 0, sizeof(frame));
        frame.sequence = 1u;
        frame.capture = capture_samples;
        frame.capture_count = cap_count;
        frame.render = reference_samples;
        frame.render_count = ref_count;
        frame.capture_epoch = 1u;
        frame.render_epoch = 1u;
        bridge_status = fe_s3_bridge_step(&T.bridge, &frame,
            out, 160u, ref_out, 160u, T.work,
            fe_b2s1_work_bytes(&T.config));
        must(bridge_status != FE_S3_OK && T.recorder.appended == 0u &&
             memcmp(T.snapshot, T.record, T.recorder.total_bytes) == 0,
             "F0_PRIVATE_APX3_FALSE_COMMIT");
        ++*violations;
    }
    id = f0_hash(id, scene->mics, rate, depth, mode);
    id = hash(id, &current.processed, sizeof(current.processed));
    id = hash(id, &current.capture_queued, sizeof(current.capture_queued));
    id = hash(id, &current.render_queued, sizeof(current.render_queued));
    return id;
}
static unsigned reachability_model(unsigned *jump_cases) {
    uint32_t consumed, capture, render;
    unsigned reachable_stale = 0u;
    *jump_cases = 0u;
    /* From S1 paired consume at P, all retained render sequences > P.
     * Capture continuous requires C=P+1. Therefore R<C is unreachable.
     * Enumerate all bounded cases; do not infer physical ADC timebase.
     */
    for (consumed = 0u; consumed < 16u; ++consumed)
        for (capture = consumed+1u; capture <= consumed+5u; ++capture)
            for (render = consumed+1u; render <= consumed+5u; ++render) {
                if (render < capture) {
                    if (capture == consumed+1u) ++reachable_stale;
                    else ++*jump_cases;
                }
            }
    return reachable_stale;
}
int main(void) {
    uint32_t i, rate, depth, mode;
    const uint32_t rates[3] = {16000u, 32000u, 48000u};
    unsigned cases = 0u, negative_checks = 0u, jump_cases = 0u;
    uint64_t digest = UINT64_C(14695981039346656037);
    unsigned stale_with_continuous_capture = reachability_model(&jump_cases);
    must(stale_with_continuous_capture == 0u && jump_cases > 0u,
         "F0_REACHABILITY_COUNTEREXAMPLE");
    printf("{\"schema_version\":1,\"decision\":\"FE09_S3_T2_F0_FROZEN_S1_RENDER_RECOVERY_INFEASIBLE_WITH_CAPTURE_CONTINUITY\",\"source_role\":\"first-party-synthetic\",\"no_public_abi\":true,\"automatic_recovery_qualified\":false,\"physical_clock_measured\":false,\"stale_with_contiguous_capture\":%u,\"capture_gap_cases\":%u,\"cases\":[",
           stale_with_continuous_capture, jump_cases);
    for (i=0u;i<4u;++i)
        for (rate=0u;rate<3u;++rate)
            for(depth=2u;depth<=4u;depth+=2u)
                for(mode=0u;mode<4u;++mode) {
                    uint64_t value;
                    if(cases) putchar(',');
                    value = bounded_negative(&SCENES[i], rates[rate],
                                             depth, mode, &negative_checks);
                    digest ^= value;
                    digest *= UINT64_C(1099511628211);
                    printf("{\"scene\":\"%s\",\"rate\":%u,\"depth\":%u,\"mode\":%u,\"negative_hash\":\"%016" PRIx64 "\"}",
                           SCENES[i].name, rates[rate], depth, mode, value);
                    ++cases;
                }
    printf("],\"profile_count\":%u,\"negative_checks\":%u,\"digest\":\"%016" PRIx64 "\"}\n",
           cases, negative_checks, digest);
    must(cases==96u && negative_checks>=4u*96u &&
         stale_with_continuous_capture==0u,
         "F0_BOUNDED_NEGATIVE_MATRIX_INCOMPLETE");
    return 0;
}
