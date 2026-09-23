#include "enhance/ap_enhance.h"
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
        const uint32_t band_lo = nfft / 64u;
        const uint32_t band_hi = nfft * 7u / 16u;
        double power_sum = 1.0e-18;
        double base_noise_sum = 1.0e-18;
        double stress_noise_sum = 1.0e-18;
        uint32_t band_bins = 0u;
        uint32_t i;
        uint32_t k;
        float base_snr_db;
        float stress_snr_db;

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

        for (k = band_lo + 1u; k < band_hi; ++k) {
            const double re = analysis_spectrum[k].re;
            const double im = analysis_spectrum[k].im;
            const double power = re * re + im * im + 1.0e-12;
            const double nb = base_state.noise_tracker.estimate[k] + 1.0e-12;
            const double ns = stress_state.noise_tracker.estimate[k] + 1.0e-12;
            power_sum += power;
            base_noise_sum += nb;
            stress_noise_sum += ns;
            band_bins++;
        }
        if (band_bins == 0u) {
            fclose(input_file);
            return 6;
        }

        base_snr_db = 10.0f * log10f((float)(power_sum / base_noise_sum));
        stress_snr_db = 10.0f * log10f((float)(power_sum / stress_noise_sum));

        printf(
            "{\"frame\":%u,\"spectral_base_snr_db\":%.9g,"
            "\"spectral_stress_snr_db\":%.9g,"
            "\"base_speech_probability\":%.9g,"
            "\"stress_speech_probability\":%.9g,"
            "\"band_bins\":%u,\"band_lo_exclusive\":%u,"
            "\"band_hi_exclusive\":%u,\"nfft\":%u}\n",
            frame_index,
            (double)base_snr_db,
            (double)stress_snr_db,
            (double)rb.speech_probability,
            (double)rs.speech_probability,
            band_bins,
            band_lo,
            band_hi,
            nfft);

        memcpy(analysis_previous, input, sizeof(float) * FRAME);
        frame_index++;
    }

    fclose(input_file);
    if (frame_index == 0u) return 7;
    return 0;
}
