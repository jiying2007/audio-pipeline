/* FE09-R2A fixed synthetic-only prototype qualification; no product exposure.
 * Actually links research array_sdk_draft_r2a.c + the SAME array_native.c.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_array_sdk_draft_r2a.h"
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define R2A_TEST_ARENA 8192u
#define TEST_FRAMES 100u
#define TEST_CASES 4u
#define TEST_NEGATIVES 25u
#define FNV_START UINT64_C(14695981039346656037)
#define FNV_MUL UINT64_C(1099511628211)

typedef struct { const char *name; unsigned mics, ring, render, delay; } test_case;
static const test_case CASES[TEST_CASES] = {
    {"C1_BASELINE", 1u, 0u, 0u, 17u},
    {"C2_ULA_35MM", 2u, 0u, 1u, 19u},
    {"C4_ULA_105MM", 4u, 0u, 1u, 22u},
    {"C4_UCA_RADIUS35MM", 4u, 1u, 1u, 21u},
};
typedef struct {
    uint64_t input, output, render, cpu_ns;
    uint64_t clipped;
    size_t state_bytes, native_bytes;
    unsigned negative_checks;
} evidence;

static void hash_s16(uint64_t *state, int16_t sample) {
    const uint16_t word = (uint16_t)sample;
    *state = (*state ^ (uint8_t)(word & 255u)) * FNV_MUL;
    *state = (*state ^ (uint8_t)(word >> 8u)) * FNV_MUL;
}
static int64_t cpu_time_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now) != 0) return -1;
    return (int64_t)now.tv_sec * INT64_C(1000000000) + (int64_t)now.tv_nsec;
}
static fe_r2a_config config_for(const test_case *sc) {
    fe_r2a_config cfg;
    unsigned mic;
    memset(&cfg, 0, sizeof(cfg));
    cfg.struct_size = (uint32_t)sizeof(cfg);
    cfg.api_version = FE_R2A_DRAFT_VERSION;
    cfg.sample_rate_hz = FE_R2A_RATE_HZ;
    cfg.frame_ms = FE_R2A_FRAME_MS;
    cfg.physical_mics = sc->mics;
    cfg.render_channels = sc->render;
    cfg.active_mic_mask = (1u << sc->mics) - 1u;
    cfg.source_direction[1] = 1.0;
    for (mic = 0u; mic < sc->mics; ++mic) {
        static const double ring_xy[4][2] = {
            {0.035, 0.0}, {0.0, 0.035},
            {-0.035, 0.0}, {0.0, -0.035}
        };
        cfg.microphones[mic].input_channel = mic;
        cfg.microphones[mic].gain = 1.0;
        cfg.microphones[mic].position_m[0] =
            sc->ring ? ring_xy[mic][0] : 0.035 * (double)mic;
        cfg.microphones[mic].position_m[1] =
            sc->ring ? ring_xy[mic][1] : 0.0;
    }
    return cfg;
}
static int test_bad_init(unsigned char *mem, size_t capacity,
                         const fe_r2a_config *cfg, fe_r2a_status expected) {
    unsigned char before[R2A_TEST_ARENA];
    fe_r2a_adapter *out = NULL;
    fe_r2a_status status;
    if (capacity > sizeof(before)) return 0;
    memcpy(before, mem, capacity);
    status = fe_r2a_init(mem, capacity, cfg, &out);
    return status == expected && out == NULL &&
           memcmp(mem, before, capacity) == 0;
}
static int negatives(const test_case *sc, unsigned char *mem,
                     fe_r2a_adapter *valid_state, size_t need,
                     unsigned *tested) {
    fe_r2a_config cfg = config_for(sc), malformed;
    int16_t capture[FE_R2A_FRAME_SAMPLES * FE_ARRAY_MAX_MICS] = {0};
    int16_t render[FE_R2A_FRAME_SAMPLES] = {0};
    int16_t output[FE_R2A_FRAME_SAMPLES];
    unsigned char state_snapshot[R2A_TEST_ARENA];
    unsigned char output_snapshot[sizeof(output)];
    const size_t cap_count = (size_t)FE_R2A_FRAME_SAMPLES * sc->mics;
    const size_t ren_count = (size_t)FE_R2A_FRAME_SAMPLES * sc->render;
    const int16_t *ref = sc->render ? render : NULL;
    const double invalid_dir[3] = {2.0, 0.0, 0.0};
    fe_r2a_info info;
    unsigned count = 0u;
#define INVALID_INIT(expected) do { \
    memset(mem, 0xa5, R2A_TEST_ARENA); \
    if (!test_bad_init(mem, R2A_TEST_ARENA, &malformed, (expected))) return 0; \
    ++count; \
} while (0)
    malformed = cfg;
    malformed.api_version = 1u;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.struct_size--;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.physical_mics = 3u;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.render_channels = 2u;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.sample_rate_hz = 48000u;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.capture_clock_authority = 1u;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.microphones[0].input_channel = cfg.physical_mics;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    if (sc->mics > 1u)
        malformed.microphones[1].input_channel = 0u;
    else
        malformed.microphones[0].gain = 0.0;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.source_direction[1] = NAN;
    INVALID_INIT(FE_R2A_EINVAL);
    memset(mem, 0xa5, R2A_TEST_ARENA);
    if (!test_bad_init(mem, need - 1u, &cfg, FE_R2A_ENOMEM)) return 0;
    ++count;
    {
        fe_r2a_adapter *out = NULL;
        memset(mem, 0xa5, R2A_TEST_ARENA);
        if (fe_r2a_init(mem + 1u, need, &cfg, &out) != FE_R2A_EINVAL ||
            out != NULL || mem[1] != 0xa5) return 0;
        ++count;
    }
    malformed = cfg;
    malformed.reference_mic = cfg.physical_mics;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.microphones[0].gain = NAN;
    INVALID_INIT(FE_R2A_EINVAL);
    malformed = cfg;
    malformed.microphones[0].latency_samples = 9.0;
    INVALID_INIT(FE_R2A_EINVAL);
#undef INVALID_INIT
    /* Re-initialize the same caller-owned arena exactly once. */
    if (fe_r2a_init(mem, R2A_TEST_ARENA, &cfg, &valid_state) != FE_R2A_OK ||
        !valid_state) return 0;
    memset(output, 0xa5, sizeof(output));
    memcpy(output_snapshot, output, sizeof(output));
    memcpy(state_snapshot, mem, need);
