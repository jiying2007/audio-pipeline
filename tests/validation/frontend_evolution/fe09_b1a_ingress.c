/* FE09-R2B1A: research-only 16kHz capture/render ingress (NOT installed).
 * No FIR/BF/ASR/AEC/SRC algorithms: later B1-B must reuse the one existing
 * first-party DSP authority rather than copying or diverging from it.
 */
#include "fe09_b1a_ingress.h"
#include <limits.h>
#include <stdint.h>
#include <string.h>

#if defined(__FAST_MATH__)
#error "B1A strict source bounds require non-fast-math"
#endif

#define B1A_MAGIC UINT32_C(0x42314131)
#define B1A_FNV_OFFSET UINT64_C(14695981039346656037)
#define B1A_FNV_PRIME UINT64_C(1099511628211)

struct fe_b1a_ingress {
    uint32_t magic;
    uint32_t physical_mics;
    uint32_t render_channels;
    uint32_t active_mic_mask;
    uint32_t slots[FE_B1A_MAX_MICS];
    size_t requested_bytes;
    uint64_t accepted_frames;
    uint64_t capture_epoch;
    uint64_t render_epoch;
    uint64_t clock_epoch;
    uint64_t capture_frames_in_epoch;
    uint64_t render_frames_in_epoch;
    uint64_t stream_hash[]; /* N physical channels + optional render */
};

static int supported_mics(uint32_t n) {
    return n == 1u || n == 2u || n == 4u;
}

static int valid_mask(uint32_t mics, uint32_t mask) {
    return supported_mics(mics) && mask != 0u &&
        (mask & ~((1u << mics) - 1u)) == 0u;
}

static int intervals_overlap(const void *a, size_t n,
                             const void *b, size_t m) {
    uintptr_t x, y;
    if (!a || !b || n == 0u || m == 0u) return 0;
    x = (uintptr_t)a;
    y = (uintptr_t)b;
    if (n > UINTPTR_MAX - x || m > UINTPTR_MAX - y) return 1;
    return x < y + m && y < x + n;
}

static int config_ok(const fe_b1a_config *cfg) {
    uint32_t i, seen = 0u;
    if (!cfg || cfg->struct_size != sizeof(*cfg) ||
        cfg->api_version != FE_B1A_API_VERSION ||
        cfg->io_rate_hz != FE_B1A_RATE_HZ ||
        cfg->frame_ms != FE_B1A_FRAME_MS ||
        !supported_mics(cfg->physical_mics) ||
        cfg->render_channels > 1u ||
        !valid_mask(cfg->physical_mics, cfg->active_mic_mask) ||
        cfg->capture_clock_authority != 0u) return 0;
    for (i = 0u; i < 4u; ++i) {
        if (cfg->reserved[i] != 0u) return 0;
        if (i >= cfg->physical_mics) {
            if (cfg->physical_to_capture_slot[i] != 0u) return 0;
        } else {
            uint32_t slot = cfg->physical_to_capture_slot[i];
            if (slot >= cfg->physical_mics || (seen & (1u << slot))) return 0;
            seen |= 1u << slot;
        }
    }
    return seen == (1u << cfg->physical_mics) - 1u;
}

static size_t state_bytes_count(uint32_t n, uint32_t render) {
    const size_t align = FE_B1A_ALIGNMENT;
    size_t required;
    if (!supported_mics(n) || render > 1u) return 0u;
    if ((size_t)n + (size_t)render >
        (SIZE_MAX - sizeof(fe_b1a_ingress)) / sizeof(uint64_t))
        return 0u;
    required = sizeof(fe_b1a_ingress) +
               ((size_t)n + (size_t)render) * sizeof(uint64_t);
    if (required > SIZE_MAX - (align - 1u)) return 0u;
    return (required + align - 1u) & ~(align - 1u);
}

size_t fe_b1a_state_bytes(const fe_b1a_config *config) {
    if (!config_ok(config)) return 0u;
    return state_bytes_count(config->physical_mics, config->render_channels);
}

static int state_ok(const fe_b1a_ingress *s) {
    uint32_t i, seen = 0u;
    if (!s || s->magic != B1A_MAGIC || !supported_mics(s->physical_mics) ||
        s->render_channels > 1u ||
        !valid_mask(s->physical_mics, s->active_mic_mask) ||
        s->requested_bytes !=
            state_bytes_count(s->physical_mics, s->render_channels))
        return 0;
    for (i = 0u; i < s->physical_mics; ++i) {
        uint32_t slot = s->slots[i];
        if (slot >= s->physical_mics || (seen & (1u << slot))) return 0;
        seen |= 1u << slot;
    }
    return seen == (1u << s->physical_mics) - 1u;
}

