/* FE09-R2B1A deterministic source-generated 16kHz ingress tests.
 * No original audio, physical timestamps, BF/AEC/SRC, DUT or product claims.
 */
#include "fe09_b1a_ingress.h"
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define TEST_ARENA 512u
#define FRAMES 100u
#define MIN_NEGATIVES 25u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

typedef struct {
    const char *name;
    uint32_t mics;
    uint32_t render;
    uint32_t slots[4];
} profile_t;

static const profile_t PROFILES[] = {
    {"C1_BASELINE", 1u, 0u, {0u, 0u, 0u, 0u}},
    {"C2_ULA", 2u, 1u, {1u, 0u, 0u, 0u}},
    {"C4_ULA", 4u, 1u, {2u, 0u, 3u, 1u}},
    {"C4_UCA", 4u, 1u, {3u, 2u, 1u, 0u}}
};

typedef struct {
    size_t state_bytes;
    uint32_t negatives;
    uint64_t input_fp;
    uint64_t output_fp;
    uint64_t render_fp;
    fe_b1a_info info;
} proof_t;

static uint64_t hash_s16(uint64_t h, int16_t value) {
    const uint16_t word = (uint16_t)value;
    h = (h ^ (uint8_t)(word & UINT16_C(255))) * FNV_PRIME;
    return (h ^ (uint8_t)(word >> 8u)) * FNV_PRIME;
}

static uint64_t hash_f32(uint64_t h, float value) {
    uint32_t bits, i;
    memcpy(&bits, &value, sizeof(bits));
    for (i = 0u; i < 4u; ++i)
        h = (h ^ (uint8_t)(bits >> (8u * i))) * FNV_PRIME;
    return h;
}

static fe_b1a_config config_for(const profile_t *p) {
    fe_b1a_config cfg;
    uint32_t i;
    memset(&cfg, 0, sizeof(cfg));
    cfg.struct_size = (uint32_t)sizeof(cfg);
    cfg.api_version = FE_B1A_API_VERSION;
    cfg.io_rate_hz = FE_B1A_RATE_HZ;
    cfg.frame_ms = FE_B1A_FRAME_MS;
    cfg.physical_mics = p->mics;
    cfg.render_channels = p->render;
    cfg.active_mic_mask = (1u << p->mics) - 1u;
    for (i = 0u; i < p->mics; ++i)
        cfg.physical_to_capture_slot[i] = p->slots[i];
    return cfg;
}

static int16_t capture_pcm(uint32_t physical, uint32_t sample, uint32_t frame) {
    const uint32_t raw = (frame * 337u + sample * 73u +
                          physical * 1931u) % UINT32_C(65536);
    if (frame == 0u && physical == 0u && sample == 0u) return INT16_MIN;
    if (frame == 0u && physical == 0u && sample == 1u) return INT16_MAX;
    return (int16_t)((int32_t)raw - 32768);
}

static int16_t render_pcm(uint32_t sample, uint32_t frame) {
    const uint32_t raw = (frame * 233u + sample * 229u) % UINT32_C(65536);
    return (int16_t)((int32_t)raw - 32768);
}

static int bad_init(const fe_b1a_config *cfg, size_t size,
                    fe_b1a_status expected, size_t shift) {
    _Alignas(16) unsigned char arena[TEST_ARENA + 16u];
    unsigned char before[sizeof(arena)];
    fe_b1a_ingress *state = (fe_b1a_ingress *)(uintptr_t)1u;
    fe_b1a_status got;
    memset(arena, 0x35, sizeof(arena));
    memcpy(before, arena, sizeof(before));
    got = fe_b1a_init(arena + shift, size, cfg, &state);
    return got == expected && state == NULL &&
           memcmp(arena, before, sizeof(arena)) == 0;
}

static int bad_null_memory(const fe_b1a_config *cfg) {
    fe_b1a_ingress *state = (fe_b1a_ingress *)(uintptr_t)1u;
    return fe_b1a_init(NULL, 0u, cfg, &state) == FE_B1A_EINVAL &&
           state == NULL;
}

