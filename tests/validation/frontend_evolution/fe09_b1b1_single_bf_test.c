/* FE09-R2B1B-S1: native/sanitized/AArch32 actual SRC -> one actual array BF.
 * All scenes are synthetic fixtures; hashes and bit equality are per-target.
 * Production src/ and installed 2.x interface are never included/modified.
 */
#include "fe09_b1b1_single_bf.h"
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#define STATE_CAP 16384u
#define WORK_CAP 32768u
#define FRAMES 100u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

typedef struct {
    const char *name;
    uint32_t n, render, slots[4], circle;
} scene_t;
static const scene_t SCENES[4] = {
    {"C1_BASELINE", 1u, 0u, {0u, 0u, 0u, 0u}, 0u},
    {"C2_ULA", 2u, 1u, {1u, 0u, 0u, 0u}, 0u},
    {"C4_ULA", 4u, 1u, {2u, 0u, 3u, 1u}, 0u},
    {"C4_UCA", 4u, 1u, {3u, 2u, 1u, 0u}, 1u}
};
static const uint32_t RATES[3] = {16000u, 32000u, 48000u};

typedef struct {
    fe_b1b1_info info;
    uint64_t source_hash, beam_hash, render_hash;
    uint32_t negatives;
} evidence_t;

static uint64_t h16(uint64_t h, int16_t v) {
    const uint16_t w = (uint16_t)v;
    h = (h ^ (uint8_t)(w & UINT16_C(255))) * FNV_PRIME;
    return (h ^ (uint8_t)(w >> 8u)) * FNV_PRIME;
}
static uint64_t hf32(uint64_t h, float v) {
    uint32_t word;
    uint32_t k;
    memcpy(&word, &v, sizeof(word));
    for (k = 0u; k < 4u; ++k)
        h = (h ^ (uint8_t)(word >> (8u * k))) * FNV_PRIME;
    return h;
}
static int16_t signal_for(uint32_t physical, uint32_t sample, uint32_t frame) {
    uint32_t value = (frame * 337u + sample * 73u + physical * 1931u) % 65536u;
    return (int16_t)((int32_t)value - 32768);
}
static int16_t ref_for(uint32_t sample, uint32_t frame) {
    uint32_t value = (frame * 233u + sample * 229u) % 65536u;
    return (int16_t)((int32_t)value - 32768);
}

static fe_b1b1_config make_cfg(const scene_t *sc, uint32_t rate) {
    fe_b1b1_config c;
    uint32_t i;
    static const double square[4][2] = {
        {0.03, 0.00}, {0.00, 0.03}, {-0.03, 0.00}, {0.00, -0.03}
    };
    memset(&c, 0, sizeof(c));
    c.ingress.struct_size = (uint32_t)sizeof(c.ingress);
    c.ingress.api_version = FE_B1B0_VERSION;
    c.ingress.capture_and_render_rate_hz = rate;
    c.ingress.frame_ms = 10u;
    c.ingress.physical_mics = sc->n;
    c.ingress.render_channels = sc->render;
    c.ingress.active_mic_mask = (1u << sc->n) - 1u;
    c.array.sample_rate_hz = 16000u;
    c.array.mic_count = sc->n;
    c.array.reference_mic = 0u;
    c.array.active_mask = c.ingress.active_mic_mask;
    c.array.interpolation = FE_ARRAY_FIR33_HANN;
    c.array.direction[0] = 1.0;
    for (i = 0u; i < sc->n; ++i) {
        c.ingress.physical_to_capture_slot[i] = sc->slots[i];
        c.array.microphones[i].input_channel = i;
        c.array.microphones[i].gain = 1.0;
        if (sc->circle) {
            c.array.microphones[i].position_m[0] = square[i][0];
            c.array.microphones[i].position_m[1] = square[i][1];
        } else {
            c.array.microphones[i].position_m[0] = 0.035 * (double)i;
        }
    }
    return c;
}

