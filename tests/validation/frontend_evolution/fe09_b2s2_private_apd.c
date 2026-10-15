/* FE09-R2B2-S2 experimental APX3 codec. No dependency on public SDK. */
#include "fe09_b2s2_private_apd.h"
#include <stdint.h>
#include <string.h>

static int disjoint(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 1;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 0;
    return x + na <= y || y + nb <= x;
}
static void put32(uint8_t *p, uint32_t v) {
    unsigned i;
    for (i = 0u; i != 4u; ++i) p[i] = (uint8_t)(v >> (8u*i));
}
static uint32_t get32(const uint8_t *p) {
    unsigned i;
    uint32_t v = 0u;
    for (i = 0u; i != 4u; ++i) v |= ((uint32_t)p[i]) << (8u*i);
    return v;
}
static void put64(uint8_t *p, uint64_t v) {
    unsigned i;
    for (i = 0u; i != 8u; ++i) p[i] = (uint8_t)(v >> (8u*i));
}
static uint64_t get64(const uint8_t *p) {
    unsigned i;
    uint64_t v = UINT64_C(0);
    for (i = 0u; i != 8u; ++i) v |= ((uint64_t)p[i]) << (8u*i);
    return v;
}
static uint32_t crc32_bytes(const uint8_t *data, size_t n) {
    uint32_t crc = UINT32_MAX;
    size_t i;
    for (i = 0u; i < n; ++i) {
        unsigned j;
        crc ^= data[i];
        for (j = 0u; j < 8u; ++j)
            crc = (crc & 1u) ? ((crc >> 1u) ^ UINT32_C(0xedb88320))
                             : (crc >> 1u);
    }
    return ~crc;
}
static int config_ok(const fe_s2_config *cfg) {
    uint32_t n, i, j;
    if (!cfg) return 0;
    n = cfg->physical_mics;
    if ((n != 1u && n != 2u && n != 4u) ||
        (cfg->rate_hz != 16000u && cfg->rate_hz != 32000u &&
         cfg->rate_hz != 48000u) ||
        cfg->render_channels > 1u ||
        cfg->capture_source_id == 0u || cfg->capture_epoch == 0u ||
        cfg->clock_authority != 0u || cfg->capture_timestamp_valid != 0u ||
        cfg->render_timestamp_valid != 0u)
        return 0;
    if (cfg->render_channels) {
        if (cfg->render_source_id == 0u ||
            cfg->render_source_id == cfg->capture_source_id ||
            cfg->render_epoch == 0u) return 0;
    } else if (cfg->render_source_id || cfg->render_epoch) {
        return 0;
    }
    for (i = 0u; i < 4u; ++i) {
        if (i >= n) {
            if (cfg->physical_to_capture_slot[i] != UINT32_MAX) return 0;
        } else {
            if (cfg->physical_to_capture_slot[i] >= n) return 0;
            for (j = 0u; j < i; ++j)
                if (cfg->physical_to_capture_slot[i] ==
                    cfg->physical_to_capture_slot[j]) return 0;
        }
    }
    return 1;
}

fe_s2_status fe_s2_layout(const fe_s2_config *cfg, uint32_t frames,
                          size_t *total_bytes, size_t *record_stride) {
    size_t samples, stride, total;
    if (!total_bytes || !record_stride || total_bytes == record_stride ||
        !config_ok(cfg) || frames == 0u || frames > FE_S2_MAX_FRAMES)
        return FE_S2_EINVAL;
    samples = (size_t)(cfg->rate_hz / 100u);
    stride = FE_S2_RECORD_META_BYTES +
             2u * samples * (cfg->physical_mics + cfg->render_channels) + 4u;
    if (stride < FE_S2_RECORD_META_BYTES ||
        stride > FE_S2_MAX_BYTES - FE_S2_HEADER_BYTES ||
        (size_t)frames > (FE_S2_MAX_BYTES - FE_S2_HEADER_BYTES) / stride)
        return FE_S2_EINVAL;
    total = FE_S2_HEADER_BYTES + (size_t)frames * stride;
    *total_bytes = total;
    *record_stride = stride;
    return FE_S2_OK;
}

