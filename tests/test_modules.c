#include "audio_pipeline/audio_modules.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static AP_ALIGN16 unsigned char memory[AP_MODULE_STATE_MAX_BYTES];
static float a[AP_MAX_IO_FRAME_SAMPLES];
static float b[AP_MAX_IO_FRAME_SAMPLES];
static float out[AP_MAX_IO_FRAME_SAMPLES];
static float echo[AP_MAX_IO_FRAME_SAMPLES];

static uint32_t test_rate(void) { return AP_BUILD_MAX_INTERNAL_RATE_HZ; }
static size_t test_frame(void) { return (size_t)test_rate() / 100u; }

static void fill_signal(float *x, size_t n) {
    size_t i;
    for (i = 0u; i < n; ++i) x[i] = 0.1f * sinf((float)i * 0.11f);
}

static void test_resampler(void) {
#if AP_HAVE_MODULE_RESAMPLER
    ap_resampler_module_t *m = NULL;
    int16_t in[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t pcm[AP_MAX_IO_FRAME_SAMPLES];
    const size_t in_frames = AP_BUILD_MAX_IO_RATE_HZ / 100u;
    const size_t out_frames = test_frame();
    assert(ap_module_resampler_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_resampler_init(memory, sizeof(memory), &m) == AP_OK);
    assert(ap_module_resampler_input_s16(m, in, in_frames, 1u, 0u, a, out_frames) == AP_OK);
    assert(ap_module_resampler_output_s16(m, a, out_frames, pcm, in_frames) == AP_OK);
    ap_module_resampler_reset(m);
#endif
}

static void test_hpf(void) {
#if AP_HAVE_MODULE_HPF
    ap_hpf_module_t *m = NULL;
    const size_t frame = test_frame();
    fill_signal(a, frame);
    assert(ap_module_hpf_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_hpf_init(memory, sizeof(memory), test_rate(), 1u, &m) == AP_OK);
    assert(ap_module_hpf_process(m, a, frame, 0u) == AP_OK);
    assert(ap_module_hpf_process(m, a, frame - 1u, 0u) == AP_EINVAL);
    ap_module_hpf_reset(m);
#endif
}

static void test_beamformer(void) {
#if AP_HAVE_MODULE_BF
    ap_beamformer_module_t *m = NULL;
    const size_t frame = test_frame();
    fill_signal(a, frame);
    memcpy(b, a, frame * sizeof(float));
    assert(AP_BUILD_MAX_MIC_CHANNELS == 2u);
    assert(ap_module_beamformer_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_beamformer_init(memory, sizeof(memory), test_rate(), 35.0f, &m) == AP_OK);
    assert(ap_module_beamformer_process(m, 1, a, b, out, frame) == AP_OK);
    assert(ap_module_beamformer_process(m, 1, a, b, out, frame - 1u) == AP_EINVAL);
    ap_module_beamformer_reset(m);
    assert(ap_module_beamformer_init(memory, sizeof(memory), test_rate(), NAN, &m) == AP_EINVAL);
#endif
}

static void test_sync(void) {
#if AP_HAVE_MODULE_SYNC
    ap_sync_module_t *m = NULL;
    ap_module_sync_event_t event;
    ap_module_sync_status_t status;
    const size_t frame = test_frame();
    const uint32_t max_delay = AP_BUILD_MAX_DELAY_MS < 120u ? AP_BUILD_MAX_DELAY_MS : 120u;
    int underrun = 0;
    fill_signal(a, frame);
    assert(ap_module_sync_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_sync_init(memory, sizeof(memory), 0u, &m) == AP_OK);
    assert(ap_module_sync_push_render(m, a, frame, 0u) == AP_OK);
    assert(ap_module_sync_track(m, a, frame, test_rate(), max_delay, 0, 0, &event) == AP_OK);
    assert(ap_module_sync_observe_timestamps(m, 1050000000ull, 1000000000ull,
                                             test_rate(), max_delay, &event) == AP_OK);
    assert(event.timestamp_observed == 1u);
    assert(ap_module_sync_get_reference(m, frame, out, &underrun) == AP_OK);
    ap_module_sync_get_status(m, &status);
    assert(status.delay_samples <= max_delay * test_rate() / 1000u);
    assert(ap_module_sync_track(m, a, frame - 1u, test_rate(), max_delay, 0, 0,
                                &event) == AP_EINVAL);
    ap_module_sync_reset(m);
#endif
}

static void test_activity(void) {
#if AP_HAVE_MODULE_ACTIVITY
    ap_activity_module_t *m = NULL;
    ap_module_activity_config_t cfg = {1.0e-7f, 1.5f, 3u};
    ap_module_activity_result_t result;
    assert(ap_module_activity_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_activity_init(memory, sizeof(memory), &cfg, &m) == AP_OK);
    assert(ap_module_activity_process(m, 3.0e-7f, 2.0e-7f, &result) == AP_OK);
    assert(result.far_end_active == 1u);
    assert(ap_module_activity_process(m, 5.0e-7f, 2.0e-7f, &result) == AP_OK);
    assert(result.double_talk_active == 1u);
    ap_module_activity_reset(m);
    cfg.double_talk_ratio = NAN;
    assert(ap_module_activity_init(memory, sizeof(memory), &cfg, &m) == AP_EINVAL);
#endif
}

static void test_aec(void) {
#if AP_HAVE_MODULE_AEC
    ap_aec_module_t *m = NULL;
    ap_module_aec_config_t cfg;
    ap_module_aec_result_t result;
    const size_t frame = test_frame();
    cfg.sample_rate_hz = test_rate();
    cfg.filter_ms = AP_BUILD_MAX_AEC_TAIL_MS < 64u ? AP_BUILD_MAX_AEC_TAIL_MS : 64u;
    cfg.adapt_stride = 1u;
    cfg.mu = 0.2f;
    fill_signal(a, frame);
    memcpy(b, a, frame * sizeof(float));
    assert(ap_module_aec_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_aec_init(memory, sizeof(memory), &cfg, &m) == AP_OK);
    assert(ap_module_aec_process(m, a, b, out, echo, frame, 1, 0, &result) == AP_OK);
    assert(result.active_taps > 0u);
    assert(ap_module_aec_process(m, a, b, out, echo, frame - 1u, 1, 0, &result) == AP_EINVAL);
    ap_module_aec_reset(m);
    cfg.mu = NAN;
    assert(ap_module_aec_init(memory, sizeof(memory), &cfg, &m) == AP_EINVAL);
#endif
}

static void test_res(void) {
#if AP_HAVE_MODULE_RES
    ap_res_module_t *m = NULL;
    float gain = 1.0f;
    const size_t frame = test_frame();
    fill_signal(a, frame);
    assert(ap_module_res_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_res_init(memory, sizeof(memory), &m) == AP_OK);
    assert(ap_module_res_process(m, AP_QUALITY_FULL, a, frame,
                                 0.1f, 0.02f, 1, 0, &gain) == AP_OK);
    assert(gain > 0.0f && gain <= 1.0f);
    ap_module_res_reset(m);
#endif
}

static void test_ns(void) {
#if AP_HAVE_MODULE_NS
    ap_ns_module_t *m = NULL;
    ap_module_ns_config_t cfg = {0u, 0.12f};
    ap_module_ns_result_t result;
    const size_t frame = test_frame();
    cfg.sample_rate_hz = test_rate();
    fill_signal(a, frame);
    memset(echo, 0, frame * sizeof(float));
    assert(ap_module_ns_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_ns_init(memory, sizeof(memory), &cfg, &m) == AP_OK);
    assert(ap_module_ns_process(m, AP_QUALITY_FULL, a, echo, out, frame,
                                0, 0, 0, &result) == AP_OK);
    assert(result.speech_probability >= 0.0f && result.speech_probability <= 1.0f);
    assert(ap_module_ns_process(m, AP_QUALITY_FULL, a, echo, out, frame - 1u,
                                0, 0, 0, &result) == AP_EINVAL);
    ap_module_ns_reset(m);
    cfg.floor_gain = NAN;
    assert(ap_module_ns_init(memory, sizeof(memory), &cfg, &m) == AP_EINVAL);
#endif
}

static void test_agc(void) {
#if AP_HAVE_MODULE_AGC
    ap_agc_module_t *m = NULL;
    ap_module_agc_config_t cfg = {-20.0f, -2.0f};
    const size_t frame = test_frame();
    fill_signal(a, frame);
    assert(ap_module_agc_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_agc_init(memory, sizeof(memory), &cfg, &m) == AP_OK);
    assert(ap_module_agc_process(m, a, frame) == AP_OK);
    ap_module_agc_reset(m);
    cfg.target_dbfs = NAN;
    assert(ap_module_agc_init(memory, sizeof(memory), &cfg, &m) == AP_EINVAL);
#endif
}

static void test_vad(void) {
#if AP_HAVE_MODULE_VAD
    ap_vad_module_t *m = NULL;
    ap_module_vad_result_t result;
    const size_t frame = test_frame();
    fill_signal(a, frame);
    assert(ap_module_vad_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_vad_init(memory, sizeof(memory), &m) == AP_OK);
    assert(ap_module_vad_process(m, a, frame, 0.8f, 1, &result) == AP_OK);
    assert(result.probability >= 0.0f && result.probability <= 1.0f);
    assert(ap_module_vad_process(m, a, frame, NAN, 1, &result) == AP_EINVAL);
    ap_module_vad_reset(m);
#endif
}

int main(void) {
    test_resampler();
    test_hpf();
    test_beamformer();
    test_sync();
    test_activity();
    test_aec();
    test_res();
    test_ns();
    test_agc();
    test_vad();
    puts("audio module contracts: OK");
    return 0;
}
