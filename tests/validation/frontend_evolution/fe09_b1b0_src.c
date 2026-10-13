/* FE09-R2B1B-S0: no new SRC kernel. Links the unchanged first-party
 * src/frontend/ap_resampler.c in BANDLIMITED mode, using ONLY stream 0
 * of one separately owned ap_resampler_state_t per physical mic/render.
 */
#include "fe09_b1b0_src.h"
#include "frontend/ap_resampler.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifndef AP_BUILD_RESAMPLER_BANDLIMITED
#error "B1B0 qualification must use the existing first-party BANDLIMITED SRC"
#endif
#ifdef __FAST_MATH__
#error "B1B0 source and output fingerprint boundaries need strict math"
#endif

#define FE_B1B0_MAGIC UINT32_C(0x42314230)
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

struct fe_b1b0_src {
    uint32_t magic, input_rate, input_frames, n, render, mask, slot[4];
    size_t allocated;
    uint64_t accepted, cap_epoch, ref_epoch, clock_epoch;
    uint64_t cap_frames_epoch, ref_frames_epoch;
    uint64_t mic_hash[FE_B1B0_MAX_MICS], render_hash;
    ap_resampler_state_t histories[]; /* n independent physical + optional DAC */
};

static int count_ok(uint32_t n) {
    return n == 1u || n == 2u || n == 4u;
}

static int rate_ok(uint32_t hz) {
    return hz == 16000u || hz == 32000u || hz == 48000u;
}

static int mask_ok(uint32_t n, uint32_t mask) {
    return count_ok(n) && mask != 0u &&
           (mask & ~((1u << n) - 1u)) == 0u;
}

static size_t align_up(size_t n) {
    return (n + FE_B1B0_ALIGNMENT - 1u) &
           ~(size_t)(FE_B1B0_ALIGNMENT - 1u);
}

static size_t by_count(uint32_t n, uint32_t ref) {
    size_t size;
    const size_t head = offsetof(fe_b1b0_src, histories);
    if (!count_ok(n) || ref > 1u ||
        (size_t)n + (size_t)ref > (SIZE_MAX - head) / sizeof(ap_resampler_state_t))
        return 0u;
    size = head + ((size_t)n + (size_t)ref) * sizeof(ap_resampler_state_t);
    if (size > SIZE_MAX - (FE_B1B0_ALIGNMENT - 1u)) return 0u;
    return align_up(size);
}

static int intersects(const void *a, size_t na, const void *b, size_t nb) {
    const uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || na == 0u || nb == 0u) return 0;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 1;
    return x < y + nb && y < x + na;
}

static int config_ok(const fe_b1b0_config *c) {
    uint32_t i, seen = 0u;
    if (!c || c->struct_size != sizeof(*c) ||
        c->api_version != FE_B1B0_VERSION ||
        !rate_ok(c->capture_and_render_rate_hz) ||
        !ap_supported_io_rate(c->capture_and_render_rate_hz) ||
        c->frame_ms != FE_B1B0_FRAME_MS ||
        !count_ok(c->physical_mics) ||
        c->render_channels > 1u ||
        !mask_ok(c->physical_mics, c->active_mic_mask) ||
        c->capture_clock_authority != 0u) return 0;
    for (i = 0u; i < 4u; ++i) {
        if (c->reserved[i]) return 0;
        if (i >= c->physical_mics) {
            if (c->physical_to_capture_slot[i]) return 0;
        } else {
            const uint32_t slot = c->physical_to_capture_slot[i];
            if (slot >= c->physical_mics || (seen & (1u << slot))) return 0;
            seen |= 1u << slot;
        }
    }
    return seen == (1u << c->physical_mics) - 1u;
}

size_t fe_b1b0_state_bytes(const fe_b1b0_config *c) {
    return config_ok(c) ? by_count(c->physical_mics, c->render_channels) : 0u;
}

static int state_ok(const fe_b1b0_src *s) {
    uint32_t i, seen = 0u;
    if (!s || s->magic != FE_B1B0_MAGIC ||
        !rate_ok(s->input_rate) || s->input_frames != s->input_rate / 100u ||
        !count_ok(s->n) || s->render > 1u || !mask_ok(s->n, s->mask) ||
        s->allocated != by_count(s->n, s->render)) return 0;
    for (i = 0u; i < s->n; ++i) {
        if (s->slot[i] >= s->n || (seen & (1u << s->slot[i]))) return 0;
        seen |= 1u << s->slot[i];
    }
    return seen == (1u << s->n) - 1u;
}