static int bad_out_alias(const fe_b1a_config *cfg) {
    _Alignas(16) unsigned char arena[TEST_ARENA], before[TEST_ARENA];
    memset(arena, 0x45, sizeof(arena));
    memcpy(before, arena, sizeof(before));
    return fe_b1a_init(arena, sizeof(arena), cfg,
                        (fe_b1a_ingress **)(void *)arena) == FE_B1A_EINVAL &&
           memcmp(arena, before, sizeof(arena)) == 0;
}

static int bad_config_alias(const fe_b1a_config *cfg) {
    _Alignas(16) unsigned char arena[TEST_ARENA], before[TEST_ARENA];
    fe_b1a_ingress *state = (fe_b1a_ingress *)(uintptr_t)1u;
    fe_b1a_status got;
    memset(arena, 0x55, sizeof(arena));
    memcpy(arena, cfg, sizeof(*cfg));
    memcpy(before, arena, sizeof(before));
    got = fe_b1a_init(arena, sizeof(arena),
                       (const fe_b1a_config *)(const void *)arena, &state);
    return got == FE_B1A_EINVAL && state == NULL &&
           memcmp(arena, before, sizeof(arena)) == 0;
}

static int negatives(const profile_t *p, unsigned char *arena, size_t need,
                     fe_b1a_ingress *state, uint32_t *negative_count) {
    fe_b1a_config cfg = config_for(p), bad;
    int16_t capture[FE_B1A_SAMPLES_PER_MIC * FE_B1A_MAX_MICS] = {0};
    int16_t render[FE_B1A_SAMPLES_PER_MIC] = {0};
    int16_t input_before[sizeof(capture)/sizeof(capture[0])];
    int16_t render_before[sizeof(render)/sizeof(render[0])];
    float mic[FE_B1A_SAMPLES_PER_MIC * FE_B1A_MAX_MICS];
    float reference[FE_B1A_SAMPLES_PER_MIC];
    float mic_before[sizeof(mic)/sizeof(mic[0])];
    float ref_before[sizeof(reference)/sizeof(reference[0])];
    unsigned char state_before[TEST_ARENA];
    const size_t cap = (size_t)p->mics * FE_B1A_SAMPLES_PER_MIC;
    const size_t ren = (size_t)p->render * FE_B1A_SAMPLES_PER_MIC;
    const int16_t *r = p->render ? render : NULL;
    float *ro = p->render ? reference : NULL;
    fe_b1a_info info;
    uint32_t count = 0u;
    size_t i;
    if (need > TEST_ARENA) return 0;
    for (i = 0u; i < sizeof(mic)/sizeof(mic[0]); ++i)
        mic[i] = -999.0f;
    for (i = 0u; i < sizeof(reference)/sizeof(reference[0]); ++i)
        reference[i] = -999.0f;

#define BAD_CONFIG() do { \
    if (!bad_init(&bad, TEST_ARENA, FE_B1A_EINVAL, 0u)) return 0; \
    ++count; \
} while (0)
    bad = cfg; bad.struct_size--; BAD_CONFIG();
    bad = cfg; bad.api_version = 1u; BAD_CONFIG();
    bad = cfg; bad.io_rate_hz = 48000u; BAD_CONFIG();
    bad = cfg; bad.frame_ms = 20u; BAD_CONFIG();
    bad = cfg; bad.physical_mics = 3u; BAD_CONFIG();
    bad = cfg; bad.render_channels = 2u; BAD_CONFIG();
    bad = cfg; bad.active_mic_mask = 0u; BAD_CONFIG();
    bad = cfg; bad.active_mic_mask = UINT32_MAX; BAD_CONFIG();
    bad = cfg; bad.capture_clock_authority = 1u; BAD_CONFIG();
    bad = cfg; bad.physical_to_capture_slot[0] = p->mics; BAD_CONFIG();
    bad = cfg;
    if (p->mics >= 2u)
        bad.physical_to_capture_slot[1] = cfg.physical_to_capture_slot[0];
    else
        bad.physical_to_capture_slot[0] = 1u;
    BAD_CONFIG();
    bad = cfg; bad.reserved[1] = 1u; BAD_CONFIG();
    bad = cfg;
    if (p->mics < FE_B1A_MAX_MICS)
        bad.physical_to_capture_slot[p->mics] = 1u;
    else
        bad.reserved[3] = 1u;
    BAD_CONFIG();
