#ifndef AUDIO_PIPELINE_AP_INTERNAL_H
#define AUDIO_PIPELINE_AP_INTERNAL_H

#include "audio_pipeline/audio_pipeline.h"
#include <stdint.h>

#define AP_INTERNAL_RATE_MAX 16000u
#define AP_INTERNAL_FRAME_MAX 160u
#define AP_AEC_CAP 2048u
#define AP_RENDER_CAP 8192u
#define AP_NS_FFT_MAX 512u
#define AP_NS_BINS_MAX (AP_NS_FFT_MAX / 2u + 1u)
#define AP_BF_HISTORY 8u
#define AP_PI 3.14159265358979323846f

/* MDF uses five exact sub-blocks per 10 ms frame. At 16 kHz this gives
 * 32-sample blocks and a 64-point FFT; at 8 kHz, 16 samples / 32-point FFT.
 * The maximum 120 ms tail therefore needs at most 60 partitions. */
#define AP_AEC_SUBBLOCKS_PER_FRAME 5u
#define AP_AEC_BLOCK_MAX (AP_INTERNAL_FRAME_MAX / AP_AEC_SUBBLOCKS_PER_FRAME)
#define AP_AEC_FFT_MAX (AP_AEC_BLOCK_MAX * 2u)
#define AP_AEC_BINS_MAX (AP_AEC_FFT_MAX / 2u + 1u)
#define AP_AEC_PARTITIONS_MAX 60u
#define AP_PIPELINE_RESIDENT_BUDGET_BYTES 80000u

_Static_assert((AP_RENDER_CAP & (AP_RENDER_CAP - 1u)) == 0u,
               "AP_RENDER_CAP must remain a power of two");

typedef struct ap_complex {
    float re;
    float im;
} ap_complex_t;

typedef struct ap_ns_state {
    uint32_t frame;
    uint32_t nfft;
    float window[AP_INTERNAL_FRAME_MAX * 2u];
    float previous[AP_INTERNAL_FRAME_MAX];
    float previous_echo[AP_INTERNAL_FRAME_MAX];
    float overlap[AP_INTERNAL_FRAME_MAX];
    float noise_psd[AP_NS_BINS_MAX];
    float residual_gain_bins[AP_NS_BINS_MAX];
    ap_complex_t spectrum[AP_NS_FFT_MAX];
    /* Frequency RES only consumes echo magnitude power after the forward FFT.
     * Retaining 257 power bins instead of a second resident 512-point complex
     * spectrum lets the same FFT scratch be reused sequentially. */
    float echo_power[AP_NS_BINS_MAX];
    float speech_probability;
    float noise_rms_dbfs;
} ap_ns_state_t;

#if defined(AP_ENABLE_MDF_AEC)
typedef struct ap_mdf_state {
    uint32_t block;
    uint32_t nfft;
    uint32_t bins;
    uint32_t partitions;
    uint32_t active_partitions;
    uint32_t x_head;
    uint32_t constrain_partition;
    uint32_t adapt_phase;
    float prev_ref[AP_AEC_BLOCK_MAX];
    /* Rolling sum of |X|^2 across the currently active render partitions.
     * Keeping it incrementally avoids a full partition scan for every bin on
     * each MDF adaptation step. x_power_total allows the echo synthesis path
     * to sleep once the entire active reference tail has drained to zero. */
    float x_power_sum[AP_AEC_BINS_MAX];
    float x_power_total;
    ap_complex_t x_history[AP_AEC_PARTITIONS_MAX][AP_AEC_BINS_MAX];
    ap_complex_t weights[AP_AEC_PARTITIONS_MAX][AP_AEC_BINS_MAX];
    ap_complex_t fft[AP_AEC_FFT_MAX];
    ap_complex_t acc[AP_AEC_FFT_MAX];
} ap_mdf_state_t;
#endif

struct ap_pipeline {
    ap_config_t cfg;
    ap_metrics_t metrics;
    uint32_t io_frame;
    uint32_t internal_frame;
    float hpf_r;
    float hpf_x[AP_MAX_MIC_CHANNELS];
    float hpf_y[AP_MAX_MIC_CHANNELS];

    /* These frame buffers are live in strictly sequential stages:
     * mic0 -> reference, mic1 -> aec_out, mono -> ns_out. Reusing their
     * storage keeps the synchronous data plane unchanged while removing three
     * resident 160-float scratch buffers from every pipeline instance. */
    union {
        float mic0[AP_INTERNAL_FRAME_MAX];
        float reference[AP_INTERNAL_FRAME_MAX];
    };
    union {
        float mic1[AP_INTERNAL_FRAME_MAX];
        float aec_out[AP_INTERNAL_FRAME_MAX];
    };
    union {
        float mono[AP_INTERNAL_FRAME_MAX];
        float ns_out[AP_INTERNAL_FRAME_MAX];
    };
    float echo_estimate[AP_INTERNAL_FRAME_MAX];
    float work[AP_INTERNAL_FRAME_MAX];

    float bf_history[AP_MAX_MIC_CHANNELS][AP_BF_HISTORY];
    int bf_lag;
    int bf_max_lag;
    uint32_t bf_counter;

    float render_ring[AP_RENDER_CAP];
    uint64_t render_total;
    uint64_t last_render_capture_frame;
    uint32_t delay_samples;
    uint32_t delay_update_counter;
    uint32_t last_best_delay;
    uint8_t have_last_best_delay;
    float drift_ppm;
    float drift_credit;

    uint32_t aec_taps;
    uint32_t active_aec_taps;
    uint32_t active_aec_adapt_stride;
#if defined(AP_ENABLE_MDF_AEC)
    ap_mdf_state_t mdf;
#else
    float aec_history[AP_AEC_CAP * 2u];
    float aec_weights[AP_AEC_CAP];
    uint32_t aec_pos;
    uint32_t aec_adapt_phase;
#endif

    ap_ns_state_t ns;
    float agc_gain;
    float agc_target_linear;
    float limiter_linear;
    float residual_gain;
    float vad_noise_rms;
    uint32_t vad_hangover;
    ap_quality_t quality;
};

_Static_assert(sizeof(struct ap_pipeline) <= AP_PIPELINE_RESIDENT_BUDGET_BYTES,
               "pipeline resident state exceeded the 80 kB product budget");

void ap_fft(ap_complex_t *x, uint32_t n, int inverse);
float ap_clampf(float x, float lo, float hi);
float ap_rms_dbfs(const float *x, uint32_t n);

#if defined(AP_ENABLE_MDF_AEC)
void ap_mdf_init(ap_pipeline_t *p);
void ap_mdf_reset(ap_pipeline_t *p, int count_reset);
void ap_mdf_set_active(ap_pipeline_t *p);
void ap_mdf_process(ap_pipeline_t *p,
                    const float *mic,
                    const float *ref,
                    float *out,
                    float *echo_out,
                    float mic_energy,
                    float ref_energy,
                    float *echo_energy_out);
#endif

#endif
