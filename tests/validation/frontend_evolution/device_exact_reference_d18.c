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
    if ((argc != 6 && argc != 7) || !configure(argv[1], &cfg) ||
        *(const unsigned char *)&endian != 1u || sizeof(float) != 4u) return 2;
#if D18_OBSERVER
    g_expected_delay = cfg.initial_delay_ms * 16u;
    if (argc == 7) {
        g_reference_file = fopen(argv[6], "wb");
        if (!g_reference_file) return 4;
    }
#else
    if (argc == 7) return 2;
#endif
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