#undef BAD_CONFIG
    if (!bad_init(&cfg, need - 1u, FE_B1A_ENOMEM, 0u)) return 0;
    ++count;
    if (!bad_init(&cfg, TEST_ARENA - 1u, FE_B1A_EINVAL, 1u))
        return 0;
    ++count;
    if (!bad_null_memory(&cfg) || !bad_out_alias(&cfg) ||
        !bad_config_alias(&cfg)) return 0;
    count += 3u;

#define REJECT(expression, expected) do { \
    fe_b1a_status got; \
    memcpy(state_before, arena, need); \
    memcpy(mic_before, mic, sizeof(mic)); \
    memcpy(ref_before, reference, sizeof(reference)); \
    memcpy(input_before, capture, sizeof(capture)); \
    memcpy(render_before, render, sizeof(render)); \
    got = (expression); \
    if (got != (expected) || memcmp(arena, state_before, need) || \
        memcmp(mic, mic_before, sizeof(mic)) || \
        memcmp(reference, ref_before, sizeof(reference)) || \
        memcmp(capture, input_before, sizeof(capture)) || \
        memcmp(render, render_before, sizeof(render))) return 0; \
    ++count; \
} while (0)
#define PROC(a,b,c,d,e,f,g,h) \
    fe_b1a_process(state, (a),(b),(c),(d),(e),(f),(g),(h))
    REJECT(PROC(NULL,cap,r,ren,mic,cap,ro,ren), FE_B1A_EINVAL);
    REJECT(PROC(capture,cap,r,ren,NULL,cap,ro,ren), FE_B1A_EINVAL);
    REJECT(PROC(capture,cap-1u,r,ren,mic,cap,ro,ren), FE_B1A_EINVAL);
    REJECT(PROC(capture,cap+1u,r,ren,mic,cap,ro,ren), FE_B1A_EINVAL);
    REJECT(PROC(capture,cap,r,ren,mic,cap-1u,ro,ren), FE_B1A_EINVAL);
    REJECT(PROC(capture,cap,r,ren,mic,cap+1u,ro,ren), FE_B1A_EINVAL);
    REJECT(PROC((const int16_t *)(const void *)arena,cap,r,ren,mic,cap,ro,ren),
           FE_B1A_EINVAL);
    REJECT(PROC(capture,cap,r,ren,(float *)(void *)arena,cap,ro,ren),
           FE_B1A_EINVAL);
    REJECT(PROC(capture,cap,r,ren,(float *)(void *)capture,cap,ro,ren),
           FE_B1A_EINVAL);
    if (p->render) {
        REJECT(PROC(capture,cap,NULL,ren,mic,cap,ro,ren), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,r,ren,mic,cap,NULL,ren), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,r,ren-1u,mic,cap,ro,ren), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,r,ren,mic,cap,ro,ren-1u), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,capture,ren,mic,cap,ro,ren), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,r,ren,mic,cap,mic,ren), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,r,ren,mic,cap,(float *)(void *)render,ren),
               FE_B1A_EINVAL);
    } else {
        REJECT(PROC(capture,cap,render,0u,mic,cap,NULL,0u), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,NULL,0u,mic,cap,reference,0u), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,NULL,1u,mic,cap,NULL,0u), FE_B1A_EINVAL);
        REJECT(PROC(capture,cap,NULL,0u,mic,cap,NULL,1u), FE_B1A_EINVAL);
    }
    REJECT(fe_b1a_set_active_mask(state, 0u), FE_B1A_EINVAL);
    REJECT(fe_b1a_set_active_mask(state, UINT32_MAX), FE_B1A_EINVAL);
    REJECT(fe_b1a_notify_gap(state, 0u), FE_B1A_EINVAL);
    REJECT(fe_b1a_notify_gap(state, UINT32_MAX), FE_B1A_EINVAL);
    if (!p->render)
        REJECT(fe_b1a_notify_gap(state, FE_B1A_RENDER_GAP), FE_B1A_EINVAL);
    REJECT(fe_b1a_get_info(state, NULL), FE_B1A_EINVAL);
    REJECT(fe_b1a_get_info(state, (fe_b1a_info *)(void *)arena), FE_B1A_EINVAL);
