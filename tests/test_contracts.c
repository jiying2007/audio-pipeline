#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_STATE_ALIGN __declspec(align(AP_PIPELINE_STATE_ALIGNMENT))
#else
#define AP_STATE_ALIGN _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
#endif

static AP_STATE_ALIGN unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
static AP_STATE_ALIGN unsigned char misaligned_state[
    AP_PIPELINE_STATE_MAX_BYTES + AP_PIPELINE_STATE_ALIGNMENT];

static void run_silence_rate(uint32_t rate) {
    ap_config_t c = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_pipeline_t *p = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    const size_t frame = rate / 100u;
    unsigned f, i;

    if (rate > AP_BUILD_MAX_IO_RATE_HZ) return;
    memset(mic, 0, sizeof(mic));
    memset(render, 0, sizeof(render));
    memset(out, 0, sizeof(out));
    c.io_sample_rate_hz = rate;
    c.internal_sample_rate_hz =
        (rate == 8000u || AP_BUILD_MAX_INTERNAL_RATE_HZ == 8000u) ? 8000u : 16000u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    assert(ap_pipeline_frame_samples(p) == frame);
    assert(ap_pipeline_sample_rate_hz(p) == rate);
    assert(ap_pipeline_mic_channels(p) == c.mic_channels);
    assert(ap_pipeline_stages(p) == c.stages);
    for (f = 0u; f < 8u; ++f) {
        if (c.stages & AP_STAGE_SYNC)
            assert(ap_pipeline_push_render(p, render, frame) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, frame, out) == AP_OK);
    }
    for (i = 0u; i < frame; ++i) assert(out[i] > -32 && out[i] < 32);
}

static void test_supported_rates(void) {
    static const uint32_t rates[] = {8000u, 16000u, 24000u, 32000u, 48000u};
    size_t i;
    for (i = 0u; i < sizeof(rates) / sizeof(rates[0]); ++i) run_silence_rate(rates[i]);
}

static void test_resource_classes(void) {
    const ap_config_t standard = ap_config_default(AP_PROFILE_CALL);
    const ap_config_t low = ap_config_for_resource(AP_PROFILE_CALL, AP_RESOURCE_LOW);
    const ap_config_t tiny = ap_config_for_resource(AP_PROFILE_CALL, AP_RESOURCE_TINY);
    assert(standard.resource_class == AP_RESOURCE_STANDARD);
    assert(low.resource_class == AP_RESOURCE_LOW);
    assert(tiny.resource_class == AP_RESOURCE_TINY);
    assert(standard.internal_sample_rate_hz <= AP_BUILD_MAX_INTERNAL_RATE_HZ);
    assert(low.internal_sample_rate_hz <= AP_BUILD_MAX_INTERNAL_RATE_HZ);
    assert(tiny.internal_sample_rate_hz == 8000u);
    assert(standard.aec_filter_ms <= AP_BUILD_MAX_AEC_TAIL_MS);
    assert(low.aec_filter_ms <= AP_BUILD_MAX_AEC_TAIL_MS);
    assert(tiny.aec_filter_ms <= AP_BUILD_MAX_AEC_TAIL_MS);
    assert(standard.max_delay_ms <= AP_BUILD_MAX_DELAY_MS);
    assert(low.max_delay_ms <= AP_BUILD_MAX_DELAY_MS);
    assert(tiny.max_delay_ms <= AP_BUILD_MAX_DELAY_MS);
    assert((tiny.stages & AP_STAGE_BF) == 0u);
    assert((standard.stages & ~ap_pipeline_compiled_stages()) == 0u);
    if (AP_BUILD_MAX_MIC_CHANNELS == 1u) {
        assert(standard.mic_channels == 1u);
        assert((standard.stages & AP_STAGE_BF) == 0u);
    }
}

