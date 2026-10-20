/* Offline first-party public-API diagnostic. Not installed in the SDK. */
#include "audio_pipeline/audio_pipeline.h"
#include <stdio.h>
#include <string.h>

#include "sync/ap_sync.h"
#include <assert.h>

#ifndef D18_OBSERVER
#define D18_OBSERVER 0
#endif

#if D18_OBSERVER
static FILE *g_reference_file;
static uint64_t g_reference_calls;
static uint32_t g_expected_delay;
static int g_reference_error;
int ap_sync_get_reference_d18_real(ap_sync_state_t *, uint32_t, float *);
int ap_sync_get_reference(ap_sync_state_t *state, uint32_t samples, float *out) {
    const int result = ap_sync_get_reference_d18_real(state, samples, out);
    ++g_reference_calls;
    if (samples != 160u || state->delay_samples != g_expected_delay || state->drift_credit != 0.0f)
        g_reference_error = 1;
    if (g_reference_file && fwrite(out, sizeof(float), samples, g_reference_file) != samples)
        g_reference_error = 1;
    return result;
}
#endif


#include "aec/ap_aec.h"
#include "enhance/ap_enhance.h"
#include <math.h>

static FILE *g_stage_files[5], *g_control_file;
static uint64_t g_aec_calls, g_ns_calls, g_agc_calls, g_res_calls;
static int g_stage_error, g_far, g_double, g_frequency, g_frequency_active;
static float g_ns_gain;
static float g_aec_residual[160], g_echo[160], g_ns_output[160];

static void stage_write(uint32_t which, const float *samples, uint32_t count) {
    uint32_t i;
    if (count != 160u) { g_stage_error = 1; return; }
    for (i = 0u; i < count; ++i) if (!isfinite(samples[i])) g_stage_error = 1;
    if (g_stage_files[which] && fwrite(samples, sizeof(float), count, g_stage_files[which]) != count)
        g_stage_error = 1;
}

void ap_aec_backend_process_d19_real(ap_aec_state_t *, int, float, uint32_t,
    const float *, const float *, float *, float *, int, int, ap_aec_result_t *);
void ap_aec_backend_process(ap_aec_state_t *state, int enabled, float mu, uint32_t n,
    const float *mic, const float *ref, float *out, float *echo, int far, int dt, ap_aec_result_t *result) {
    float saved[160];
    uint32_t i;
    if (n != 160u || g_aec_calls != g_agc_calls) { g_stage_error = 1; return; }
    memcpy(saved, mic, sizeof(saved));
    stage_write(0u, saved, n);
    ap_aec_backend_process_d19_real(state, enabled, mu, n, mic, ref, out, echo, far, dt, result);
    for (i = 0u; i < n; ++i) if (fabsf(saved[i] - (out[i] + echo[i])) > 1.0e-6f) g_stage_error = 1;
    memcpy(g_aec_residual, out, sizeof(g_aec_residual));
    memcpy(g_echo, echo, sizeof(g_echo));
    stage_write(1u, echo, n);
    stage_write(2u, out, n);
    g_far = far; g_double = dt;
    ++g_aec_calls;
}

void ap_ns_process_d19_real(ap_ns_state_t *, ap_enhance_mode_t, float, const float *,
    const float *, float *, uint32_t, int, int, int, ap_ns_result_t *);
void ap_ns_process(ap_ns_state_t *state, ap_enhance_mode_t mode, float floor_gain,
    const float *in, const float *echo, float *out, uint32_t n, int frequency, int far, int dt,
    ap_ns_result_t *result) {
    if (n != 160u || g_aec_calls != g_ns_calls + 1u || !echo ||
        memcmp(in, g_aec_residual, sizeof(g_aec_residual)) ||
        memcmp(echo, g_echo, sizeof(g_echo)) || far != g_far || dt != g_double || frequency != 1) {
        g_stage_error = 1; return;
    }
    ap_ns_process_d19_real(state, mode, floor_gain, in, echo, out, n, frequency, far, dt, result);
    memcpy(g_ns_output, out, sizeof(g_ns_output));
    stage_write(3u, out, n);
    g_frequency = frequency;
    g_frequency_active = result->frequency_res_active;
    g_ns_gain = result->residual_echo_gain;
    ++g_ns_calls;
}

void ap_agc_process_controlled_d19_real(ap_agc_state_t *, float *, uint32_t, int);
void ap_agc_process_controlled(ap_agc_state_t *state, float *samples, uint32_t n, int allow) {
    const float before = state->gain;
    if (n != 160u || g_ns_calls != g_agc_calls + 1u ||
        memcmp(samples, g_ns_output, sizeof(g_ns_output)) || allow != !(g_far && !g_double)) {
        g_stage_error = 1; return;
    }
    ap_agc_process_controlled_d19_real(state, samples, n, allow);
    stage_write(4u, samples, n);
    if (g_control_file && fprintf(g_control_file, "%llu,%d,%d,%d,%d,%.9g,%d,%.9g,%.9g\n",
        (unsigned long long)g_agc_calls, g_far, g_double, g_frequency, g_frequency_active,
        (double)g_ns_gain, allow, (double)before, (double)state->gain) < 0) g_stage_error = 1;
    ++g_agc_calls;
}

