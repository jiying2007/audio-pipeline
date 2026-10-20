#ifndef FE09_B2S3_T2A_CONTROLLED_RESTART_H
#define FE09_B2S3_T2A_CONTROLLED_RESTART_H

/* FE09 #769: NONINSTALLED control-plane STOP/ACK/QUARANTINE/RESTART.
 * No in-place S1 reset, no seamless BF continuity, no actual ALSA clock,
 * audio callback control operations, public SDK, HIL or SSC305 resource claim.
 *
 * Each owner must finish all in-flight S1/T1 calls before it ACKs STOP.
 * After ACK, that owner MUST NOT touch the old session. An external supervisor
 * must join/quiesce owners, and may only start new owners AFTER restart.
 * Directly bypassing this exclusive-facade protocol is explicitly unsafe.
 */
#include "fe09_b2s3_t1_source_witness.h"
#include <stdint.h>
#include <stdatomic.h>

#define FE_T2A_CAPTURE_OWNER 1u
#define FE_T2A_RENDER_OWNER 2u
#define FE_T2A_WORKER_OWNER 4u

typedef enum {
    FE_T2A_OK = 0,
    FE_T2A_DENIED = -1,
    FE_T2A_BAD_STATE = -2
} fe_t2a_status;

typedef enum {
    FE_T2A_REASON_RENDER_ABSENT = 1,
    FE_T2A_REASON_SOURCE_MISMATCH = 2,
    FE_T2A_REASON_CAPTURE_RESET = 3,
    FE_T2A_REASON_XRUN = 4
} fe_t2a_reason;

typedef enum {
    FE_T2A_OFF = 0,
    FE_T2A_RUNNING = 1,
    FE_T2A_STOPPING = 2
} fe_t2a_phase;

typedef struct {
    uint32_t schema_version;
    uint32_t reason, owner_acks;
    uint32_t old_capture_source_id, old_render_source_id;
    uint32_t new_capture_source_id, new_render_source_id;
    uint32_t old_capture_epoch, old_render_epoch;
    uint32_t fresh_capture_epoch, fresh_render_epoch;
    uint32_t old_capture_queued, old_render_queued;
    uint32_t old_recorder_committed, old_recorder_target;
    uint32_t old_recorder_quarantined; /* Always 1, even if no incomplete frame. */
    uint32_t mic_bf_history_preserved; /* Always 0: this is an epoch reset. */
    uint32_t public_sdk_admitted; /* Always 0. */
    uint64_t old_generation, new_generation;
    uint64_t old_processed, old_capture_sequence, old_render_sequence;
} fe_t2a_receipt;

typedef struct {
    _Atomic uint32_t phase, acknowledgments;
    _Atomic uint64_t generation;
    _Atomic(fe_s3_t1_source_witness *) current;
    uint32_t required_owners; /* Fixed for one C1/C2/C4 render configuration. */
    uint32_t requested_reason; /* Control-plane only. */
    fe_t2a_receipt last_receipt; /* Quiescent control-plane reads only. */
} fe_t2a_gate;

/* Call when FIRST source witness is bound and no owner is running.
 * No attempt to attest arbitrary physical clock/source provenance.
 */
fe_t2a_status fe_t2a_init(fe_t2a_gate *gate,
    fe_s3_t1_source_witness *first, uint64_t generation);

/* Worker/producer must check returned session and expected generation before
 * source calls. A simultaneous STOP may begin; in-flight work must finish
 * before the owner can acknowledge quiescence. NULL means do not touch.
 */
fe_s3_t1_source_witness *fe_t2a_session(
    fe_t2a_gate *gate, uint64_t expected_generation);

fe_t2a_status fe_t2a_request_stop(fe_t2a_gate *gate,
    uint64_t expected_generation, fe_t2a_reason reason);

/* Caller must be the respective joined or halted owner after its last use of
 * old S1/T1; ACK is NOT itself a thread-stop implementation. Once ACKed the
 * owner must not call S1/T1 again until an independent next-session launch.
 * Duplicate/stale ACKs do not count toward required ownership.
 */
fe_t2a_status fe_t2a_ack_stopped(fe_t2a_gate *gate,
    uint64_t expected_generation, uint32_t owner);

/* Control thread only, after complete owner quiescence. The next T1 witness,
 * S1 BF state, S2 writer and all storage MUST already be fresh and separate.
 * Old queue/BF/recorder bytes stay unchanged and are quarantined as-is.
 * No call may fake Render, reuse any logical source IDs or carry BF history.
 */
fe_t2a_status fe_t2a_restart(fe_t2a_gate *gate,
    uint64_t expected_generation, fe_s3_t1_source_witness *next,
    fe_t2a_receipt *receipt);

#endif