/* Each invalid init must leave target memory byte-for-byte unchanged. */
static int init_bad(const fe_b1b1_config *cfg, size_t length,
                    size_t shift, fe_b1b1_status wanted) {
    _Alignas(16) unsigned char storage[STATE_CAP + 16u];
    unsigned char before[STATE_CAP + 16u];
    fe_b1b1 *out = (fe_b1b1 *)(uintptr_t)1u;
    fe_b1b1_status got;
    memset(storage, 0xA9, sizeof(storage));
    memcpy(before, storage, sizeof(storage));
    got = fe_b1b1_init(storage + shift, length, cfg, &out);
    return got == wanted && out == NULL &&
           memcmp(before, storage, sizeof(storage)) == 0;
}
static uint32_t init_negatives(const fe_b1b1_config *good) {
    fe_b1b1_config c;
    uint32_t i, passed = 0u;
    const size_t need = fe_b1b1_state_bytes(good);
    for (i = 0u; i < 25u; ++i) {
        c = *good;
        switch (i) {
        case 0u: c.ingress.capture_and_render_rate_hz = 8000u; break;
        case 1u: c.ingress.capture_and_render_rate_hz = 24000u; break;
        case 2u: c.ingress.capture_and_render_rate_hz = 12345u; break;
        case 3u: c.ingress.frame_ms = 20u; break;
        case 4u: c.ingress.struct_size = 0u; break;
        case 5u: c.ingress.api_version = 0u; break;
        case 6u: c.ingress.physical_mics = 3u; break;
        case 7u: c.ingress.render_channels = 2u; break;
        case 8u: c.ingress.active_mic_mask = 0u; break;
        case 9u: c.ingress.active_mic_mask = 16u; break;
        case 10u: c.ingress.physical_to_capture_slot[0] = 4u; break;
        case 11u: c.ingress.physical_to_capture_slot[0] = c.ingress.physical_mics; break;
        case 12u: c.ingress.reserved[0] = 1u; break;
        case 13u: c.ingress.capture_clock_authority = 1u; break;
        case 14u: c.array.sample_rate_hz = 32000u; break;
        case 15u: c.array.mic_count = 3u; break;
        case 16u: c.array.active_mask = 0u; break;
        case 17u: c.array.interpolation = FE_ARRAY_LINEAR; break;
        case 18u: c.array.microphones[0].input_channel = 2u; break;
        case 19u: c.array.microphones[0].gain = 0.0; break;
        case 20u: c.array.microphones[0].latency_samples = 1.0; break;
        case 21u: c.array.direction[0] = 0.0; break;
        case 22u: c.array.microphones[0].position_m[0] = 2.0; break;
        case 23u: c.array.reference_mic = c.array.mic_count; break;
        default: c.array.direction[1] = NAN; break;
        }
        if (!init_bad(&c, need, 0u, FE_B1B1_EINVAL)) return 0u;
        ++passed;
    }
    if (need == 0u || need > STATE_CAP ||
        !init_bad(good, need - 1u, 0u, FE_B1B1_ENOMEM) ||
        !init_bad(good, need, 1u, FE_B1B1_EINVAL))
        return 0u;
    passed += 2u;
    return passed;
}

