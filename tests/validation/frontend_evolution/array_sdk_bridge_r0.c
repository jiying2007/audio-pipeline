/*
 * FE09-R0: non-shipping C2/C4 array-to-existing-2.x mono SDK handoff.
 * Preregistered #726. First-party synthetic 16 kHz / 10 ms only.
 * No public API change, original-audio source, DOA accuracy or DUT timing.
 */
#define _POSIX_C_SOURCE 200809L
#include "array_native.h"
#include "audio_pipeline/audio_pipeline.h"
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { R0_FRAME = 160, R0_FRAMES = 100, R0_SCENES = 3, R0_ARENA = 4096 };
#define R0_FNV_OFFSET UINT64_C(14695981039346656037)
#define R0_FNV_PRIME UINT64_C(1099511628211)

typedef struct {
    const char *name;
    unsigned channels;
    unsigned circular;
    unsigned expected_delay;
} r0_case;
static const r0_case R0_CASES[R0_SCENES] = {
    {"C2_ULA_35MM", 2u, 0u, 19u},
    {"C4_ULA_105MM", 4u, 0u, 22u},
    {"C4_UCA_RADIUS35MM", 4u, 1u, 21u}
};
typedef struct {
    uint64_t source_hash, bridge_hash, sdk_hash, cpu_ns;
    size_t array_bytes, sdk_bytes;
    unsigned delay, clipped, synthetic_frames, reset_at_50, negative_count;
} r0_result;

