/* I036 candidate-zero NS noise-estimate aggregation-domain decomposition probe. */
#include "audio_pipeline/audio_modules.h"
#include "enhance/ap_enhance.h"
#include "enhance/ap_noise_tracker.h"
#include "enhance/ap_window.h"
#include "dsp/ap_dsp.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define FRAME 160u
#define NS_FLOOR 0.12f
#define VAD_NOISE_LIKE_CREST_DB 8.0f
#define VAD_TRANSIENT_CREST_DB 12.0f
#define VAD_FAST_NOISE_ALPHA 0.08f
#define VAD_UPSTREAM_SPEECH_GUARD 0.55f
#define VAD_LOCAL_SPEECH_GUARD 0.15f
#define VAD_UPSTREAM_BLEND 0.40f
#define VAD_NS_DECISION_THRESHOLD 0.35f
#define VAD_STRONG_REFRESH_THRESHOLD 0.50f
#define VAD_STRONG_HOLD_FRAMES 8u
#define VAD_WEAK_HOLD_FRAMES 6u
#define TRACKER_SLOW_UPDATE_SPEECH_THRESHOLD 0.35f

enum refresh_kind {
    REFRESH_NONE = 0,
    REFRESH_WEAK = 1,
    REFRESH_STRONG = 2,
};

typedef struct vad_state {
    float noise_rms;
    uint32_t hangover;
} vad_state_t;

typedef struct vad_diagnostic_result {
    float probability;
    float rms;
    float ratio_db;
    uint32_t pre_hangover;
    uint8_t active;
    uint8_t local_guard_pass;
    uint8_t refresh_kind;
} vad_diagnostic_result_t;

typedef struct upstream_components {
    float gap;
    float all_noise_rms_dbfs;
    float low_mean_noise_dbfs;
    float speech_mean_noise_dbfs;
    float high_mean_noise_dbfs;
    float low_noise_energy_share;
    float speech_noise_energy_share;
    float high_noise_energy_share;
    float low_update_abs_contribution_fraction;
    float speech_update_abs_contribution_fraction;
    float high_update_abs_contribution_fraction;
    float low_signed_update_fraction_of_previous_noise;
    float speech_signed_update_fraction_of_previous_noise;
    float high_signed_update_fraction_of_previous_noise;
    float all_abs_update_fraction_of_previous_noise;
    uint32_t low_bins;
    uint32_t speech_bins;
    uint32_t high_bins;
} upstream_components_t;

static ap_ns_state_t ns_state;
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char public_shipping_mem[AP_MODULE_STATE_MAX_BYTES];
static ap_vad_module_t *public_shipping_module;
static vad_state_t diagnostic_vad_state;

static ap_noise_tracker_state_t mirror_tracker;
static ap_complex_t analysis_spectrum[AP_NS_FFT_MAX];
static float analysis_previous[AP_INTERNAL_FRAME_MAX];