static void encode_header(uint8_t *p, const fe_s2_config *cfg,
                          uint32_t frames, size_t total, size_t stride) {
    unsigned i;
    memset(p, 0, FE_S2_HEADER_BYTES);
    put32(p + 0u, FE_S2_MAGIC);
    put32(p + 4u, FE_S2_SCHEMA);
    put32(p + 8u, FE_S2_ENDIAN_TAG);
    put32(p + 12u, FE_S2_HEADER_BYTES);
    put32(p + 16u, (uint32_t)total);
    put32(p + 20u, frames);
    put32(p + 24u, cfg->rate_hz);
    put32(p + 28u, cfg->rate_hz / 100u);
    put32(p + 32u, cfg->physical_mics);
    put32(p + 36u, cfg->render_channels);
    put32(p + 40u, (uint32_t)stride);
    put32(p + 44u, (1u << cfg->physical_mics) - 1u);
    for (i = 0u; i < 4u; ++i)
        put32(p + 48u + 4u*i, cfg->physical_to_capture_slot[i]);
    put32(p + 64u, cfg->capture_source_id);
    put32(p + 68u, cfg->render_source_id);
    put32(p + 72u, cfg->capture_epoch);
    put32(p + 76u, cfg->render_epoch);
    /* [80,124) is zero, documenting UNKNOWN time and reserved bytes. */
    put32(p + 124u, crc32_bytes(p, 124u));
}

fe_s2_status fe_s2_writer_begin(fe_s2_writer *writer, uint8_t *buffer,
    size_t buffer_bytes, const fe_s2_config *cfg, uint32_t frames) {
    size_t total = 0u, stride = 0u;
    fe_s2_writer tmp;
    if (!writer || !buffer || !cfg ||
        fe_s2_layout(cfg, frames, &total, &stride) != FE_S2_OK ||
        buffer_bytes < total || buffer_bytes > FE_S2_MAX_BYTES ||
        !disjoint(writer, sizeof(*writer), buffer, buffer_bytes) ||
        !disjoint(cfg, sizeof(*cfg), buffer, buffer_bytes) ||
        !disjoint(writer, sizeof(*writer), cfg, sizeof(*cfg)))
        return FE_S2_EINVAL;
    memset(&tmp, 0, sizeof(tmp));
    tmp.output = buffer;
    tmp.capacity = buffer_bytes;
    tmp.total_bytes = total;
    tmp.record_stride = stride;
    tmp.config = *cfg;
    tmp.target_frames = frames;
    tmp.current_capture_epoch = cfg->capture_epoch;
    tmp.current_render_epoch = cfg->render_epoch;
    /* All rejection conditions have been checked before any mutation. */
    encode_header(buffer, cfg, frames, total, stride);
    *writer = tmp;
    return FE_S2_OK;
}

static int frame_valid(const fe_s2_config *cfg,
    uint64_t previous_seq, uint32_t capture_epoch, uint32_t render_epoch,
    uint64_t sequence, uint32_t cap_flags, uint32_t ren_flags,
    uint32_t cap_epoch_next, uint32_t ren_epoch_next,
    uint32_t cap_ts, uint32_t ren_ts) {
    int cap_gap, ren_gap;
    if (cap_ts || ren_ts || !sequence ||
        (cap_flags & ~(FE_S2_CAPTURE_GAP | FE_S2_CLOCK_RESET | FE_S2_XRUN)) ||
        (ren_flags & ~(FE_S2_RENDER_GAP | FE_S2_CLOCK_RESET | FE_S2_XRUN)))
        return 0;
    if (!cfg->render_channels && (ren_flags || ren_epoch_next))
        return 0;
    if (cfg->render_channels &&
        (!!(cap_flags & FE_S2_CLOCK_RESET) !=
         !!(ren_flags & FE_S2_CLOCK_RESET))) return 0;
    cap_gap = !!(cap_flags &
        (FE_S2_CAPTURE_GAP | FE_S2_CLOCK_RESET | FE_S2_XRUN));
    ren_gap = !!(ren_flags &
        (FE_S2_RENDER_GAP | FE_S2_CLOCK_RESET | FE_S2_XRUN));
    if ((cap_gap && capture_epoch == UINT32_MAX) ||
        (ren_gap && render_epoch == UINT32_MAX) ||
        cap_epoch_next != capture_epoch + (uint32_t)cap_gap ||
        ren_epoch_next != render_epoch + (uint32_t)ren_gap)
        return 0;
    if (previous_seq == 0u) return sequence == UINT64_C(1);
    if (previous_seq == UINT64_MAX || sequence <= previous_seq) return 0;
    if (sequence != previous_seq + 1u &&
        !(cap_gap && (!cfg->render_channels || ren_gap))) return 0;
    return 1;
}

