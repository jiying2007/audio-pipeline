#include "audio_pipeline/audio_modules.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if !AP_HAVE_MODULE_NS || !AP_HAVE_MODULE_AGC || !AP_HAVE_MODULE_VAD
#error "I010 probe requires standalone NS, AGC and VAD modules"
#endif

#define FRAME 160u
#define SCENARIOS 4u
#define FRAMES_PER_SCENARIO 320u
#define PROB_EPS 1.0e-7f
#define WAVE_EPS 1.0e-8f

_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char ns_base_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char ns_low_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char agc_base_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char agc_low_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char vad_base_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char vad_low_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char vad_low_base_up_mem[AP_MODULE_STATE_MAX_BYTES];
_Alignas(AP_MODULE_STATE_ALIGNMENT) static unsigned char vad_base_low_up_mem[AP_MODULE_STATE_MAX_BYTES];

static uint32_t rng_state;

static float prng_signed(void) {
    rng_state = rng_state * 1664525u + 1013904223u;
    return ((float)((rng_state >> 8u) & 0x00ffffffu) / 8388607.5f) - 1.0f;
}

static float frame_rms(const float *x) {
    double e = 1.0e-18;
    uint32_t i;
    for (i = 0u; i < FRAME; ++i) e += (double)x[i] * (double)x[i];
    return (float)sqrt(e / (double)FRAME);
}

static int speech_active(uint32_t scenario, uint32_t frame) {
    if (scenario < 2u) return 0;
    if (scenario == 2u) return ((frame / 55u) % 2u) == 0u;
    return ((frame / 70u) % 3u) != 2u;
}

static void make_frame(uint32_t seed,
                       uint32_t scenario,
                       uint32_t frame,
                       float *out) {
    uint32_t i;
    const int active = speech_active(scenario, frame);
    float noise_amp;
    float speech_amp;
    const double pi = 3.14159265358979323846;

    (void)seed;
    if (scenario == 0u) {
        noise_amp = 0.018f;
        speech_amp = 0.0f;
    } else if (scenario == 1u) {
        static const float levels[] = {0.006f, 0.012f, 0.024f, 0.048f, 0.080f, 0.032f};
        noise_amp = levels[(frame / 32u) % (sizeof(levels) / sizeof(levels[0]))];
        speech_amp = 0.0f;
    } else if (scenario == 2u) {
        noise_amp = 0.020f;
        speech_amp = active ? 0.075f : 0.0f;
    } else {
        noise_amp = 0.016f;
        speech_amp = active ? 0.032f : 0.0f;
    }

    for (i = 0u; i < FRAME; ++i) {
        const uint64_t n = (uint64_t)frame * FRAME + i;
        const float white = prng_signed();
        const float colored =
            0.55f * (float)sin(2.0 * pi * 83.0 * (double)n / 16000.0) +
            0.30f * (float)sin(2.0 * pi * 137.0 * (double)n / 16000.0);
        float speech = 0.0f;
        if (active) {
            speech =
                0.70f * (float)sin(2.0 * pi * 223.0 * (double)n / 16000.0) +
                0.30f * (float)sin(2.0 * pi * 487.0 * (double)n / 16000.0);
        }
        out[i] = noise_amp * (0.72f * white + 0.28f * colored) +
                 speech_amp * speech;
    }
}

