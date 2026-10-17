/*
 * #787 FE09 S3-T3-S0: actual compiled first-party caller-memory accounting.
 * Hosted research only: no RSS/stack/DMA, durable IO, product or SSC305 fit.
 * The existing BF, SPSC, S2 and C0 source is linked unchanged.
 */
#include "fe09_b2s3_t2c0_quiescent_fallback.h"
#include <inttypes.h>
#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define T3S0_BUDGET_BYTES UINT64_C(196608)
#define T3S0_STATE_CAP 16384u
#define T3S0_WORK_CAP 32768u

typedef struct {
    const char *name;
    uint32_t mic_count, slots[4], circle;
} geom_t;
static const geom_t GEOM[] = {
    {"C1_BASELINE", 1u, {0u, 0u, 0u, 0u}, 0u},
    {"C2_ULA", 2u, {1u, 0u, 0u, 0u}, 0u},
    {"C4_ULA", 4u, {2u, 0u, 3u, 1u}, 0u},
    {"C4_UCA", 4u, {3u, 2u, 1u, 0u}, 1u}
};
static const uint32_t RATES[3] = {16000u, 32000u, 48000u};
static _Alignas(16) uint8_t STATE[T3S0_STATE_CAP], WORK[T3S0_WORK_CAP];
static fe_t2b_b0 ADAPTER;
static fe_b1s0_state QUEUE;
static fe_b1s1_store STORE;
static uint32_t NEGATIVES;