static int rejected_frame(fe_b1b1 *s, uint32_t rate, const scene_t *sc,
                          int16_t *input, int16_t *render,
                          float *bf, float *ref, void *work, size_t work_bytes,
                          unsigned char *arena, size_t state_bytes,
                          uint32_t which) {
    unsigned char snapshot[STATE_CAP];
    float beam_before[160], ref_before[160];
    fe_b1b1_status status;
    const size_t cap = (size_t)(rate / 100u) * sc->n;
    const size_t rc = (size_t)(rate / 100u) * sc->render;
    const int16_t *c = input;
    const int16_t *r = sc->render ? render : NULL;
    float *b = bf, *o = sc->render ? ref : NULL;
    size_t cc = cap, rr = rc, bc = 160u, oc = 160u * sc->render;
    void *w = work;
    size_t wc = work_bytes;
    if (state_bytes > STATE_CAP) return 0;
    memcpy(snapshot, arena, state_bytes);
    memcpy(beam_before, bf, sizeof(beam_before));
    memcpy(ref_before, ref, sizeof(ref_before));
    switch (which) {
    case 0u: cc = cap - 1u; break;
    case 1u: cc = cap + 1u; break;
    case 2u: rr = rc + 1u; break;
    case 3u: rr = rc ? rc - 1u : 1u; break;
    case 4u: bc = 159u; break;
    case 5u: bc = 161u; break;
    case 6u: oc = 159u; break;
    case 7u: oc = 161u; break;
    case 8u: c = NULL; break;
    case 9u: b = NULL; break;
    case 10u: w = NULL; break;
    case 11u: wc = 0u; break;
    case 12u: wc = work_bytes - 16u; break;
    case 13u: w = (unsigned char *)work + 1u; break;
    case 14u: w = bf; break;
    case 15u: w = (void *)input; break;
    case 16u: b = (float *)(void *)arena; break;
    case 17u: b = (float *)(void *)work; break;
    case 18u: c = (const int16_t *)(const void *)bf; break;
    case 19u: c = (const int16_t *)(const void *)arena; break;
    case 20u: o = bf; break;
    case 21u: r = (const int16_t *)(const void *)bf; break;
    case 22u: o = (float *)(void *)work; break;
    case 23u: o = (float *)(void *)arena; break;
    case 24u: r = (const int16_t *)(const void *)arena; break;
    case 25u: r = (const int16_t *)(const void *)input; break;
    default: return 0;
    }
    /* For no render, intentionally supplied unexpected pointers must reject. */
    status = fe_b1b1_process(s, c, cc, r, rr, b, bc, o, oc, w, wc);
    return status != FE_B1B1_OK &&
           memcmp(snapshot, arena, state_bytes) == 0 &&
           memcmp(beam_before, bf, sizeof(beam_before)) == 0 &&
           memcmp(ref_before, ref, sizeof(ref_before)) == 0;
}

static int pure_transfer_negatives(void) {
    float src[640], out[640], before[640];
    uint64_t count = UINT64_C(112233);
    uint32_t k, cases = 0u;
    for (k = 0u; k < 640u; ++k) { src[k] = 0.4f; out[k] = -91.0f; }
    memcpy(before, out, sizeof(out));
    src[10] = NAN;
    if (fe_b1b1_transpose_clamp(src, 640u, 4u, out, 640u, &count) != FE_B1B1_EINVAL ||
        memcmp(before, out, sizeof(out)) || count != UINT64_C(112233)) return 0;
    ++cases;
    src[10] = INFINITY;
    if (fe_b1b1_transpose_clamp(src, 640u, 4u, out, 640u, &count) != FE_B1B1_EINVAL ||
        memcmp(before, out, sizeof(out))) return 0;
    ++cases;
    src[10] = -INFINITY;
    if (fe_b1b1_transpose_clamp(src, 640u, 4u, out, 640u, &count) != FE_B1B1_EINVAL ||
        memcmp(before, out, sizeof(out))) return 0;
    ++cases;
    src[10] = 0.4f;
    if (fe_b1b1_transpose_clamp(src, 640u, 3u, out, 640u, &count) != FE_B1B1_EINVAL ||
        fe_b1b1_transpose_clamp(src, 639u, 4u, out, 640u, &count) != FE_B1B1_EINVAL ||
        fe_b1b1_transpose_clamp(src, 640u, 4u, out, 639u, &count) != FE_B1B1_EINVAL ||
        fe_b1b1_transpose_clamp(src, 640u, 4u, src, 640u, &count) != FE_B1B1_EINVAL ||
        fe_b1b1_transpose_clamp(src, 640u, 4u, out, 640u, NULL) != FE_B1B1_EINVAL ||
        fe_b1b1_transpose_clamp(NULL, 640u, 4u, out, 640u, &count) != FE_B1B1_EINVAL ||
        fe_b1b1_transpose_clamp(src, 640u, 4u, NULL, 640u, &count) != FE_B1B1_EINVAL ||
        memcmp(before, out, sizeof(out)) || count != UINT64_C(112233))
        return 0;
    cases += 7u;
    return (int)cases;
}

