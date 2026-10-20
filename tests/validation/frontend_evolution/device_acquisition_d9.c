/* Disclosed synthetic engineering input; not acoustic or DUT qualification. */
#include "audio_pipeline/audio_pipeline.h"
#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static _Alignas(16) unsigned char storage[AP_PIPELINE_STATE_MAX_BYTES];
static const char *signals[4] = {"broad", "periodic", "lowref", "doubletalk"};
static float white(uint32_t n, uint32_t seed) {
    uint32_t x = n + seed * 0x9e3779b9u;
    x ^= x >> 16u; x *= 0x7feb352du; x ^= x >> 15u; x *= 0x846ca68bu; x ^= x >> 16u;
    return (float)(x >> 8u) / 16777216.0f - 0.5f;
}
static float broad(uint32_t n, uint32_t rate, uint32_t seed) {
    const uint32_t width = rate / 500u;
    float v = 0.0f;
    uint32_t i;
    for (i = 0u; i < width; ++i) if (n >= i) v += white(n - i, seed);
    return v / (float)width;
}
static int16_t render_value(uint32_t n, uint32_t rate, uint32_t seed, uint32_t signal) {
    float v;
    if (signal == 1u) {
        const float t = (float)n / (float)rate;
        v = 0.18f * sinf(6.28318530718f * 733.0f * t + (float)seed * 0.173f) +
            0.08f * sinf(6.28318530718f * 1187.0f * t + (float)seed * 0.311f);
    } else v = (signal == 2u ? 0.03f : 0.30f) * broad(n, rate, seed);
    assert(isfinite(v) && fabsf(v) < 1.0f);
    return (int16_t)(v * 32767.0f);
}
static void s16(FILE *f, int16_t value) {
    const uint16_t v = (uint16_t)value;
    const unsigned char bytes[2] = {(unsigned char)(v & 255u), (unsigned char)(v >> 8u)};
    assert(fwrite(bytes, 1u, 2u, f) == 2u);
}
static FILE *opened(const char *directory, const char *id, const char *suffix) {
    char path[1024];
    const int length = snprintf(path, sizeof(path), "%s/%s%s", directory, id, suffix);
    FILE *f;
    assert(length > 0 && (size_t)length < sizeof(path));
    f = fopen(path, "wb"); assert(f != NULL); return f;
}
static void run_case(const char *directory, uint32_t rate, uint32_t seed,
                     uint32_t signal, uint32_t target_ms, uint32_t regime, uint32_t gap) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    ap_metrics_t m;
    int16_t render[160], mic[160], output[160];
    uint32_t frame, i, n = 0u, last20 = 0u, capture_count = 0u;
    int first = -1;
    char id[160];
    FILE *input, *metrics, *pcm;
    const uint32_t hop = rate / 100u;
    const uint32_t phase = regime ? 120u : 0u;
    const int length = snprintf(id, sizeof(id), "r%u-s%u-%s-%s-d%u-g%u", rate, seed, signals[signal], regime ? "switch" : "acquire", target_ms, gap);
    assert(length > 0 && (size_t)length < sizeof(id));
    c.io_sample_rate_hz = rate; c.internal_sample_rate_hz = rate; c.mic_channels = 1u;
    c.stages = AP_STAGE_SYNC; c.initial_delay_ms = 40u; c.max_delay_ms = 100u;
    c.enable_delay_tracking = 1u; c.enable_clock_drift_compensation = 1u;
    assert(ap_pipeline_init(storage, sizeof(storage), &c, &p) == AP_OK);
    input = opened(directory, id, ".input.s16le"); metrics = opened(directory, id, ".metrics.csv");
    pcm = opened(directory, id, ".output.s16le");
    assert(fprintf(metrics, "frame,delay_ms,jumps,resets,slips\n") > 0);
    memset(&m, 0, sizeof(m));
    for (frame = 0u; frame < 300u; ++frame) {
        const uint32_t delay_ms = frame < phase ? 40u : target_ms;
        const uint32_t delay = delay_ms * rate / 1000u;
        for (i = 0u; i < hop; ++i, ++n) {
            float v;
            render[i] = render_value(n, rate, seed, signal);
            v = n >= delay ? 0.4f * (float)render_value(n - delay, rate, seed, signal) : 0.0f;
            if (signal == 3u) v += 0.42f * 32767.0f * broad(n, rate, seed + 100u);
            assert(isfinite(v) && fabsf(v) < 32767.0f); mic[i] = (int16_t)v;
            s16(input, render[i]); s16(input, mic[i]);
        }
        assert(ap_pipeline_push_render(p, render, hop) == AP_OK);
        if (gap && frame == 120u) {
            if (gap == 2u) assert(ap_pipeline_notify_stream_discontinuity(p, AP_DISCONTINUITY_CAPTURE_GAP, 1u) == AP_OK);
            continue;
        }
        assert(ap_pipeline_process_capture(p, mic, hop, output) == AP_OK);
        ap_pipeline_get_metrics(p, &m); capture_count++;
        assert(isfinite(m.estimated_drift_ppm));
        assert(fprintf(metrics, "%u,%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n", frame, m.estimated_delay_ms, m.delay_jumps, m.aec_resets, m.reference_sample_slips) > 0);
        for (i = 0u; i < hop; ++i) s16(pcm, output[i]);
        if (frame >= phase && abs((int)m.estimated_delay_ms - (int)target_ms) <= 3) {
            if (first < 0) first = (int)frame;
            if (frame >= 280u) last20++;
        }
    }
    assert(fclose(input) == 0 && fclose(metrics) == 0 && fclose(pcm) == 0);
    printf("{\"case_id\":\"%s\",\"rate\":%u,\"seed\":%u,\"signal\":\"%s\",\"target_ms\":%u,\"phase_frame\":%u,\"gap\":%u,\"capture_frames\":%u,\"first_in_band_frame\":%d,\"last20_in_band\":%u,\"final_delay_ms\":%u,\"jumps\":%" PRIu64 ",\"resets\":%" PRIu64 ",\"slips\":%" PRIu64 "}\n", id, rate, seed, signals[signal], target_ms, phase, gap, capture_count, first, last20, m.estimated_delay_ms, m.delay_jumps, m.aec_resets, m.reference_sample_slips);
}
int main(int argc, char **argv) {
    const uint32_t rates[2] = {8000u, 16000u};
    const uint32_t delays[3] = {1u, 7u, 80u};
    uint32_t r, s, k, d, mode;
    if (argc != 2 && argc != 3) return 2;
    if (argc == 3) {
        if (strcmp(argv[2], "repeat") != 0) return 2;
        run_case(argv[1], 16000u, 1u, 0u, 7u, 0u, 0u); return 0;
    }
    for (r = 0u; r < 2u; ++r) {
        for (s = 1u; s <= 2u; ++s) for (k = 0u; k < 4u; ++k)
            for (d = 0u; d < 3u; ++d) for (mode = 0u; mode < 2u; ++mode)
                run_case(argv[1], rates[r], s, k, delays[d], mode, 0u);
        for (mode = 1u; mode <= 2u; ++mode) run_case(argv[1], rates[r], 1u, 0u, 80u, 1u, mode);
    }
    return 0;
}
