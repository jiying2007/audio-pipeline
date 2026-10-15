/* S3 #762 test-only S1 SRC/FIR33 -> S2 APX3 transactional worker.
 * Not a shipping Linux runtime or verified real audio timebase.
 */
#include "fe09_b2s3_private_bridge.h"
#include <stdint.h>
#include <string.h>

static int disjoint(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 1;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 0;
    return x + na <= y || y + nb <= x;
}

fe_s3_status fe_s3_bridge_init(fe_s3_bridge *out,
    fe_b2s1_queue *queue, fe_s2_writer *writer,
    uint8_t *shadow, size_t shadow_bytes) {
    fe_b2s1_info qinfo;
    fe_b2s1_dump_sketch map;
    fe_s3_bridge next;
    size_t total = 0u, stride = 0u;
    uint32_t i;
    if (!out || !queue || !writer || !shadow ||
        fe_b2s1_get_info(queue, &qinfo) != FE_B2S1_OK ||
        fe_b2s1_private_dump_sketch(queue, &map) != FE_B2S1_OK ||
        fe_s2_layout(&writer->config, writer->target_frames,
                     &total, &stride) != FE_S2_OK ||
        !writer->output || writer->appended != 0u ||
        writer->last_sequence != 0u ||
        writer->current_capture_epoch != writer->config.capture_epoch ||
        writer->current_render_epoch != writer->config.render_epoch ||
        writer->total_bytes != total || writer->record_stride != stride ||
        writer->capacity < total || writer->capacity > FE_S2_MAX_BYTES ||
        shadow_bytes < total || shadow_bytes > FE_S2_MAX_BYTES ||
        qinfo.processed != 0u || qinfo.capture_queued != 0u ||
        qinfo.render_queued != 0u ||
        qinfo.physical_mics != writer->config.physical_mics ||
        qinfo.render_channels != writer->config.render_channels ||
        qinfo.input_hz != writer->config.rate_hz ||
        qinfo.state_bytes == 0u || qinfo.state_bytes > 65536u ||
        map.new_magic_assigned != 0u || map.clock_authority != 0u ||
        !disjoint(out, sizeof(*out), queue, qinfo.state_bytes) ||
        !disjoint(out, sizeof(*out), writer, sizeof(*writer)) ||
        !disjoint(out, sizeof(*out), writer->output, writer->capacity) ||
        !disjoint(out, sizeof(*out), shadow, shadow_bytes) ||
        !disjoint(queue, qinfo.state_bytes, writer, sizeof(*writer)) ||
        !disjoint(queue, qinfo.state_bytes, writer->output, writer->capacity) ||
        !disjoint(queue, qinfo.state_bytes, shadow, shadow_bytes) ||
        !disjoint(writer, sizeof(*writer), writer->output, writer->capacity) ||
        !disjoint(writer, sizeof(*writer), shadow, shadow_bytes) ||
        !disjoint(shadow, shadow_bytes, writer->output, writer->capacity))
        return FE_S3_EINVAL;
    for (i = 0u; i < qinfo.physical_mics; ++i)
        if (writer->config.physical_to_capture_slot[i] !=
            map.physical_capture_slots[i])
            return FE_S3_EINVAL;
    memset(&next, 0, sizeof(next));
    next.queue = queue;
    next.writer = writer;
    next.shadow = shadow;
    next.shadow_bytes = shadow_bytes;
    next.record_bytes = total;
    next.record_stride = stride;
    next.s1_state_bytes = qinfo.state_bytes;
    next.capture_source_id = writer->config.capture_source_id;
    next.render_source_id = writer->config.render_source_id;
    *out = next;
    return FE_S3_OK;
}

