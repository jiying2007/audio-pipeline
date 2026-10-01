/* I040 candidate-zero NS synthesis/overlap-add transfer decomposition probe. */
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
    uint32_t all_noise_rms_bits;
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

typedef struct post_ns_components {
    float all_mean_power_dbfs;
    float low_mean_power_dbfs;
    float speech_mean_power_dbfs;
    float high_mean_power_dbfs;
    float low_energy_share;
    float speech_energy_share;
    float high_energy_share;
    uint32_t low_bins;
    uint32_t speech_bins;
    uint32_t high_bins;
} post_ns_components_t;

enum suppression_transfer_domain {
    TRANSFER_ALL = 0,
    TRANSFER_LOW = 1,
    TRANSFER_SPEECH = 2,
    TRANSFER_HIGH = 3,
    TRANSFER_DOMAIN_COUNT = 4,
};

typedef struct suppression_transfer_components {
    float pre_ns_mean_power_dbfs[TRANSFER_DOMAIN_COUNT];
    float predicted_suppressed_mean_power_dbfs[TRANSFER_DOMAIN_COUNT];
    float suppression_attenuation_db[TRANSFER_DOMAIN_COUNT];
    float mean_gain[TRANSFER_DOMAIN_COUNT];
    float floor_gain_fraction[TRANSFER_DOMAIN_COUNT];
    uint32_t bins[TRANSFER_DOMAIN_COUNT];
} suppression_transfer_components_t;

static ap_ns_state_t ns_state;
_Alignas(AP_MODULE_STATE_ALIGNMENT)
static unsigned char public_shipping_mem[AP_MODULE_STATE_MAX_BYTES];
static ap_vad_module_t *public_shipping_module;
static vad_state_t diagnostic_vad_state;

static ap_noise_tracker_state_t mirror_tracker;
static ap_complex_t analysis_spectrum[AP_NS_FFT_MAX];
static float analysis_previous[AP_INTERNAL_FRAME_MAX];
static ap_complex_t post_ns_spectrum[AP_NS_FFT_MAX];
static float post_ns_previous[AP_INTERNAL_FRAME_MAX];
static ap_complex_t synthesis_spectrum[AP_NS_FFT_MAX];
static float synthesis_overlap[AP_INTERNAL_FRAME_MAX];
static float predicted_ns_output[AP_INTERNAL_FRAME_MAX];
static ap_complex_t predicted_post_ns_spectrum[AP_NS_FFT_MAX];
static float predicted_post_ns_previous[AP_INTERNAL_FRAME_MAX];

static float clampf_local(float x, float lo, float hi) {
    return x < lo ? lo : (x > hi ? hi : x);
}

static uint32_t float_bits(float value) {
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
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
                                    float *previous,
                                    uint32_t nfft,
                                    ap_complex_t *spectrum) {
    const float *window = ap_window_half(FRAME);
    uint32_t i;
    if (!window) return;
    for (i = 0u; i < FRAME; ++i) {
        const float w0 = window[i];
        const float w1 = window[FRAME - 1u - i];
        spectrum[i].re = previous[i] * w0;
        spectrum[i].im = 0.0f;
        spectrum[FRAME + i].re = input[i] * w1;
        spectrum[FRAME + i].im = 0.0f;
    }
    memset(spectrum + 2u * FRAME, 0,
           (nfft - 2u * FRAME) * sizeof(spectrum[0]));
    ap_fft(spectrum, nfft, 0);
}

