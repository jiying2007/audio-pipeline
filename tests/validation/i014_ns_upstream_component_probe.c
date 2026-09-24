#include "enhance/ap_enhance.h"
#include "enhance/ap_noise_tracker.h"
#include "enhance/ap_window.h"
#include "dsp/ap_dsp.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define FRAME 160u
#define BASE_FLOOR 0.12f
#define STRESS_FLOOR 0.05f

static ap_ns_state_t base_state;
static ap_ns_state_t stress_state;
static ap_noise_tracker_state_t mirror_tracker;
static ap_complex_t analysis_spectrum[AP_NS_FFT_MAX];
static float analysis_previous[AP_INTERNAL_FRAME_MAX];

static void build_analysis_spectrum(const float *input,
                                    uint32_t nfft,
                                    ap_complex_t *spectrum) {
    const float *window = ap_window_half(FRAME);
    uint32_t i;
    if (!window) return;
    for (i = 0u; i < FRAME; ++i) {
        const float w0 = window[i];
        const float w1 = window[FRAME - 1u - i];
        spectrum[i].re = analysis_previous[i] * w0;
        spectrum[i].im = 0.0f;
        spectrum[FRAME + i].re = input[i] * w1;
        spectrum[FRAME + i].im = 0.0f;
    }
    memset(spectrum + 2u * FRAME, 0,
           (nfft - 2u * FRAME) * sizeof(spectrum[0]));
    ap_fft(spectrum, nfft, 0);
}

static void mirror_components(uint32_t nfft,
                              float *mean,
                              float *concentration,
                              float *gap,
                              uint32_t *speech_bins_out) {
    const uint32_t bins = nfft / 2u + 1u;
    float speech_sum = 0.0f;
    float speech_sq_sum = 0.0f;
    uint32_t speech_bins = 0u;
    uint32_t k;

    for (k = 0u; k < bins; ++k) {
        const float re = analysis_spectrum[k].re;
        const float im = analysis_spectrum[k].im;
        const float power = re * re + im * im + 1.0e-12f;
        ap_noise_tracker_result_t noise_result;
        ap_noise_tracker_update(&mirror_tracker, k, power, &noise_result);
        if (k > nfft / 64u && k < nfft * 7u / 16u) {
            const float speech = noise_result.speech_probability;
            speech_sum += speech;
            speech_sq_sum += speech * speech;
            speech_bins++;
        }
    }
    ap_noise_tracker_next_frame(&mirror_tracker);

    *mean = speech_bins ? speech_sum / (float)speech_bins : 0.0f;
    *concentration = speech_sum > 1.0e-9f ?
                     speech_sq_sum / speech_sum : 0.0f;
    *gap = ap_clampf(*concentration - *mean, 0.0f, 1.0f);
    *speech_bins_out = speech_bins;
}

int main(int argc, char **argv) {
    FILE *input_file;
    int16_t raw[FRAME];
    float input[FRAME];
    float out_base[FRAME];
    float out_stress[FRAME];
    uint32_t frame_index = 0u;

    if (argc != 2) {
        fprintf(stderr, "usage: %s <raw-s16-mono-pcm>\n", argv[0]);
        return 2;
    }

    ap_ns_init(&base_state, FRAME);
    ap_ns_init(&stress_state, FRAME);
    ap_noise_tracker_init(&mirror_tracker);
    if (base_state.nfft != 512u || stress_state.nfft != 512u) return 3;
    memset(analysis_previous, 0, sizeof(analysis_previous));

    input_file = fopen(argv[1], "rb");
    if (!input_file) {
        perror("fopen");
        return 4;
    }

    for (;;) {
        const size_t got = fread(raw, sizeof(raw[0]), FRAME, input_file);
        ap_ns_result_t rb;
        ap_ns_result_t rs;
        const uint32_t nfft = base_state.nfft;
        float mean;
        float concentration;
        float gap;
        uint32_t speech_bins;
        uint32_t i;

        if (got == 0u) break;
        if (got != FRAME) {
            fprintf(stderr, "partial input frame: %zu\n", got);
            fclose(input_file);
            return 5;
        }

        for (i = 0u; i < FRAME; ++i)
            input[i] = (float)raw[i] / 32768.0f;

        build_analysis_spectrum(input, nfft, analysis_spectrum);

        ap_ns_process(&base_state, AP_ENHANCE_FULL, BASE_FLOOR,
                      input, NULL, out_base, FRAME, 0, 0, 0, &rb);
        ap_ns_process(&stress_state, AP_ENHANCE_FULL, STRESS_FLOOR,
                      input, NULL, out_stress, FRAME, 0, 0, 0, &rs);

        mirror_components(
            nfft, &mean, &concentration, &gap, &speech_bins);
        if (speech_bins != 215u) {
            fclose(input_file);
            return 6;
        }

        printf(
            "{\"frame\":%u,"
            "\"mean\":%.9g,"
            "\"mean_suppression_score\":%.9g,"
            "\"concentration\":%.9g,"
            "\"mirror_gap\":%.9g,"
            "\"base_speech_probability\":%.9g,"
            "\"stress_speech_probability\":%.9g,"
            "\"speech_bins\":%u,\"nfft\":%u}\n",
            frame_index,
            (double)mean,
            (double)(1.0f - mean),
            (double)concentration,
            (double)gap,
            (double)rb.speech_probability,
            (double)rs.speech_probability,
            speech_bins,
            nfft);

        memcpy(analysis_previous, input, sizeof(float) * FRAME);
        frame_index++;
    }

    fclose(input_file);
    if (frame_index == 0u) return 7;
    return 0;
}
