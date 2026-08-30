#include "audio_pipeline/audio_pipeline.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN(N) __declspec(align(N))
#else
#define AP_ALIGN(N) _Alignas(N)
#endif

static AP_ALIGN(AP_PIPELINE_STATE_ALIGNMENT)
unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];

static ap_pipeline_t *new_pipeline(ap_config_t *config) {
    ap_pipeline_t *pipeline = NULL;
    assert(ap_pipeline_init(state, sizeof(state), config, &pipeline) == AP_OK);
    assert(pipeline != NULL);
    return pipeline;
}

static void test_query_and_discontinuity_validation(void) {
    ap_config_t config = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = new_pipeline(&config);
    ap_metrics_t metrics;

    assert(ap_pipeline_stages(NULL) == 0u);
    assert(ap_pipeline_notify_stream_discontinuity(NULL,
                                                    AP_DISCONTINUITY_CAPTURE_GAP,
                                                    1u) == AP_EINVAL);
    assert(ap_pipeline_notify_stream_discontinuity(pipeline, 0u, 0u) == AP_EINVAL);
    assert(ap_pipeline_notify_stream_discontinuity(pipeline, 1u << 31, 0u) == AP_EINVAL);

    assert(ap_pipeline_notify_stream_discontinuity(
               pipeline,
               AP_DISCONTINUITY_CAPTURE_GAP | AP_DISCONTINUITY_RENDER_GAP |
                   AP_DISCONTINUITY_CLOCK_RESET | AP_DISCONTINUITY_XRUN |
                   AP_DISCONTINUITY_CODEC_REOPEN | AP_DISCONTINUITY_ROUTE_CHANGE,
               7u) == AP_OK);
    ap_pipeline_get_metrics(pipeline, &metrics);
    assert(metrics.estimated_drift_ppm == 0.0f);
    assert(metrics.aec_convergence_frames == 0u);
    assert(metrics.aec_converged == 0u);
    assert(metrics.erle_valid == 0u);
}

static void test_tuning_validation(void) {
    ap_config_t config = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = new_pipeline(&config);
    ap_tuning_t tuning;

    memset(&tuning, 0, sizeof(tuning));
    tuning.struct_size = sizeof(tuning);
    tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    tuning.mask = AP_TUNING_AEC_MU | AP_TUNING_NS_FLOOR |
                  AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER;
    tuning.aec_mu = 0.12f;
    tuning.ns_floor = 0.25f;
    tuning.agc_target_dbfs = -15.0f;
    tuning.limiter_dbfs = -2.0f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_OK);

    assert(ap_pipeline_apply_tuning(NULL, &tuning) == AP_EINVAL);
    assert(ap_pipeline_apply_tuning(pipeline, NULL) == AP_EINVAL);

    tuning.struct_size = 0u;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.struct_size = sizeof(tuning);
    tuning.api_version = 0u;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    tuning.mask = 0u;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.mask = 1u << 31;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);

    tuning.mask = AP_TUNING_AEC_MU;
    tuning.aec_mu = 0.0f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.aec_mu = NAN;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.aec_mu = 1.1f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);

    tuning.mask = AP_TUNING_NS_FLOOR;
    tuning.ns_floor = 0.01f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.ns_floor = INFINITY;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);

    tuning.mask = AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER;
    tuning.agc_target_dbfs = -2.0f;
    tuning.limiter_dbfs = -3.0f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.agc_target_dbfs = -61.0f;
    tuning.limiter_dbfs = -2.0f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.agc_target_dbfs = -15.0f;
    tuning.limiter_dbfs = -0.05f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
    tuning.agc_target_dbfs = NAN;
    tuning.limiter_dbfs = -2.0f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_EINVAL);
}

static void test_tuning_survives_processing(void) {
    ap_config_t config = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = new_pipeline(&config);
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t output[AP_MAX_IO_FRAME_SAMPLES] = {0};
    ap_tuning_t tuning;
    const size_t frames = ap_pipeline_frame_samples(pipeline);
    unsigned i;

    memset(&tuning, 0, sizeof(tuning));
    tuning.struct_size = sizeof(tuning);
    tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    tuning.mask = AP_TUNING_AGC_TARGET;
    tuning.agc_target_dbfs = -18.0f;
    assert(ap_pipeline_apply_tuning(pipeline, &tuning) == AP_OK);

    for (i = 0u; i < 4u; ++i) {
        if (config.stages & AP_STAGE_SYNC)
            assert(ap_pipeline_push_render(pipeline, render, frames) == AP_OK);
        assert(ap_pipeline_process_capture(pipeline, mic, frames, output) == AP_OK);
    }

    assert(ap_pipeline_notify_stream_discontinuity(pipeline,
                                                    AP_DISCONTINUITY_CAPTURE_GAP,
                                                    1u) == AP_OK);
    if (config.stages & AP_STAGE_SYNC)
        assert(ap_pipeline_push_render(pipeline, render, frames) == AP_OK);
    assert(ap_pipeline_process_capture(pipeline, mic, frames, output) == AP_OK);
}

int main(void) {
    test_query_and_discontinuity_validation();
    test_tuning_validation();
    test_tuning_survives_processing();
    puts("audio-pipeline v2 pipeline control contracts: OK");
    return 0;
}