fe_s2_status fe_s2_writer_append(fe_s2_writer *writer,
                                 const fe_s2_frame *frame) {
    size_t total = 0u, stride = 0u, ncap, nrender, i, pos;
    uint8_t *p;
    if (!writer || !frame || !writer->output ||
        fe_s2_layout(&writer->config, writer->target_frames,
                     &total, &stride) != FE_S2_OK ||
        total != writer->total_bytes || stride != writer->record_stride ||
        writer->capacity < total || writer->appended >= writer->target_frames ||
        !frame_valid(&writer->config, writer->last_sequence,
                     writer->current_capture_epoch,
                     writer->current_render_epoch,
                     frame->sequence, frame->capture_flags, frame->render_flags,
                     frame->capture_epoch, frame->render_epoch,
                     frame->capture_timestamp_valid,
                     frame->render_timestamp_valid))
        return FE_S2_EINVAL;
    ncap = (size_t)(writer->config.rate_hz / 100u) *
           writer->config.physical_mics;
    nrender = (size_t)(writer->config.rate_hz / 100u) *
              writer->config.render_channels;
    if (!frame->capture || frame->capture_count != ncap ||
        frame->render_count != nrender ||
        (nrender && !frame->render) || (!nrender && frame->render) ||
        !disjoint(writer->output, total, frame, sizeof(*frame)) ||
        !disjoint(writer->output, total, frame->capture,
                  ncap * sizeof(int16_t)) ||
        !disjoint(writer->output, total, frame->render,
                  nrender * sizeof(int16_t)) ||
        !disjoint(writer, sizeof(*writer), frame->capture,
                  ncap * sizeof(int16_t)) ||
        !disjoint(writer, sizeof(*writer), frame->render,
                  nrender * sizeof(int16_t)))
        return FE_S2_EINVAL;
    p = writer->output + FE_S2_HEADER_BYTES +
        writer->appended * writer->record_stride;
    memset(p, 0, FE_S2_RECORD_META_BYTES);
    put64(p, frame->sequence);
    put32(p + 8u, frame->capture_flags);
    put32(p + 12u, frame->render_flags);
    put32(p + 16u, frame->capture_epoch);
    put32(p + 20u, frame->render_epoch);
    pos = FE_S2_RECORD_META_BYTES;
    for (i = 0u; i < ncap; ++i) {
        uint16_t bits = (uint16_t)frame->capture[i];
        p[pos++] = (uint8_t)bits;
        p[pos++] = (uint8_t)(bits >> 8u);
    }
    for (i = 0u; i < nrender; ++i) {
        uint16_t bits = (uint16_t)frame->render[i];
        p[pos++] = (uint8_t)bits;
        p[pos++] = (uint8_t)(bits >> 8u);
    }
    put32(p + pos, crc32_bytes(p, pos));
    writer->last_sequence = frame->sequence;
    writer->current_capture_epoch = frame->capture_epoch;
    writer->current_render_epoch = frame->render_epoch;
    ++writer->appended;
    return FE_S2_OK;
}

fe_s2_status fe_s2_writer_finish(const fe_s2_writer *writer,
                                 size_t *completed_bytes) {
    size_t total = 0u, stride = 0u;
    if (!writer || !completed_bytes || !writer->output ||
        fe_s2_layout(&writer->config, writer->target_frames,
                     &total, &stride) != FE_S2_OK ||
        total != writer->total_bytes || stride != writer->record_stride ||
        writer->capacity < total ||
        !disjoint(completed_bytes, sizeof(*completed_bytes),
                  writer->output, total) ||
        !disjoint(completed_bytes, sizeof(*completed_bytes),
                  writer, sizeof(*writer)))
        return FE_S2_EINVAL;
    if (writer->appended != writer->target_frames)
        return FE_S2_EINCOMPLETE;
    *completed_bytes = total;
    return FE_S2_OK;
}

