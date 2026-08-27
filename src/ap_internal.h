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

#define AP_AEC_SUBBLOCKS_PER_FRAME 5u
#define AP_AEC_BLOCK_MAX (AP_INTERNAL_FRAME_MAX / AP_AEC_SUBBLOCKS_PER_FRAME)
#define AP_AEC_FFT_MAX (AP_AEC_BLOCK_MAX * 2u)
#define AP_AEC_BINS_MAX (AP_AEC_FFT_MAX / 2u + 1u)
#define AP_AEC_PARTITIONS_MAX 60u

_Static_assert((AP_RENDER_CAP & (AP_RENDER_CAP - 1u)) == 0u,
               "AP_RENDER_CAP must remain a power of two");
_Static_assert((AP_PIPELINE_STATE_ALIGNMENT & (AP_PIPELINE_STATE_ALIGNMENT - 1u)) == 0u,
               "pipeline state alignment must remain power of two");

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
    float echo_power[AP_NS_BINS_MAX];
    float speech_probability;
    float noise_rms_dbfs;
} ap_ns_state_t;

#if defined(AP_BUILD_AEC_MDF)
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

    /* Strictly sequential frame stages share storage. */
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
#if defined(AP_BUILD_AEC_MDF)
    ap_mdf_state_t mdf;
#elif defined(AP_BUILD_AEC_NLMS)
    float aec_history[AP_AEC_CAP * 2u];
    float aec_weights[AP_AEC_CAP];
    uint32_t aec_pos;
    uint32_t aec_adapt_phase;
#else
#error "Exactly one AEC backend must be selected"
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

_Static_assert(sizeof(struct ap_pipeline) <= AP_PIPELINE_STATE_MAX_BYTES,
               "pipeline resident state exceeded the public static-state ceiling");

/* DSP primitives. */
void ap_fft(ap_complex_t *x, uint32_t n, int inverse);
float ap_clampf(float x, float lo, float hi);
float ap_rms_dbfs(const float *x, uint32_t n);

/* Compile-time architecture kernel boundary. */
float ap_kernel_dot_f32(const float *a, const float *b, uint32_t n);
void ap_kernel_complex_mac(ap_complex_t *acc,
                           const ap_complex_t *w,
                           const ap_complex_t *x,
                           uint32_t bins);
void ap_kernel_complex_adapt(ap_complex_t *w,
                             const ap_complex_t *x,
                             const ap_complex_t *gradient,
                             uint32_t bins);
void ap_kernel_nlms_update(float *w, const float *x, float step, uint32_t n);

/* Boundary/frontend. */
int ap_supported_io_rate(uint32_t hz);
void ap_resample_input_channel(const int16_t *in, uint32_t in_frames,
                               uint32_t channels, uint32_t channel,
                               float *out, uint32_t out_frames);
void ap_resample_output(const float *in, uint32_t in_frames,
                        int16_t *out, uint32_t out_frames);
void ap_frontend_init(ap_pipeline_t *p);
void ap_hpf_process(ap_pipeline_t *p, float *x, uint32_t n, uint32_t ch);
void ap_beamform(ap_pipeline_t *p, float *a, float *b, float *out, uint32_t n);

/* Render synchronization. */
void ap_sync_track_delay(ap_pipeline_t *p, const float *mic);
void ap_sync_get_reference(ap_pipeline_t *p, uint32_t delay, float *out);

/* Compile-time AEC backend boundary. */
void ap_aec_backend_init(ap_pipeline_t *p);
void ap_aec_backend_reset(ap_pipeline_t *p, int count_reset);
void ap_aec_backend_set_active(ap_pipeline_t *p);
void ap_aec_backend_process(ap_pipeline_t *p,
                            const float *mic,
                            const float *ref,
                            float *out,
                            float *echo_out,
                            float mic_energy,
                            float ref_energy,
                            float *echo_energy_out);

/* Enhancement. */
void ap_enhance_init(ap_pipeline_t *p);
float ap_apply_broadband_res(ap_pipeline_t *p, float *x,
                             float echo_energy, float residual_energy,
                             float ref_energy, float mic_energy);
void ap_ns_process(ap_pipeline_t *p, const float *in, const float *echo,
                   float *out, float ref_energy, float mic_energy);
void ap_agc_process(ap_pipeline_t *p, float *x, uint32_t n);
void ap_vad_process(ap_pipeline_t *p, const float *x, uint32_t n);

#endif