static int run_one(const scene_t *sc, uint32_t rate, evidence_t *proof) {
    _Alignas(16) unsigned char state[STATE_CAP], work[WORK_CAP];
    _Alignas(16) unsigned char src_state[STATE_CAP], bf_state[STATE_CAP];
    int16_t input[4u * 480u] = {0}, render[480u] = {0};
    float bf[160], ref[160], oracle_bf[160], oracle_ref[160];
    float physical[4u * 160u], interleaved[4u * 160u];
    fe_b1b1_config cfg = make_cfg(sc, rate);
    fe_b1b1 *s = NULL;
    fe_b1b0_src *src = NULL;
    fe_array *array = NULL;
    fe_b1b1_info info;
    uint64_t source_hash = FNV_OFFSET, beam_hash = FNV_OFFSET;
    uint64_t ref_hash = FNV_OFFSET, clipped_total = 0u, clipped;
    uint32_t frame, mic, k, checked = 0u, active = cfg.array.active_mask;
    const size_t state_bytes = fe_b1b1_state_bytes(&cfg);
    const size_t work_bytes = fe_b1b1_work_bytes(&cfg);
    const size_t input_count = (size_t)(rate / 100u) * sc->n;
    const size_t render_count = (size_t)(rate / 100u) * sc->render;
    const size_t major_count = (size_t)sc->n * 160u;
    if (!state_bytes || state_bytes > STATE_CAP || work_bytes > WORK_CAP ||
        !fe_b1b0_state_bytes(&cfg.ingress) ||
        fe_array_state_bytes_for_mode(sc->n, FE_ARRAY_FIR33_HANN) > STATE_CAP)
        return 0;
    memset(proof, 0, sizeof(*proof));
    checked = init_negatives(&cfg);
    if (checked < 27u) return 0;
    memset(state, 0x17, sizeof(state));
    memset(work, 0xA2, sizeof(work));
    if (fe_b1b1_init(state, state_bytes, &cfg, &s) != FE_B1B1_OK ||
        fe_b1b0_init(src_state, sizeof(src_state), &cfg.ingress, &src) != FE_B1B0_OK ||
        fe_array_init(bf_state, sizeof(bf_state), &cfg.array, &array) != FE_ARRAY_OK ||
        !s || !src || !array)
        return 0;
    if (pure_transfer_negatives() != 10) return 0;
    checked += 10u;
    for (k = 0u; k < 160u; ++k) { bf[k] = -7.0f; ref[k] = -13.0f; }
    for (k = 0u; k < 26u; ++k) {
        if (!rejected_frame(s, rate, sc, input, render, bf, ref,
                            work, work_bytes, state, state_bytes, k))
            return 0;
        ++checked;
    }
    {
        unsigned char before[STATE_CAP];
        const double wrong[3] = {NAN, 0.0, 0.0};
        memcpy(before, state, state_bytes);
        if (fe_b1b1_set_active_mask(s, 0u) == FE_B1B1_OK ||
            fe_b1b1_set_active_mask(s, 16u) == FE_B1B1_OK ||
            fe_b1b1_notify_gap(s, 0u) == FE_B1B1_OK ||
            fe_b1b1_notify_gap(s, 8u) == FE_B1B1_OK ||
            (!sc->render && fe_b1b1_notify_gap(s, FE_B1B0_RENDER_GAP) == FE_B1B1_OK) ||
            fe_b1b1_request_steer(s, wrong, 16u) == FE_B1B1_OK ||
            fe_b1b1_request_steer(s, cfg.array.direction, 0u) == FE_B1B1_OK ||
            fe_b1b1_request_steer(s, cfg.array.direction, 2000u) == FE_B1B1_OK ||
            memcmp(before, state, state_bytes) != 0)
            return 0;
        checked += sc->render ? 7u : 8u;
    }

    for (frame = 0u; frame <= FRAMES; ++frame) {
        if (frame == 50u) {
            if (fe_b1b1_notify_gap(s, FE_B1B0_CAPTURE_GAP) != FE_B1B1_OK ||
                fe_b1b0_notify_gap(src, FE_B1B0_CAPTURE_GAP) != FE_B1B0_OK ||
                fe_array_reset(array) != FE_ARRAY_OK)
                return 0;
            continue; /* A real absent capture, not synthesized silence. */
        }
        if (frame == 70u) {
            active = sc->n == 4u ? 13u : 1u;
            if (fe_b1b1_set_active_mask(s, active) != FE_B1B1_OK ||
                fe_b1b0_set_active_mask(src, active) != FE_B1B0_OK ||
                fe_array_set_active_mask(array, active) != FE_ARRAY_OK)
                return 0;
        }
        if (frame == 75u) {
            const double dir[3] = {0.0, 1.0, 0.0};
            if (fe_b1b1_request_steer(s, dir, 80u) != FE_B1B1_OK ||
                fe_array_request_steer(array, dir, 80u) != FE_ARRAY_OK)
                return 0;
        }
        if (frame == 80u && sc->render) {
            fe_b1b1_info before;
            if (fe_b1b1_get_info(s, &before) != FE_B1B1_OK ||
                fe_b1b1_notify_gap(s, FE_B1B0_RENDER_GAP) != FE_B1B1_OK ||
                fe_b1b0_notify_gap(src, FE_B1B0_RENDER_GAP) != FE_B1B0_OK ||
                fe_b1b1_get_info(s, &info) != FE_B1B1_OK ||
                info.array.samples_processed != before.array.samples_processed)
                return 0;
        }
        if (frame == 90u) {
            if (fe_b1b1_notify_gap(s, FE_B1B0_CLOCK_RESET) != FE_B1B1_OK ||
                fe_b1b0_notify_gap(src, FE_B1B0_CLOCK_RESET) != FE_B1B0_OK ||
                fe_array_reset(array) != FE_ARRAY_OK)
                return 0;
        }
        for (k = 0u; k < rate / 100u; ++k) {
            uint32_t p;
            for (p = 0u; p < sc->n; ++p) {
                const int16_t value = signal_for(p, k, frame);
                input[(size_t)k * sc->n + sc->slots[p]] = value;
            }
            if (sc->render) render[k] = ref_for(k, frame);
        }
        for (k = 0u; k < input_count; ++k)
            source_hash = h16(source_hash, input[k]);
        for (k = 0u; k < render_count; ++k)
            source_hash = h16(source_hash, render[k]);
        if (fe_b1b1_process(s, input, input_count, sc->render ? render : NULL,
                            render_count, bf, 160u, sc->render ? ref : NULL,
                            160u * sc->render, work, work_bytes) != FE_B1B1_OK ||
            fe_b1b0_process(src, input, input_count, sc->render ? render : NULL,
                            render_count, physical, major_count,
                            sc->render ? oracle_ref : NULL,
                            160u * sc->render) != FE_B1B0_OK ||
            fe_b1b1_transpose_clamp(physical, major_count, sc->n,
                                    interleaved, major_count, &clipped) != FE_B1B1_OK ||
            fe_array_process(array, interleaved, major_count,
                             oracle_bf, 160u) != FE_ARRAY_OK)
            return 0;
        clipped_total += clipped;
        for (k = 0u; k < 160u; ++k) {
            if (!isfinite(bf[k]) || memcmp(&bf[k], &oracle_bf[k], sizeof(float)))
                return 0;
            beam_hash = hf32(beam_hash, bf[k]);
            if (sc->render) {
                if (!isfinite(ref[k]) ||
                    memcmp(&ref[k], &oracle_ref[k], sizeof(float))) return 0;
                ref_hash = hf32(ref_hash, ref[k]);
            }
        }
        for (k = 0u; k < 160u; ++k)
            for (mic = 0u; mic < sc->n; ++mic) {
                const float value = physical[(size_t)mic * 160u + k];
                const float normalized = value < -1.0f ? -1.0f :
                                         value > 1.0f ? 1.0f : value;
                if (!isfinite(value) ||
                    memcmp(&interleaved[(size_t)k * sc->n + mic],
                           &normalized, sizeof(float)) != 0)
                    return 0;
            }
    }
    if (fe_b1b1_get_info(s, &info) != FE_B1B1_OK ||
        info.accepted_frames != FRAMES ||
        info.source.accepted_frames != FRAMES ||
        info.clipped_samples != clipped_total ||
        info.source.capture_epoch != 2u ||
        info.source.render_epoch != (sc->render ? 2u : 0u) ||
        info.source.clock_epoch != 1u ||
        info.source.capture_frames_in_epoch != 11u ||
        info.source.render_frames_in_epoch != (sc->render ? 11u : 0u) ||
        info.physical_mics != sc->n || info.render_channels != sc->render ||
        info.array.active_mask != active ||
        info.source.active_mic_mask != active ||
        info.state_bytes != state_bytes ||
        info.work_bytes > work_bytes ||
        info.source_state_bytes != fe_b1b0_state_bytes(&cfg.ingress) ||
        info.array_state_bytes !=
            fe_array_state_bytes_for_mode(sc->n, FE_ARRAY_FIR33_HANN))
        return 0;
    proof->info = info;
    proof->source_hash = source_hash;
    proof->beam_hash = beam_hash;
    proof->render_hash = ref_hash;
    proof->negatives = checked;
    if (fe_b1b1_reset(s) != FE_B1B1_OK ||
        fe_b1b1_get_info(s, &info) != FE_B1B1_OK ||
        info.accepted_frames != 0u || info.clipped_samples != 0u)
        return 0;
    return 1;
}