static void test_composition_contract(void) {
    const ap_stage_mask_t compiled = ap_pipeline_compiled_stages();
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);

    if (compiled & AP_STAGE_BF) {
        c.mic_channels = 1u;
        c.stages = AP_STAGE_BF;
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
    if (compiled & AP_STAGE_AEC) {
        c = ap_config_default(AP_PROFILE_CALL);
        c.stages = AP_STAGE_AEC;
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
    if (compiled & AP_STAGE_RES) {
        c = ap_config_default(AP_PROFILE_CALL);
        c.stages = AP_STAGE_RES;
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }

    c = ap_config_default(AP_PROFILE_CALL);
    c.stages = compiled & (AP_STAGE_HPF | AP_STAGE_NS | AP_STAGE_AGC | AP_STAGE_VAD);
    c.mic_channels = 1u;
    c.enable_delay_tracking = 0u;
    c.enable_clock_drift_compensation = 0u;
    if (c.stages != 0u) assert(ap_pipeline_validate_config(&c) == AP_OK);

    c = ap_config_default(AP_PROFILE_CALL);
    c.stages = 0u;
    c.enable_delay_tracking = 1u;
    c.enable_clock_drift_compensation = 0u;
    assert(ap_pipeline_validate_config(&c) == AP_EINVAL);

    c = ap_config_default(AP_PROFILE_CALL);
    c.stages = compiled | (1u << 31);
    assert(ap_pipeline_validate_config(&c) == AP_ESTATE);
}

static void test_finite_and_envelope_validation(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);

    c.io_sample_rate_hz = AP_BUILD_MAX_IO_RATE_HZ == 48000u ? 32000u : 48000u;
    if (c.io_sample_rate_hz > AP_BUILD_MAX_IO_RATE_HZ)
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);

    c = ap_config_default(AP_PROFILE_CALL);
    if (c.stages & AP_STAGE_BF) {
        c.mic_spacing_mm = NAN;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
    c = ap_config_default(AP_PROFILE_CALL);
    if (c.stages & AP_STAGE_AEC) {
        c.aec_mu = NAN;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
        c = ap_config_default(AP_PROFILE_CALL);
        c.aec_filter_ms = AP_BUILD_MAX_AEC_TAIL_MS + 1u;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
    c = ap_config_default(AP_PROFILE_CALL);
    if (c.stages & AP_STAGE_NS) {
        c.ns_floor = NAN;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
    c = ap_config_default(AP_PROFILE_CALL);
    if (c.stages & AP_STAGE_AGC) {
        c.agc_target_dbfs = INFINITY;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
        c = ap_config_default(AP_PROFILE_CALL);
        c.limiter_dbfs = NAN;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
    c = ap_config_default(AP_PROFILE_CALL);
    if (c.stages & AP_STAGE_SYNC) {
        c.max_delay_ms = AP_BUILD_MAX_DELAY_MS + 1u;
        assert(ap_pipeline_validate_config(&c) == AP_EINVAL);
    }
}

static void test_init_contract(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    assert(ap_pipeline_state_alignment() == AP_PIPELINE_STATE_ALIGNMENT);
    assert(ap_pipeline_state_size() <= AP_PIPELINE_STATE_MAX_BYTES);
    assert(ap_pipeline_init(NULL, sizeof(state), &c, &p) == AP_EINVAL);
    assert(ap_pipeline_init(state, sizeof(state), NULL, &p) == AP_EINVAL);
    assert(ap_pipeline_init(state, sizeof(state), &c, NULL) == AP_EINVAL);
    assert(ap_pipeline_init(state, ap_pipeline_state_size() - 1u, &c, &p) == AP_ENOMEM);
    assert(ap_pipeline_init(misaligned_state + 1u, sizeof(misaligned_state) - 1u,
                            &c, &p) == AP_EINVAL);
    c.resource_class = (ap_resource_class_t)99;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_EINVAL);
}

static void test_quality_contract(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    ap_metrics_t m;
    uint32_t full_taps = 0u;
    uint32_t full_stride = 0u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    ap_pipeline_get_metrics(p, &m);
    assert(m.quality == AP_QUALITY_FULL);
    assert(m.erle_valid == 0u);
    if (c.stages & AP_STAGE_AEC) {
        full_taps = m.active_aec_taps;
        full_stride = m.active_aec_adapt_stride;
        assert(full_taps > 0u);
        assert(full_stride == c.aec_adapt_stride);
    }

    assert(ap_pipeline_set_quality(p, AP_QUALITY_LITE) == AP_OK);
    ap_pipeline_get_metrics(p, &m);
    assert(m.quality == AP_QUALITY_LITE);
    if (c.stages & AP_STAGE_AEC) {
        assert(m.active_aec_taps <= full_taps);
        assert(m.active_aec_adapt_stride >= 2u);
    }

    assert(ap_pipeline_set_quality(p, AP_QUALITY_SAFE) == AP_OK);
    ap_pipeline_get_metrics(p, &m);
    assert(m.quality == AP_QUALITY_SAFE);
    if (c.stages & AP_STAGE_AEC) {
        assert(m.active_aec_taps <= full_taps);
        assert(m.active_aec_taps <= 40u * c.internal_sample_rate_hz / 1000u);
        assert(m.active_aec_adapt_stride >= 4u);
    }

    assert(ap_pipeline_set_quality(p, AP_QUALITY_FULL) == AP_OK);
    ap_pipeline_get_metrics(p, &m);
    assert(m.quality == AP_QUALITY_FULL);
    if (c.stages & AP_STAGE_AEC) {
        assert(m.active_aec_taps == full_taps);
        assert(m.active_aec_adapt_stride == full_stride);
    }
}

static void test_timestamp_and_route_contract(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    ap_metrics_t before, after;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    if (c.stages & AP_STAGE_SYNC) {
        assert(ap_pipeline_observe_io_timestamps(p, 1100000000ull, 1000000000ull) == AP_OK);
        ap_pipeline_get_metrics(p, &before);
        assert(before.timestamp_observations == 1u);
        assert(ap_pipeline_observe_io_timestamps(p, 1000000000ull, 1100000000ull) == AP_EINVAL);
        assert(ap_pipeline_notify_echo_path_change(p) == AP_OK);
        ap_pipeline_get_metrics(p, &after);
        if (c.stages & AP_STAGE_AEC) {
            assert(after.aec_resets == before.aec_resets + 1u);
            assert(after.erle_valid == 0u);
            assert(after.aec_convergence_frames == 0u);
        }
    } else {
        assert(ap_pipeline_observe_io_timestamps(p, 1u, 1u) == AP_ESTATE);
        assert(ap_pipeline_notify_echo_path_change(p) == AP_ESTATE);
    }
}

static void test_frame_contract_rejects_wrong_sizes(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t out[AP_MAX_IO_FRAME_SAMPLES] = {0};
    size_t frame;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    frame = ap_pipeline_frame_samples(p);
    assert(frame > 1u);
    if (c.stages & AP_STAGE_SYNC)
        assert(ap_pipeline_push_render(p, render, frame - 1u) == AP_EINVAL);
    assert(ap_pipeline_process_capture(p, mic, frame - 1u, out) == AP_EINVAL);
}

int main(void) {
    test_supported_rates();
    test_resource_classes();
    test_composition_contract();
    test_finite_and_envelope_validation();
    test_init_contract();
    test_quality_contract();
    test_timestamp_and_route_contract();
    test_frame_contract_rejects_wrong_sizes();
    puts("audio-pipeline contract tests: OK");
    return 0;
}