float ap_res_process_d19_real(ap_res_state_t *, ap_enhance_mode_t, float *, uint32_t, float, float, int, int);
float ap_res_process(ap_res_state_t *state, ap_enhance_mode_t mode, float *samples, uint32_t n,
    float echo_energy, float residual_energy, int far, int dt) {
    ++g_res_calls;
    g_stage_error = 1;
    return ap_res_process_d19_real(state, mode, samples, n, echo_energy, residual_energy, far, dt);
}

static int stage_open(const char *directory) {
    static const char *names[] = {"aec_input", "echo", "aec_residual", "ns_output", "agc_output"};
    char path[1024];
    uint32_t i;
    for (i = 0u; i < 5u; ++i) {
        const int written = snprintf(path, sizeof(path), "%s/%s.f32le", directory, names[i]);
        if (written < 0 || (size_t)written >= sizeof(path)) return 2;
        g_stage_files[i] = fopen(path, "wb");
        if (!g_stage_files[i]) return 4;
    }
    if (snprintf(path, sizeof(path), "%s/control.csv", directory) < 0) return 4;
    g_control_file = fopen(path, "wb");
    if (!g_control_file) return 4;
    if (fprintf(g_control_file, "frame,far,dt,frequency_enabled,frequency_active,res_gain,agc_allow,gain_before,gain_after\n") < 0)
        return 4;
    return 0;
}

static int stage_close(void) {
    uint32_t i;
    int error = 0;
    for (i = 0u; i < 5u; ++i) if (g_stage_files[i] && fclose(g_stage_files[i])) error = 9;
    if (g_control_file && fclose(g_control_file)) error = 9;
    return error;
}

static int known_answers(void) {
    static ap_sync_state_t state;
    static const uint32_t delays[] = {0u, 16u, 20u, 640u};
    float input[160], reference[160];
    uint32_t d, frame, i;
    for (d = 0u; d < 4u; ++d) {
        ap_sync_init(&state, delays[d]);
#if D18_OBSERVER
        g_expected_delay = delays[d];
#endif
        for (frame = 0u; frame < 5u; ++frame) {
            for (i = 0u; i < 160u; ++i) {
                const uint32_t j = frame * 160u + i;
                input[i] = (float)((int32_t)((j * 997u) % 65536u) - 32768) / 32768.0f;
            }
            ap_sync_push_render(&state, input, 160u, frame);
            assert(ap_sync_get_reference(&state, 160u, reference) == (frame * 160u < delays[d]));
            for (i = 0u; i < 160u; ++i) {
                const uint32_t j = frame * 160u + i;
                const float expected = j < delays[d] ? 0.0f :
                    (float)((int32_t)(((j - delays[d]) * 997u) % 65536u) - 32768) / 32768.0f;
                assert(reference[i] == expected);
            }
        }
    }
#if D18_OBSERVER
    assert(g_reference_calls == 20u && !g_reference_error);
#endif
    puts("D18 known answers: 3200 samples PASS");
    return 0;
}

static int configure(const char *mode, ap_config_t *cfg) {
    *cfg = ap_config_default(AP_PROFILE_CALL);
    cfg->io_sample_rate_hz = 16000u;
    cfg->mic_channels = 2u;
    cfg->enable_delay_tracking = 0u;
    cfg->enable_clock_drift_compensation = 0u;
    if (strcmp(mode, "fixed1") == 0) cfg->initial_delay_ms = 1u;
    else if (strcmp(mode, "used0") == 0) cfg->initial_delay_ms = 0u;
    else return 0;
    return ap_pipeline_validate_config(cfg) == AP_OK && cfg->internal_sample_rate_hz == 16000u;
}

static int describe(const ap_config_t *c) {
    return printf("{\"profile\":\"CALL\",\"io_sample_rate_hz\":%u,\"internal_sample_rate_hz\":%u,"
                  "\"mic_channels\":%u,\"mic_spacing_mm\":%.9g,\"aec_filter_ms\":%u,"
                  "\"max_delay_ms\":%u,\"initial_delay_ms\":%u,\"aec_mu\":%.9g,"
                  "\"aec_adapt_stride\":%u,\"ns_floor\":%.9g,\"agc_target_dbfs\":%.9g,"
                  "\"limiter_dbfs\":%.9g,\"resource_class\":%u,\"stages\":%u,"
                  "\"enable_delay_tracking\":%u,\"enable_clock_drift_compensation\":%u}\n",
                  c->io_sample_rate_hz, c->internal_sample_rate_hz, c->mic_channels,
                  (double)c->mic_spacing_mm, c->aec_filter_ms, c->max_delay_ms, c->initial_delay_ms,
                  (double)c->aec_mu, c->aec_adapt_stride, (double)c->ns_floor,
                  (double)c->agc_target_dbfs, (double)c->limiter_dbfs, (unsigned)c->resource_class,
                  c->stages, (unsigned)c->enable_delay_tracking,
                  (unsigned)c->enable_clock_drift_compensation) < 0 ? 9 : 0;
}