static void measure_spectral_components(const ap_complex_t *spectrum,
                                        uint32_t nfft,
                                        post_ns_components_t *result) {
    const uint32_t bins = nfft / 2u + 1u;
    const uint32_t low_last = nfft / 64u;
    const uint32_t high_first = nfft * 7u / 16u;
    const float nfft_sq = (float)nfft * (float)nfft;
    float low_sum = 0.0f;
    float speech_sum = 0.0f;
    float high_sum = 0.0f;
    float all_sum = 1.0e-18f;
    uint32_t k;

    memset(result, 0, sizeof(*result));
    for (k = 0u; k < bins; ++k) {
        const float re = spectrum[k].re;
        const float im = spectrum[k].im;
        const float power = re * re + im * im + 1.0e-12f;
        all_sum += power;
        if (k <= low_last) {
            result->low_bins++;
            low_sum += power;
        } else if (k < high_first) {
            result->speech_bins++;
            speech_sum += power;
        } else {
            result->high_bins++;
            high_sum += power;
        }
    }

    result->all_mean_power_dbfs = 10.0f * log10f(
        all_sum / (float)bins / nfft_sq + 1.0e-18f);
    result->low_mean_power_dbfs = 10.0f * log10f(
        low_sum / (float)result->low_bins / nfft_sq + 1.0e-18f);
    result->speech_mean_power_dbfs = 10.0f * log10f(
        speech_sum / (float)result->speech_bins / nfft_sq + 1.0e-18f);
    result->high_mean_power_dbfs = 10.0f * log10f(
        high_sum / (float)result->high_bins / nfft_sq + 1.0e-18f);

    {
        const float partition_sum = low_sum + speech_sum + high_sum;
        if (partition_sum > 1.0e-20f) {
            result->low_energy_share = low_sum / partition_sum;
            result->speech_energy_share = speech_sum / partition_sum;
            result->high_energy_share = high_sum / partition_sum;
        }
    }
}

static void synthesize_suppressed_spectrum(uint32_t nfft, float *out) {
    const float *window = ap_window_half(FRAME);
    uint32_t i;
    if (!window) return;

    ap_fft(synthesis_spectrum, nfft, 1);
    for (i = 0u; i < FRAME; ++i) {
        const float w0 = window[i];
        const float w1 = window[FRAME - 1u - i];
        out[i] = synthesis_spectrum[i].re * w0 + synthesis_overlap[i];
        synthesis_overlap[i] = synthesis_spectrum[FRAME + i].re * w1;
    }
}

