#define _POSIX_C_SOURCE 200809L
/* FE09-R2B2-S2 deterministic 12-profile native/ASan/AArch32 APX3 fixture.
 * All audio here is synthetic and deterministic; no BF gain or device timing.
 */
#include "fe09_b2s2_private_apd.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint8_t IMAGE[2][FE_S2_MAX_BYTES], SNAP[FE_S2_MAX_BYTES];
static int16_t CAPTURE[FE_S2_MAX_CAPTURE_SAMPLES];
static int16_t RENDER[FE_S2_MAX_SOURCE_SAMPLES];
static unsigned fail_count;

static void need(int condition, const char *where) {
    if (!condition) {
        fprintf(stderr, "FE09_B2S2_TEST_FAIL: %s\n", where);
        ++fail_count;
        exit(1);
    }
}
static void put32(uint8_t *p, uint32_t n) {
    unsigned i;
    for (i = 0u; i != 4u; ++i) p[i] = (uint8_t)(n >> (8u*i));
}
static void put64(uint8_t *p, uint64_t n) {
    unsigned i;
    for (i = 0u; i != 8u; ++i) p[i] = (uint8_t)(n >> (8u*i));
}
static uint32_t crc32_bytes(const uint8_t *p, size_t n) {
    uint32_t x = UINT32_MAX;
    size_t i;
    for (i = 0u; i < n; ++i) {
        unsigned j;
        x ^= p[i];
        for (j = 0u; j != 8u; ++j)
            x = (x & 1u) ? (x >> 1u) ^ UINT32_C(0xedb88320) : (x >> 1u);
    }
    return ~x;
}
static void repair_header_crc(uint8_t *p) {
    put32(p + 124u, crc32_bytes(p, 124u));
}
static void repair_frame_crc(uint8_t *p, size_t stride) {
    put32(p + stride - 4u, crc32_bytes(p, stride - 4u));
}
static uint64_t fnv(const uint8_t *p, size_t n) {
    uint64_t v = UINT64_C(14695981039346656037);
    size_t i;
    for (i = 0u; i < n; ++i) {
        v ^= p[i];
        v *= UINT64_C(1099511628211);
    }
    return v;
}
static int16_t sample(size_t pos, uint32_t frame, uint32_t seed) {
    uint32_t code = (uint32_t)((pos * 37u + (size_t)frame * 113u +
                               (size_t)seed * 61u) % 4096u);
    return (int16_t)((int32_t)code - 2048);
}
static void fill(uint32_t frame, uint32_t seed, size_t ncap, size_t nref) {
    size_t i;
    for (i = 0u; i < ncap; ++i) CAPTURE[i] = sample(i, frame, seed);
    for (i = 0u; i < nref; ++i) RENDER[i] = sample(i, frame, seed + 53u);
}
typedef struct {
    unsigned visited;
    uint32_t seed, mics, rate, render;
    uint64_t last_seq;
} visitor_ctx;
static int visit(const fe_s2_stream *stream, uint32_t index, uint64_t sequence,
    uint32_t capture_flags, uint32_t render_flags,
    const uint8_t *capture_le, size_t cap_bytes,
    const uint8_t *render_le, size_t ref_bytes, void *context) {
    visitor_ctx *ctx = (visitor_ctx *)context;
    size_t i;
    (void)capture_flags;
    (void)render_flags;
    if (!ctx || !stream || stream->config.physical_mics != ctx->mics ||
        stream->config.rate_hz != ctx->rate ||
        stream->config.render_channels != ctx->render ||
        index != ctx->visited || !capture_le ||
        cap_bytes != (size_t)(ctx->rate / 100u) * ctx->mics * 2u ||
        ref_bytes != (size_t)(ctx->rate / 100u) * ctx->render * 2u ||
        (!!render_le) != (!!ctx->render) ||
        (ctx->last_seq && sequence <= ctx->last_seq)) return -1;
    for (i = 0u; i < cap_bytes / 2u; ++i) {
        uint16_t got = (uint16_t)((uint16_t)capture_le[2u*i] |
                                 ((uint16_t)capture_le[2u*i + 1u] << 8u));
        if (got != (uint16_t)sample(i, index, ctx->seed)) return -1;
    }
    for (i = 0u; i < ref_bytes / 2u; ++i) {
        uint16_t got = (uint16_t)((uint16_t)render_le[2u*i] |
                                 ((uint16_t)render_le[2u*i + 1u] << 8u));
        if (got != (uint16_t)sample(i, index, ctx->seed + 53u)) return -1;
    }
    ctx->last_seq = sequence;
    ++ctx->visited;
    return 0;
}
static fe_s2_config config(uint32_t scenario, uint32_t rate, uint32_t render) {
    fe_s2_config c;
    uint32_t i;
    memset(&c, 0, sizeof(c));
    c.rate_hz = rate;
    c.physical_mics = scenario == 0u ? 1u : scenario == 1u ? 2u : 4u;
    c.render_channels = render;
    c.capture_source_id = 100u + scenario;
    c.render_source_id = render ? 200u + scenario : 0u;
    c.capture_epoch = 1u;
    c.render_epoch = render ? 1u : 0u;
    for (i = 0u; i < 4u; ++i)
        c.physical_to_capture_slot[i] =
            i < c.physical_mics ? c.physical_mics - 1u - i : UINT32_MAX;
    return c;
}
static uint64_t ns_now(void) {
    struct timespec ts;
    need(clock_gettime(CLOCK_MONOTONIC, &ts) == 0, "clock_gettime");
    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) +
           (uint64_t)ts.tv_nsec;
}
static void sorted_insert(uint64_t *a, size_t count, uint64_t t) {
    size_t i = count;
    while (i > 0u && a[i - 1u] > t) {
        a[i] = a[i - 1u];
        --i;
    }
    a[i] = t;
}
static size_t make_stream(uint8_t *buffer, const fe_s2_config *cfg,
                          uint32_t seed, int record_timing) {
    fe_s2_writer w;
    fe_s2_frame frame;
    uint32_t cap_epoch = cfg->capture_epoch, ren_epoch = cfg->render_epoch;
    uint64_t sequence = UINT64_C(0);
    uint64_t times[100] = {0};
    size_t ncap = (size_t)(cfg->rate_hz / 100u) * cfg->physical_mics;
    size_t nref = (size_t)(cfg->rate_hz / 100u) * cfg->render_channels;
    size_t total = 0u;
    uint32_t i;
    memset(buffer, 0xa5, FE_S2_MAX_BYTES);
    need(fe_s2_writer_begin(&w, buffer, FE_S2_MAX_BYTES,
                            cfg, 100u) == FE_S2_OK, "writer_begin");
    need(fe_s2_writer_finish(&w, &total) == FE_S2_EINCOMPLETE,
         "incomplete_was_not_rejected");
    for (i = 0u; i < 100u; ++i) {
        uint32_t cap_flags = 0u, ren_flags = 0u;
        uint64_t start;
        if (i == 30u) {
            cap_flags = FE_S2_CAPTURE_GAP;
            ren_flags = cfg->render_channels ? FE_S2_RENDER_GAP : 0u;
            ++cap_epoch;
            if (cfg->render_channels) ++ren_epoch;
            sequence += UINT64_C(2);
        } else {
            ++sequence;
        }
        if (i == 60u) {
            cap_flags = FE_S2_CLOCK_RESET;
            ren_flags = cfg->render_channels ? FE_S2_CLOCK_RESET : 0u;
            ++cap_epoch;
            if (cfg->render_channels) ++ren_epoch;
        }
        if (i == 80u) {
            cap_flags = FE_S2_XRUN;
            ren_flags = cfg->render_channels ? FE_S2_XRUN : 0u;
            ++cap_epoch;
            if (cfg->render_channels) ++ren_epoch;
        }
        fill(i, seed, ncap, nref);
        memset(&frame, 0, sizeof(frame));
        frame.sequence = sequence;
        frame.capture_flags = cap_flags;
        frame.render_flags = ren_flags;
        frame.capture_epoch = cap_epoch;
        frame.render_epoch = ren_epoch;
        frame.capture = CAPTURE;
        frame.capture_count = ncap;
        frame.render = nref ? RENDER : NULL;
        frame.render_count = nref;
        start = ns_now();
        need(fe_s2_writer_append(&w, &frame) == FE_S2_OK, "append");
        sorted_insert(times, (size_t)i, ns_now() - start);
    }
    need(fe_s2_writer_finish(&w, &total) == FE_S2_OK, "writer_finish");
    if (record_timing)
        fprintf(stderr,
                "FE09_B2S2_HOSTED_ONLY_PER_10MS_ENCODE_NS rate=%u mics=%u render=%u p95=%llu p99=%llu (NOT_SSC305)\n",
                cfg->rate_hz, cfg->physical_mics, cfg->render_channels,
                (unsigned long long)times[94], (unsigned long long)times[98]);
    return total;
}
static void negative_parse(uint8_t *b, size_t total,
                           size_t location, int resign_header,
                           size_t record_offset, size_t stride,
                           unsigned *counter) {
    fe_s2_stream out, prior;
    uint8_t before = b[location];
    memset(&out, 0xcd, sizeof(out));
    prior = out;
    b[location] ^= 0x01u;
    if (resign_header) repair_header_crc(b);
    if (stride) repair_frame_crc(b + record_offset, stride);
    need(fe_s2_decode(b, total, &out) != FE_S2_OK, "bad_stream_admitted");
    need(memcmp(&out, &prior, sizeof(out)) == 0,
         "invalid_parse_modified_out");
    b[location] = before;
    if (resign_header) repair_header_crc(b);
    if (stride) repair_frame_crc(b + record_offset, stride);
    ++*counter;
}
static void negative_set32(uint8_t *b, size_t total,
                           size_t offset, uint32_t value,
                           int record, size_t stride, unsigned *counter) {
    uint8_t old[4];
    fe_s2_stream out, unchanged;
    size_t base = record ? FE_S2_HEADER_BYTES : 0u;
    memcpy(old, b + base + offset, sizeof(old));
    put32(b + base + offset, value);
    if (record) repair_frame_crc(b + base, stride);
    else repair_header_crc(b);
    memset(&out, 0x5a, sizeof(out));
    unchanged = out;
    need(fe_s2_decode(b, total, &out) != FE_S2_OK, "semantic_mutation_admitted");
    need(memcmp(&out, &unchanged, sizeof(out)) == 0,
         "bad_semantic_parse_modified_out");
    memcpy(b + base + offset, old, sizeof(old));
    if (record) repair_frame_crc(b + base, stride);
    else repair_header_crc(b);
    ++*counter;
}
static void negative_set64(uint8_t *b, size_t total,
                           uint64_t value, size_t stride, unsigned *counter) {
    uint8_t saved[8], *p = b + FE_S2_HEADER_BYTES;
    fe_s2_stream o;
    memcpy(saved, p, sizeof(saved));
    put64(p, value);
    repair_frame_crc(p, stride);
    need(fe_s2_decode(b, total, &o) != FE_S2_OK,
         "sequence_mutation_admitted");
    memcpy(p, saved, sizeof(saved));
    repair_frame_crc(p, stride);
    ++*counter;
}
static void negative_writer(const fe_s2_config *cfg, uint32_t seed,
                            unsigned *counter) {
    fe_s2_writer w, prior;
    fe_s2_frame f;
    size_t length = 0u, stride = 0u, ncap, nref;
    size_t i;
    need(fe_s2_layout(cfg, 2u, &length, &stride) == FE_S2_OK,
         "writer_layout");
    memset(IMAGE[1], 0xee, FE_S2_MAX_BYTES);
    need(fe_s2_writer_begin(&w, IMAGE[1], FE_S2_MAX_BYTES,
                            cfg, 2u) == FE_S2_OK, "writer_negative_begin");
    ncap = (size_t)(cfg->rate_hz / 100u) * cfg->physical_mics;
    nref = (size_t)(cfg->rate_hz / 100u) * cfg->render_channels;
    fill(0u, seed, ncap, nref);
    memset(&f, 0, sizeof(f));
    f.sequence = 1u;
    f.capture_epoch = cfg->capture_epoch;
    f.render_epoch = cfg->render_epoch;
    f.capture = CAPTURE;
    f.capture_count = ncap;
    f.render = nref ? RENDER : NULL;
    f.render_count = nref;
    for (i = 0u; i < 12u; ++i) {
        fe_s2_frame bad = f;
        switch (i) {
        case 0u: bad.sequence = 0u; break;
        case 1u: bad.sequence = 2u; break;
        case 2u: bad.capture = NULL; break;
        case 3u: bad.capture_count = ncap + 1u; break;
        case 4u: bad.capture_count = ncap - 1u; break;
        case 5u: bad.capture_flags = FE_S2_RENDER_GAP; break;
        case 6u: bad.capture_flags = FE_S2_CAPTURE_GAP; break;
        case 7u: bad.capture_epoch = 0u; break;
        case 8u: bad.capture_timestamp_valid = 1u; break;
        case 9u: bad.render_timestamp_valid = 1u; break;
        case 10u: bad.capture = (const int16_t *)(const void *)IMAGE[1]; break;
        default: bad.render_flags = FE_S2_CAPTURE_GAP; break;
        }
        memcpy(SNAP, IMAGE[1], length);
        prior = w;
        need(fe_s2_writer_append(&w, &bad) == FE_S2_EINVAL,
             "bad_writer_frame_admitted");
        need(memcmp(SNAP, IMAGE[1], length) == 0 &&
             memcmp(&prior, &w, sizeof(w)) == 0,
             "rejected_writer_modified_bytes");
        ++*counter;
    }
    need(fe_s2_writer_append(&w, &f) == FE_S2_OK, "positive_after_reject");
    prior = w;
    memcpy(SNAP, IMAGE[1], length);
    need(fe_s2_writer_append(&w, &f) == FE_S2_EINVAL, "repeated_seq");
    need(memcmp(SNAP, IMAGE[1], length) == 0 &&
         memcmp(&prior, &w, sizeof(w)) == 0,
         "repeated_seq_modified_bytes");
    ++*counter;
    (void)stride;
}
static unsigned mutations(uint8_t *b, size_t total,
                          size_t stride, const fe_s2_config *cfg,
                          uint32_t seed) {
    unsigned n = 0u, i;
    fe_s2_stream stream, before;
    size_t start = FE_S2_HEADER_BYTES + FE_S2_RECORD_META_BYTES;
    need(fe_s2_decode(b, total, &stream) == FE_S2_OK, "baseline_before_mutation");
    for (i = 0u; i < 64u; ++i) {
        /* 64 distinct frame/byte perturbations in the first four records.
         * Bounded near-front controls avoid quadratic QEMU CRC replay cost.
         */
        size_t at = start + ((size_t)i % 4u) * stride +
                    ((size_t)i * 17u % (stride - FE_S2_RECORD_META_BYTES - 4u));
        negative_parse(b, total, at, 0, 0u, 0u, &n);
    }
    for (i = 0u; i < 20u; ++i)
        negative_parse(b, total, (size_t)i * 4u, 0, 0u, 0u, &n);
    /* New parser must explicitly reject the unchanged legacy APD2/v1 magic. */
    negative_set32(b, total, 0u, UINT32_C(0x32445041), 0, stride, &n);
    negative_set32(b, total, 0u, FE_S2_MAGIC + 1u, 0, stride, &n);
    negative_set32(b, total, 4u, 3u, 0, stride, &n);
    negative_set32(b, total, 8u, UINT32_C(0x04030201), 0, stride, &n);
    negative_set32(b, total, 12u, 124u, 0, stride, &n);
    negative_set32(b, total, 16u, (uint32_t)total - 1u, 0, stride, &n);
    negative_set32(b, total, 20u, 0u, 0, stride, &n);
    negative_set32(b, total, 24u, 24000u, 0, stride, &n);
    negative_set32(b, total, 28u, 0u, 0, stride, &n);
    negative_set32(b, total, 32u, 3u, 0, stride, &n);
    negative_set32(b, total, 36u, 2u, 0, stride, &n);
    negative_set32(b, total, 40u, (uint32_t)stride + 1u, 0, stride, &n);
    negative_set32(b, total, 44u, 0u, 0, stride, &n);
    negative_set32(b, total, 48u, cfg->physical_mics, 0, stride, &n);
    negative_set32(b, total, 64u, 0u, 0, stride, &n);
    negative_set32(b, total, 68u, cfg->capture_source_id, 0, stride, &n);
    negative_set32(b, total, 72u, 0u, 0, stride, &n);
    negative_set32(b, total, 76u,
                   cfg->render_channels ? 0u : 1u, 0, stride, &n);
    negative_set32(b, total, 80u, 1u, 0, stride, &n);
    negative_set32(b, total, 84u, 1u, 0, stride, &n);
    negative_set32(b, total, 88u, 1u, 0, stride, &n);
    negative_set32(b, total, 92u, 1u, 0, stride, &n);
    negative_parse(b, total, 100u, 1, 0u, 0u, &n);
    negative_parse(b, total, 124u, 0, 0u, 0u, &n);
    negative_set64(b, total, UINT64_C(0), stride, &n);
    negative_set64(b, total, UINT64_C(5), stride, &n);
    negative_set32(b, total, 8u, 16u, 1, stride, &n);
    negative_set32(b, total, 12u, 16u, 1, stride, &n);
    negative_set32(b, total, 16u, 0u, 1, stride, &n);
    negative_set32(b, total, 20u,
                   cfg->render_channels ? 0u : 1u, 1, stride, &n);
    negative_set32(b, total, 24u, 1u, 1, stride, &n);
    negative_set32(b, total, 28u, 1u, 1, stride, &n);
    memset(&before, 0x6d, sizeof(before));
    stream = before;
    need(fe_s2_decode(b, total - 1u, &stream) != FE_S2_OK &&
         memcmp(&stream, &before, sizeof(before)) == 0, "truncated_accepted");
    ++n;
    b[total] = 0xa3u;
    stream = before;
    need(fe_s2_decode(b, total + 1u, &stream) != FE_S2_OK &&
         memcmp(&stream, &before, sizeof(before)) == 0, "appended_accepted");
    ++n;
    negative_writer(cfg, seed, &n);
    /* A successful replay must never overwrite any bytes of the original
     * APX3 stream via a caller-supplied, overlapping result pointer.
     * Align the interior pointer explicitly for native/ASan/ARM32.
     */
    {
        const size_t alignment = _Alignof(fe_s2_stream);
        const size_t offset =
            (size_t)((alignment - ((uintptr_t)b % alignment)) % alignment);
        fe_s2_stream *overlap;
        need(offset + sizeof(fe_s2_stream) <= total,
             "replay_alias_fixture_not_bounded");
        overlap = (fe_s2_stream *)(void *)(b + offset);
        memcpy(SNAP, b, total);
        need(fe_s2_replay(b, total, visit, NULL, overlap) == FE_S2_EINVAL,
             "replay_alias_admitted");
        need(memcmp(SNAP, b, total) == 0,
             "replay_alias_modified_original_bytes");
        ++n;
    }
    need(fe_s2_decode(b, total, &stream) == FE_S2_OK, "mutations_left_damage");
    return n;
}
int main(void) {
    const char *names[4] = {"C1_BASELINE", "C2_ULA", "C4_ULA", "C4_UCA"};
    const uint32_t rates[3] = {16000u, 32000u, 48000u};
    unsigned total_negatives = 0u, profiles = 0u, total_replays = 0u;
    uint64_t digest = UINT64_C(14695981039346656037);
    uint32_t s, r, ref;
    puts("{\"schema_version\":1,\"decision\":\"FE09_R2B2_S2_PRIVATE_APD_V2_READ_WRITE_REPLAY_RESEARCH_ONLY_NO_PUBLIC_ABI\",\"source_role\":\"first-party-synthetic\",\"public_sdk_installed\":false,\"actual_device_clock_qualified\":false,\"legacy_apd2_modified\":false,\"ssc305_dut_qualified\":false,\"profiles\":[");
    for (s = 0u; s < 4u; ++s) for (r = 0u; r < 3u; ++r) {
        unsigned negatives = 0u;
        uint64_t profile_hash = UINT64_C(0);
        if (profiles) puts(",");
        for (ref = 0u; ref < 2u; ++ref) {
            fe_s2_config cfg = config(s, rates[r], ref);
            fe_s2_stream stream, observed;
            visitor_ctx ctx;
            size_t a, b, stride;
            uint64_t hash;
            a = make_stream(IMAGE[0], &cfg, 11u + s, 1);
            b = make_stream(IMAGE[1], &cfg, 11u + s, 0);
            need(a == b && memcmp(IMAGE[0], IMAGE[1], a) == 0,
                 "independent_replay_not_byte_identical");
            need(fe_s2_layout(&cfg, 100u, &b, &stride) == FE_S2_OK &&
                 b == a, "layout_changed");
            need(fe_s2_decode(IMAGE[0], a, &stream) == FE_S2_OK &&
                 stream.frames == 100u && stream.total_bytes == a &&
                 stream.record_stride == stride, "strict_decode");
            memset(&ctx, 0, sizeof(ctx));
            ctx.seed = 11u + s; ctx.mics = cfg.physical_mics;
            ctx.rate = cfg.rate_hz; ctx.render = ref;
            need(fe_s2_replay(IMAGE[0], a, visit, &ctx, &observed) == FE_S2_OK &&
                 ctx.visited == 100u && observed.frames == 100u,
                 "bounded_replay_payload_mismatch");
            ++total_replays;
            hash = fnv(IMAGE[0], a);
            digest ^= hash; digest *= UINT64_C(1099511628211);
            profile_hash ^= hash;
            negatives += mutations(IMAGE[0], a, stride, &cfg, 11u + s);
            need(negatives >= 60u, "too_few_negative_mutations");
        }
        printf("{\"scene\":\"%s\",\"rate\":%u,\"mics\":%u,\"render_subcases\":2,\"repeats\":2,\"frames_per_subcase\":100,\"negative_cases\":%u,\"byte_hash\":\"%016llx\"}",
               names[s], rates[r], s == 0u ? 1u : s == 1u ? 2u : 4u,
               negatives, (unsigned long long)profile_hash);
        ++profiles;
        total_negatives += negatives;
    }
    printf("],\"profile_count\":%u,\"replay_subcases\":%u,\"total_negatives\":%u,\"stream_digest\":\"%016llx\"}\n",
           profiles, total_replays, total_negatives,
           (unsigned long long)digest);
    need(profiles == 12u && total_replays == 24u &&
         total_negatives >= 1440u && fail_count == 0u, "fixture_totals");
    return 0;
}