static int init_modules(ap_ns_module_t **ns_base,
                        ap_ns_module_t **ns_low,
                        ap_agc_module_t **agc_base,
                        ap_agc_module_t **agc_low,
                        ap_vad_module_t **vad_base,
                        ap_vad_module_t **vad_low,
                        ap_vad_module_t **vad_low_base_up,
                        ap_vad_module_t **vad_base_low_up) {
    const ap_module_ns_config_t ns_base_cfg = {16000u, 0.12f};
    const ap_module_ns_config_t ns_low_cfg = {16000u, 0.05f};
    const ap_module_agc_config_t agc_cfg = {-20.0f, -2.0f};

    if (ap_module_ns_init(ns_base_mem, sizeof(ns_base_mem), &ns_base_cfg, ns_base) != AP_OK)
        return 1;
    if (ap_module_ns_init(ns_low_mem, sizeof(ns_low_mem), &ns_low_cfg, ns_low) != AP_OK)
        return 2;
    if (ap_module_agc_init(agc_base_mem, sizeof(agc_base_mem), &agc_cfg, agc_base) != AP_OK)
        return 3;
    if (ap_module_agc_init(agc_low_mem, sizeof(agc_low_mem), &agc_cfg, agc_low) != AP_OK)
        return 4;
    if (ap_module_vad_init(vad_base_mem, sizeof(vad_base_mem), vad_base) != AP_OK)
        return 5;
    if (ap_module_vad_init(vad_low_mem, sizeof(vad_low_mem), vad_low) != AP_OK)
        return 6;
    if (ap_module_vad_init(vad_low_base_up_mem, sizeof(vad_low_base_up_mem), vad_low_base_up) != AP_OK)
        return 7;
    if (ap_module_vad_init(vad_base_low_up_mem, sizeof(vad_base_low_up_mem), vad_base_low_up) != AP_OK)
        return 8;
    return 0;
}

