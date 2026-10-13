#ifndef FE09_R2B1B_S0_N_RENDER_SRC_H
#define FE09_R2B1B_S0_N_RENDER_SRC_H

/* FE09-R2B1B-S0: noninstalled 16/32/48kHz first-party SRC ownership.
 * Test-only interface. NOT public 3.x SDK, AEC, BF, DOA or ADC-clock evidence.
 * Links the unchanged first-party src/frontend/ap_resampler.c implementation.
 */
#include <stddef.h>
#include <stdint.h>

#define FE_B1B0_VERSION UINT32_C(0x00030002) /* Unstable research identity */
#define FE_B1B0_ALIGNMENT 16u
#define FE_B1B0_FRAME_MS 10u
#define FE_B1B0_INTERNAL_HZ 16000u
#define FE_B1B0_INTERNAL_FRAMES 160u
#define FE_B1B0_MAX_MICS 4u
#define FE_B1B0_CAPTURE_GAP 1u
#define FE_B1B0_RENDER_GAP 2u
#define FE_B1B0_CLOCK_RESET 4u

typedef enum {
    FE_B1B0_OK = 0,
    FE_B1B0_EINVAL = -1,
    FE_B1B0_ENOMEM = -2,
    FE_B1B0_ESTATE = -3
} fe_b1b0_status;

typedef struct {
    uint32_t struct_size;
    uint32_t api_version;
    uint32_t capture_and_render_rate_hz;  /* exactly 16000 / 32000 / 48000 */
    uint32_t frame_ms;
    uint32_t physical_mics;              /* 1, 2, or 4 */
    uint32_t render_channels;            /* 0 or 1; NOT physical mic #N */
    uint32_t active_mic_mask;            /* physical mic bits */
    uint32_t capture_clock_authority;    /* zero = UNKNOWN; only value allowed */
    uint32_t physical_to_capture_slot[FE_B1B0_MAX_MICS];
    uint32_t reserved[4];
} fe_b1b0_config;

typedef struct fe_b1b0_src fe_b1b0_src;

typedef struct {
    size_t requested_state_bytes;
    size_t first_party_src_state_bytes_per_stream;
    uint32_t input_rate_hz;
    uint32_t capture_frame_samples;
    uint32_t internal_frame_samples;
    uint32_t existing_first_party_filter_delay_samples;
    uint32_t physical_mics;
    uint32_t render_channels;
    uint32_t active_mic_mask;
    uint32_t capture_clock_authority;
    uint64_t accepted_frames;
    uint64_t capture_epoch, render_epoch, clock_epoch;
    uint64_t capture_frames_in_epoch, render_frames_in_epoch;
    uint64_t mic_output_hash[FE_B1B0_MAX_MICS];
    uint64_t render_output_hash;
} fe_b1b0_info;

/* Config-specific, 16-byte-aligned caller arena including independent first-party
 * ap_resampler_state_t per physical source and optional render. The old
 * 3-stream history array INSIDE each copy is used only with stream index 0.
 * This is deliberately NOT a compressed product memory profile.
 */
size_t fe_b1b0_state_bytes(const fe_b1b0_config *cfg);
fe_b1b0_status fe_b1b0_init(void *memory, size_t memory_size,
                            const fe_b1b0_config *cfg, fe_b1b0_src **out);

/* Actual ap_resample_input_channel source, BANDLIMITED mode. Exact 10ms
 * input with rate/100 per physical mic; optional mono render at SAME rate.
 * F32 outputs are physical-mic-major N*160 plus independent render 160.
 * Masked physical channels are zero-output but their real capture SRC
 * histories still advance; no fabricated extra capture/render frames.
 * On ANY rejected call, state, outputs, inputs are all unchanged.
 */
fe_b1b0_status fe_b1b0_process(fe_b1b0_src *s,
                               const int16_t *capture, size_t capture_scalars,
                               const int16_t *render, size_t render_scalars,
                               float *mic_output, size_t mic_output_scalars,
                               float *render_output, size_t render_output_scalars);

/* Caller-serialized frame boundary commands; no microphone fault detection.
 * Capture gap resets only N real mic histories; render gap only optional
 * reference history; CLOCK_RESET invalidates both domains if available.
 * Cumulative accepted frame count persists through gaps/reset events.
 */
fe_b1b0_status fe_b1b0_set_active_mask(fe_b1b0_src *s, uint32_t mask);
fe_b1b0_status fe_b1b0_notify_gap(fe_b1b0_src *s, uint32_t flags);
fe_b1b0_status fe_b1b0_reset(fe_b1b0_src *s);
fe_b1b0_status fe_b1b0_get_info(const fe_b1b0_src *s, fe_b1b0_info *out);

#endif