#undef PROC
#undef REJECT
    if (fe_b1a_process(NULL, capture, cap, r, ren, mic, cap, ro, ren) !=
        FE_B1A_ESTATE) return 0;
    ++count;
    if (fe_b1a_reset(NULL) != FE_B1A_ESTATE) return 0;
    ++count;
    if (fe_b1a_get_info(state, &info) != FE_B1A_OK ||
        info.accepted_frames != 0u || info.capture_epoch != 0u)
        return 0;
    if (count < MIN_NEGATIVES) return 0;
    *negative_count = count;
    return 1;
}

static int run_profile(const profile_t *p, proof_t *out) {
    _Alignas(16) unsigned char arena[TEST_ARENA];
    fe_b1a_config cfg = config_for(p);
    fe_b1a_ingress *state = NULL;
    fe_b1a_info info;
    uint32_t frame, k, physical;
    int16_t capture[FE_B1A_SAMPLES_PER_MIC * FE_B1A_MAX_MICS] = {0};
    int16_t render[FE_B1A_SAMPLES_PER_MIC] = {0};
    float mic[FE_B1A_SAMPLES_PER_MIC * FE_B1A_MAX_MICS];
    float reference[FE_B1A_SAMPLES_PER_MIC];
    const size_t cap = (size_t)p->mics * FE_B1A_SAMPLES_PER_MIC;
    const size_t ref = (size_t)p->render * FE_B1A_SAMPLES_PER_MIC;
    uint32_t negative_count = 0u;
    memset(out, 0, sizeof(*out));
    out->state_bytes = fe_b1a_state_bytes(&cfg);
    if (out->state_bytes == 0u || out->state_bytes > TEST_ARENA ||
        fe_b1a_init(arena, sizeof(arena), &cfg, &state) != FE_B1A_OK ||
        !state) return 0;
    if (!negatives(p, arena, out->state_bytes, state, &negative_count))
        return 0;
    out->negatives = negative_count;
    out->input_fp = FNV_OFFSET;
    out->output_fp = FNV_OFFSET;
    out->render_fp = FNV_OFFSET;
    for (frame = 0u; frame < FRAMES; ++frame) {
        const uint32_t capture_source = frame + (frame >= 50u ? 1u : 0u);
        const uint32_t render_source = frame + (frame >= 80u ? 1u : 0u);
        const uint32_t mask = frame < 70u ? (1u << p->mics) - 1u :
                              (p->mics == 4u ? 13u : 1u);
        if (frame == 50u &&
            fe_b1a_notify_gap(state, FE_B1A_CAPTURE_GAP) != FE_B1A_OK)
            return 0;
        if (frame == 70u &&
            fe_b1a_set_active_mask(state, mask) != FE_B1A_OK)
            return 0;
        if (frame == 80u && p->render &&
            fe_b1a_notify_gap(state, FE_B1A_RENDER_GAP) != FE_B1A_OK)
            return 0;
        if (frame == 90u &&
            fe_b1a_notify_gap(state, FE_B1A_CLOCK_RESET) != FE_B1A_OK)
            return 0;
        for (physical = 0u; physical < p->mics; ++physical) {
            for (k = 0u; k < FE_B1A_SAMPLES_PER_MIC; ++k) {
                const int16_t sample = capture_pcm(physical, k, capture_source);
                capture[(size_t)k * p->mics + p->slots[physical]] = sample;
                out->input_fp = hash_s16(out->input_fp, sample);
            }
        }
        if (p->render)
            for (k = 0u; k < FE_B1A_SAMPLES_PER_MIC; ++k) {
                render[k] = render_pcm(k, render_source);
                out->render_fp = hash_s16(out->render_fp, render[k]);
            }
        if (fe_b1a_process(state, capture, cap,
                            p->render ? render : NULL, ref,
                            mic, cap, p->render ? reference : NULL, ref)
            != FE_B1A_OK) return 0;
        for (physical = 0u; physical < p->mics; ++physical) {
            for (k = 0u; k < FE_B1A_SAMPLES_PER_MIC; ++k) {
                const int active = (mask & (1u << physical)) != 0u;
                const int16_t raw = active ?
                    capture[(size_t)k * p->mics + p->slots[physical]] : 0;
                const float expected = (float)raw * (1.0f / 32768.0f);
                const float actual = mic[(size_t)physical * FE_B1A_SAMPLES_PER_MIC + k];
                if (memcmp(&actual, &expected, sizeof(float)) != 0) return 0;
                out->output_fp = hash_f32(out->output_fp, actual);
            }
        }
        if (p->render)
            for (k = 0u; k < FE_B1A_SAMPLES_PER_MIC; ++k) {
                const float expected = (float)render[k] * (1.0f / 32768.0f);
                if (memcmp(&expected, &reference[k], sizeof(float)) != 0)
                    return 0;
            }
    }
    if (fe_b1a_get_info(state, &info) != FE_B1A_OK ||
        info.requested_state_bytes != out->state_bytes ||
        info.physical_mics != p->mics ||
        info.render_channels != p->render ||
        info.active_mic_mask != (p->mics == 4u ? 13u : 1u) ||
        info.capture_clock_authority != 0u ||
        info.accepted_frames != FRAMES ||
        info.capture_epoch != 2u ||
        info.render_epoch != (p->render ? 2u : 0u) ||
        info.clock_epoch != 1u ||
        info.capture_frames_in_epoch != 10u ||
        info.render_frames_in_epoch != (p->render ? 10u : 0u) ||
        (!p->render && info.render_stream_hash != 0u))
        return 0;
    out->info = info;
    if (fe_b1a_reset(state) != FE_B1A_OK ||
        fe_b1a_get_info(state, &info) != FE_B1A_OK ||
        info.accepted_frames != 0u || info.capture_epoch != 0u ||
        info.render_epoch != 0u || info.clock_epoch != 0u ||
        info.active_mic_mask != (p->mics == 4u ? 13u : 1u))
        return 0;
    return 1;
}