#define NEGATIVE(call) do { \
    if ((call) != FE_R2A_EINVAL || memcmp(mem, state_snapshot, need) || \
        memcmp(output, output_snapshot, sizeof(output))) return 0; \
    ++count; \
} while (0)
    NEGATIVE(fe_r2a_process(valid_state, capture, cap_count-1u, ref, ren_count,
                             output, FE_R2A_FRAME_SAMPLES));
    NEGATIVE(fe_r2a_process(valid_state, capture, cap_count,
                            sc->render ? NULL : render, ren_count,
                            output, FE_R2A_FRAME_SAMPLES));
    NEGATIVE(fe_r2a_process(valid_state, capture, cap_count, ref, ren_count,
                            output, FE_R2A_FRAME_SAMPLES-1u));
    NEGATIVE(fe_r2a_process(valid_state, capture, cap_count, ref, ren_count,
                            capture, FE_R2A_FRAME_SAMPLES));
    NEGATIVE(fe_r2a_set_active_mask(valid_state, 0u));
    NEGATIVE(fe_r2a_request_steer(valid_state, invalid_dir, 32u));
    NEGATIVE(fe_r2a_notify_gap(valid_state, 0u));
    NEGATIVE(fe_r2a_process(valid_state, NULL, cap_count, ref, ren_count,
                            output, FE_R2A_FRAME_SAMPLES));
    NEGATIVE(fe_r2a_process(valid_state, (const int16_t *)mem, cap_count,
                            ref, ren_count, output, FE_R2A_FRAME_SAMPLES));
    NEGATIVE(fe_r2a_process(valid_state, capture, cap_count,
                            output, sc->render ? ren_count : 0u,
                            output, FE_R2A_FRAME_SAMPLES));
    NEGATIVE(fe_r2a_notify_gap(valid_state, 4u));