static void hash_byte(uint64_t *state, unsigned value) {
    *state ^= (uint8_t)value;
    *state *= R0_FNV_PRIME;
}
static void hash_s16(uint64_t *state, int16_t value) {
    const uint16_t v = (uint16_t)value;
    hash_byte(state, v & 255u);
    hash_byte(state, (v >> 8u) & 255u);
}
static int64_t cpu_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts) != 0) return -1;
    return (int64_t)ts.tv_sec * INT64_C(1000000000) + (int64_t)ts.tv_nsec;
}
static int16_t mono_s16(float x, unsigned *clipped) {
    long v;
    if (x >= 1.0f) { ++*clipped; return INT16_MAX; }
    if (x <= -1.0f) { if (x < -1.0f) ++*clipped; return INT16_MIN; }
    v = lrintf(x * 32768.0f);
    if (v > INT16_MAX) { ++*clipped; return INT16_MAX; }
    if (v < INT16_MIN) { ++*clipped; return INT16_MIN; }
    return (int16_t)v;
}
static fe_array_config array_config(const r0_case *selected) {
    fe_array_config c;
    unsigned i;
    memset(&c, 0, sizeof(c));
    c.sample_rate_hz = 16000u;
    c.mic_count = selected->channels;
    c.active_mask = (1u << selected->channels) - 1u;
    c.reference_mic = 0u;
    c.interpolation = FE_ARRAY_FIR33_HANN;
    c.direction[1] = 1.0;
    for (i = 0u; i < c.mic_count; ++i) {
        c.microphones[i].input_channel = i;
        c.microphones[i].gain = 1.0;
        if (!selected->circular) {
            c.microphones[i].position_m[0] = 0.035 * (double)i;
        } else {
            /* Frozen clockwise cardinal coordinate order, reference is +X. */
            static const double xy[4][2] = {
                {0.035, 0.0}, {0.0, 0.035},
                {-0.035, 0.0}, {0.0, -0.035}
            };
            c.microphones[i].position_m[0] = xy[i][0];
            c.microphones[i].position_m[1] = xy[i][1];
        }
    }
    return c;
}
static ap_config_t mono_config(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    c.io_sample_rate_hz = 16000u;
    c.internal_sample_rate_hz = 16000u;
    c.mic_channels = 1u;
    c.stages &= ~(ap_stage_mask_t)AP_STAGE_BF;
    return c;
}
static int check_negatives(const fe_array_config *input, ap_config_t mono,
                           fe_array *state, size_t state_bytes,
                           unsigned *count) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char canary[R0_ARENA];
    fe_array *out = state;
    fe_array_config malformed = *input;
    float samples[R0_FRAME * FE_ARRAY_MAX_MICS + FE_ARRAY_MAX_MICS] = {0.0f};
    float output[R0_FRAME] = {0.0f};
    fe_array_info before, after;
    uint8_t before_memory[R0_ARENA];
    int16_t pcm[R0_FRAME] = {0};
    int16_t processed[R0_FRAME] = {0};
    ap_status_t ps;
    unsigned i;
    if (state_bytes > sizeof(canary) ||
        fe_array_get_info(state, &before) != FE_ARRAY_OK ||
        before.samples_processed != 0u) return 0;
    if (ap_pipeline_validate_config(&mono) != AP_OK) return 0;
    mono.mic_channels = 4u;
    ps = ap_pipeline_validate_config(&mono);
    if (ps != AP_EINVAL) return 0;
    ++*count;
    mono.mic_channels = 1u;
    mono.stages |= AP_STAGE_BF;
    if (ap_pipeline_validate_config(&mono) != AP_EINVAL) return 0;
    ++*count;
    malformed.mic_count = 3u;
    malformed.active_mask = 7u;
    memset(canary, 0xa5, sizeof(canary));
    memcpy(before_memory, canary, sizeof(canary));
    if (fe_array_init(canary, sizeof(canary), &malformed, &out) != FE_ARRAY_EINVAL ||
        out != NULL || memcmp(canary, before_memory, sizeof(canary)) != 0) return 0;
    ++*count;
    malformed = *input;
    malformed.microphones[1].input_channel = 0u;
    out = state;
    if (fe_array_init(canary, sizeof(canary), &malformed, &out) != FE_ARRAY_EINVAL ||
        out != NULL || memcmp(canary, before_memory, sizeof(canary)) != 0) return 0;
    ++*count;
    /* An out-of-range physical-to-input slot is distinct from a duplicate. */
    malformed = *input;
    malformed.microphones[1].input_channel = input->mic_count;
    out = state;
    if (fe_array_init(canary, sizeof(canary), &malformed, &out) != FE_ARRAY_EINVAL ||
        out != NULL || memcmp(canary, before_memory, sizeof(canary)) != 0) return 0;
    ++*count;
    out = state;
    if (fe_array_init(canary, state_bytes - 1u, input, &out) != FE_ARRAY_ENOMEM ||
        out != NULL || memcmp(canary, before_memory, sizeof(canary)) != 0) return 0;
    ++*count;
    if (fe_array_process(state, samples, R0_FRAME*input->mic_count - 1u,
                         output, R0_FRAME) != FE_ARRAY_EINVAL) return 0;
    ++*count;
    if (fe_array_process(state, samples, (R0_FRAME+1u)*input->mic_count,
                         output, R0_FRAME+1u) != FE_ARRAY_EINVAL) return 0;
    ++*count;
    samples[0] = NAN;
    if (fe_array_process(state, samples, R0_FRAME*input->mic_count,
                         output, R0_FRAME) != FE_ARRAY_EINVAL) return 0;
    ++*count;
    samples[0] = 1.01f;
    if (fe_array_process(state, samples, R0_FRAME*input->mic_count,
                         output, R0_FRAME) != FE_ARRAY_EINVAL) return 0;
    ++*count;
    samples[0] = 0.0f;
    if (fe_array_process(state, samples, R0_FRAME*input->mic_count,
                         samples, R0_FRAME) != FE_ARRAY_EINVAL) return 0;
    ++*count;
    if (fe_array_get_info(state, &after) != FE_ARRAY_OK ||
        after.samples_processed != before.samples_processed) return 0;
    for (i = 0u; i < R0_FRAME; ++i)
        if (output[i] != 0.0f || pcm[i] != 0 || processed[i] != 0) return 0;
    return 1;
}
static int run_case(const r0_case *selected, r0_result *result, int timed) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char array_memory[R0_ARENA];
    _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
        unsigned char pipeline_memory[AP_PIPELINE_STATE_MAX_BYTES];
    float input[R0_FRAME * FE_ARRAY_MAX_MICS], beam[R0_FRAME];
    int16_t capture[R0_FRAME], render[R0_FRAME], output[R0_FRAME];
    fe_array_config geometry = array_config(selected);
    fe_array *array = NULL;
    ap_pipeline_t *pipeline = NULL;
    ap_config_t config = mono_config();
    size_t need = fe_array_state_bytes_for_mode(selected->channels,
                                                FE_ARRAY_FIR33_HANN);
    unsigned pass, frame, sample, mic;
    uint64_t digest[2][3] = {{0u}}, cpu_total = 0u;
    unsigned clipped[2] = {0u, 0u};
    const ap_build_info_t *build = ap_build_info();
    fe_array_info info;
    ap_metrics_t metrics;
    if (!build || build->version_major != 2u || build->max_mic_channels != 2u ||
        build->fast_math || !build->has_pipeline || !build->config_digest ||
        need == 0u || need > sizeof(array_memory) ||
        ap_pipeline_state_size() > sizeof(pipeline_memory) ||
        ap_pipeline_validate_config(&config) != AP_OK ||
        ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory),
                         &config, &pipeline) != AP_OK ||
        fe_array_init(array_memory, need, &geometry, &array) != FE_ARRAY_OK ||
        !array || !pipeline) return 0;
    if (!check_negatives(&geometry, config, array, need,
                         &result->negative_count)) return 0;
    {
        /* Invalid discontinuity controls must leave every public pipeline
         * state byte untouched, not merely preserve the frame counter. */
        const size_t state_bytes = ap_pipeline_state_size();
        unsigned char snapshot[AP_PIPELINE_STATE_MAX_BYTES];
        memcpy(snapshot, pipeline_memory, state_bytes);
        if (ap_pipeline_notify_stream_discontinuity(pipeline, 0u, 1u) != AP_EINVAL ||
            memcmp(snapshot, pipeline_memory, state_bytes) != 0) return 0;
        ++result->negative_count;
    }
    if (ap_pipeline_process_capture(pipeline, capture, R0_FRAME-1u,
                                    output) != AP_EINVAL) return 0;
    ++result->negative_count;
    for (pass = 0u; pass < 2u; ++pass) {
        uint32_t rng = UINT32_C(0x13579bdf) ^ (selected->channels << 8u) ^
                       (selected->circular << 16u);
        if (fe_array_reset(array) != FE_ARRAY_OK) return 0;
        ap_pipeline_reset(pipeline);
        digest[pass][0] = digest[pass][1] = digest[pass][2] = R0_FNV_OFFSET;
        for (frame = 0u; frame < R0_FRAMES; ++frame) {
            int64_t begin = 0, end = 0;
            if (frame == 50u) {
                if (fe_array_reset(array) != FE_ARRAY_OK ||
                    ap_pipeline_notify_stream_discontinuity(
                        pipeline, AP_DISCONTINUITY_CAPTURE_GAP, 1u) != AP_OK)
                    return 0;
                /* Exactly one lost synthetic 10-ms capture block. Render
                 * continues independently; no fabricated shared epoch. */
                for (sample = 0u; sample < R0_FRAME; ++sample)
                    for (mic = 0u; mic < selected->channels; ++mic)
                        rng = 1664525u * rng + 1013904223u;
            }
            for (sample = 0u; sample < R0_FRAME; ++sample) {
                const int32_t t = (int32_t)(frame*R0_FRAME + sample);
                render[sample] = (int16_t)(((t*31 + 7) % 2048) - 1024);
                for (mic = 0u; mic < selected->channels; ++mic) {
                    int32_t v;
                    rng = 1664525u * rng + 1013904223u;
                    v = (int32_t)((rng >> 15u) & 8191u) - 4096 +
                        (int32_t)(mic * 37u);
                    input[sample*selected->channels + mic] = (float)v / 32768.0f;
                    hash_s16(&digest[pass][0], (int16_t)v);
                }
            }
            if (timed && (begin = cpu_ns()) < 0) return 0;
            if (fe_array_process(array, input,
                                 R0_FRAME*selected->channels, beam,
                                 R0_FRAME) != FE_ARRAY_OK) return 0;
            for (sample = 0u; sample < R0_FRAME; ++sample) {
                if (!isfinite(beam[sample])) return 0;
                capture[sample] = mono_s16(beam[sample], &clipped[pass]);
                hash_s16(&digest[pass][1], capture[sample]);
            }
            if (config.stages & AP_STAGE_SYNC)
                if (ap_pipeline_push_render(pipeline, render, R0_FRAME) != AP_OK)
                    return 0;
            if (ap_pipeline_process_capture(pipeline, capture, R0_FRAME,
                                            output) != AP_OK) return 0;
            for (sample = 0u; sample < R0_FRAME; ++sample)
                hash_s16(&digest[pass][2], output[sample]);
            if (timed) {
                end = cpu_ns();
                if (end < begin) return 0;
                cpu_total += (uint64_t)(end - begin);
            }
        }
        if (fe_array_get_info(array, &info) != FE_ARRAY_OK ||
            info.samples_processed != (R0_FRAMES-50u)*R0_FRAME ||
            info.common_delay_samples != selected->expected_delay) return 0;
        ap_pipeline_get_metrics(pipeline, &metrics);
        if (metrics.processed_frames != R0_FRAMES ||
            ap_pipeline_mic_channels(pipeline) != 1u) return 0;
    }
    if (memcmp(digest[0], digest[1], sizeof(digest[0])) != 0 ||
        clipped[0] != clipped[1]) return 0;
    result->source_hash = digest[0][0];
    result->bridge_hash = digest[0][1];
    result->sdk_hash = digest[0][2];
    result->clipped = clipped[0];
    result->array_bytes = need;
    result->sdk_bytes = ap_pipeline_state_size();
    result->delay = selected->expected_delay;
    result->synthetic_frames = R0_FRAMES;
    result->reset_at_50 = 1u;
    result->cpu_ns = cpu_total;
    return 1;
}
int main(int argc, char **argv) {
    r0_result results[R0_SCENES] = {{0}};
    const ap_build_info_t *info = ap_build_info();
    int timed = 0;
    unsigned i;
    if (argc == 2 && strcmp(argv[1], "--timing") == 0) timed = 1;
    else if (argc != 1) return 2;
    if (!info || !info->config_digest || !info->source_revision ||
        AP_MAX_MIC_CHANNELS != 2u || info->max_mic_channels != 2u)
        return 3;
    for (i = 0u; i < R0_SCENES; ++i)
        if (!run_case(&R0_CASES[i], &results[i], timed)) {
            fprintf(stderr, "FE09_R0_INTEGRATION_OR_ABI_GATE_FAILED case=%s\n",
                    R0_CASES[i].name);
            return 4;
        }
    printf("{\"schema_version\":1,"
           "\"decision\":\"FE09_R0_C2_C4_MONO_SDK_BRIDGE_RESEARCH_ONLY_NO_PROMOTION\","
           "\"source_role\":\"first-party-deterministic-synthetic\","
           "\"installed_public_c4_supported\":false,"
           "\"shipping_authority\":false,"
           "\"product_qualification\":false,"
           "\"geometry_count\":3,\"run_repeats\":2,"
           "\"sdk_build_info\":{\"major\":%u,\"max_mic_channels\":%u,"
           "\"config_digest\":\"%s\",\"source_revision\":\"%s\"},\"profiles\":[",
           info->version_major, info->max_mic_channels,
           info->config_digest, info->source_revision);
    for (i = 0u; i < R0_SCENES; ++i) {
        const r0_result *r = &results[i];
        printf("%s{\"name\":\"%s\",\"mic_count\":%u,"
               "\"fir33_common_delay_samples\":%u,"
               "\"array_state_bytes\":%zu,\"sdk_mono_state_bytes\":%zu,"
               "\"capture_frame_bytes\":%u,\"mono_frame_bytes\":320,"
               "\"frames_per_repeat\":%u,\"capture_gap_at_frame\":50,"
               "\"negative_checks\":%u,\"clipped_samples\":%u,"
               "\"input_fnv64\":\"%016" PRIx64 "\","
               "\"bridge_fnv64\":\"%016" PRIx64 "\","
               "\"sdk_fnv64\":\"%016" PRIx64 "\"",
               i ? "," : "", R0_CASES[i].name, R0_CASES[i].channels,
               r->delay, r->array_bytes, r->sdk_bytes,
               320u * R0_CASES[i].channels, r->synthetic_frames,
               r->negative_count, r->clipped, r->source_hash,
               r->bridge_hash, r->sdk_hash);
        if (timed) printf(",\"combined_host_thread_cpu_ns_two_repeats\":%" PRIu64,
                          r->cpu_ns);
        printf("}");
    }
    printf("]}\n");
    return 0;
}
