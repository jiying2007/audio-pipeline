/* I025 candidate-zero NS upstream disagreement-noise source decomposition. */
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
    float mean;
    float mean_suppression;
    float concentration;
    float gap;
    float posterior_max;
    float posterior_variance;
    float positive_bin_fraction;
    float slow_update_bin_fraction;
    float mean_post_ratio;
    float max_post_ratio;
    uint32_t speech_bins;
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
    float speech_sum = 0.0f;
    float speech_sq_sum = 0.0f;
    float post_sum = 0.0f;
    float post_max = 0.0f;
    float posterior_max = 0.0f;
    uint32_t speech_bins = 0u;
    uint32_t positive_bins = 0u;
    uint32_t slow_bins = 0u;
    uint32_t k;

    memset(result, 0, sizeof(*result));

    for (k = 0u; k < bins; ++k) {
        const float re = analysis_spectrum[k].re;
        const float im = analysis_spectrum[k].im;
        const float power = re * re + im * im + 1.0e-12f;
        const float previous_noise = mirror_tracker.estimate[k];
        ap_noise_tracker_result_t noise_result;
        float post_ratio = 1.0f;

        if (mirror_tracker.frame >= 20u && previous_noise > 0.0f)
            post_ratio = power / (previous_noise + 1.0e-12f);

        ap_noise_tracker_update(&mirror_tracker, k, power, &noise_result);

        if (k > nfft / 64u && k < nfft * 7u / 16u) {
            const float speech = noise_result.speech_probability;
            speech_sum += speech;
            speech_sq_sum += speech * speech;
            if (speech > posterior_max) posterior_max = speech;
            if (speech > 0.0f) positive_bins++;
            if (speech > TRACKER_SLOW_UPDATE_SPEECH_THRESHOLD) slow_bins++;
            post_sum += post_ratio;
            if (post_ratio > post_max) post_max = post_ratio;
            speech_bins++;
        }
    }
    ap_noise_tracker_next_frame(&mirror_tracker);

    result->speech_bins = speech_bins;
    result->mean = speech_bins ? speech_sum / (float)speech_bins : 0.0f;
    result->mean_suppression = 1.0f - result->mean;
    result->concentration = speech_sum > 1.0e-9f ?
                            speech_sq_sum / speech_sum : 0.0f;
    result->gap = clampf_local(
        result->concentration - result->mean, 0.0f, 1.0f);
    result->posterior_max = posterior_max;
    if (speech_bins) {
        const float sq_mean = speech_sq_sum / (float)speech_bins;
        result->posterior_variance =
            fmaxf(0.0f, sq_mean - result->mean * result->mean);
        result->positive_bin_fraction =
            (float)positive_bins / (float)speech_bins;
        result->slow_update_bin_fraction =
            (float)slow_bins / (float)speech_bins;
        result->mean_post_ratio = post_sum / (float)speech_bins;
        result->max_post_ratio = post_max;
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

        printf(
            "{\"frame\":%u,"
            "\"upstream_probability\":%.9g,"
            "\"mirror_mean\":%.9g,"
            "\"mirror_mean_suppression\":%.9g,"
            "\"mirror_concentration\":%.9g,"
            "\"mirror_gap\":%.9g,"
            "\"posterior_max\":%.9g,"
            "\"posterior_variance\":%.9g,"
            "\"positive_bin_fraction\":%.9g,"
            "\"slow_update_bin_fraction\":%.9g,"
            "\"mean_post_ratio\":%.9g,"
            "\"max_post_ratio\":%.9g,"
            "\"ns_noise_rms_dbfs\":%.9g,"
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
            (double)upstream.mean,
            (double)upstream.mean_suppression,
            (double)upstream.concentration,
            (double)upstream.gap,
            (double)upstream.posterior_max,
            (double)upstream.posterior_variance,
            (double)upstream.positive_bin_fraction,
            (double)upstream.slow_update_bin_fraction,
            (double)upstream.mean_post_ratio,
            (double)upstream.max_post_ratio,
            (double)ns_result.noise_rms_dbfs,
            (double)vad_diagnostic.ratio_db,
            (unsigned)vad_diagnostic.local_guard_pass,
            (double)public_shipping.probability,
            (unsigned)public_shipping.active,
            (double)vad_diagnostic.probability,
            (unsigned)vad_diagnostic.active,
            (unsigned)vad_diagnostic.refresh_kind,
            vad_diagnostic.pre_hangover);

        memcpy(analysis_previous, input, sizeof(float) * FRAME);
        frame_index++;
    }

    fclose(input_file);
    return frame_index ? 0 : 8;
}
