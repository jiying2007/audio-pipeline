/* FE09-R2B2-S1: actual first-party SRC+FIR33 inside private SPSC ring.
 * Synthetic tests only; hosted CPU numbers are NOT SSC305 device timing.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s1_private_queue.h"
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#define FRAME_COUNT 100u
#define STATE_CAP 65536u
#define WORK_CAP 65536u
#define FNV0 UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

typedef struct {
    const char *name;
    uint32_t mics, render, slots[4], circle;
} scene_t;

static const scene_t SCENES[] = {
    {"C1_BASELINE", 1u, 0u, {0u, 0u, 0u, 0u}, 0u},
    {"C2_ULA", 2u, 1u, {1u, 0u, 0u, 0u}, 0u},
    {"C4_ULA", 4u, 1u, {2u, 0u, 3u, 1u}, 0u},
    {"C4_UCA", 4u, 1u, {3u, 2u, 1u, 0u}, 1u},
};
static const uint32_t RATES[] = {16000u, 32000u, 48000u};
static _Alignas(16) unsigned char STATE[STATE_CAP], WORK[WORK_CAP];
static _Alignas(16) unsigned char DIRECT[16384], DIRECT_WORK[32768];
static unsigned char SNAPSHOT[STATE_CAP];

typedef struct {
    uint64_t input_hash, beam_hash, render_hash;
    uint64_t elapsed_ns[FRAME_COUNT];
    size_t state_bytes, work_bytes, bf_bytes;
    uint32_t depth, processed, negatives;
} result_t;

static int fail(const char *message, int line) {
    fprintf(stderr, "FE09_B2S1_FAIL line=%d reason=%s\n", line, message);
    return -1;
}
#define MUST(cond) do { if (!(cond)) return fail(#cond, __LINE__); } while (0)

static uint64_t hash_bytes(uint64_t start, const void *p, size_t length) {
    const unsigned char *b = (const unsigned char *)p;
    size_t i;
    for (i = 0u; i < length; ++i) start = (start ^ b[i]) * FNV_PRIME;
    return start;
}
static int16_t cap_signal(uint32_t mic, uint32_t sample, uint32_t frame) {
    const uint32_t x = (frame * 337u + sample * 73u + mic * 1931u) & 65535u;
    return (int16_t)((int32_t)x - 32768);
}
static int16_t ref_signal(uint32_t sample, uint32_t frame) {
    const uint32_t x = (frame * 233u + sample * 229u) & 65535u;
    return (int16_t)((int32_t)x - 32768);
}
static void make_pcm(const scene_t *sc, uint32_t rate, uint32_t k,
                     int16_t capture[1920], int16_t render[480]) {
    uint32_t slot, sample, physical, n = sc->mics;
    const uint32_t frames = rate / 100u;
    for (sample = 0u; sample < frames; ++sample) {
        for (physical = 0u; physical < n; ++physical) {
            slot = sc->slots[physical];
            capture[(size_t)sample * n + slot] = cap_signal(physical, sample, k);
        }
        render[sample] = ref_signal(sample, k);
    }
}
static fe_b2s1_config make_cfg(const scene_t *sc, uint32_t rate, uint32_t depth) {
    fe_b2s1_config c;
    static const double square[4][2] = {
        {0.03, 0.00}, {0.00, 0.03}, {-0.03, 0.00}, {0.00, -0.03}
    };
    uint32_t i;
    memset(&c, 0, sizeof(c));
    c.depth = depth;
    c.pipeline.ingress.struct_size = (uint32_t)sizeof(c.pipeline.ingress);
    c.pipeline.ingress.api_version = FE_B1B0_VERSION;
    c.pipeline.ingress.capture_and_render_rate_hz = rate;
    c.pipeline.ingress.frame_ms = 10u;
    c.pipeline.ingress.physical_mics = sc->mics;
    c.pipeline.ingress.render_channels = sc->render;
    c.pipeline.ingress.active_mic_mask = (1u << sc->mics) - 1u;
    c.pipeline.array.sample_rate_hz = 16000u;
    c.pipeline.array.mic_count = sc->mics;
    c.pipeline.array.reference_mic = 0u;
    c.pipeline.array.active_mask = c.pipeline.ingress.active_mic_mask;
    c.pipeline.array.interpolation = FE_ARRAY_FIR33_HANN;
    c.pipeline.array.direction[0] = 1.0;
    for (i = 0u; i < sc->mics; ++i) {
        c.pipeline.ingress.physical_to_capture_slot[i] = sc->slots[i];
        c.pipeline.array.microphones[i].input_channel = i;
        c.pipeline.array.microphones[i].gain = 1.0;
        if (sc->circle) {
            c.pipeline.array.microphones[i].position_m[0] = square[i][0];
            c.pipeline.array.microphones[i].position_m[1] = square[i][1];
        } else {
            c.pipeline.array.microphones[i].position_m[0] = 0.035 * (double)i;
        }
    }
    return c;
}
static uint64_t nano_time(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0u;
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) +
           (uint64_t)ts.tv_nsec;
}
static void hosted_stats(const scene_t *sc, uint32_t rate, result_t *r) {
    size_t i, j;
    uint64_t copy[FRAME_COUNT];
    for (i = 0u; i < FRAME_COUNT; ++i) copy[i] = r->elapsed_ns[i];
    for (i = 1u; i < FRAME_COUNT; ++i) {
        const uint64_t pivot = copy[i];
        for (j = i; j > 0u && copy[j - 1u] > pivot; --j)
            copy[j] = copy[j - 1u];
        copy[j] = pivot;
    }
    fprintf(stderr, "FE09_B2S1_HOSTED_SIMULATION_NOT_SSC305 scene=%s rate=%u "
            "depth=%u p95_ns=%" PRIu64 " p99_ns=%" PRIu64 "\n",
            sc->name, rate, r->depth, copy[94], copy[98]);
}
static int run_profile(const scene_t *sc, uint32_t rate, uint32_t depth,
                       result_t *r) {
    fe_b2s1_config cfg = make_cfg(sc, rate, depth);
    fe_b2s1_queue *q = NULL;
    fe_b1b1 *direct = NULL;
    fe_b2s1_dump_sketch dump;
    fe_b2s1_info info;
    int16_t capture[1920], render[480];
    float beam[160], reference[160], expected[160], expected_ref[160];
    uint32_t k;
    const size_t state_bytes = fe_b2s1_state_bytes(&cfg);
    const size_t work_bytes = fe_b2s1_work_bytes(&cfg);
    const size_t direct_bytes = fe_b1b1_state_bytes(&cfg.pipeline);
    const size_t direct_work = fe_b1b1_work_bytes(&cfg.pipeline);
    uint64_t hash_in = FNV0, hash_beam = FNV0, hash_ref = FNV0;
    MUST(state_bytes && state_bytes <= STATE_CAP);
    MUST(work_bytes && work_bytes <= WORK_CAP);
    MUST(direct_bytes && direct_bytes <= sizeof(DIRECT));
    MUST(direct_work && direct_work <= sizeof(DIRECT_WORK));
    memset(STATE, 0x5A, sizeof(STATE));
    memset(DIRECT, 0, sizeof(DIRECT));
    MUST(fe_b2s1_init(STATE, state_bytes, &cfg, &q) == FE_B2S1_OK);
    MUST(fe_b1b1_init(DIRECT, direct_bytes, &cfg.pipeline, &direct) == FE_B1B1_OK);
    MUST(fe_b2s1_private_dump_sketch(q, &dump) == FE_B2S1_OK);
    MUST(dump.schema_version == 2u && dump.new_magic_assigned == 0u &&
         dump.endian_tag == UINT32_C(0x01020304) &&
         dump.source_samples == rate / 100u &&
         dump.physical_mics == sc->mics &&
         dump.render_channels == sc->render &&
         dump.clock_authority == 0u);
    for (k = 1u; k <= FRAME_COUNT; ++k) {
        const size_t ccount = (size_t)(rate / 100u) * sc->mics;
        const size_t rcount = (size_t)(rate / 100u) * sc->render;
        uint32_t cflags = 0u, rflags = 0u, flags;
        uint64_t start, end;
        if (k == 15u) cflags |= FE_B1B0_CAPTURE_GAP;
        if (k == 25u && sc->render) rflags |= FE_B1B0_RENDER_GAP;
        if (k == 60u) {
            cflags |= FE_B1B0_CLOCK_RESET;
            if (sc->render) rflags |= FE_B1B0_CLOCK_RESET;
        }
        if (k == 80u) cflags |= FE_B2S1_XRUN;
        if (k == 81u && sc->render) rflags |= FE_B2S1_XRUN;
        make_pcm(sc, rate, k, capture, render);
        hash_in = hash_bytes(hash_in, capture, ccount * sizeof(int16_t));
        MUST(fe_b2s1_submit_capture(q, k, cflags, capture, ccount) == FE_B2S1_OK);
        if (sc->render)
            MUST(fe_b2s1_submit_render(q, k, rflags, render, rcount) ==
                 FE_B2S1_OK);
        flags = (cflags & (FE_B1B0_CAPTURE_GAP | FE_B2S1_XRUN)) ?
                FE_B1B0_CAPTURE_GAP : 0u;
        if (rflags & (FE_B1B0_RENDER_GAP | FE_B2S1_XRUN))
            flags |= FE_B1B0_RENDER_GAP;
        if (cflags & FE_B1B0_CLOCK_RESET)
            flags = FE_B1B0_CLOCK_RESET;
        if (flags) MUST(fe_b1b1_notify_gap(direct, flags) == FE_B1B1_OK);
        MUST(fe_b1b1_process(direct, capture, ccount,
             sc->render ? render : NULL, rcount, expected, 160u,
             sc->render ? expected_ref : NULL, (size_t)160u * sc->render,
             DIRECT_WORK, direct_work) == FE_B1B1_OK);
        start = nano_time();
        MUST(fe_b2s1_process_one(q, beam, 160u,
             sc->render ? reference : NULL, (size_t)160u * sc->render,
             WORK, work_bytes) == FE_B2S1_OK);
        end = nano_time();
        r->elapsed_ns[k - 1u] = end >= start ? end - start : 0u;
        MUST(memcmp(beam, expected, sizeof(beam)) == 0);
        hash_beam = hash_bytes(hash_beam, beam, sizeof(beam));
        if (sc->render) {
            MUST(memcmp(reference, expected_ref, sizeof(reference)) == 0);
            hash_ref = hash_bytes(hash_ref, reference, sizeof(reference));
        }
        MUST(fe_b2s1_get_info(q, &info) == FE_B2S1_OK);
        MUST(info.processed == k && info.pipeline.accepted_frames == k &&
             info.capture_queued == 0u &&
             info.render_queued == 0u);
    }
    MUST(fe_b2s1_get_info(q, &info) == FE_B2S1_OK);
    MUST(info.capture_submitted == FRAME_COUNT &&
         info.render_submitted == FRAME_COUNT * sc->render &&
         info.depth == depth && info.capture_high_water == 1u);
    MUST(fe_b2s1_process_one(q, beam, 160u, sc->render ? reference : NULL,
         (size_t)160u * sc->render, WORK, work_bytes) == FE_B2S1_EEMPTY);
    r->state_bytes = state_bytes;
    r->work_bytes = work_bytes;
    r->bf_bytes = direct_bytes;
    r->depth = depth;
    r->processed = FRAME_COUNT;
    r->input_hash = hash_in;
    r->beam_hash = hash_beam;
    r->render_hash = hash_ref;
    hosted_stats(sc, rate, r);
    return 0;
}
static int reject_unchanged(fe_b2s1_queue *q, size_t bytes,
                            fe_b2s1_status got, fe_b2s1_status wanted) {
    if (got != wanted || memcmp(STATE, SNAPSHOT, bytes) != 0)
        return fail("rejected mutation/incorrect status", __LINE__);
    (void)q;
    return 0;
}
#define REJECT(q,need,expr,status) do { \
    memcpy(SNAPSHOT, STATE, (need)); \
    if (reject_unchanged((q),(need),(expr),(status)) != 0) { \
        return -1; \
    } \
    ++negatives; \
} while (0)

static int negatives_profile(const scene_t *sc, uint32_t rate,
                             uint32_t *out_count) {
    fe_b2s1_config cfg = make_cfg(sc, rate, 2u),bad;
    fe_b2s1_queue *q = NULL;
    fe_b2s1_info info;
    size_t state_bytes, work_bytes;
    int16_t capture[1920], render[480];
    float beam[160], ref[160];
    const size_t ccount = (size_t)(rate / 100u) * sc->mics;
    const size_t rcount = (size_t)(rate / 100u) * sc->render;
    uint32_t negatives = 0u, i;
    const struct { uint32_t rate, n, ref, depth; } invalid[] = {
        {8000u,sc->mics,sc->render,2u}, {24000u,sc->mics,sc->render,2u},
        {44100u,sc->mics,sc->render,2u}, {0u,sc->mics,sc->render,2u},
        {rate,3u,sc->render,2u}, {rate,5u,sc->render,2u},
        {rate,sc->mics,2u,2u}, {rate,sc->mics,sc->render,1u},
        {rate,sc->mics,sc->render,3u}, {rate,sc->mics,sc->render,8u}
    };
    for (i = 0u; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
        bad = cfg;
        bad.pipeline.ingress.capture_and_render_rate_hz = invalid[i].rate;
        bad.pipeline.ingress.physical_mics = invalid[i].n;
        bad.pipeline.ingress.render_channels = invalid[i].ref;
        bad.depth = invalid[i].depth;
        MUST(fe_b2s1_state_bytes(&bad) == 0u);
        ++negatives;
    }
    bad=cfg; bad.pipeline.ingress.capture_clock_authority = 1u;
    MUST(fe_b2s1_state_bytes(&bad) == 0u); ++negatives;
    bad=cfg; bad.pipeline.ingress.frame_ms = 20u;
    MUST(fe_b2s1_state_bytes(&bad) == 0u); ++negatives;
    bad=cfg; bad.pipeline.ingress.active_mic_mask = 0u;
    MUST(fe_b2s1_state_bytes(&bad) == 0u); ++negatives;
    bad=cfg; bad.pipeline.array.sample_rate_hz = 48000u;
    MUST(fe_b2s1_state_bytes(&bad) == 0u); ++negatives;
    bad=cfg; bad.pipeline.array.mic_count = 3u;
    MUST(fe_b2s1_state_bytes(&bad) == 0u); ++negatives;
    state_bytes=fe_b2s1_state_bytes(&cfg);
    work_bytes=fe_b2s1_work_bytes(&cfg);
    MUST(state_bytes && work_bytes);
    memset(STATE,0,sizeof(STATE));
    MUST(fe_b2s1_init(STATE,state_bytes,&cfg,&q)==FE_B2S1_OK);
    make_pcm(sc,rate,1u,capture,render);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,0u,0u,capture,ccount),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,0u,NULL,ccount),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,0u,capture,0u),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,0u,capture,ccount-1u),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,0u,capture,ccount+1u),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,FE_B1B0_RENDER_GAP,capture,ccount),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,16u,capture,ccount),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,32u,capture,ccount),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,64u,capture,ccount),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,0u,(int16_t *)(void *)STATE,ccount),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,
           sc->render?ref:NULL,(size_t)160u*sc->render,WORK,work_bytes),
           FE_B2S1_EEMPTY);
    if (!sc->render) {
        REJECT(q,state_bytes,fe_b2s1_submit_render(q,1u,0u,render,rate/100u),
               FE_B2S1_EINVAL);
    } else {
        REJECT(q,state_bytes,fe_b2s1_submit_render(q,0u,0u,render,rcount),
               FE_B2S1_EINVAL);
        REJECT(q,state_bytes,fe_b2s1_submit_render(q,1u,0u,render,rcount-1u),
               FE_B2S1_EINVAL);
        REJECT(q,state_bytes,fe_b2s1_submit_render(q,1u,FE_B1B0_CAPTURE_GAP,render,rcount),
               FE_B2S1_EINVAL);
    }
    MUST(fe_b2s1_submit_capture(q,1u,0u,capture,ccount)==FE_B2S1_OK);
    if (sc->render) {
        REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,ref,160u,WORK,work_bytes),
               FE_B2S1_EEMPTY);
        MUST(fe_b2s1_submit_render(q,1u,0u,render,rcount)==FE_B2S1_OK);
    }
    memset(beam,0xBE,sizeof(beam));
    memset(ref,0xCD,sizeof(ref));
    REJECT(q,state_bytes,fe_b2s1_process_one(q,NULL,160u,
           sc->render?ref:NULL,(size_t)160u*sc->render,WORK,work_bytes),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,0u,
           sc->render?ref:NULL,(size_t)160u*sc->render,WORK,work_bytes),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,159u,
           sc->render?ref:NULL,(size_t)160u*sc->render,WORK,work_bytes),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,161u,
           sc->render?ref:NULL,(size_t)160u*sc->render,WORK,work_bytes),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,
           sc->render?ref:NULL,(size_t)160u*sc->render,NULL,work_bytes),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,
           sc->render?ref:NULL,(size_t)160u*sc->render,WORK,work_bytes-1u),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,
           sc->render?ref:NULL,(size_t)160u*sc->render,WORK+1u,work_bytes),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,(float *)(void *)STATE,160u,
           sc->render?ref:NULL,(size_t)160u*sc->render,WORK,work_bytes),
           FE_B2S1_EINVAL);
    REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,
           sc->render?ref:NULL,(size_t)160u*sc->render,STATE,work_bytes),
           FE_B2S1_EINVAL);
    if (sc->render) {
        REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,NULL,160u,WORK,work_bytes),
               FE_B2S1_EINVAL);
        REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,ref,159u,WORK,work_bytes),
               FE_B2S1_EINVAL);
        REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,beam,160u,WORK,work_bytes),
               FE_B2S1_EINVAL);
    } else {
        REJECT(q,state_bytes,fe_b2s1_process_one(q,beam,160u,ref,0u,WORK,work_bytes),
               FE_B2S1_EINVAL);
    }
    MUST(fe_b2s1_get_info(q,&info)==FE_B2S1_OK && info.capture_queued==1u);
    if (sc->render) MUST(info.render_queued==1u);
    /* Invalid future sequence and ordering: exact byte-level rejection. */
    for (i=0u;i<25u;++i) {
        REJECT(q,state_bytes,fe_b2s1_submit_capture(q,3u+i,0u,capture,ccount),
               FE_B2S1_EINVAL);
    }
    MUST(fe_b2s1_process_one(q,beam,160u,sc->render?ref:NULL,
         (size_t)160u*sc->render,WORK,work_bytes)==FE_B2S1_OK);
    for (i=0u;i<10u;++i) {
        REJECT(q,state_bytes,fe_b2s1_submit_capture(q,1u,0u,capture,ccount),
               FE_B2S1_EINVAL);
    }
    /* Fill both depth=2 queues; no accepted mutation on a fifth-ish frame. */
    for (i=2u;i<=3u;++i) {
        MUST(fe_b2s1_submit_capture(q,i,0u,capture,ccount)==FE_B2S1_OK);
        if (sc->render) MUST(fe_b2s1_submit_render(q,i,0u,render,rcount)==FE_B2S1_OK);
    }
    REJECT(q,state_bytes,fe_b2s1_submit_capture(q,4u,0u,capture,ccount),
           FE_B2S1_EFULL);
    if (sc->render)
        REJECT(q,state_bytes,fe_b2s1_submit_render(q,4u,0u,render,rcount),
               FE_B2S1_EFULL);
    MUST(fe_b2s1_get_info(q,&info)==FE_B2S1_OK);
    MUST(info.capture_high_water==2u && info.capture_queued==2u);
    for (i=0u;i<2u;++i) MUST(fe_b2s1_process_one(q,beam,160u,
         sc->render?ref:NULL,(size_t)160u*sc->render,WORK,work_bytes)==FE_B2S1_OK);
    MUST(fe_b2s1_get_info(q,&info)==FE_B2S1_OK && info.capture_queued==0u);
    *out_count=negatives;
    MUST(negatives>=50u);
    return 0;
}
int main(void) {
    size_t r, s;
    int first = 1;
    uint32_t negatives = 0u, max_state = 0u;
    printf("{\"schema_version\":1,\"decision\":"
           "\"FE09_R2B2_S1_PRIVATE_LINUX_QUEUE_RUNTIME_RESEARCH_ONLY_NO_PUBLIC_ABI\","
           "\"source_role\":\"first-party-synthetic\","
           "\"public_sdk_installed\":false,\"actual_apd_v2_writer\":false,"
           "\"real_adc_clock_qualified\":false,\"ssc305_dut_qualified\":false,"
           "\"full_c4_system_budget_qualified\":false,"
           "\"repeats\":2,\"profiles\":[");
    for (r = 0u; r < 3u; ++r) {
        for (s = 0u; s < 4u; ++s) {
            const scene_t *sc = &SCENES[s];
            result_t a, b;
            uint32_t local_negatives = 0u;
            const uint32_t rate = RATES[r];
            const uint32_t depth = s==3u?4u:2u;
            memset(&a,0,sizeof(a));memset(&b,0,sizeof(b));
            if (run_profile(sc,rate,depth,&a) != 0 ||
                run_profile(sc,rate,depth,&b) != 0 ||
                a.state_bytes != b.state_bytes ||
                a.work_bytes != b.work_bytes ||
                a.input_hash != b.input_hash ||
                a.beam_hash != b.beam_hash ||
                a.render_hash != b.render_hash ||
                negatives_profile(sc,rate,&local_negatives) != 0)
                return 2;
            if(a.state_bytes>max_state)max_state=(uint32_t)a.state_bytes;
            negatives+=local_negatives;
            if(!first)printf(",");
            first=0;
            printf("{\"scene\":\"%s\",\"rate\":%u,\"mics\":%u,\"render\":%u,"
                   "\"depth\":%u,\"frames\":%u,\"negatives\":%u,"
                   "\"state_bytes\":%zu,\"work_bytes\":%zu,\"core_bytes\":%zu,"
                   "\"capture_hash\":\"%016" PRIx64 "\","
                   "\"beam_hash\":\"%016" PRIx64 "\","
                   "\"render_hash\":\"%016" PRIx64 "\"}",
                   sc->name,rate,sc->mics,sc->render,depth,
                   a.processed,local_negatives,a.state_bytes,a.work_bytes,
                   a.bf_bytes,a.input_hash,a.beam_hash,a.render_hash);
        }
    }
    printf("],\"profile_count\":12,\"total_negatives\":%u,"
           "\"max_state_bytes\":%u}\n",negatives,max_state);
    return 0;
}