static float clampf_local(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static float frame_rms_dbfs(const float *x, uint32_t n) {
    float e = 1.0e-18f;
    uint32_t i;
    for (i = 0u; i < n; ++i)
        e += x[i] * x[i];
    return 20.0f * log10f(sqrtf(e / (float)n) + 1.0e-12f);
}

static void diagnostic_vad_init(vad_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->noise_rms = 1.0e-3f;
}

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

static void mirror_upstream_components(uint32_t nfft,
                                       upstream_components_t *result) {
    const uint32_t bins = nfft / 2u + 1u;
    const uint32_t low_last = nfft / 64u;
    const uint32_t high_first = nfft * 7u / 16u;
    float speech_sum = 0.0f;
    float speech_sq_sum = 0.0f;
    float low_noise_sum = 0.0f;
    float speech_noise_sum = 0.0f;
    float high_noise_sum = 0.0f;
    float low_previous_sum = 0.0f;
    float speech_previous_sum = 0.0f;
    float high_previous_sum = 0.0f;
    float low_abs_update_sum = 0.0f;
    float speech_abs_update_sum = 0.0f;
    float high_abs_update_sum = 0.0f;
    float low_signed_update_sum = 0.0f;
    float speech_signed_update_sum = 0.0f;
    float high_signed_update_sum = 0.0f;
    uint32_t k;

    memset(result, 0, sizeof(*result));

    for (k = 0u; k < bins; ++k) {
        const float re = analysis_spectrum[k].re;
        const float im = analysis_spectrum[k].im;
        const float power = re * re + im * im + 1.0e-12f;
        const float previous_noise = mirror_tracker.estimate[k];
        ap_noise_tracker_result_t noise_result;
        float update_delta;
        float update_abs;

        ap_noise_tracker_update(&mirror_tracker, k, power, &noise_result);
        update_delta = noise_result.noise - previous_noise;
        update_abs = fabsf(update_delta);

        if (k <= low_last) {
            result->low_bins++;
            low_noise_sum += noise_result.noise;
            low_previous_sum += fmaxf(previous_noise, 0.0f);
            low_abs_update_sum += update_abs;
            low_signed_update_sum += update_delta;
        } else if (k < high_first) {
            const float speech = noise_result.speech_probability;
            result->speech_bins++;
            speech_sum += speech;
            speech_sq_sum += speech * speech;
            speech_noise_sum += noise_result.noise;
            speech_previous_sum += fmaxf(previous_noise, 0.0f);
            speech_abs_update_sum += update_abs;
            speech_signed_update_sum += update_delta;
        } else {
            result->high_bins++;
            high_noise_sum += noise_result.noise;
            high_previous_sum += fmaxf(previous_noise, 0.0f);
            high_abs_update_sum += update_abs;
            high_signed_update_sum += update_delta;
        }
    }
    ap_noise_tracker_next_frame(&mirror_tracker);

    {
        const float mean = result->speech_bins ?
                           speech_sum / (float)result->speech_bins : 0.0f;
        const float concentration = speech_sum > 1.0e-9f ?
                                    speech_sq_sum / speech_sum : 0.0f;
        const float estimate_sum =
            low_noise_sum + speech_noise_sum + high_noise_sum;
        const float all_noise_sum = 1.0e-18f + estimate_sum;
        const float update_abs_sum =
            low_abs_update_sum + speech_abs_update_sum + high_abs_update_sum;
        const float previous_sum =
            low_previous_sum + speech_previous_sum + high_previous_sum;
        const float nfft_sq = (float)nfft * (float)nfft;

        result->gap = clampf_local(concentration - mean, 0.0f, 1.0f);
        result->all_noise_rms_dbfs = 10.0f * log10f(
            all_noise_sum / (float)bins / nfft_sq + 1.0e-18f);
        result->low_mean_noise_dbfs = 10.0f * log10f(
            low_noise_sum / (float)result->low_bins / nfft_sq + 1.0e-18f);
        result->speech_mean_noise_dbfs = 10.0f * log10f(
            speech_noise_sum / (float)result->speech_bins / nfft_sq + 1.0e-18f);
        result->high_mean_noise_dbfs = 10.0f * log10f(
            high_noise_sum / (float)result->high_bins / nfft_sq + 1.0e-18f);

        if (estimate_sum > 1.0e-20f) {
            result->low_noise_energy_share = low_noise_sum / estimate_sum;
            result->speech_noise_energy_share = speech_noise_sum / estimate_sum;
            result->high_noise_energy_share = high_noise_sum / estimate_sum;
        }
        if (update_abs_sum > 1.0e-20f) {
            result->low_update_abs_contribution_fraction =
                low_abs_update_sum / update_abs_sum;
            result->speech_update_abs_contribution_fraction =
                speech_abs_update_sum / update_abs_sum;
            result->high_update_abs_contribution_fraction =
                high_abs_update_sum / update_abs_sum;
        }
        if (low_previous_sum > 1.0e-20f)
            result->low_signed_update_fraction_of_previous_noise =
                low_signed_update_sum / low_previous_sum;
        if (speech_previous_sum > 1.0e-20f)
            result->speech_signed_update_fraction_of_previous_noise =
                speech_signed_update_sum / speech_previous_sum;
        if (high_previous_sum > 1.0e-20f)
            result->high_signed_update_fraction_of_previous_noise =
                high_signed_update_sum / high_previous_sum;
        if (previous_sum > 1.0e-20f)
            result->all_abs_update_fraction_of_previous_noise =
                update_abs_sum / previous_sum;
    }
}

static void process_vad_diagnostic(vad_state_t *state,
                                   const float *x,
                                   uint32_t n,
                                   float upstream_probability,
                                   vad_diagnostic_result_t *result) {
    float e = 1.0e-12f;
    float peak = 0.0f;
    float prob;
    uint32_t i;
    int upstream_speech;

    memset(result, 0, sizeof(*result));
    result->pre_hangover = state->hangover;

    for (i = 0u; i < n; ++i) {
        const float magnitude = fabsf(x[i]);
        e += x[i] * x[i];
        if (magnitude > peak) peak = magnitude;
    }

    result->rms = sqrtf(e / (float)n);
    if (state->noise_rms <= 0.0f)
        state->noise_rms = result->rms + 1.0e-6f;

    result->ratio_db = 20.0f * log10f(
        (result->rms + 1.0e-7f) / (state->noise_rms + 1.0e-7f));
    {
        const float crest_db = 20.0f * log10f(
            (peak + 1.0e-7f) / (result->rms + 1.0e-7f));
        prob = clampf_local((result->ratio_db - 2.0f) / 12.0f, 0.0f, 1.0f);
        result->local_guard_pass =
            (uint8_t)(prob > VAD_LOCAL_SPEECH_GUARD);
        upstream_speech =
            (upstream_probability > VAD_UPSTREAM_SPEECH_GUARD) &&
            result->local_guard_pass;

        if (!upstream_speech &&
            crest_db > VAD_TRANSIENT_CREST_DB &&
            prob > 0.30f)
            prob = 0.30f;

        if (upstream_probability > prob) {
            prob += VAD_UPSTREAM_BLEND * (upstream_probability - prob);
            prob = clampf_local(prob, 0.0f, 1.0f);
        }

        if (prob < VAD_NS_DECISION_THRESHOLD) {
            state->noise_rms =
                0.98f * state->noise_rms + 0.02f * result->rms;
        } else if (!upstream_speech &&
                   crest_db >= VAD_NOISE_LIKE_CREST_DB &&
                   crest_db <= VAD_TRANSIENT_CREST_DB) {
            state->noise_rms =
                (1.0f - VAD_FAST_NOISE_ALPHA) * state->noise_rms +
                VAD_FAST_NOISE_ALPHA * result->rms;
        }
    }

    if (prob >= VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = VAD_STRONG_HOLD_FRAMES;
        result->refresh_kind = REFRESH_STRONG;
    } else if (prob > VAD_NS_DECISION_THRESHOLD) {
        if (state->hangover < VAD_WEAK_HOLD_FRAMES)
            state->hangover = VAD_WEAK_HOLD_FRAMES;
        result->refresh_kind = REFRESH_WEAK;
    } else if (state->hangover) {
        state->hangover--;
    }

    result->probability = prob;
    result->active = (uint8_t)(state->hangover > 0u);
}

int main(int argc, char **argv) {
    FILE *input_file;
    int16_t raw[FRAME];
    float input[FRAME];
    float ns_output[FRAME];
    uint32_t frame_index = 0u;

    if (argc != 2) {
        fprintf(stderr, "usage: %s <raw-s16-mono-pcm>\n", argv[0]);
        return 2;
    }

    ap_ns_init(&ns_state, FRAME);
    ap_noise_tracker_init(&mirror_tracker);
    if (ns_state.nfft != 512u) return 3;

    if (ap_module_vad_init(public_shipping_mem, sizeof(public_shipping_mem),
                           &public_shipping_module) != AP_OK)
        return 4;

    diagnostic_vad_init(&diagnostic_vad_state);
    memset(analysis_previous, 0, sizeof(analysis_previous));

    input_file = fopen(argv[1], "rb");
    if (!input_file) return 5;

    for (;;) {
        const size_t got = fread(raw, sizeof(raw[0]), FRAME, input_file);
        ap_ns_result_t ns_result;
        ap_module_vad_result_t public_shipping;
        vad_diagnostic_result_t vad_diagnostic;
        upstream_components_t upstream;
        uint32_t i;

        if (got == 0u) break;
        if (got != FRAME) break;

        for (i = 0u; i < FRAME; ++i)
            input[i] = (float)raw[i] / 32768.0f;

        build_analysis_spectrum(input, ns_state.nfft, analysis_spectrum);

        ap_ns_process(&ns_state, AP_ENHANCE_FULL, NS_FLOOR,
                      input, NULL, ns_output, FRAME, 0, 0, 0, &ns_result);

        mirror_upstream_components(ns_state.nfft, &upstream);
        if (upstream.speech_bins != 215u) {
            fclose(input_file);
            return 6;
        }

        if (ap_module_vad_process(public_shipping_module, ns_output, FRAME,
                                  ns_result.speech_probability, 1,
                                  &public_shipping) != AP_OK) {
            fclose(input_file);
            return 7;
        }

        process_vad_diagnostic(
            &diagnostic_vad_state, ns_output, FRAME,
            ns_result.speech_probability, &vad_diagnostic);

        {
            const float post_ns_rms_dbfs = frame_rms_dbfs(ns_output, FRAME);

        printf(
            "{\"frame\":%u,"
            "\"upstream_probability\":%.9g,"
            "\"mirror_gap\":%.9g,"
            "\"all_noise_rms_dbfs\":%.9g,"
            "\"noise_rms_reconstruction_gap\":%.9g,"
            "\"low_mean_noise_dbfs\":%.9g,"
            "\"speech_mean_noise_dbfs\":%.9g,"
            "\"high_mean_noise_dbfs\":%.9g,"
            "\"low_noise_energy_share\":%.9g,"
            "\"speech_noise_energy_share\":%.9g,"
            "\"high_noise_energy_share\":%.9g,"
            "\"low_update_abs_contribution_fraction\":%.9g,"
            "\"speech_update_abs_contribution_fraction\":%.9g,"
            "\"high_update_abs_contribution_fraction\":%.9g,"
            "\"low_signed_update_fraction_of_previous_noise\":%.9g,"
            "\"speech_signed_update_fraction_of_previous_noise\":%.9g,"
            "\"high_signed_update_fraction_of_previous_noise\":%.9g,"
            "\"all_abs_update_fraction_of_previous_noise\":%.9g,"
            "\"low_bins\":%u,"
            "\"speech_bins\":%u,"
            "\"high_bins\":%u,"
            "\"ns_noise_rms_dbfs\":%.9g,"
            "\"post_ns_rms_dbfs\":%.9g,"
            "\"local_ratio_db\":%.9g,"
            "\"local_guard_pass\":%u,"
            "\"public_shipping_probability\":%.9g,"
            "\"public_shipping_active\":%u,"
            "\"shipping_probability\":%.9g,"
            "\"shipping_active\":%u,"
            "\"refresh_kind\":%u,"
            "\"pre_hangover\":%u}\n",
            frame_index,
            (double)ns_result.speech_probability,
            (double)upstream.gap,
            (double)upstream.all_noise_rms_dbfs,
            (double)(upstream.all_noise_rms_dbfs - ns_result.noise_rms_dbfs),
            (double)upstream.low_mean_noise_dbfs,
            (double)upstream.speech_mean_noise_dbfs,
            (double)upstream.high_mean_noise_dbfs,
            (double)upstream.low_noise_energy_share,
            (double)upstream.speech_noise_energy_share,
            (double)upstream.high_noise_energy_share,
            (double)upstream.low_update_abs_contribution_fraction,
            (double)upstream.speech_update_abs_contribution_fraction,
            (double)upstream.high_update_abs_contribution_fraction,
            (double)upstream.low_signed_update_fraction_of_previous_noise,
            (double)upstream.speech_signed_update_fraction_of_previous_noise,
            (double)upstream.high_signed_update_fraction_of_previous_noise,
            (double)upstream.all_abs_update_fraction_of_previous_noise,
            upstream.low_bins,
            upstream.speech_bins,
            upstream.high_bins,
            (double)ns_result.noise_rms_dbfs,
            (double)post_ns_rms_dbfs,
            (double)vad_diagnostic.ratio_db,
            (unsigned)vad_diagnostic.local_guard_pass,
            (double)public_shipping.probability,
            (unsigned)public_shipping.active,
            (double)vad_diagnostic.probability,
            (unsigned)vad_diagnostic.active,
            (unsigned)vad_diagnostic.refresh_kind,
            vad_diagnostic.pre_hangover);
        }

        memcpy(analysis_previous, input, sizeof(float) * FRAME);
        frame_index++;
    }

    fclose(input_file);
    return frame_index ? 0 : 8;
}
