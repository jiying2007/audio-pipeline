#ifndef FE_MIC_FAULT_CONTROL_H
#define FE_MIC_FAULT_CONTROL_H

/* FE06 first-party, research-only D0. Never installed in the product SDK.
 * Observes four PHYSICAL microphone channels in interleaved F32 frames.
 * No allocation, I/O, locking, audio mutation, or automatic channel disabling.
 * The caller alone decides whether/when to apply a proposed active mask.
 */
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FE_MIC_FAULT_CHANNELS 4u
#define FE_MIC_FAULT_FRAME_SAMPLES 160u
#define FE_MIC_FAULT_ALL_MASK UINT32_C(15)

typedef struct {
    uint32_t signature_zero_frames[FE_MIC_FAULT_CHANNELS];
    uint32_t signature_rail_frames[FE_MIC_FAULT_CHANNELS];
    uint64_t complete_frames;
    uint32_t initialized;
} fe_mic_fault_control;

typedef struct {
    uint64_t complete_frames;
    uint32_t observed_mask;
    uint32_t proposed_mask;
    uint32_t newly_suspected_mask;
    uint32_t zero_signature_mask;
    uint32_t rail_signature_mask;
} fe_mic_fault_observation;

/* Init/reset clear history; never alter an array/BF state. */
int fe_mic_fault_init(fe_mic_fault_control *control);

/* Exactly 160 frames x 4 physical microphones at 16 kHz, normalized Float32.
 * No implicit channel mapping: the owner must explicitly map PCM to physical order.
 * All input floats must be finite in [-1,1]. Invalid calls fail atomically,
 * leaving control AND observation untouched.
 *
 * Zero signature: >=3 consecutive COMPLETE exact-zero frames on one channel,
 * each with >=2 other channels RMS >= 0.01 AND nonzero variance.
 * Rail signature: >=3 complete all-+1 or all--1 frames on one channel,
 * each with >=2 other channels not rail stuck.
 * Suspicion never auto-mutes; proposed_mask is just a caller-visible suggestion.
 * If proposed mask would be empty it is withheld, rather than muting all channels.
 * State is caller-owned/serialized; there are no speech/noise quality claims.
 */
int fe_mic_fault_observe(fe_mic_fault_control *control, const float *physical_pcm,
                         size_t float_count, uint32_t active_mask,
                         fe_mic_fault_observation *observation);

#ifdef __cplusplus
}
#endif
#endif
