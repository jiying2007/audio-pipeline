/* Offline first-party public-API diagnostic. Not installed in the SDK. */
#include "audio_pipeline/audio_pipeline.h"
#include <stdio.h>
#include <string.h>

static int configure(const char *mode, ap_config_t *cfg) {
    *cfg = ap_config_default(AP_PROFILE_CALL);
    cfg->io_sample_rate_hz = 16000u;
    cfg->mic_channels = 2u;
    if (strcmp(mode, "default") == 0 || strcmp(mode, "sync-default-control") == 0) {
        /* Exact unchanged CALL configuration: control for D0/D1 reproduction. */
    } else if (strcmp(mode, "tracked1") == 0 || strcmp(mode, "tracked1-no-drift") == 0 ||
               strcmp(mode, "fixed1") == 0) {
        cfg->initial_delay_ms = 1u;
        if (strcmp(mode, "tracked1-no-drift") == 0 || strcmp(mode, "fixed1") == 0)
            cfg->enable_clock_drift_compensation = 0u;
        if (strcmp(mode, "fixed1") == 0) cfg->enable_delay_tracking = 0u;
    } else if (strcmp(mode, "bf-isolated") == 0 || strcmp(mode, "ns-isolated") == 0 ||
               strcmp(mode, "agc-isolated") == 0) {
        cfg->enable_delay_tracking = 0u;
        cfg->enable_clock_drift_compensation = 0u;
        cfg->stages = strcmp(mode, "bf-isolated") == 0 ? AP_STAGE_BF :
                      strcmp(mode, "ns-isolated") == 0 ? AP_STAGE_NS | AP_STAGE_VAD : AP_STAGE_AGC;
    } else return 0;
    return ap_pipeline_validate_config(cfg) == AP_OK;
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
    uint16_t endian = 1u;
    int result = 0;
    if (argc == 3 && strcmp(argv[1], "--describe") == 0)
        return configure(argv[2], &cfg) ? describe(&cfg) : 2;
    if (argc != 6 || !configure(argv[1], &cfg) || *(const unsigned char *)&endian != 1u) return 2;
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
    return result;
}