fe_b1a_status fe_b1a_init(void *memory, size_t memory_bytes,
                          const fe_b1a_config *config, fe_b1a_ingress **out) {
    size_t need;
    fe_b1a_ingress *s;
    uint32_t k;
    if (!out || intervals_overlap(memory, memory_bytes, out, sizeof(*out)) ||
        (config && intervals_overlap(config, sizeof(*config),
                                     out, sizeof(*out))))
        return FE_B1A_EINVAL;
    *out = NULL;
    need = fe_b1a_state_bytes(config);
    if (!memory || !need || ((uintptr_t)memory % FE_B1A_ALIGNMENT) != 0u ||
        intervals_overlap(memory, memory_bytes, config, sizeof(*config)))
        return FE_B1A_EINVAL;
    if (memory_bytes < need) return FE_B1A_ENOMEM;
    memset(memory, 0, need);
    s = (fe_b1a_ingress *)memory;
    s->magic = B1A_MAGIC;
    s->physical_mics = config->physical_mics;
    s->render_channels = config->render_channels;
    s->active_mic_mask = config->active_mic_mask;
    memcpy(s->slots, config->physical_to_capture_slot, sizeof(s->slots));
    s->requested_bytes = need;
    for (k = 0u; k < s->physical_mics + s->render_channels; ++k)
        s->stream_hash[k] = B1A_FNV_OFFSET;
    *out = s;
    return FE_B1A_OK;
}

static uint64_t hash_s16(uint64_t value, int16_t sample) {
    const uint16_t x = (uint16_t)sample;
    value = (value ^ (uint8_t)(x & UINT16_C(255))) * B1A_FNV_PRIME;
    return (value ^ (uint8_t)(x >> 8u)) * B1A_FNV_PRIME;
}

fe_b1a_status fe_b1a_process(fe_b1a_ingress *s,
                             const int16_t *capture, size_t capture_samples,
                             const int16_t *render, size_t render_samples,
                             float *mic_output, size_t mic_output_samples,
                             float *render_output, size_t render_output_samples) {
    size_t capture_expected, render_expected;
    size_t cap_bytes, ref_bytes, mic_bytes, refout_bytes;
    uint32_t phys, k;
    if (!state_ok(s)) return FE_B1A_ESTATE;
    capture_expected = (size_t)s->physical_mics * FE_B1A_SAMPLES_PER_MIC;
    render_expected = (size_t)s->render_channels * FE_B1A_SAMPLES_PER_MIC;
    if (!capture || !mic_output ||
        capture_samples != capture_expected ||
        mic_output_samples != capture_expected ||
        render_samples != render_expected ||
        render_output_samples != render_expected ||
        (render_expected ? (!render || !render_output)
                         : (render || render_output)) ||
        s->accepted_frames == UINT64_MAX ||
        s->capture_frames_in_epoch == UINT64_MAX ||
        (render_expected && s->render_frames_in_epoch == UINT64_MAX))
        return FE_B1A_EINVAL;
    cap_bytes = capture_expected * sizeof(*capture);
    mic_bytes = capture_expected * sizeof(*mic_output);
    ref_bytes = render_expected * sizeof(*render);
    refout_bytes = render_expected * sizeof(*render_output);
    if (intervals_overlap(capture, cap_bytes, mic_output, mic_bytes) ||
        intervals_overlap(capture, cap_bytes, s, s->requested_bytes) ||
        intervals_overlap(mic_output, mic_bytes, s, s->requested_bytes) ||
        (render_expected &&
          (intervals_overlap(render, ref_bytes, s, s->requested_bytes) ||
           intervals_overlap(render_output, refout_bytes, s, s->requested_bytes) ||
           intervals_overlap(render, ref_bytes, capture, cap_bytes) ||
           intervals_overlap(render, ref_bytes, mic_output, mic_bytes) ||
           intervals_overlap(render_output, refout_bytes, capture, cap_bytes) ||
           intervals_overlap(render_output, refout_bytes, mic_output, mic_bytes) ||
           intervals_overlap(render, ref_bytes, render_output, refout_bytes))))
        return FE_B1A_EINVAL;

    /* No errors past this line: data-plane outputs and state commit together. */
    for (phys = 0u; phys < s->physical_mics; ++phys) {
        uint64_t hash = s->stream_hash[phys];
        const uint32_t slot = s->slots[phys];
        const int active = (s->active_mic_mask & (1u << phys)) != 0u;
        for (k = 0u; k < FE_B1A_SAMPLES_PER_MIC; ++k) {
            const int16_t value = active ?
                capture[(size_t)k * s->physical_mics + slot] : 0;
            mic_output[(size_t)phys * FE_B1A_SAMPLES_PER_MIC + k] =
                (float)value * (1.0f / 32768.0f);
            hash = hash_s16(hash, value);
        }
        s->stream_hash[phys] = hash;
    }
    if (render_expected) {
        uint64_t hash = s->stream_hash[s->physical_mics];
        for (k = 0u; k < FE_B1A_SAMPLES_PER_MIC; ++k) {
            const int16_t sample = render[k];
            render_output[k] = (float)sample * (1.0f / 32768.0f);
            hash = hash_s16(hash, sample);
        }
        s->stream_hash[s->physical_mics] = hash;
        s->render_frames_in_epoch++;
    }
    s->capture_frames_in_epoch++;
    s->accepted_frames++;
    return FE_B1A_OK;
}