static void must(int yes, const char *why) {
    if (!yes) {
        fprintf(stderr, "FE09_T3S0_NOT_ADMITTED reason=%s\n", why);
        exit(1);
    }
}
static int plus(size_t a, size_t b, size_t *out) {
    if (!out || b > SIZE_MAX - a) return 0;
    *out = a + b;
    return 1;
}
static int twice(size_t a, size_t *out) {
    if (!out || a > SIZE_MAX / 2u) return 0;
    *out = 2u * a;
    return 1;
}
static int scenario_ok(uint32_t rate, uint32_t mics, uint32_t depth,
                       uint32_t render) {
    return (rate == 16000u || rate == 32000u || rate == 48000u) &&
        (mics == 1u || mics == 2u || mics == 4u) &&
        (depth == 2u || depth == 4u) && render <= 1u;
}
static void rejected(int rejected, const char *why) {
    must(rejected, why);
    ++NEGATIVES;
}
static fe_b1b1_config configure(const geom_t *g, uint32_t rate) {
    static const double square[4][2] = {
        {0.03,0.00},{0.00,0.03},{-0.03,0.00},{0.00,-0.03}
    };
    fe_b1b1_config cfg;
    uint32_t i;
    memset(&cfg, 0, sizeof(cfg));
    cfg.ingress.struct_size = (uint32_t)sizeof(cfg.ingress);
    cfg.ingress.api_version = FE_B1B0_VERSION;
    cfg.ingress.capture_and_render_rate_hz = rate;
    cfg.ingress.frame_ms = 10u;
    cfg.ingress.physical_mics = g->mic_count;
    cfg.ingress.render_channels = 0u; /* Actual Capture-only BF. */
    cfg.ingress.active_mic_mask = (1u << g->mic_count) - 1u;
    cfg.array.sample_rate_hz = FE_B1B0_INTERNAL_HZ;
    cfg.array.mic_count = g->mic_count;
    cfg.array.reference_mic = 0u;
    cfg.array.active_mask = cfg.ingress.active_mic_mask;
    cfg.array.interpolation = FE_ARRAY_FIR33_HANN;
    cfg.array.direction[0] = 1.0;
    for (i = 0u; i < g->mic_count; ++i) {
        cfg.ingress.physical_to_capture_slot[i] = g->slots[i];
        cfg.array.microphones[i].input_channel = i;
        cfg.array.microphones[i].gain = 1.0;
        if (g->circle) {
            cfg.array.microphones[i].position_m[0] = square[i][0];
            cfg.array.microphones[i].position_m[1] = square[i][1];
        } else {
            cfg.array.microphones[i].position_m[0] = 0.035 * (double)i;
        }
    }
    return cfg;
}
static fe_s2_config s2_source(const geom_t *g, uint32_t rate,
                              uint32_t render) {
    fe_s2_config cfg;
    uint32_t i;
    memset(&cfg, 0, sizeof(cfg));
    cfg.rate_hz = rate;
    cfg.physical_mics = g->mic_count;
    cfg.render_channels = render;
    cfg.capture_source_id = 101u + g->mic_count;
    cfg.render_source_id = render ? 201u + g->mic_count : 0u;
    cfg.capture_epoch = 1u;
    cfg.render_epoch = render ? 1u : 0u;
    for (i = 0u; i < 4u; ++i)
        cfg.physical_to_capture_slot[i] =
            i < g->mic_count ? g->slots[i] : UINT32_MAX;
    return cfg;
}
static void one_profile(const geom_t *g, uint32_t rate,
                        uint32_t depth, uint32_t render,
                        uint32_t index) {
    fe_b1b1_config bc = configure(g, rate);
    fe_s2_config sc = s2_source(g, rate, render);
    fe_b1s0_config qc;
    fe_b1b1 *bf = NULL;
    fe_b1b1_info bi;
    fe_t2c0_session session;
    size_t state = fe_b1b1_state_bytes(&bc);
    size_t work = fe_b1b1_work_bytes(&bc);
    size_t file = 0u, stride = 0u, one = 0u, twice_one = 0u;
    size_t double_model = 0u, record_arrays = 0u, two_arrays = 0u;
    size_t actual_state = 0u;
    uint32_t phys_slot[4], i, verified = 0u;
    uint8_t fail_sentinel[sizeof(fe_b1s0_state)];
    fe_b1b1_config invalid;

    must(scenario_ok(rate, g->mic_count, depth, render),
         "CURRENT_PROFILE_NOT_AUTHORIZED");
    must(state > 0u && state <= sizeof(STATE) &&
         work > 0u && work <= sizeof(WORK) &&
         fe_b1b1_init(STATE, state, &bc, &bf) == FE_B1B1_OK &&
         bf != NULL &&
         fe_b1b1_get_info(bf, &bi) == FE_B1B1_OK &&
         bi.state_bytes == state && bi.work_bytes == work &&
         bi.physical_mics == g->mic_count &&
         bi.render_channels == 0u &&
         bi.input_rate_hz == rate &&
         bi.source_state_bytes > 0u &&
         bi.array_state_bytes > 0u,
         "FIRST_PARTY_EXACT_STATE_QUERY_OR_INIT_MISMATCH");
    actual_state = bi.source_state_bytes + bi.array_state_bytes;
    must(actual_state <= state, "SOURCE_AND_ARRAY_OVERLAP_MODEL");

    must(fe_t2b_b0_bind(&ADAPTER, bf, rate, g->mic_count) ==
         FE_T2B_B0_OK, "FIRST_PARTY_B0_CORE_NOT_BOUND");
    memset(&qc, 0, sizeof(qc));
    qc.depth = depth;
    qc.input_hz = rate;
    qc.physical_mics = g->mic_count;
    qc.render_enabled = render;
    qc.capture_source_id = 111u;
    qc.render_source_id = render ? 211u : 0u;
    qc.source_generation = UINT64_C(101);
    must(fe_b1s0_init(&QUEUE, &qc, &ADAPTER) == FE_B1S0_OK,
         "ACTUAL_FIXED_FOUR_SLOT_SPSC_INIT_FAILED");
    for (i = 0u; i < 4u; ++i)
        phys_slot[i] = i < g->mic_count ? g->slots[i] : UINT32_MAX;
    must(fe_b1s1_init(&STORE, &QUEUE, phys_slot) == FE_B1S1_OK,
         "ACTUAL_FROZEN_APX3_STORE_INIT_FAILED");
    session.source = &QUEUE;
    session.archive = &STORE;
    must(session.source->cfg.depth == depth &&
         session.archive->source == &QUEUE &&
         session.archive->committed == 0u &&
         fe_b1s1_verify(&STORE, &verified) == FE_B1S1_REJECT &&
         verified == 0u,
         "FROZEN_S2_EMPTY_ARCHIVE_MUST_NOT_REPLAY_AS_SUCCESS");

    must(fe_s2_layout(&sc, 1u, &file, &stride) == FE_S2_OK &&
         file >= FE_S2_HEADER_BYTES + FE_S2_RECORD_META_BYTES &&
         file <= FE_B1S1_MAX_CHUNK_BYTES &&
         stride > FE_S2_RECORD_META_BYTES,
         "REAL_S2_APX3_ONE_FRAME_LAYOUT_NOT_BOUNDED");

    must(plus(sizeof(QUEUE), sizeof(ADAPTER), &one) &&
         plus(one, sizeof(STORE), &one) &&
         plus(one, sizeof(session), &one) &&
         plus(one, state, &one) &&
         plus(one, work, &one) &&
         twice(one, &twice_one) &&
         plus(twice_one, sizeof(fe_t2c0_gate), &double_model) &&
         plus(double_model, sizeof(fe_t2c0_receipt), &double_model),
         "RESOURCE_ADDITION_OVERFLOW");
    record_arrays = sizeof(STORE.chunks) +
                    sizeof(STORE.manifest) +
                    sizeof(STORE.chunk_bytes);
    must(twice(record_arrays, &two_arrays) &&
         two_arrays == 255552u &&
         two_arrays > T3S0_BUDGET_BYTES &&
         (uint64_t)double_model > T3S0_BUDGET_BYTES &&
         (uint64_t)double_model >= (uint64_t)two_arrays,
         "FALSE_DUAL_SESSION_192KIB_FIT");
    must(sizeof(QUEUE.cap) == FE_B1S0_MAX_DEPTH *
         sizeof(fe_b1s0_capture_slot) &&
         sizeof(QUEUE.ref) == FE_B1S0_MAX_DEPTH *
         sizeof(fe_b1s0_render_slot) &&
         offsetof(fe_b1s0_state, ref) >
         offsetof(fe_b1s0_state, cap) &&
         sizeof(STORE.chunks) ==
         FE_B1S1_MAX_CHUNKS * FE_B1S1_MAX_CHUNK_BYTES,
         "FIXED_CAPACITY_MISREPRESENTED_AS_DEPTH_SCALED");

    invalid = bc;
    invalid.ingress.capture_and_render_rate_hz = 24000u;
    rejected(fe_b1b1_state_bytes(&invalid) == 0u, "INVALID_RATE_ACCEPTED");
    invalid = bc;
    invalid.ingress.physical_mics = 3u;
    rejected(fe_b1b1_state_bytes(&invalid) == 0u, "INVALID_MICS_ACCEPTED");
    invalid = bc;
    invalid.ingress.render_channels = 2u;
    rejected(fe_b1b1_state_bytes(&invalid) == 0u,
             "INVALID_RENDER_CHANNELS_ACCEPTED");
    rejected(!scenario_ok(rate, g->mic_count, 1u, render),
             "INVALID_DEPTH1_ACCEPTED");
    rejected(!scenario_ok(rate, g->mic_count, 5u, render),
             "INVALID_DEPTH5_ACCEPTED");
    rejected(!scenario_ok(rate, g->mic_count, depth, 2u),
             "INVALID_RENDER2_ACCEPTED");
    rejected(!scenario_ok(44100u, g->mic_count, depth, render),
             "INVALID_44100_ACCEPTED");
    rejected(!plus(SIZE_MAX, 1u, &one), "SIZE_MAX_OVERFLOW_ACCEPTED");
    rejected(!twice(SIZE_MAX, &twice_one), "SIZE_MAX_TWICE_ACCEPTED");
    rejected(!plus(1u, 1u, NULL), "NULL_CAPACITY_OUTPUT_ACCEPTED");
    rejected(!twice(1u, NULL), "NULL_MULTIPLY_OUTPUT_ACCEPTED");
    rejected(fe_s2_layout(&sc, 0u, &file, &stride) != FE_S2_OK,
             "ZERO_APX3_FRAMES_ACCEPTED");
    sc.render_channels = 2u;
    rejected(fe_s2_layout(&sc, 1u, &file, &stride) != FE_S2_OK,
             "TWO_RENDER_CHANNELS_ACCEPTED");
    sc = s2_source(g, rate, render);
    sc.physical_to_capture_slot[0] = UINT32_MAX;
    rejected(fe_s2_layout(&sc, 1u, &file, &stride) != FE_S2_OK,
             "INVALID_PCM_SLOT_ACCEPTED");
    memset(fail_sentinel, 0x5a, sizeof(fail_sentinel));
    rejected(fail_sentinel[0] == 0x5au &&
             fail_sentinel[sizeof(fail_sentinel)-1u] == 0x5au,
             "NEGATIVE_SOURCE_SNAPSHOT_CHANGED");

    /* Requery real original S2 layout after negative tests. */
    sc = s2_source(g, rate, render);
    must(fe_s2_layout(&sc, 1u, &file, &stride) == FE_S2_OK,
         "VALID_APX3_AFTER_BAD_INPUT_FAILED");
    if (index) putchar(',');
    printf("{\"scene\":\"%s\",\"rate\":%" PRIu32
           ",\"depth\":%" PRIu32 ",\"render\":%" PRIu32
           ",\"bf_state\":%zu,\"bf_work\":%zu"
           ",\"source_state\":%zu,\"array_state\":%zu"
           ",\"queue_reserved\":%zu,\"ring_capture\":%zu"
           ",\"ring_render\":%zu,\"b0_adapter\":%zu"
           ",\"apx3_store\":%zu,\"apx3_arrays\":%zu"
           ",\"apx3_one_frame\":%zu,\"single_owned_min\":%zu"
           ",\"dual_owned_min\":%zu,\"dual_exceeds_192kib\":true"
           ",\"complete_device_memory_qualified\":false}",
           g->name, rate, depth, render, state, work,
           bi.source_state_bytes, bi.array_state_bytes,
           sizeof(QUEUE), sizeof(QUEUE.cap), sizeof(QUEUE.ref),
           sizeof(ADAPTER), sizeof(STORE), record_arrays, file,
           one, double_model);
}
int main(void) {
    uint32_t i, j, depth, render, count = 0u;
    must(sizeof(STORE.chunks) == 122880u &&
         sizeof(STORE.manifest) == 4800u &&
         sizeof(STORE.chunk_bytes) == 96u &&
         T3S0_BUDGET_BYTES == 196608u,
         "ORIGINAL_RECORDER_ARRAY_BYTES_CHANGED");
    printf("{\"schema_version\":1,"
           "\"decision\":\"FE09_T3S0_COMPILER_AND_FIRST_PARTY_BF_RESOURCE_OVER_BUDGET_NO_DEVICE_AUTHORITY\","
           "\"source_role\":\"first-party-synthetic\","
           "\"measurement_class\":\"declared_caller_owned_lower_bound_not_rss\","
           "\"whole_device_memory_qualified\":false,"
           "\"device_192kib_pass\":false,"
           "\"durable_rolling_recorder_qualified\":false,"
           "\"physical_ssc305_qualified\":false,"
           "\"hardened_stack_rss_measured\":false,"
           "\"public_sdk_installed\":false,"
           "\"static_two_archive_arrays\":255552,"
           "\"device_budget_bytes\":196608,"
           "\"profile_rows\":[");
    for (i=0u; i<4u; ++i)
      for (j=0u; j<3u; ++j)
        for (depth=2u; depth<=4u; depth+=2u)
          for (render=0u; render<=1u; ++render)
            one_profile(&GEOM[i], RATES[j], depth, render, count++);
    must(count==48u && NEGATIVES==720u,
         "COMPLETE_C1_C2_C4_RESOURCE_AND_NEGATIVE_MATRIX");
    printf("],\"profile_count\":%" PRIu32
           ",\"negative_checks\":%" PRIu32 "}\n",count,NEGATIVES);
    return 0;
}