int main(int argc, char **argv) {
    _Alignas(16) static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[320], render[160], output[160];
    ap_config_t cfg;
    ap_pipeline_t *pipeline = NULL;
    FILE *fm = NULL, *fr = NULL, *fo = NULL, *fj = NULL;
    uint32_t frame = 0u, latency;
    uint64_t underruns = 0u;
    uint16_t endian = 1u;
    int result = 0;
    if (argc == 2 && strcmp(argv[1], "--self-test") == 0) return known_answers();
    if (argc == 3 && strcmp(argv[1], "--describe") == 0)
        return configure(argv[2], &cfg) ? describe(&cfg) : 2;
    if ((argc != 6 && argc != 7 && argc != 8) || !configure(argv[1], &cfg) ||
        *(const unsigned char *)&endian != 1u || sizeof(float) != 4u) return 2;
#if D18_OBSERVER
    g_expected_delay = cfg.initial_delay_ms * 16u;
    if (argc >= 7) {
        g_reference_file = fopen(argv[6], "wb");
        if (!g_reference_file) return 4;
    }
#else
    if (argc == 7) return 2;
#endif
    if (argc == 8) { result = stage_open(argv[7]); if (result) return result; }
    if (ap_pipeline_state_size() > sizeof(state) ||
        ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) != AP_OK) return 3;
    latency = ap_pipeline_algorithmic_latency_ms(pipeline);
    fm = fopen(argv[2], "rb"); fr = fopen(argv[3], "rb");
    fo = fopen(argv[4], "wb"); fj = fopen(argv[5], "wb");
    if (!fm || !fr || !fo || !fj) { result = 4; goto done; }
    for (;;) {
        ap_metrics_t m;
        const size_t got = fread(mic, 1u, sizeof(mic), fm);
        if (got == 0u) break;
        if (got != sizeof(mic) || fread(render, 1u, sizeof(render), fr) != sizeof(render)) {
            result = 5; goto done;
        }
        if ((cfg.stages & AP_STAGE_SYNC) != 0u &&
            ap_pipeline_push_render(pipeline, render, 160u) != AP_OK) { result = 6; goto done; }
        if (ap_pipeline_process_capture(pipeline, mic, 160u, output) != AP_OK ||
            fwrite(output, 1u, sizeof(output), fo) != sizeof(output)) { result = 6; goto done; }
        ap_pipeline_get_metrics(pipeline, &m);
        underruns = m.render_underruns;
        if (g_stage_error || g_res_calls || g_aec_calls != (uint64_t)frame + 1u ||
            g_ns_calls != g_aec_calls || g_agc_calls != g_aec_calls) { result = 12; goto done; }
        if (underruns != (cfg.initial_delay_ms == 1u ? 1u : 0u)) { result = 10; goto done; }
#if D18_OBSERVER
        if (g_reference_error || g_reference_calls != (uint64_t)frame + 1u) { result = 11; goto done; }
#endif
        if (fprintf(fj, "{\"frame\":%u,\"algorithmic_latency_ms\":%u,\"vad_probability\":%.7g,"
                        "\"vad_active\":%u,\"far_end_active\":%u,\"double_talk_active\":%u,"
                        "\"erle_db\":%.7g,\"erle_valid\":%u,\"aec_converged\":%u,"
                        "\"estimated_delay_ms\":%u,\"delay_error_samples\":%d,\"delay_jumps\":%llu,"
                        "\"reference_sample_slips\":%llu,\"aec_resets\":%llu}\n",
                    frame++, latency, (double)m.vad_probability, (unsigned)m.vad_active,
                    (unsigned)m.far_end_active, (unsigned)m.double_talk_active, (double)m.erle_db,
                    (unsigned)m.erle_valid, (unsigned)m.aec_converged, m.estimated_delay_ms,
                    m.delay_error_samples, (unsigned long long)m.delay_jumps,
                    (unsigned long long)m.reference_sample_slips, (unsigned long long)m.aec_resets) < 0) {
            result = 7; goto done;
        }
    }
    if (frame == 0u || fgetc(fr) != EOF || ferror(fm) || ferror(fr)) result = 8;
done:
    if (stage_close()) result = 9;
    if (fm && fclose(fm) != 0) result = 9;
    if (fr && fclose(fr) != 0) result = 9;
    if (fo && fclose(fo) != 0) result = 9;
    if (fj && fclose(fj) != 0) result = 9;
#if D18_OBSERVER
    if (g_reference_file && fclose(g_reference_file) != 0) result = 9;
#endif
    if (!result) printf("{\"frames\":%u,\"render_underruns\":%llu}\n",
                        frame, (unsigned long long)underruns);
    return result;
}