fe_b1a_status fe_b1a_set_active_mask(fe_b1a_ingress *s, uint32_t mask) {
    if (!state_ok(s)) return FE_B1A_ESTATE;
    if (!valid_mask(s->physical_mics, mask)) return FE_B1A_EINVAL;
    s->active_mic_mask = mask;
    return FE_B1A_OK;
}

fe_b1a_status fe_b1a_notify_gap(fe_b1a_ingress *s, uint32_t flags) {
    uint32_t k;
    const uint32_t supported =
        FE_B1A_CAPTURE_GAP | FE_B1A_RENDER_GAP | FE_B1A_CLOCK_RESET;
    int cap, ref, clock;
    if (!state_ok(s)) return FE_B1A_ESTATE;
    if (!flags || (flags & ~supported) ||
        ((flags & FE_B1A_RENDER_GAP) && !s->render_channels))
        return FE_B1A_EINVAL;
    cap = (flags & (FE_B1A_CAPTURE_GAP | FE_B1A_CLOCK_RESET)) != 0u;
    ref = (flags & (FE_B1A_RENDER_GAP | FE_B1A_CLOCK_RESET)) != 0u &&
        s->render_channels != 0u;
    clock = (flags & FE_B1A_CLOCK_RESET) != 0u;
    if ((cap && s->capture_epoch == UINT64_MAX) ||
        (ref && s->render_epoch == UINT64_MAX) ||
        (clock && s->clock_epoch == UINT64_MAX))
        return FE_B1A_EINVAL;
    if (cap) {
        s->capture_epoch++;
        s->capture_frames_in_epoch = 0u;
        for (k = 0u; k < s->physical_mics; ++k)
            s->stream_hash[k] = B1A_FNV_OFFSET;
    }
    if (ref) {
        s->render_epoch++;
        s->render_frames_in_epoch = 0u;
        s->stream_hash[s->physical_mics] = B1A_FNV_OFFSET;
    }
    if (clock) s->clock_epoch++;
    return FE_B1A_OK;
}

fe_b1a_status fe_b1a_reset(fe_b1a_ingress *s) {
    uint32_t k;
    if (!state_ok(s)) return FE_B1A_ESTATE;
    s->accepted_frames = 0u;
    s->capture_epoch = 0u;
    s->render_epoch = 0u;
    s->clock_epoch = 0u;
    s->capture_frames_in_epoch = 0u;
    s->render_frames_in_epoch = 0u;
    for (k = 0u; k < s->physical_mics + s->render_channels; ++k)
        s->stream_hash[k] = B1A_FNV_OFFSET;
    return FE_B1A_OK;
}

fe_b1a_status fe_b1a_get_info(const fe_b1a_ingress *s, fe_b1a_info *out) {
    uint32_t k;
    if (!state_ok(s) || !out ||
        intervals_overlap(s, s ? s->requested_bytes : 0u, out, sizeof(*out)))
        return FE_B1A_EINVAL;
    memset(out, 0, sizeof(*out));
    out->requested_state_bytes = s->requested_bytes;
    out->physical_mics = s->physical_mics;
    out->render_channels = s->render_channels;
    out->active_mic_mask = s->active_mic_mask;
    out->capture_clock_authority = 0u;
    out->accepted_frames = s->accepted_frames;
    out->capture_epoch = s->capture_epoch;
    out->render_epoch = s->render_epoch;
    out->clock_epoch = s->clock_epoch;
    out->capture_frames_in_epoch = s->capture_frames_in_epoch;
    out->render_frames_in_epoch = s->render_frames_in_epoch;
    for (k = 0u; k < s->physical_mics; ++k)
        out->capture_stream_hash[k] = s->stream_hash[k];
    out->render_stream_hash = s->render_channels ?
        s->stream_hash[s->physical_mics] : 0u;
    return FE_B1A_OK;
}