#undef NEGATIVE
    if (fe_r2a_get_info(valid_state, &info) != FE_R2A_OK ||
        info.total_frames != 0u || info.capture_epoch != 0u ||
        info.clipped_samples != 0u || count != TEST_NEGATIVES)
        return 0;
    *tested = count;
    return 1;
}
static int run_case(const test_case *sc, evidence *result, int timed) {
    _Alignas(FE_R2A_ALIGNMENT) unsigned char arena[R2A_TEST_ARENA];
    fe_r2a_config cfg = config_for(sc);
    fe_r2a_adapter *state = NULL;
    fe_r2a_info info;
    const size_t needed = fe_r2a_state_bytes(&cfg);
    uint64_t digest[2][3] = {{0u}}, cpu = 0u, clips[2] = {0u,0u};
    unsigned pass, frame, sample, mic, neg=0u;
    int16_t capture[FE_R2A_FRAME_SAMPLES * FE_ARRAY_MAX_MICS];
    int16_t render[FE_R2A_FRAME_SAMPLES], output[FE_R2A_FRAME_SAMPLES];
    if (needed == 0u || needed > sizeof(arena) ||
        !negatives(sc, arena, state, needed, &neg)) return 0;
    for (pass = 0u; pass < 2u; ++pass) {
        uint32_t rng = UINT32_C(0x13579bdf) ^ (sc->mics << 8u) ^ (sc->ring << 16u);
        if (fe_r2a_init(arena, sizeof(arena), &cfg, &state) != FE_R2A_OK ||
            !state) return 0;
        for (mic=0u;mic<3u;++mic) digest[pass][mic]=FNV_START;
        for (frame = 0u; frame < TEST_FRAMES; ++frame) {
            int64_t begin=0, end=0;
            if (frame == 25u) {
                const double xdir[3] = {1.0, 0.0, 0.0};
                if (fe_r2a_request_steer(state, xdir, 32u) != FE_R2A_OK) return 0;
            }
            if (frame == 50u) {
                if (fe_r2a_notify_gap(state, FE_R2A_CAPTURE_GAP) != FE_R2A_OK)
                    return 0;
                /* Exactly one synthetic capture frame absent, never padded. */
                for (sample=0u;sample<FE_R2A_FRAME_SAMPLES;++sample)
                    for (mic=0u;mic<sc->mics;++mic)
                        rng = 1664525u*rng + 1013904223u;
            }
            if (frame == 70u && sc->mics > 1u) {
                if (fe_r2a_set_active_mask(state, ((1u << sc->mics)-1u) & ~1u)
                    != FE_R2A_OK) return 0;
            }
            if (frame == 80u && sc->render) {
                if (fe_r2a_notify_gap(state, FE_R2A_RENDER_GAP) != FE_R2A_OK)
                    return 0;
            }
            for (sample=0u; sample<FE_R2A_FRAME_SAMPLES; ++sample) {
                const int32_t tick=(int32_t)(frame*FE_R2A_FRAME_SAMPLES+sample);
                render[sample] = (int16_t)(((tick*31+7)%2048)-1024);
                for (mic=0u;mic<sc->mics;++mic) {
                    int32_t value;
                    rng = 1664525u*rng + 1013904223u;
                    value = (int32_t)((rng>>15u)&8191u)-4096+(int32_t)(mic*37u);
                    capture[sample*sc->mics+mic]=(int16_t)value;
                    hash_s16(&digest[pass][0], (int16_t)value);
                }
                if (sc->render) hash_s16(&digest[pass][1],render[sample]);
            }
            if (timed && (begin=cpu_time_ns()) < 0) return 0;
            if (fe_r2a_process(state, capture,
                               (size_t)FE_R2A_FRAME_SAMPLES*sc->mics,
                               sc->render ? render : NULL,
                               (size_t)FE_R2A_FRAME_SAMPLES*sc->render,
                               output, FE_R2A_FRAME_SAMPLES) != FE_R2A_OK) return 0;
            if (timed) {
                end=cpu_time_ns();
                if (end < begin) return 0;
                cpu+=(uint64_t)(end-begin);
            }
            for (sample=0u;sample<FE_R2A_FRAME_SAMPLES;++sample)
                hash_s16(&digest[pass][2],output[sample]);
        }
        if (fe_r2a_get_info(state, &info) != FE_R2A_OK ||
            info.requested_state_bytes != needed ||
            info.native_fir33_state_bytes !=
                fe_array_state_bytes_for_mode(sc->mics, FE_ARRAY_FIR33_HANN) ||
            info.common_delay_samples != sc->delay ||
            info.physical_mics != sc->mics ||
            info.render_channels != sc->render ||
            info.total_frames != TEST_FRAMES ||
            info.capture_epoch != 1u ||
            info.render_epoch != (uint64_t)sc->render ||
            info.observed_render_frames != (uint64_t)(TEST_FRAMES*sc->render))
            return 0;
        clips[pass]=info.clipped_samples;
    }
    if (memcmp(digest[0],digest[1],sizeof(digest[0])) || clips[0]!=clips[1] ||
        clips[0]!=0u) return 0;
    result->input=digest[0][0];
    result->render=digest[0][1];
    result->output=digest[0][2];
    result->state_bytes=needed;
    result->native_bytes=info.native_fir33_state_bytes;
    result->clipped=clips[0];
    result->cpu_ns=cpu;
    result->negative_checks=neg;
    return 1;
}
int main(int argc,char **argv) {
    evidence results[TEST_CASES] = {{0}};
    int timed=0;
    unsigned i;
    if (argc==2 && strcmp(argv[1],"--timing")==0) timed=1;
    else if (argc!=1) return 2;
    for(i=0u;i<TEST_CASES;++i) {
        if (!run_case(&CASES[i],&results[i],timed)) {
            fprintf(stderr,"FE09_R2A_ABI_OR_LIFECYCLE_NOT_ADMITTED profile=%s\n",
                    CASES[i].name);
            return 3;
        }
    }
    printf("{\"schema_version\":1,\"decision\":\"FE09_R2A_UNIFIED_ARRAY_SDK_PROTOTYPE_RESEARCH_ONLY_NO_RELEASE\","
           "\"public_sdk_installed\":false,\"shipping_authority\":false,"
           "\"actual_adc_clock_qualified\":false,\"target_cpu_qualified\":false,"
           "\"render_is_not_aec\":true,\"source_role\":\"first-party-synthetic\","
           "\"profile_count\":4,\"repeats\":2,\"profiles\":[");
    for(i=0u;i<TEST_CASES;++i) {
        const evidence *r=&results[i];
        printf("%s{\"name\":\"%s\",\"physical_mics\":%u,\"render_channels\":%u,"
               "\"state_bytes\":%zu,\"native_fir33_bytes\":%zu,"
               "\"common_delay_samples\":%u,\"capture_frame_bytes\":%u,"
               "\"render_frame_bytes\":%u,\"frames_per_repeat\":100,"
               "\"negative_checks\":%u,\"capture_epoch\":1,"
               "\"render_epoch\":%u,\"clipped_samples\":%" PRIu64 ","
               "\"input_fnv64\":\"%016" PRIx64 "\","
               "\"render_fnv64\":\"%016" PRIx64 "\","
               "\"output_fnv64\":\"%016" PRIx64 "\"",
               i?",":"", CASES[i].name,CASES[i].mics,CASES[i].render,
               r->state_bytes,r->native_bytes,CASES[i].delay,320u*CASES[i].mics,
               320u*CASES[i].render,r->negative_checks,CASES[i].render,
               r->clipped,r->input,r->render,r->output);
        if(timed)printf(",\"host_thread_cpu_ns_two_repeats\":%" PRIu64,r->cpu_ns);
        printf("}");
    }
    puts("]}");
    return 0;
}
