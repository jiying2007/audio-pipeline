#ifndef FE09_B2S2_PRIVATE_APD_H
#define FE09_B2S2_PRIVATE_APD_H

/* FE09-R2B2-S2, preregistration #760: NONINSTALLED first-party research.
 * APX3 is a private experimental APD-v2 identity; it is deliberately NOT
 * legacy APD2/v1. No public ABI, Linux runtime or physical clock authority.
 * All multibyte on-disk fields are explicitly little-endian.
 */
#include <stddef.h>
#include <stdint.h>

#define FE_S2_MAGIC UINT32_C(0x33585041) /* "APX3", not "APD2" */
#define FE_S2_SCHEMA 2u
#define FE_S2_ENDIAN_TAG UINT32_C(0x01020304)
#define FE_S2_HEADER_BYTES 128u
#define FE_S2_RECORD_META_BYTES 32u
#define FE_S2_MAX_FRAMES 128u
#define FE_S2_MAX_BYTES (1024u * 1024u)
#define FE_S2_MAX_SOURCE_SAMPLES 480u
#define FE_S2_MAX_CAPTURE_SAMPLES (4u * FE_S2_MAX_SOURCE_SAMPLES)
#define FE_S2_CAPTURE_GAP 1u
#define FE_S2_RENDER_GAP 2u
#define FE_S2_CLOCK_RESET 4u
#define FE_S2_XRUN 8u

typedef enum {
    FE_S2_OK = 0,
    FE_S2_EINVAL = -1,
    FE_S2_EFORMAT = -2,
    FE_S2_EINCOMPLETE = -3,
    FE_S2_EVISITOR = -4
} fe_s2_status;

typedef struct {
    uint32_t rate_hz; /* 16000, 32000 or 48000, exactly 10 ms */
    uint32_t physical_mics; /* 1, 2, 4 only */
    uint32_t render_channels; /* separate optional mono render */
    uint32_t physical_to_capture_slot[4]; /* bijection, inactive=UINT32_MAX */
    uint32_t capture_source_id; /* logical label; NOT a physical clock claim */
    uint32_t render_source_id; /* distinct logical label or zero if absent */
    uint32_t capture_epoch; /* nonzero source-local generation */
    uint32_t render_epoch; /* separate nonzero generation or zero if absent */
    uint32_t clock_authority; /* must be UNKNOWN=0 */
    uint32_t capture_timestamp_valid; /* must be 0 */
    uint32_t render_timestamp_valid; /* must be 0 */
} fe_s2_config;

typedef struct {
    uint64_t sequence; /* initial 1; otherwise contiguous or explicit gap */
    uint32_t capture_flags; /* CAPTURE_GAP | CLOCK_RESET | XRUN */
    uint32_t render_flags; /* RENDER_GAP | CLOCK_RESET | XRUN, or 0 if absent */
    uint32_t capture_epoch, render_epoch;
    uint32_t capture_timestamp_valid, render_timestamp_valid; /* both 0 */
    const int16_t *capture; /* physical capture-slot order, 10 ms */
    size_t capture_count;
    const int16_t *render; /* separate mono 10 ms, NULL if absent */
    size_t render_count;
} fe_s2_frame;

typedef struct {
    uint8_t *output;
    size_t capacity, total_bytes, record_stride;
    fe_s2_config config;
    uint32_t target_frames, appended;
    uint32_t current_capture_epoch, current_render_epoch;
    uint64_t last_sequence;
} fe_s2_writer;

typedef struct {
    fe_s2_config config;
    uint32_t frames;
    size_t record_stride, total_bytes;
} fe_s2_stream;

/* Callback only runs after the complete immutable stream validates.
 * PCM is little-endian bytes, NOT host-aligned int16_t*. A visitor error
 * may have caller-side effects, so such effects belong to the caller.
 * If non-NULL, the decoded output result must be disjoint from the entire
 * input file. An overlapping result fails before any visitor invocation.
 */
typedef int (*fe_s2_visitor)(
    const fe_s2_stream *stream, uint32_t index, uint64_t sequence,
    uint32_t capture_flags, uint32_t render_flags,
    const uint8_t *capture_le, size_t capture_bytes,
    const uint8_t *render_le, size_t render_bytes, void *context);

/* No allocations or I/O anywhere in this private codec. All failures
 * before a successful write preserve caller-owned bytes and state.
 * Format limits: 128 frames, 1 MiB, per-record CRC32, header CRC32.
 */
fe_s2_status fe_s2_layout(const fe_s2_config *config, uint32_t frames,
                          size_t *total_bytes, size_t *record_stride);
fe_s2_status fe_s2_writer_begin(
    fe_s2_writer *writer, uint8_t *buffer, size_t buffer_bytes,
    const fe_s2_config *config, uint32_t frames);
fe_s2_status fe_s2_writer_append(fe_s2_writer *writer, const fe_s2_frame *frame);
fe_s2_status fe_s2_writer_finish(
    const fe_s2_writer *writer, size_t *completed_bytes);
fe_s2_status fe_s2_decode(
    const uint8_t *bytes, size_t byte_count, fe_s2_stream *out);
fe_s2_status fe_s2_replay(
    const uint8_t *bytes, size_t byte_count, fe_s2_visitor visitor,
    void *context, fe_s2_stream *out);

#endif
