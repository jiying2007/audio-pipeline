#ifndef FE09_B3_F0_COMPOSITION_H
#define FE09_B3_F0_COMPOSITION_H
/* #837 frozen, NONINSTALLED C4/16k research seam. No new public API or DSP.
 * One caller serializes the original source owners and this worker.
 * No live capture/clock recovery, recorder, device or shipping qualification. */
#include "fe09_b2s3_t2b_b1s0_owner_spsc.h"
#include "audio_pipeline/audio_pipeline.h"
#include <stddef.h>
#include <stdint.h>

#define FE_B3_F0_FRAMES 600u
#define FE_B3_F0_HOP 160u
#define FE_B3_F0_CAPTURE_ID 104u
#define FE_B3_F0_RENDER_ID 204u
#define FE_B3_F0_GENERATION UINT64_C(900001)
#define FE_B3_F0_STAGE_MASK UINT32_C(253)

typedef enum {
    FE_B3_F0_OK = 0, FE_B3_F0_REJECT = -1,
    FE_B3_F0_PENDING = -2, FE_B3_F0_FATAL = -3
} fe_b3_f0_status;

typedef struct {
    uint32_t magic, failed, prior_event;
    fe_b1s0_state *owner;
    fe_t2b_b0 *front;
    fe_b1b1 *capture;
    ap_pipeline_t *mono;
    size_t mono_bytes, capture_bytes, work_bytes;
    fe_b1s0_config owner_config;
    ap_config_t mono_config;
    uint64_t accepted, present, absent, notifications;
    uint64_t beam_clips, reference_clips;
} fe_b3_f0;

typedef struct {
    fe_b1s0_receipt source;
    uint32_t explicit_notify, absent_reference_untouched;
    uint32_t notify_capture_preserved;
    uint64_t beam_clips, reference_clips;
    float beam[FE_B3_F0_HOP];
} fe_b3_f0_receipt;

/* All declared arenas must remain disjoint and owned for the binding lifetime.
 * Only completely fresh, fixed C4/16k owner and real mono CALL states bind.
 * Rejected bind leaves the bridge and every input state unchanged. */
fe_b3_f0_status fe_b3_f0_bind(fe_b3_f0 *bridge, fe_b1s0_state *owner,
                             ap_pipeline_t *mono, size_t mono_bytes);
/* Reject/PENDING is before commit; outputs/receipt/mono/source state unchanged.
 * Work is scratch owned by the caller. On unexpected postcommit invariant
 * breach return FATAL, poison this bridge, preserve evidence and STOP; this is
 * never an atomic reject or a recoverable retry. No generic control API. */
fe_b3_f0_status fe_b3_f0_process_one(fe_b3_f0 *bridge,
    int16_t *output, size_t output_count, void *work, size_t work_bytes,
    fe_b3_f0_receipt *receipt);

/* Shared evidence primitives only; no transition/gate oracle or DSP. */
uint64_t fe_b3_f0_hash_bytes(const void *bytes, size_t count);
uint64_t fe_b3_f0_hash_s16(const int16_t *pcm, size_t count);
uint64_t fe_b3_f0_hash_f32(const float *pcm, size_t count);
/* Test evidence only: original state layout, two allocation pointers zeroed.
 * Caller supplies bounded scratch; no mutation of capture state. */
uint64_t fe_b3_f0_capture_fingerprint(const fe_b1b1 *capture, size_t bytes,
                                      void *scratch, size_t scratch_bytes);
#define FE_B3_F0_BIND_REFERENCE_BYTES (16384u + AP_PIPELINE_STATE_MAX_BYTES)

enum fe_b3_observed_call {
    FE_B3_OBS_HPF, FE_B3_OBS_SYNC_TRACK, FE_B3_OBS_SYNC_REFERENCE,
    FE_B3_OBS_ACTIVITY, FE_B3_OBS_AEC, FE_B3_OBS_NS, FE_B3_OBS_AGC,
    FE_B3_OBS_VAD, FE_B3_OBS_PUSH, FE_B3_OBS_SYNC_RESET,
    FE_B3_OBS_AEC_RESET, FE_B3_OBS_RES, FE_B3_OBS_LEGACY_BF,
    FE_B3_OBS_NOTIFY, FE_B3_OBS_CALLS
};
#define FE_B3_OBS_ORDER_CAP 32u
typedef struct {
    uint32_t calls[FE_B3_OBS_CALLS], order[FE_B3_OBS_ORDER_CAP];
    uint32_t order_count, violations, far, dt, aec_far, aec_dt;
    uint32_t ns_far, ns_dt, ns_enable, ns_echo_present, ns_mode;
    uint32_t frequency_res_active, agc_allow, vad_active, sync_delay_samples;
    uint32_t route_jump, notify_flags, notify_lost_frames;
    int32_t notify_status;
    uint32_t explicit_aec_resets, automatic_aec_resets;
    uint32_t notify_capture_preserved, notify_processed_preserved;
    uint32_t notify_reset_state_mask, agc_gain_before_bits, agc_gain_after_bits;
    uint32_t vad_probability_bits, residual_gain_bits;
} fe_b3_observation;
_Static_assert(sizeof(fe_b3_observation) <= 384u, "frozen observer row cap");
void fe_b3_observer_configure(const void *capture, size_t capture_bytes,
                              const ap_pipeline_t *fresh_mono);
void fe_b3_observer_begin(uint32_t one_based_frame);
void fe_b3_observer_end(void);
const fe_b3_observation *fe_b3_observer_frame(uint32_t one_based_frame);
size_t fe_b3_observer_storage_bytes(void);
int fe_b3_observer_enabled(void);
#endif