static void mirror_upstream_components(
    uint32_t nfft,
    upstream_components_t *result,
    suppression_transfer_components_t *transfer) {
    const uint32_t bins = nfft / 2u + 1u;
    const uint32_t low_last = nfft / 64u;
    const uint32_t high_first = nfft * 7u / 16u;
    float speech_sum = 0.0f;
    float speech_sq_sum = 0.0f;
    float all_noise_sum = 1.0e-18f;
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
    float pre_sum[TRANSFER_DOMAIN_COUNT] = {1.0e-18f, 0.0f, 0.0f, 0.0f};
    float suppressed_sum[TRANSFER_DOMAIN_COUNT] = {1.0e-18f, 0.0f, 0.0f, 0.0f};
    float gain_sum[TRANSFER_DOMAIN_COUNT] = {0.0f, 0.0f, 0.0f, 0.0f};
    uint32_t floor_hits[TRANSFER_DOMAIN_COUNT] = {0u, 0u, 0u, 0u};
    uint32_t k;

    memset(result, 0, sizeof(*result));
    memset(transfer, 0, sizeof(*transfer));
    memcpy(synthesis_spectrum, analysis_spectrum,
           nfft * sizeof(synthesis_spectrum[0]));

    for (k = 0u; k < bins; ++k) {
        const float re = analysis_spectrum[k].re;
        const float im = analysis_spectrum[k].im;
        const float power = re * re + im * im + 1.0e-12f;
        const float previous_noise = mirror_tracker.estimate[k];
        ap_noise_tracker_result_t noise_result;
        float update_delta;
        float update_abs;
        float suppression_post;
        float suppression_gain;
        float predicted_suppressed_power;
        uint32_t transfer_domain;

        ap_noise_tracker_update(&mirror_tracker, k, power, &noise_result);
        all_noise_sum += noise_result.noise;
        update_delta = noise_result.noise - previous_noise;
        update_abs = fabsf(update_delta);

        suppression_post = power / (noise_result.noise + 1.0e-12f);
        suppression_gain = suppression_post > 1.0f ?
            sqrtf((suppression_post - 1.0f) / suppression_post) : 0.0f;
        suppression_gain = clampf_local(suppression_gain, NS_FLOOR, 1.0f);
        predicted_suppressed_power =
            power * suppression_gain * suppression_gain;
        transfer_domain = k <= low_last ? TRANSFER_LOW :
            (k < high_first ? TRANSFER_SPEECH : TRANSFER_HIGH);

        synthesis_spectrum[k].re *= suppression_gain;
        synthesis_spectrum[k].im *= suppression_gain;
        if (k != 0u && k != nfft / 2u) {
            synthesis_spectrum[nfft - k].re *= suppression_gain;
            synthesis_spectrum[nfft - k].im *= suppression_gain;
        }

        transfer->bins[TRANSFER_ALL]++;
        transfer->bins[transfer_domain]++;
        pre_sum[TRANSFER_ALL] += power;
        pre_sum[transfer_domain] += power;
        suppressed_sum[TRANSFER_ALL] += predicted_suppressed_power;
        suppressed_sum[transfer_domain] += predicted_suppressed_power;
        gain_sum[TRANSFER_ALL] += suppression_gain;
        gain_sum[transfer_domain] += suppression_gain;
        if (suppression_gain <= NS_FLOOR + 1.0e-7f) {
            floor_hits[TRANSFER_ALL]++;
            floor_hits[transfer_domain]++;
        }

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
    synthesize_suppressed_spectrum(nfft, predicted_ns_output);

    {
        const float mean = result->speech_bins ?
                           speech_sum / (float)result->speech_bins : 0.0f;
        const float concentration = speech_sum > 1.0e-9f ?
                                    speech_sq_sum / speech_sum : 0.0f;
        const float estimate_sum =
            low_noise_sum + speech_noise_sum + high_noise_sum;
        const float update_abs_sum =
            low_abs_update_sum + speech_abs_update_sum + high_abs_update_sum;
        const float previous_sum =
            low_previous_sum + speech_previous_sum + high_previous_sum;
        const float nfft_sq = (float)nfft * (float)nfft;

        result->gap = clampf_local(concentration - mean, 0.0f, 1.0f);
        result->all_noise_rms_dbfs = 10.0f * log10f(
            all_noise_sum / (float)bins / nfft_sq + 1.0e-18f);
        memcpy(&result->all_noise_rms_bits,
               &result->all_noise_rms_dbfs,
               sizeof(result->all_noise_rms_bits));
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

        for (k = 0u; k < TRANSFER_DOMAIN_COUNT; ++k) {
            if (transfer->bins[k] == 0u) continue;
            transfer->pre_ns_mean_power_dbfs[k] = 10.0f * log10f(
                pre_sum[k] / (float)transfer->bins[k] / nfft_sq + 1.0e-18f);
            transfer->predicted_suppressed_mean_power_dbfs[k] =
                10.0f * log10f(
                    suppressed_sum[k] / (float)transfer->bins[k] / nfft_sq
                    + 1.0e-18f);
            transfer->suppression_attenuation_db[k] =
                transfer->predicted_suppressed_mean_power_dbfs[k]
                - transfer->pre_ns_mean_power_dbfs[k];
            transfer->mean_gain[k] =
                gain_sum[k] / (float)transfer->bins[k];
            transfer->floor_gain_fraction[k] =
                (float)floor_hits[k] / (float)transfer->bins[k];
        }
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
    memset(post_ns_previous, 0, sizeof(post_ns_previous));
    memset(synthesis_overlap, 0, sizeof(synthesis_overlap));
    memset(predicted_ns_output, 0, sizeof(predicted_ns_output));
    memset(predicted_post_ns_previous, 0, sizeof(predicted_post_ns_previous));

    input_file = fopen(argv[1], "rb");
    if (!input_file) return 5;

    for (;;) {
        const size_t got = fread(raw, sizeof(raw[0]), FRAME, input_file);
        ap_ns_result_t ns_result;
        ap_module_vad_result_t public_shipping;
        vad_diagnostic_result_t vad_diagnostic;
        upstream_components_t upstream;
        post_ns_components_t post_ns;
        post_ns_components_t predicted_post_ns;
        suppression_transfer_components_t transfer;
        float synthesis_max_abs_delta = 0.0f;
        float synthesis_rmse = 0.0f;
        uint32_t i;

        if (got == 0u) break;
        if (got != FRAME) break;

        for (i = 0u; i < FRAME; ++i)
            input[i] = (float)raw[i] / 32768.0f;

        build_analysis_spectrum(input, analysis_previous,
                                ns_state.nfft, analysis_spectrum);

        ap_ns_process(&ns_state, AP_ENHANCE_FULL, NS_FLOOR,
                      input, NULL, ns_output, FRAME, 0, 0, 0, &ns_result);

        build_analysis_spectrum(ns_output, post_ns_previous,
                                ns_state.nfft, post_ns_spectrum);
        measure_spectral_components(post_ns_spectrum, ns_state.nfft, &post_ns);
        mirror_upstream_components(ns_state.nfft, &upstream, &transfer);

        build_analysis_spectrum(predicted_ns_output, predicted_post_ns_previous,
                                ns_state.nfft, predicted_post_ns_spectrum);
        measure_spectral_components(predicted_post_ns_spectrum,
                                    ns_state.nfft, &predicted_post_ns);
        for (i = 0u; i < FRAME; ++i) {
            const float delta = predicted_ns_output[i] - ns_output[i];
            const float abs_delta = fabsf(delta);
            if (abs_delta > synthesis_max_abs_delta)
                synthesis_max_abs_delta = abs_delta;
            synthesis_rmse += delta * delta;
        }
        synthesis_rmse = sqrtf(synthesis_rmse / (float)FRAME);

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
            "\"all_noise_rms_bits\":%u,"
            "\"ns_noise_rms_bits\":%u,"
            "\"noise_rms_bitwise_match\":%u,"
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
            "\"post_ns_all_mean_power_dbfs\":%.9g,"
            "\"post_ns_low_mean_power_dbfs\":%.9g,"
            "\"post_ns_speech_mean_power_dbfs\":%.9g,"
            "\"post_ns_high_mean_power_dbfs\":%.9g,"
            "\"post_ns_low_energy_share\":%.9g,"
            "\"post_ns_speech_energy_share\":%.9g,"
            "\"post_ns_high_energy_share\":%.9g,"
            "\"post_ns_low_bins\":%u,"
            "\"post_ns_speech_bins\":%u,"
            "\"post_ns_high_bins\":%u,"
            "\"pre_ns_all_mean_power_dbfs\":%.9g,"
            "\"pre_ns_low_mean_power_dbfs\":%.9g,"
            "\"pre_ns_speech_mean_power_dbfs\":%.9g,"
            "\"pre_ns_high_mean_power_dbfs\":%.9g,"
            "\"predicted_suppressed_all_mean_power_dbfs\":%.9g,"
            "\"predicted_suppressed_low_mean_power_dbfs\":%.9g,"
            "\"predicted_suppressed_speech_mean_power_dbfs\":%.9g,"
            "\"predicted_suppressed_high_mean_power_dbfs\":%.9g,"
            "\"suppression_all_attenuation_db\":%.9g,"
            "\"suppression_low_attenuation_db\":%.9g,"
            "\"suppression_speech_attenuation_db\":%.9g,"
            "\"suppression_high_attenuation_db\":%.9g,"
            "\"suppression_all_mean_gain\":%.9g,"
            "\"suppression_low_mean_gain\":%.9g,"
            "\"suppression_speech_mean_gain\":%.9g,"
            "\"suppression_high_mean_gain\":%.9g,"
            "\"suppression_all_floor_fraction\":%.9g,"
            "\"suppression_low_floor_fraction\":%.9g,"
            "\"suppression_speech_floor_fraction\":%.9g,"
            "\"suppression_high_floor_fraction\":%.9g,"
            "\"suppression_all_bins\":%u,"
            "\"suppression_low_bins\":%u,"
            "\"suppression_speech_bins\":%u,"
            "\"suppression_high_bins\":%u,"
            "\"predicted_post_ns_all_mean_power_dbfs\":%.9g,"
            "\"predicted_post_ns_low_mean_power_dbfs\":%.9g,"
            "\"predicted_post_ns_speech_mean_power_dbfs\":%.9g,"
            "\"predicted_post_ns_high_mean_power_dbfs\":%.9g,"
            "\"predicted_post_ns_low_energy_share\":%.9g,"
            "\"predicted_post_ns_speech_energy_share\":%.9g,"
            "\"predicted_post_ns_high_energy_share\":%.9g,"
            "\"predicted_post_ns_low_bins\":%u,"
            "\"predicted_post_ns_speech_bins\":%u,"
            "\"predicted_post_ns_high_bins\":%u,"
            "\"synthesis_max_abs_sample_delta\":%.9g,"
            "\"synthesis_output_rmse\":%.9g,"
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
            upstream.all_noise_rms_bits,
            float_bits(ns_result.noise_rms_dbfs),
            (unsigned)(upstream.all_noise_rms_bits ==
                       float_bits(ns_result.noise_rms_dbfs)),
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
            (double)post_ns.all_mean_power_dbfs,
            (double)post_ns.low_mean_power_dbfs,
            (double)post_ns.speech_mean_power_dbfs,
            (double)post_ns.high_mean_power_dbfs,
            (double)post_ns.low_energy_share,
            (double)post_ns.speech_energy_share,
            (double)post_ns.high_energy_share,
            post_ns.low_bins,
            post_ns.speech_bins,
            post_ns.high_bins,
            (double)transfer.pre_ns_mean_power_dbfs[TRANSFER_ALL],
            (double)transfer.pre_ns_mean_power_dbfs[TRANSFER_LOW],
            (double)transfer.pre_ns_mean_power_dbfs[TRANSFER_SPEECH],
            (double)transfer.pre_ns_mean_power_dbfs[TRANSFER_HIGH],
            (double)transfer.predicted_suppressed_mean_power_dbfs[TRANSFER_ALL],
            (double)transfer.predicted_suppressed_mean_power_dbfs[TRANSFER_LOW],
            (double)transfer.predicted_suppressed_mean_power_dbfs[TRANSFER_SPEECH],
            (double)transfer.predicted_suppressed_mean_power_dbfs[TRANSFER_HIGH],
            (double)transfer.suppression_attenuation_db[TRANSFER_ALL],
            (double)transfer.suppression_attenuation_db[TRANSFER_LOW],
            (double)transfer.suppression_attenuation_db[TRANSFER_SPEECH],
            (double)transfer.suppression_attenuation_db[TRANSFER_HIGH],
            (double)transfer.mean_gain[TRANSFER_ALL],
            (double)transfer.mean_gain[TRANSFER_LOW],
            (double)transfer.mean_gain[TRANSFER_SPEECH],
            (double)transfer.mean_gain[TRANSFER_HIGH],
            (double)transfer.floor_gain_fraction[TRANSFER_ALL],
            (double)transfer.floor_gain_fraction[TRANSFER_LOW],
            (double)transfer.floor_gain_fraction[TRANSFER_SPEECH],
            (double)transfer.floor_gain_fraction[TRANSFER_HIGH],
            transfer.bins[TRANSFER_ALL],
            transfer.bins[TRANSFER_LOW],
            transfer.bins[TRANSFER_SPEECH],
            transfer.bins[TRANSFER_HIGH],
            (double)predicted_post_ns.all_mean_power_dbfs,
            (double)predicted_post_ns.low_mean_power_dbfs,
            (double)predicted_post_ns.speech_mean_power_dbfs,
            (double)predicted_post_ns.high_mean_power_dbfs,
            (double)predicted_post_ns.low_energy_share,
            (double)predicted_post_ns.speech_energy_share,
            (double)predicted_post_ns.high_energy_share,
            predicted_post_ns.low_bins,
            predicted_post_ns.speech_bins,
            predicted_post_ns.high_bins,
            (double)synthesis_max_abs_delta,
            (double)synthesis_rmse,
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
        memcpy(post_ns_previous, ns_output, sizeof(float) * FRAME);
        memcpy(predicted_post_ns_previous, predicted_ns_output,
               sizeof(float) * FRAME);
        frame_index++;
    }

    fclose(input_file);
    return frame_index ? 0 : 8;
}
