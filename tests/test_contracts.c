#include "audio_pipeline/audio_pipeline.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static AP_ALIGN16 unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];

static void run_silence_rate(uint32_t rate) {
    ap_config_t c = ap_config_default(AP_PROFILE_ASSISTANT);
    ap_pipeline_t *p = NULL;
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    const size_t frame = rate / 100u;
    unsigned f, i;
    memset(mic, 0, sizeof(mic));
    memset(render, 0, sizeof(render));
    memset(out, 0, sizeof(out));
    c.io_sample_rate_hz = rate;
    c.internal_sample_rate_hz = rate == 8000u ? 8000u : 16000u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    assert(ap_pipeline_frame_samples(p) == frame);
    assert(ap_pipeline_sample_rate_hz(p) == rate);
    assert(ap_pipeline_mic_channels(p) == 2u);
    for (f = 0u; f < 8u; ++f) {
        assert(ap_pipeline_push_render(p, render, frame) == AP_OK);
        assert(ap_pipeline_process_capture(p, mic, frame, out) == AP_OK);
    }
    for (i = 0u; i < frame; ++i) assert(out[i] > -16 && out[i] < 16);
}

static void test_supported_rates(void) {
    static const uint32_t rates[] = {8000u, 16000u, 24000u, 32000u, 48000u};
    size_t i;
    for (i = 0u; i < sizeof(rates) / sizeof(rates[0]); ++i) run_silence_rate(rates[i]);
}

static void test_quality_contract(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    ap_metrics_t m;
    uint32_t full_taps;
    uint32_t full_stride;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    ap_pipeline_get_metrics(p, &m);
    assert(m.quality == AP_QUALITY_FULL);
    /* The implementation may cap the requested echo tail to its bounded
     * realtime state. Capture the effective FULL geometry rather than
     * reconstructing an uncapped internal value from public config. */
    full_taps = m.active_aec_taps;
    full_stride = m.active_aec_adapt_stride;
    assert(full_taps > 0u);
    assert(full_stride == c.aec_adapt_stride);

    assert(ap_pipeline_set_quality(p, AP_QUALITY_LITE) == AP_OK);
    ap_pipeline_get_metrics(p, &m);
    assert(m.quality == AP_QUALITY_LITE);
    assert(m.active_aec_taps <= full_taps);
    assert(m.active_aec_adapt_stride >= 2u);

    assert(ap_pipeline_set_quality(p, AP_QUALITY_SAFE) == AP_OK);
    ap_pipeline_get_metrics(p, &m);
    assert(m.quality == AP_QUALITY_SAFE);
    assert(m.active_aec_taps <= full_taps);
    assert(m.active_aec_taps <= 40u * c.internal_sample_rate_hz / 1000u);
    assert(m.active_aec_adapt_stride >= 4u);

    assert(ap_pipeline_set_quality(p, AP_QUALITY_FULL) == AP_OK);
    ap_pipeline_get_metrics(p, &m);
    assert(m.quality == AP_QUALITY_FULL);
    assert(m.active_aec_taps == full_taps);
    assert(m.active_aec_adapt_stride == full_stride);
}

static void test_frame_contract_rejects_wrong_sizes(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    int16_t mic[320] = {0};
    int16_t render[160] = {0};
    int16_t out[160] = {0};
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    assert(ap_pipeline_push_render(p, render, 159u) == AP_EINVAL);
    assert(ap_pipeline_process_capture(p, mic, 159u, out) == AP_EINVAL);
}

int main(void) {
    test_supported_rates();
    test_quality_contract();
    test_frame_contract_rejects_wrong_sizes();
    puts("audio-pipeline contract tests: OK");
    return 0;
}
