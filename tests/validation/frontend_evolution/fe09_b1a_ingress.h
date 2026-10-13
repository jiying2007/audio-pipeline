#ifndef FE09_B1A_CAPTURE_RENDER_INGRESS_H
#define FE09_B1A_CAPTURE_RENDER_INGRESS_H

/* FE09-R2B1A - noninstalled first-party research-only 16kHz ingress.
 * This is NOT a public 3.x SDK, a SRC, BF, AEC, DOA or hardware clock API.
 * Caller serializes all operations. No allocation, locks or I/O in processing.
 */
#include <stddef.h>
#include <stdint.h>

#define FE_B1A_API_VERSION UINT32_C(0x00030001) /* draft identity, not public ABI */
#define FE_B1A_ALIGNMENT 16u
#define FE_B1A_RATE_HZ 16000u
#define FE_B1A_FRAME_MS 10u
#define FE_B1A_SAMPLES_PER_MIC 160u
#define FE_B1A_MAX_MICS 4u
#define FE_B1A_CAPTURE_GAP 1u
#define FE_B1A_RENDER_GAP 2u
#define FE_B1A_CLOCK_RESET 4u

typedef enum {
    FE_B1A_OK = 0,
    FE_B1A_EINVAL = -1,
    FE_B1A_ENOMEM = -2,
    FE_B1A_ESTATE = -3
} fe_b1a_status;

typedef struct {
    uint32_t struct_size;
    uint32_t api_version;
    uint32_t io_rate_hz;
    uint32_t frame_ms;
    uint32_t physical_mics;         /* Only 1, 2, or 4 */
    uint32_t render_channels;       /* 0 or 1. Never a physical microphone */
    uint32_t active_mic_mask;       /* Physical, not interleaved slot indices */
    uint32_t capture_clock_authority; /* 0 = UNKNOWN, the only permitted value */
    uint32_t physical_to_capture_slot[FE_B1A_MAX_MICS];
    uint32_t reserved[4];
} fe_b1a_config;

typedef struct fe_b1a_ingress fe_b1a_ingress;

typedef struct {
    size_t requested_state_bytes;
    uint32_t physical_mics;
    uint32_t render_channels;
    uint32_t active_mic_mask;
    uint32_t capture_clock_authority;
    uint64_t accepted_frames;         /* Cumulative, survives gaps */
    uint64_t capture_epoch;
    uint64_t render_epoch;
    uint64_t clock_epoch;
    uint64_t capture_frames_in_epoch;
    uint64_t render_frames_in_epoch;
    uint64_t capture_stream_hash[FE_B1A_MAX_MICS];
    uint64_t render_stream_hash;
} fe_b1a_info;

/* Exact caller-owned state query: separate N physical source fingerprints
 * and optional render fingerprint in one config-sized arena. Returns 0 for
 * invalid descriptors. Memory must be 16-byte aligned. No heap in callbacks.
 */
size_t fe_b1a_state_bytes(const fe_b1a_config *config);
fe_b1a_status fe_b1a_init(void *memory, size_t memory_bytes,
                          const fe_b1a_config *config, fe_b1a_ingress **out);

/* Exact native 16kHz identity ingress only, no sample-rate conversion.
 * capture: 160 * N interleaved S16 scalar samples.
 * render: optional, separate 160 mono S16 scalar samples.
 * mic_output: 160 * N float scalars, PHYSICAL-MIC-MAJOR (NOT interleaved).
 * render_output: optional, separate 160 float scalars.
 * Active-mask excluded microphone outputs are explicitly zero, never
 * synthesized from other microphones. No fabricated gap/frame timestamps.
 * Every rejected call leaves all state and output buffers unchanged.
 */
fe_b1a_status fe_b1a_process(fe_b1a_ingress *state,
                             const int16_t *capture, size_t capture_samples,
                             const int16_t *render, size_t render_samples,
                             float *mic_output, size_t mic_output_samples,
                             float *render_output, size_t render_output_samples);

/* Caller-serialized controls at frame boundary; no automatic fault detection.
 * Capture gap resets only capture stream hashes/epoch; render gap only render.
 * Clock reset changes both available source epochs plus clock_epoch.
 * All events retain cumulative accepted_frames. This is not clock alignment.
 */
fe_b1a_status fe_b1a_set_active_mask(fe_b1a_ingress *state, uint32_t mask);
fe_b1a_status fe_b1a_notify_gap(fe_b1a_ingress *state, uint32_t flags);
fe_b1a_status fe_b1a_reset(fe_b1a_ingress *state);
fe_b1a_status fe_b1a_get_info(const fe_b1a_ingress *state, fe_b1a_info *out);

#endif