fe_b1b0_status fe_b1b0_init(void *memory, size_t memory_size,
                            const fe_b1b0_config *c, fe_b1b0_src **out) {
    fe_b1b0_src *s;
    size_t requested;
    uint32_t i;
    if (!out || intersects(memory, memory_size, out, sizeof(*out)) ||
        (c && intersects(c, sizeof(*c), out, sizeof(*out))))
        return FE_B1B0_EINVAL;
    *out = NULL;
    requested = fe_b1b0_state_bytes(c);
    if (!memory || !requested ||
        ((uintptr_t)memory % FE_B1B0_ALIGNMENT) != 0u ||
        intersects(memory, memory_size, c, sizeof(*c)))
        return FE_B1B0_EINVAL;
    if (memory_size < requested) return FE_B1B0_ENOMEM;
    memset(memory, 0, requested);
    s = (fe_b1b0_src *)memory;
    s->magic = FE_B1B0_MAGIC;
    s->input_rate = c->capture_and_render_rate_hz;
    s->input_frames = s->input_rate / 100u;
    s->n = c->physical_mics;
    s->render = c->render_channels;
    s->mask = c->active_mic_mask;
    s->allocated = requested;
    memcpy(s->slot, c->physical_to_capture_slot, sizeof(s->slot));
    for (i = 0u; i < s->n + s->render; ++i)
        ap_resampler_init(&s->histories[i]);
    for (i = 0u; i < s->n; ++i) s->mic_hash[i] = FNV_OFFSET;
    s->render_hash = s->render ? FNV_OFFSET : 0u;
    *out = s;
    return FE_B1B0_OK;
}

static uint64_t hash_float(uint64_t h, float v) {
    uint32_t bits, k;
    memcpy(&bits, &v, sizeof(bits));
    for (k = 0u; k < 4u; ++k)
        h = (h ^ (uint8_t)(bits >> (8u * k))) * FNV_PRIME;
    return h;
}

fe_b1b0_status fe_b1b0_process(fe_b1b0_src *s,
                               const int16_t *capture, size_t capture_scalars,
                               const int16_t *render, size_t render_scalars,
                               float *mic_output, size_t mic_output_scalars,
                               float *render_output, size_t render_output_scalars) {
    size_t cap, ref, cap_bytes, ref_bytes, mic_bytes, refout_bytes;
    uint32_t p, k;
    if (!state_ok(s)) return FE_B1B0_ESTATE;
    cap = (size_t)s->input_frames * s->n;
    ref = (size_t)s->input_frames * s->render;
    if (!capture || !mic_output || capture_scalars != cap ||
        mic_output_scalars != (size_t)s->n * FE_B1B0_INTERNAL_FRAMES ||
        render_scalars != ref ||
        render_output_scalars != (size_t)s->render * FE_B1B0_INTERNAL_FRAMES ||
        (ref ? (!render || !render_output) : (render || render_output)) ||
        s->accepted == UINT64_MAX || s->cap_frames_epoch == UINT64_MAX ||
        (s->render && s->ref_frames_epoch == UINT64_MAX))
        return FE_B1B0_EINVAL;
    cap_bytes = cap * sizeof(int16_t);
    ref_bytes = ref * sizeof(int16_t);
    mic_bytes = mic_output_scalars * sizeof(float);
    refout_bytes = render_output_scalars * sizeof(float);
    if (intersects(capture, cap_bytes, mic_output, mic_bytes) ||
        intersects(capture, cap_bytes, s, s->allocated) ||
        intersects(mic_output, mic_bytes, s, s->allocated) ||
        (ref && (intersects(render, ref_bytes, capture, cap_bytes) ||
                 intersects(render, ref_bytes, mic_output, mic_bytes) ||
                 intersects(render, ref_bytes, s, s->allocated) ||
                 intersects(render_output, refout_bytes, capture, cap_bytes) ||
                 intersects(render_output, refout_bytes, mic_output, mic_bytes) ||
                 intersects(render_output, refout_bytes, render, ref_bytes) ||
                 intersects(render_output, refout_bytes, s, s->allocated))))
        return FE_B1B0_EINVAL;

    /* Validation is complete; first-party original SRC is void/no-failure
     * on the strictly bounded prevalidated stream=0/rate/frame geometry.
     */
    for (p = 0u; p < s->n; ++p) {
        float *output = mic_output + (size_t)p * FE_B1B0_INTERNAL_FRAMES;
        uint64_t hash = s->mic_hash[p];
        ap_resample_input_channel(&s->histories[p], 0u, capture,
                                  s->input_frames, s->n, s->slot[p],
                                  output, FE_B1B0_INTERNAL_FRAMES);
        if ((s->mask & (1u << p)) == 0u)
            memset(output, 0, FE_B1B0_INTERNAL_FRAMES * sizeof(float));
        for (k = 0u; k < FE_B1B0_INTERNAL_FRAMES; ++k)
            hash = hash_float(hash, output[k]);
        s->mic_hash[p] = hash;
    }
    if (s->render) {
        uint64_t hash = s->render_hash;
        ap_resample_input_channel(&s->histories[s->n], 0u, render,
                                  s->input_frames, 1u, 0u,
                                  render_output, FE_B1B0_INTERNAL_FRAMES);
        for (k = 0u; k < FE_B1B0_INTERNAL_FRAMES; ++k)
            hash = hash_float(hash, render_output[k]);
        s->render_hash = hash;
        ++s->ref_frames_epoch;
    }
    ++s->accepted;
    ++s->cap_frames_epoch;
    return FE_B1B0_OK;
}

