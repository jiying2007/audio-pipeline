#ifndef FE09_B2S3_PRIVATE_BRIDGE_H
#define FE09_B2S3_PRIVATE_BRIDGE_H

/* FE09-R2B2-S3 #762: strictly NONINSTALLED software research bridge.
 * Producer ownership and SPSC C11 release/acquire remain in frozen S1.
 * APX3 LE+CRC and unknown time authority remain in frozen S2.
 * No public SDK, 2.x compatibility, BSP, ADC or actual SSC305 deadline.
 */
#include "fe09_b2s1_private_queue.h"
#include "fe09_b2s2_private_apd.h"
#include <stddef.h>
#include <stdint.h>

typedef enum {
    FE_S3_OK = 0,
    FE_S3_EINVAL = -1,
    FE_S3_EEMPTY = -2,
    FE_S3_EMISMATCH = -3,
    FE_S3_ECORE = -4
} fe_s3_status;

typedef struct {
    fe_b2s1_queue *queue;
    fe_s2_writer *writer;
    uint8_t *shadow;
    size_t shadow_bytes;
    size_t s1_state_bytes, record_bytes, record_stride;
    uint64_t processed;
    uint32_t capture_source_id, render_source_id;
} fe_s3_bridge;

/* Initialize before threads start, while all source producers are QUIESCENT.
 * The recorder is a fresh S2 writer for exactly 1..128 frames. The caller
 * supplies a separate full-size shadow arena. This worst-case scratch is
 * HOSTED RESEARCH, deliberately not an SSC305 RAM optimization claim.
 * The worker exclusively owns bridge/recorder/beam/reference/work buffers.
 * Each capture/render source owns its own frozen S1 producer sequence.
 */
fe_s3_status fe_s3_bridge_init(
    fe_s3_bridge *out, fe_b2s1_queue *queue, fe_s2_writer *writer,
    uint8_t *shadow, size_t shadow_bytes);

/* One matched 10ms pair, S1 queue -> original BF + APX3 committed record.
 * S2 serializes first into private shadow without changing the real writer.
 * If S1 rejects, the real APX3 stream, writer and all outputs are untouched
 * by this bridge. Once S1 accepts, one prevalidated byte record is committed
 * without a subsequent failure point. No allocation, mutex or file I/O.
 * EEMPTY and EMISMATCH are explicit fail-closed conditions, not automatic
 * silence, time resampling, skipped queues or a proof of self-healing.
 */
fe_s3_status fe_s3_bridge_step(
    fe_s3_bridge *bridge, const fe_s2_frame *frame,
    float *beam, size_t beam_count, float *reference, size_t reference_count,
    void *work, size_t work_bytes);

/* Only call while producers and worker are quiescent. A mismatch has NO
 * implicit reset/skip authority. Full owner-driven queue reinitialization
 * is separately permitted after join; it loses old BF history and therefore
 * does not qualify render-only seamless recovery.
 */
fe_s3_status fe_s3_bridge_finish(const fe_s3_bridge *bridge,
                                 size_t *completed_bytes);

#endif