fe_s3_status fe_s3_bridge_step(fe_s3_bridge *b,
    const fe_s2_frame *frame,
    float *beam, size_t beam_count, float *reference, size_t reference_count,
    void *work, size_t work_bytes) {
    fe_s2_writer shadow_writer;
    fe_b2s1_status status;
    size_t off, cap_bytes, render_bytes;
    if (!b || !frame || !b->queue || !b->writer || !b->shadow ||
        !b->writer->output || !frame->capture ||
        b->writer->appended != b->processed ||
        b->processed >= b->writer->target_frames ||
        b->writer->total_bytes != b->record_bytes ||
        b->writer->record_stride != b->record_stride ||
        b->writer->capacity < b->record_bytes ||
        b->shadow_bytes < b->record_bytes ||
        b->record_bytes > FE_S2_MAX_BYTES ||
        b->record_stride < FE_S2_RECORD_META_BYTES + 4u ||
        b->processed > SIZE_MAX / b->record_stride ||
        b->record_stride * b->processed > b->record_bytes - FE_S2_HEADER_BYTES)
        return FE_S3_EINVAL;
    cap_bytes = frame->capture_count * sizeof(int16_t);
    render_bytes = frame->render_count * sizeof(int16_t);
    if (frame->capture_count > FE_S2_MAX_CAPTURE_SAMPLES ||
        frame->render_count > FE_S2_MAX_SOURCE_SAMPLES ||
        !disjoint(b->queue, b->s1_state_bytes, frame, sizeof(*frame)) ||
        !disjoint(b->queue, b->s1_state_bytes, frame->capture, cap_bytes) ||
        !disjoint(b->queue, b->s1_state_bytes, frame->render, render_bytes) ||
        !disjoint(b->writer->output, b->record_bytes, frame, sizeof(*frame)) ||
        !disjoint(b->writer->output, b->record_bytes, frame->capture, cap_bytes) ||
        !disjoint(b->writer->output, b->record_bytes, frame->render, render_bytes) ||
        !disjoint(b->writer->output, b->record_bytes, work, work_bytes) ||
        !disjoint(b->writer->output, b->record_bytes, beam,
                  beam_count * sizeof(float)) ||
        !disjoint(b->writer->output, b->record_bytes, reference,
                  reference_count * sizeof(float)) ||
        !disjoint(b->shadow, b->shadow_bytes, frame, sizeof(*frame)) ||
        !disjoint(b->shadow, b->shadow_bytes, frame->capture, cap_bytes) ||
        !disjoint(b->shadow, b->shadow_bytes, frame->render, render_bytes) ||
        !disjoint(b->shadow, b->shadow_bytes, work, work_bytes) ||
        !disjoint(b->shadow, b->shadow_bytes, beam,
                  beam_count * sizeof(float)) ||
        !disjoint(b->shadow, b->shadow_bytes, reference,
                  reference_count * sizeof(float)))
        return FE_S3_EINVAL;
    /* Check final commit bounds BEFORE consuming the S1 source queues.
     * There must be no fallible checks after successful first-party BF.
     */
    off = FE_S2_HEADER_BYTES + (size_t)b->processed * b->record_stride;
    if (off > b->record_bytes ||
        b->record_stride > b->record_bytes - off)
        return FE_S3_EINVAL;
    /* Transaction preflight on full caller-owned private shadow bytes.
     * S2 writes a deterministic record slot, never the retained file.
     */
    shadow_writer = *b->writer;
    shadow_writer.output = b->shadow;
    if (fe_s2_writer_append(&shadow_writer, frame) != FE_S2_OK)
        return FE_S3_EINVAL;
    /* Frozen S1 validates actual queue pair, then processes first-party BF.
     * On mismatch/empty/kernel failure, the REAL APX3 writer is unchanged.
     */
    status = fe_b2s1_process_one(b->queue, beam, beam_count,
                                reference, reference_count, work, work_bytes);
    if (status != FE_B2S1_OK) {
        if (status == FE_B2S1_EEMPTY) return FE_S3_EEMPTY;
        if (status == FE_B2S1_EINVAL) return FE_S3_EMISMATCH;
        return FE_S3_ECORE;
    }
    memcpy(b->writer->output + off, b->shadow + off, b->record_stride);
    b->writer->appended = shadow_writer.appended;
    b->writer->last_sequence = shadow_writer.last_sequence;
    b->writer->current_capture_epoch = shadow_writer.current_capture_epoch;
    b->writer->current_render_epoch = shadow_writer.current_render_epoch;
    ++b->processed;
    return FE_S3_OK;
}

fe_s3_status fe_s3_bridge_finish(const fe_s3_bridge *b,
                                 size_t *completed_bytes) {
    if (!b || !b->writer || b->processed != b->writer->target_frames ||
        b->writer->appended != b->processed)
        return FE_S3_EINVAL;
    return fe_s2_writer_finish(b->writer, completed_bytes) == FE_S2_OK ?
           FE_S3_OK : FE_S3_ECORE;
}