fe_b1b0_status fe_b1b0_set_active_mask(fe_b1b0_src *s, uint32_t mask) {
    if (!state_ok(s)) return FE_B1B0_ESTATE;
    if (!mask_ok(s->n, mask)) return FE_B1B0_EINVAL;
    s->mask = mask;
    return FE_B1B0_OK;
}

fe_b1b0_status fe_b1b0_notify_gap(fe_b1b0_src *s, uint32_t flags) {
    uint32_t i;
    int cap, ref, clock;
    const uint32_t valid_flags = FE_B1B0_CAPTURE_GAP | FE_B1B0_RENDER_GAP |
                                 FE_B1B0_CLOCK_RESET;
    if (!state_ok(s)) return FE_B1B0_ESTATE;
    if (!flags || (flags & ~valid_flags) ||
        ((flags & FE_B1B0_RENDER_GAP) && !s->render)) return FE_B1B0_EINVAL;
    cap = (flags & (FE_B1B0_CAPTURE_GAP | FE_B1B0_CLOCK_RESET)) != 0u;
    ref = s->render &&
          (flags & (FE_B1B0_RENDER_GAP | FE_B1B0_CLOCK_RESET)) != 0u;
    clock = (flags & FE_B1B0_CLOCK_RESET) != 0u;
    if ((cap && s->cap_epoch == UINT64_MAX) ||
        (ref && s->ref_epoch == UINT64_MAX) ||
        (clock && s->clock_epoch == UINT64_MAX))
        return FE_B1B0_EINVAL;
    if (cap) {
        for (i = 0u; i < s->n; ++i) {
            ap_resampler_reset(&s->histories[i]);
            s->mic_hash[i] = FNV_OFFSET;
        }
        ++s->cap_epoch;
        s->cap_frames_epoch = 0u;
    }
    if (ref) {
        ap_resampler_reset(&s->histories[s->n]);
        s->render_hash = FNV_OFFSET;
        ++s->ref_epoch;
        s->ref_frames_epoch = 0u;
    }
    if (clock) ++s->clock_epoch;
    return FE_B1B0_OK;
}

fe_b1b0_status fe_b1b0_reset(fe_b1b0_src *s) {
    uint32_t i;
    if (!state_ok(s)) return FE_B1B0_ESTATE;
    for (i = 0u; i < s->n + s->render; ++i)
        ap_resampler_reset(&s->histories[i]);
    for (i = 0u; i < s->n; ++i) s->mic_hash[i] = FNV_OFFSET;
    s->render_hash = s->render ? FNV_OFFSET : 0u;
    s->accepted = s->cap_epoch = s->ref_epoch = s->clock_epoch = 0u;
    s->cap_frames_epoch = s->ref_frames_epoch = 0u;
    return FE_B1B0_OK;
}

fe_b1b0_status fe_b1b0_get_info(const fe_b1b0_src *s, fe_b1b0_info *out) {
    uint32_t i;
    if (!state_ok(s) || !out ||
        intersects(s, s ? s->allocated : 0u, out, sizeof(*out)))
        return FE_B1B0_EINVAL;
    memset(out, 0, sizeof(*out));
    out->requested_state_bytes = s->allocated;
    out->first_party_src_state_bytes_per_stream = sizeof(ap_resampler_state_t);
    out->input_rate_hz = s->input_rate;
    out->capture_frame_samples = s->input_frames;
    out->internal_frame_samples = FE_B1B0_INTERNAL_FRAMES;
    out->existing_first_party_filter_delay_samples =
        ap_resampler_filter_delay_samples(s->input_frames,
                                          FE_B1B0_INTERNAL_FRAMES);
    out->physical_mics = s->n;
    out->render_channels = s->render;
    out->active_mic_mask = s->mask;
    out->accepted_frames = s->accepted;
    out->capture_epoch = s->cap_epoch;
    out->render_epoch = s->ref_epoch;
    out->clock_epoch = s->clock_epoch;
    out->capture_frames_in_epoch = s->cap_frames_epoch;
    out->render_frames_in_epoch = s->ref_frames_epoch;
    for (i = 0u; i < s->n; ++i) out->mic_output_hash[i] = s->mic_hash[i];
    out->render_output_hash = s->render_hash;
    return FE_B1B0_OK;
}