int main(void) {
    uint32_t rate, scene;
    int first = 1;
    evidence_t a, b;
    printf("{\"schema_version\":1,\"decision\":\"FE09_R2B1B_S1_SINGLE_ARRAY_BF_RESEARCH_ONLY_NO_RELEASE\",");
    printf("\"source_role\":\"first-party-synthetic\",\"public_sdk_installed\":false,");
    printf("\"aec_qualified\":false,\"real_adc_clock_qualified\":false,");
    printf("\"ssc305_dut_qualified\":false,\"full_c4_budget_qualified\":false,");
    printf("\"render_to_bf_forbidden\":true,\"repeats\":2,\"profile_count\":12,\"profiles\":[");
    for (rate = 0u; rate < 3u; ++rate)
        for (scene = 0u; scene < 4u; ++scene) {
            if (!run_one(&SCENES[scene], RATES[rate], &a) ||
                !run_one(&SCENES[scene], RATES[rate], &b) ||
                memcmp(&a, &b, sizeof(a)) != 0) {
                fprintf(stderr, "FE09_B1B1_S1_PROFILE_FAILED rate=%u scene=%u\n",
                        RATES[rate], scene);
                return 1;
            }
            if (!first) printf(",");
            first = 0;
            printf("{\"name\":\"%s\",\"rate\":%u,\"mics\":%u,\"render\":%u,",
                   SCENES[scene].name, RATES[rate], SCENES[scene].n,
                   SCENES[scene].render);
            printf("\"frames\":%" PRIu64 ",\"negatives\":%u,\"clips\":%" PRIu64 ",",
                   a.info.accepted_frames, a.negatives,
                   a.info.clipped_samples);
            printf("\"state_bytes\":%zu,\"work_bytes\":%zu,",
                   a.info.state_bytes, a.info.work_bytes);
            printf("\"src_bytes\":%zu,\"bf_bytes\":%zu,",
                   a.info.source_state_bytes, a.info.array_state_bytes);
            printf("\"capture_epoch\":%" PRIu64 ",\"render_epoch\":%" PRIu64 ",",
                   a.info.source.capture_epoch, a.info.source.render_epoch);
            printf("\"clock_epoch\":%" PRIu64 ",\"array_samples\":%" PRIu64 ",",
                   a.info.source.clock_epoch, a.info.array.samples_processed);
            printf("\"source_hash\":\"%016" PRIx64 "\",", a.source_hash);
            printf("\"beam_hash\":\"%016" PRIx64 "\",", a.beam_hash);
            printf("\"render_hash\":\"%016" PRIx64 "\"}", a.render_hash);
        }
    puts("]}");
    return 0;
}