int main(void) {
    size_t i, j;
    const size_t total = sizeof(PROFILES) / sizeof(PROFILES[0]);
    proof_t first, second;
    printf("{\"schema_version\":1,\"decision\":\"FE09_R2B1A_SEPARATE_CAPTURE_RENDER_INGRESS_RESEARCH_ONLY_NO_RELEASE\",");
    printf("\"source_role\":\"first-party-synthetic\",\"profile_count\":%zu,\"repeats\":2,",total);
    printf("\"sample_rate_hz\":16000,\"frame_ms\":10,\"identity_only\":true,");
    printf("\"public_sdk_installed\":false,\"shipping_authority\":false,");
    printf("\"render_is_not_aec\":true,\"multirate_src_qualified\":false,");
    printf("\"real_adc_clock_qualified\":false,\"ssc305_dut_qualified\":false,\"profiles\":[");
    for (i = 0u; i < total; ++i) {
        if (!run_profile(&PROFILES[i], &first) ||
            !run_profile(&PROFILES[i], &second) ||
            memcmp(&first, &second, sizeof(first)) != 0) {
            fprintf(stderr, "FE09_B1A_PROOF_FAILED profile=%zu\n", i);
            return 1;
        }
        if (i) printf(",");
        printf("{\"name\":\"%s\",\"physical_mics\":%u,\"render_channels\":%u,",
               PROFILES[i].name, PROFILES[i].mics, PROFILES[i].render);
        printf("\"state_bytes\":%zu,\"frames_per_repeat\":100,\"negative_checks\":%u,",
               first.state_bytes, first.negatives);
        printf("\"capture_epoch\":%" PRIu64 ",\"render_epoch\":%" PRIu64 ",",
               first.info.capture_epoch, first.info.render_epoch);
        printf("\"clock_epoch\":%" PRIu64 ",\"capture_frames_in_epoch\":%" PRIu64 ",",
               first.info.clock_epoch, first.info.capture_frames_in_epoch);
        printf("\"render_frames_in_epoch\":%" PRIu64 ",",
               first.info.render_frames_in_epoch);
        printf("\"input_fnv64\":\"%016" PRIx64 "\",", first.input_fp);
        printf("\"output_fnv64\":\"%016" PRIx64 "\",", first.output_fp);
        printf("\"render_fnv64\":\"%016" PRIx64 "\",", first.render_fp);
        printf("\"capture_stream_hashes\":[");
        for (j = 0u; j < PROFILES[i].mics; ++j) {
            if (j) printf(",");
            printf("\"%016" PRIx64 "\"", first.info.capture_stream_hash[j]);
        }
        printf("],\"render_stream_hash\":\"%016" PRIx64 "\"}",
               first.info.render_stream_hash);
    }
    puts("]}");
    return 0;
}