fe_s2_status fe_s2_decode(const uint8_t *bytes, size_t byte_count,
                          fe_s2_stream *out) {
    fe_s2_stream tmp;
    size_t total = 0u, stride = 0u, k;
    uint32_t frames, cepoch, repoch;
    uint64_t sequence = UINT64_C(0);
    unsigned i;
    if (!bytes || !out || byte_count < FE_S2_HEADER_BYTES ||
        byte_count > FE_S2_MAX_BYTES ||
        !disjoint(out, sizeof(*out), bytes, byte_count))
        return FE_S2_EINVAL;
    if (get32(bytes + 0u) != FE_S2_MAGIC ||
        get32(bytes + 4u) != FE_S2_SCHEMA ||
        get32(bytes + 8u) != FE_S2_ENDIAN_TAG ||
        get32(bytes + 12u) != FE_S2_HEADER_BYTES ||
        get32(bytes + 124u) != crc32_bytes(bytes, 124u))
        return FE_S2_EFORMAT;
    memset(&tmp, 0, sizeof(tmp));
    tmp.config.rate_hz = get32(bytes + 24u);
    tmp.config.physical_mics = get32(bytes + 32u);
    tmp.config.render_channels = get32(bytes + 36u);
    for (i = 0u; i < 4u; ++i)
        tmp.config.physical_to_capture_slot[i] =
            get32(bytes + 48u + 4u*i);
    tmp.config.capture_source_id = get32(bytes + 64u);
    tmp.config.render_source_id = get32(bytes + 68u);
    tmp.config.capture_epoch = get32(bytes + 72u);
    tmp.config.render_epoch = get32(bytes + 76u);
    tmp.config.clock_authority = get32(bytes + 80u);
    tmp.config.capture_timestamp_valid = get32(bytes + 84u);
    tmp.config.render_timestamp_valid = get32(bytes + 88u);
    frames = get32(bytes + 20u);
    if (fe_s2_layout(&tmp.config, frames, &total, &stride) != FE_S2_OK ||
        get32(bytes + 16u) != total || byte_count != total ||
        get32(bytes + 28u) != tmp.config.rate_hz / 100u ||
        get32(bytes + 40u) != stride ||
        get32(bytes + 44u) != ((1u << tmp.config.physical_mics) - 1u) ||
        get32(bytes + 92u) != 0u)
        return FE_S2_EFORMAT;
    for (i = 96u; i < 124u; ++i)
        if (bytes[i] != 0u) return FE_S2_EFORMAT;
    cepoch = tmp.config.capture_epoch;
    repoch = tmp.config.render_epoch;
    for (k = 0u; k < frames; ++k) {
        const uint8_t *p = bytes + FE_S2_HEADER_BYTES + k*stride;
        uint64_t seq = get64(p);
        uint32_t cap_flags = get32(p + 8u), ren_flags = get32(p + 12u);
        if (get32(p + stride - 4u) != crc32_bytes(p, stride - 4u) ||
            !frame_valid(&tmp.config, sequence, cepoch, repoch,
                         seq, cap_flags, ren_flags, get32(p + 16u),
                         get32(p + 20u), get32(p + 24u), get32(p + 28u)))
            return FE_S2_EFORMAT;
        sequence = seq;
        cepoch = get32(p + 16u);
        repoch = get32(p + 20u);
    }
    tmp.frames = frames;
    tmp.record_stride = stride;
    tmp.total_bytes = total;
    *out = tmp;
    return FE_S2_OK;
}

fe_s2_status fe_s2_replay(const uint8_t *bytes, size_t byte_count,
    fe_s2_visitor visitor, void *context, fe_s2_stream *out) {
    fe_s2_stream stream;
    size_t ncap, nrender, k;
    /* The source bytes must remain immutable even after replay succeeds.
     * Decode uses a private result, so additionally reject a caller result
     * that aliases any byte of the original APX3 file before callbacks run.
     */
    if (out && !disjoint(out, sizeof(*out), bytes, byte_count))
        return FE_S2_EINVAL;
    if (!visitor || fe_s2_decode(bytes, byte_count, &stream) != FE_S2_OK)
        return FE_S2_EFORMAT;
    ncap = (size_t)(stream.config.rate_hz / 100u) *
           stream.config.physical_mics * 2u;
    nrender = (size_t)(stream.config.rate_hz / 100u) *
              stream.config.render_channels * 2u;
    for (k = 0u; k < stream.frames; ++k) {
        const uint8_t *p = bytes + FE_S2_HEADER_BYTES +
                           k * stream.record_stride;
        const uint8_t *mic = p + FE_S2_RECORD_META_BYTES;
        const uint8_t *ref = nrender ? mic + ncap : NULL;
        if (visitor(&stream, (uint32_t)k, get64(p), get32(p + 8u),
                    get32(p + 12u), mic, ncap, ref, nrender, context) != 0)
            return FE_S2_EVISITOR;
    }
    if (out) *out = stream;
    return FE_S2_OK;
}
