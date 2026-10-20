#ifndef FE09_B2S3_T2C0_QUIESCENT_FALLBACK_H
#define FE09_B2S3_T2C0_QUIESCENT_FALLBACK_H
/*
 * #784: NONINSTALLED first-party research-only logical owner ACK control.
 * Does not make a stopped or physically absent source trustworthy: the
 * embedding source owners MUST actually stop BEFORE ACK and use this control
 * for all new work. Missing ACK cannot be replaced by a timer.
 * No live S1 private fields, no DSP/codec rewrites, no durable archive,
 * no physical ADC/DAC clock or public SDK/SSC305 admission.
 */
#include "fe09_b2s3_t2b_b1s1_source_chunks.h"
#include <stdatomic.h>
#include <stdint.h>

#define FE_T2C0_CAPTURE_OWNER 1u
#define FE_T2C0_WORKER_OWNER 2u
#define FE_T2C0_RENDER_OWNER 4u
#define FE_T2C0_RUNNING 1u
#define FE_T2C0_STOPPING 2u

typedef enum {
    FE_T2C0_OK = 0,
    FE_T2C0_DENIED = -1,
    FE_T2C0_SOURCE = -2
} fe_t2c0_status;
typedef enum {
    FE_T2C0_REASON_RENDER_OWNER_UNAVAILABLE = 1,
    FE_T2C0_REASON_CAPTURE_DISCONTINUITY = 2,
    FE_T2C0_REASON_OPERATOR_RESTART = 3
} fe_t2c0_reason;

typedef struct {
    fe_b1s0_state *source;
    fe_b1s1_store *archive;
} fe_t2c0_session;

typedef struct {
    _Atomic(fe_t2c0_session *) current;
    atomic_uint_fast64_t generation;
    atomic_uint phase, acks;
    uint32_t required_owners;
    uint32_t requested_reason;
} fe_t2c0_gate;

typedef struct {
    uint32_t schema_version, reason, owners_acknowledged;
    uint32_t old_capture_source_id, old_render_source_id;
    uint32_t new_capture_source_id, new_render_source_id;
    uint32_t old_render_enabled, new_render_enabled;
    uint32_t old_completed_apx3_chunks;
    uint32_t quarantined_capture_frames, quarantined_render_events;
    uint32_t old_archival_durable, physical_clock_known;
    uint32_t capture_bf_history_preserved, public_sdk_admitted;
    uint64_t old_generation, new_generation;
    uint64_t old_processed_capture, old_source_capture_submitted;
    uint64_t old_render_source_submitted;
    uint64_t lost_capture_start, lost_capture_end;
    uint8_t previous_committed_row_sha256[32];
} fe_t2c0_receipt;

/* Initialize while old owners are quiescent, source and archive pinned.
 * After startup only one authorized supervisor may request/restart.
 */
fe_t2c0_status fe_t2c0_init(fe_t2c0_gate *gate,
                            fe_t2c0_session *first);
fe_t2c0_session *fe_t2c0_current(fe_t2c0_gate *gate,
                                 uint64_t generation);
fe_t2c0_status fe_t2c0_request_stop(fe_t2c0_gate *gate,
                                    uint64_t generation,
                                    fe_t2c0_reason reason);
/* One caller from each independently STOPPED owner, atomic bit per owner.
 * An ACK is a logical testimony by that caller, not device authentication.
 */
fe_t2c0_status fe_t2c0_ack(fe_t2c0_gate *gate,
                           uint64_t generation, uint32_t owner);
/* Single supervisor only; no producer or worker may access the old/new
 * source structs concurrently. All original source APX3 bytes/PCM remain
 * untouched, even when session switch is refused.
 */
fe_t2c0_status fe_t2c0_restart(fe_t2c0_gate *gate,
                               uint64_t generation,
                               fe_t2c0_session *fresh,
                               fe_t2c0_receipt *receipt);
#endif
