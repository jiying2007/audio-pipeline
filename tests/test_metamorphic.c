#include "audio_pipeline/audio_pipeline.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN __declspec(align(AP_PIPELINE_STATE_ALIGNMENT))
#else
#define AP_ALIGN _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
#endif

#define FRAMES 24u
#define RATE 16000u
#define FRAME (RATE / 100u)

static AP_ALIGN unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
static int16_t first_pass[FRAMES][FRAME];

static void make_frame(unsigned frame_index, int16_t *mic, int16_t *render) {
    unsigned i;
    for (i = 0u; i < FRAME; ++i) {
        const int32_t t = (int32_t)(frame_index * FRAME + i);
        const int16_t far = (int16_t)(((t * 37 + 101) % 4001) - 2000);
        const int16_t near = (int16_t)(((t * 19 + 17) % 3001) - 1500);
        render[i] = far;
        mic[2u * i] = (int16_t)(near + far / 5);
        mic[2u * i + 1u] = (int16_t)(near + far / 6);
    }
}

static void process_sequence(ap_pipeline_t *pipeline, int compare) {
    int16_t mic[FRAME * 2u];
    int16_t render[FRAME];
    int16_t out[FRAME];
    unsigned f;
    for (f = 0u; f < FRAMES; ++f) {
        make_frame(f, mic, render);
        assert(ap_pipeline_push_render(pipeline, render, FRAME) == AP_OK);
        assert(ap_pipeline_process_capture(pipeline, mic, FRAME, out) == AP_OK);
        if (compare)
            assert(memcmp(first_pass[f], out, sizeof(out)) == 0);
        else
            memcpy(first_pass[f], out, sizeof(out));
    }
}

static void test_reset_replay_is_bit_exact(void) {
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    assert(ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) == AP_OK);
    process_sequence(pipeline, 0);
    ap_pipeline_reset(pipeline);
    process_sequence(pipeline, 1);
}

static void test_silence_is_stable_in_isolated_ns(void) {
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    int16_t mic[FRAME] = {0};
    int16_t out[FRAME];
    unsigned f, i;

    cfg.mic_channels = 1u;
    cfg.stages = AP_STAGE_NS | AP_STAGE_VAD;
    cfg.enable_delay_tracking = 0u;
    cfg.enable_clock_drift_compensation = 0u;
    assert(ap_pipeline_validate_config(&cfg) == AP_OK);
    assert(ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) == AP_OK);
    for (f = 0u; f < 40u; ++f) {
        memset(out, 0x5a, sizeof(out));
        assert(ap_pipeline_process_capture(pipeline, mic, FRAME, out) == AP_OK);
        for (i = 0u; i < FRAME; ++i)
            assert(out[i] == 0);
    }
}

static void test_single_mic_geometry_requires_no_beamformer(void) {
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    cfg.mic_channels = 1u;
    assert((cfg.stages & AP_STAGE_BF) != 0u);
    assert(ap_pipeline_validate_config(&cfg) == AP_EINVAL);
    cfg.stages &= ~AP_STAGE_BF;
    assert(ap_pipeline_validate_config(&cfg) == AP_OK);
}

int main(void) {
    test_reset_replay_is_bit_exact();
    test_silence_is_stable_in_isolated_ns();
    test_single_mic_geometry_requires_no_beamformer();
    puts("metamorphic DSP contracts: OK");
    return 0;
}
