#include "audio_pipeline/audio_modules.h"
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

static void fill_signal(float *x, size_t n) {
    size_t i;
    for (i = 0u; i < n; ++i) x[i] = 0.1f * sinf((float)i * 0.11f);
}

static void test_resampler(void) {
#if AP_HAVE_MODULE_RESAMPLER
    int16_t in[160] = {0};
    int16_t pcm[80];
    assert(ap_module_resampler_input_s16(in, 160u, 1u, 0u, a, 80u) == AP_OK);
    assert(ap_module_resampler_output_s16(a, 80u, pcm, 80u) == AP_OK);
#endif
}

static void test_hpf(void) {
#if AP_HAVE_MODULE_HPF
    ap_hpf_module_t *m = NULL;
    fill_signal(a, 160u);
    assert(ap_module_hpf_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_hpf_init(memory, sizeof(memory), 16000u, 1u, &m) == AP_OK);
    assert(ap_module_hpf_process(m, a, 160u, 0u) == AP_OK);
#endif
}

static void test_beamformer(void) {
#if AP_HAVE_MODULE_BF
    ap_beamformer_module_t *m = NULL;
    fill_signal(a, 160u);
    memcpy(b, a, 160u * sizeof(float));
    assert(ap_module_beamformer_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_beamformer_init(memory, sizeof(memory), 16000u, 35.0f, &m) == AP_OK);
    assert(ap_module_beamformer_process(m, 1, a, b, out, 160u) == AP_OK);
#endif
}

static void test_sync(void) {
#if AP_HAVE_MODULE_SYNC
    ap_sync_module_t *m = NULL;
    ap_module_sync_event_t event;
    ap_module_sync_status_t status;
    int underrun = 0;
    fill_signal(a, 160u);
    assert(ap_module_sync_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_sync_init(memory, sizeof(memory), 0u, &m) == AP_OK);
    assert(ap_module_sync_push_render(m, a, 160u, 0u) == AP_OK);
    assert(ap_module_sync_track(m, a, 160u, 16000u, 120u, 0, 0, &event) == AP_OK);
    assert(ap_module_sync_get_reference(m, 160u, out, &underrun) == AP_OK);
    ap_module_sync_get_status(m, &status);
    assert(status.delay_samples == 0u);
#endif
}

static void test_aec(void) {
#if AP_HAVE_MODULE_AEC
    ap_aec_module_t *m = NULL;
    ap_module_aec_config_t cfg = {16000u, 64u, 1u, 0.2f};
    ap_module_aec_result_t result;
    fill_signal(a, 160u);
    memcpy(b, a, 160u * sizeof(float));
    assert(ap_module_aec_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_aec_init(memory, sizeof(memory), &cfg, &m) == AP_OK);
    assert(ap_module_aec_process(m, a, b, out, echo, 160u, 1, 0, &result) == AP_OK);
    assert(result.active_taps > 0u);
#endif
}

static void test_res(void) {
#if AP_HAVE_MODULE_RES
    ap_res_module_t *m = NULL;
    float gain = 1.0f;
    fill_signal(a, 160u);
    assert(ap_module_res_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_res_init(memory, sizeof(memory), &m) == AP_OK);
    assert(ap_module_res_process(m, AP_QUALITY_FULL, a, 160u,
                                 0.1f, 0.02f, 1, 0, &gain) == AP_OK);
    assert(gain > 0.0f && gain <= 1.0f);
#endif
}

static void test_ns(void) {
#if AP_HAVE_MODULE_NS
    ap_ns_module_t *m = NULL;
    ap_module_ns_config_t cfg = {16000u, 0.12f};
    ap_module_ns_result_t result;
    fill_signal(a, 160u);
    memset(echo, 0, 160u * sizeof(float));
    assert(ap_module_ns_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_ns_init(memory, sizeof(memory), &cfg, &m) == AP_OK);
    assert(ap_module_ns_process(m, AP_QUALITY_FULL, a, echo, out, 160u,
                                0, 0, 0, &result) == AP_OK);
    assert(result.speech_probability >= 0.0f && result.speech_probability <= 1.0f);
#endif
}

static void test_agc(void) {
#if AP_HAVE_MODULE_AGC
    ap_agc_module_t *m = NULL;
    ap_module_agc_config_t cfg = {-20.0f, -2.0f};
    fill_signal(a, 160u);
    assert(ap_module_agc_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_agc_init(memory, sizeof(memory), &cfg, &m) == AP_OK);
    assert(ap_module_agc_process(m, a, 160u) == AP_OK);
#endif
}

static void test_vad(void) {
#if AP_HAVE_MODULE_VAD
    ap_vad_module_t *m = NULL;
    ap_module_vad_result_t result;
    fill_signal(a, 160u);
    assert(ap_module_vad_state_size() <= AP_MODULE_STATE_MAX_BYTES);
    assert(ap_module_vad_init(memory, sizeof(memory), &m) == AP_OK);
    assert(ap_module_vad_process(m, a, 160u, 0.8f, 1, &result) == AP_OK);
    assert(result.probability >= 0.0f && result.probability <= 1.0f);
#endif
}

int main(void) {
    test_resampler();
    test_hpf();
    test_beamformer();
    test_sync();
    test_aec();
    test_res();
    test_ns();
    test_agc();
    test_vad();
    puts("audio module contracts: OK");
    return 0;
}