int main(int argc, char **argv) {
    ap_ns_module_t *ns_base = NULL, *ns_low = NULL;
    ap_agc_module_t *agc_base = NULL, *agc_low = NULL;
    ap_vad_module_t *vad_base = NULL, *vad_low = NULL;
    ap_vad_module_t *vad_low_base_up = NULL, *vad_base_low_up = NULL;
    uint32_t seed;
    uint32_t scenario, frame;
    uint32_t total_frames = 0u;
    uint32_t upstream_mismatch_frames = 0u;
    uint32_t waveform_changed_frames = 0u;
    uint32_t vad_probability_diff_frames = 0u;
    uint32_t vad_active_diff_frames = 0u;
    uint32_t noise_active_base = 0u, noise_active_low = 0u;
    uint32_t speech_active_base = 0u, speech_active_low = 0u;
    uint32_t noise_frames = 0u, speech_frames = 0u;
    uint32_t low_cross_mismatch_frames = 0u;
    uint32_t base_cross_mismatch_frames = 0u;
    float max_upstream_delta = 0.0f;
    float max_post_agc_rms_delta = 0.0f;
    float max_vad_probability_delta = 0.0f;
    float input[FRAME], out_base[FRAME], out_low[FRAME];

    if (argc != 2) {
        fprintf(stderr, "usage: %s <seed>\n", argv[0]);
        return 2;
    }
    seed = (uint32_t)strtoul(argv[1], NULL, 10);
    if (seed == 0u) return 2;
    rng_state = seed ^ 0x9e3779b9u;

    {
        const int rc = init_modules(&ns_base, &ns_low, &agc_base, &agc_low,
                                    &vad_base, &vad_low,
                                    &vad_low_base_up, &vad_base_low_up);
        if (rc != 0) {
            fprintf(stderr, "module init failed: %d\n", rc);
            return 3;
        }
    }

    for (scenario = 0u; scenario < SCENARIOS; ++scenario) {
        ap_module_ns_reset(ns_base);
        ap_module_ns_reset(ns_low);
        ap_module_agc_reset(agc_base);
        ap_module_agc_reset(agc_low);
        ap_module_vad_reset(vad_base);
        ap_module_vad_reset(vad_low);
        ap_module_vad_reset(vad_low_base_up);
        ap_module_vad_reset(vad_base_low_up);

        for (frame = 0u; frame < FRAMES_PER_SCENARIO; ++frame) {
            ap_module_ns_result_t nsr_base, nsr_low;
            ap_module_vad_result_t vb, vl, vlbu, vblu;
            float upstream_delta;
            float rms_delta;
            float vad_delta;
            const int labeled_speech = speech_active(scenario, frame);

            make_frame(seed, scenario, frame, input);
            if (ap_module_ns_process(ns_base, AP_QUALITY_FULL, input, NULL,
                                     out_base, FRAME, 0, 0, 0, &nsr_base) != AP_OK)
                return 4;
            if (ap_module_ns_process(ns_low, AP_QUALITY_FULL, input, NULL,
                                     out_low, FRAME, 0, 0, 0, &nsr_low) != AP_OK)
                return 5;
            if (ap_module_agc_process(agc_base, out_base, FRAME) != AP_OK)
                return 6;
            if (ap_module_agc_process(agc_low, out_low, FRAME) != AP_OK)
                return 7;

            upstream_delta = fabsf(nsr_base.speech_probability - nsr_low.speech_probability);
            if (upstream_delta > max_upstream_delta) max_upstream_delta = upstream_delta;
            if (upstream_delta > PROB_EPS) upstream_mismatch_frames++;

            rms_delta = fabsf(frame_rms(out_base) - frame_rms(out_low));
            if (rms_delta > max_post_agc_rms_delta) max_post_agc_rms_delta = rms_delta;
            if (rms_delta > WAVE_EPS) waveform_changed_frames++;

            if (ap_module_vad_process(vad_base, out_base, FRAME,
                                      nsr_base.speech_probability, 1, &vb) != AP_OK)
                return 8;
            if (ap_module_vad_process(vad_low, out_low, FRAME,
                                      nsr_low.speech_probability, 1, &vl) != AP_OK)
                return 9;
            if (ap_module_vad_process(vad_low_base_up, out_low, FRAME,
                                      nsr_base.speech_probability, 1, &vlbu) != AP_OK)
                return 10;
            if (ap_module_vad_process(vad_base_low_up, out_base, FRAME,
                                      nsr_low.speech_probability, 1, &vblu) != AP_OK)
                return 11;

            vad_delta = fabsf(vb.probability - vl.probability);
            if (vad_delta > max_vad_probability_delta) max_vad_probability_delta = vad_delta;
            if (vad_delta > PROB_EPS) vad_probability_diff_frames++;
            if (vb.active != vl.active) vad_active_diff_frames++;

            if (fabsf(vl.probability - vlbu.probability) > PROB_EPS ||
                vl.active != vlbu.active)
                low_cross_mismatch_frames++;
            if (fabsf(vb.probability - vblu.probability) > PROB_EPS ||
                vb.active != vblu.active)
                base_cross_mismatch_frames++;

            if (labeled_speech) {
                speech_frames++;
                speech_active_base += vb.active ? 1u : 0u;
                speech_active_low += vl.active ? 1u : 0u;
            } else {
                noise_frames++;
                noise_active_base += vb.active ? 1u : 0u;
                noise_active_low += vl.active ? 1u : 0u;
            }
            total_frames++;
        }
    }

    printf(
        "{\"schema_version\":1,\"seed\":%u,\"total_frames\":%u,"
        "\"noise_frames\":%u,\"speech_frames\":%u,"
        "\"max_upstream_probability_delta\":%.9g,"
        "\"upstream_mismatch_frames\":%u,"
        "\"max_post_agc_rms_delta\":%.9g,"
        "\"waveform_changed_frames\":%u,"
        "\"max_vad_probability_delta\":%.9g,"
        "\"vad_probability_diff_frames\":%u,"
        "\"vad_active_diff_frames\":%u,"
        "\"low_cross_mismatch_frames\":%u,"
        "\"base_cross_mismatch_frames\":%u,"
        "\"noise_active_base\":%u,\"noise_active_low\":%u,"
        "\"speech_active_base\":%u,\"speech_active_low\":%u}\n",
        seed, total_frames, noise_frames, speech_frames,
        (double)max_upstream_delta, upstream_mismatch_frames,
        (double)max_post_agc_rms_delta, waveform_changed_frames,
        (double)max_vad_probability_delta, vad_probability_diff_frames,
        vad_active_diff_frames, low_cross_mismatch_frames,
        base_cross_mismatch_frames, noise_active_base, noise_active_low,
        speech_active_base, speech_active_low);
    return 0;
}
