/* FE09-R2B1B-S1: noninstalled, one real first-party SRC + one real array BF.
 * This is routing/functional research, never a public SDK or real-array gain.
 */
#include "fe09_b1b1_single_bf.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

#ifdef __FAST_MATH__
#error "S1 requires exact finite checks; fast math is not qualified"
#endif

#define B1B1_MAGIC UINT32_C(0x42314231)

struct fe_b1b1 {
    uint32_t magic, rate, n, render, mask;
    size_t allocated, source_offset, array_offset, source_bytes, array_bytes;
    uint64_t accepted, clips;
    fe_b1b0_src *source;
    fe_array *array;
};

static int intersects(const void *a, size_t na, const void *b, size_t nb) {
    const uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || na == 0u || nb == 0u) return 0;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 1;
    return x < y + nb && y < x + na;
}

static size_t align16(size_t value) {
    if (value > SIZE_MAX - (FE_B1B1_ALIGNMENT - 1u)) return 0u;
    return (value + (FE_B1B1_ALIGNMENT - 1u)) &
           ~(size_t)(FE_B1B1_ALIGNMENT - 1u);
}

static int config_ok(const fe_b1b1_config *cfg) {
    uint32_t i;
    if (!cfg || !fe_b1b0_state_bytes(&cfg->ingress) ||
        (cfg->ingress.physical_mics != 1u &&
         cfg->ingress.physical_mics != 2u &&
         cfg->ingress.physical_mics != 4u) ||
        cfg->array.sample_rate_hz != FE_B1B0_INTERNAL_HZ ||
        cfg->array.mic_count != cfg->ingress.physical_mics ||
        cfg->array.active_mask != cfg->ingress.active_mic_mask ||
        cfg->array.interpolation != FE_ARRAY_FIR33_HANN ||
        !fe_array_state_bytes_for_mode(cfg->array.mic_count,
                                       FE_ARRAY_FIR33_HANN))
        return 0;
    for (i = 0u; i < cfg->ingress.physical_mics; ++i) {
        if (cfg->array.microphones[i].input_channel != i ||
            cfg->array.microphones[i].gain != 1.0 ||
            cfg->array.microphones[i].latency_samples != 0.0)
            return 0;
    }
    return 1;
}

static size_t sizes(const fe_b1b1_config *c, size_t *source_offset,
                    size_t *array_offset, size_t *src, size_t *arr) {
    size_t head, offset, total;
    if (!config_ok(c)) return 0u;
    *src = fe_b1b0_state_bytes(&c->ingress);
    *arr = fe_array_state_bytes_for_mode(c->array.mic_count,
                                         FE_ARRAY_FIR33_HANN);
    head = align16(sizeof(fe_b1b1));
    if (!head || *src > SIZE_MAX - head) return 0u;
    offset = align16(head + *src);
    if (!offset || *arr > SIZE_MAX - offset) return 0u;
    total = align16(offset + *arr);
    if (!total) return 0u;
    *source_offset = head;
    *array_offset = offset;
    return total;
}

size_t fe_b1b1_state_bytes(const fe_b1b1_config *cfg) {
    size_t x, y, s, a;
    return sizes(cfg, &x, &y, &s, &a);
}

size_t fe_b1b1_work_bytes(const fe_b1b1_config *cfg) {
    size_t state = fe_b1b1_state_bytes(cfg);
    size_t samples;
    if (!state) return 0u;
    /* State backup + physical-major + interleaved + ref + BF temp Float32. */
    samples = (size_t)(2u * cfg->ingress.physical_mics + 2u) *
              FE_B1B1_INTERNAL_FRAMES;
    if (samples > (SIZE_MAX - state) / sizeof(float)) return 0u;
    return align16(state + samples * sizeof(float));
}

fe_b1b1_status fe_b1b1_init(void *memory, size_t bytes,
                            const fe_b1b1_config *cfg, fe_b1b1 **out) {
    size_t so = 0u, ao = 0u, ss = 0u, as = 0u;
    size_t total;
    fe_array *array = NULL;
    fe_b1b0_src *source = NULL;
    fe_b1b1 *s;
    unsigned char *p;
    if (!out || intersects(memory, bytes, out, sizeof(*out)) ||
        intersects(cfg, cfg ? sizeof(*cfg) : 0u, out, sizeof(*out)))
        return FE_B1B1_EINVAL;
    *out = NULL;
    total = sizes(cfg, &so, &ao, &ss, &as);
    if (!memory || !total || ((uintptr_t)memory % FE_B1B1_ALIGNMENT) ||
        intersects(memory, bytes, cfg, sizeof(*cfg)))
        return FE_B1B1_EINVAL;
    if (bytes < total) return FE_B1B1_ENOMEM;
    p = (unsigned char *)memory;
    /* First-party array validation is atomic on invalid geometry. On success
     * B1B0 input was fully validated via fe_b1b0_state_bytes above. */
    if (fe_array_init(p + ao, as, &cfg->array, &array) != FE_ARRAY_OK)
        return FE_B1B1_EINVAL;
    if (fe_b1b0_init(p + so, ss, &cfg->ingress, &source) != FE_B1B0_OK)
        return FE_B1B1_ESTATE;
    s = (fe_b1b1 *)memory;
    memset(s, 0, sizeof(*s));
    s->magic = B1B1_MAGIC;
    s->rate = cfg->ingress.capture_and_render_rate_hz;
    s->n = cfg->ingress.physical_mics;
    s->render = cfg->ingress.render_channels;
    s->mask = cfg->ingress.active_mic_mask;
    s->source_offset = so;
    s->array_offset = ao;
    s->source_bytes = ss;
    s->array_bytes = as;
    s->allocated = total;
    s->source = source;
    s->array = array;
    *out = s;
    return FE_B1B1_OK;
}

static int state_ok(const fe_b1b1 *s) {
    const unsigned char *p = (const unsigned char *)s;
    if (!s || s->magic != B1B1_MAGIC ||
        (s->n != 1u && s->n != 2u && s->n != 4u) ||
        s->render > 1u ||
        (s->rate != 16000u && s->rate != 32000u && s->rate != 48000u) ||
        !s->mask || (s->mask & ~((1u << s->n) - 1u)) ||
        s->source_offset < sizeof(*s) ||
        (s->source_offset % 16u) || (s->array_offset % 16u) ||
        s->array_offset < s->source_offset ||
        s->source_bytes > s->array_offset - s->source_offset ||
        s->array_bytes > SIZE_MAX - s->array_offset ||
        s->allocated < s->array_offset + s->array_bytes ||
        s->allocated > 65536u)
        return 0;
    return s->source == (const void *)(p + s->source_offset) &&
           s->array == (const void *)(p + s->array_offset);
}

static int authorities_agree(const fe_b1b1 *s, fe_b1b0_info *source,
                             fe_array_info *array) {
    if (!state_ok(s) ||
        fe_b1b0_get_info(s->source, source) != FE_B1B0_OK ||
        fe_array_get_info(s->array, array) != FE_ARRAY_OK)
        return 0;
    return source->physical_mics == s->n &&
           source->render_channels == s->render &&
           source->input_rate_hz == s->rate &&
           source->active_mic_mask == s->mask &&
           source->accepted_frames == s->accepted &&
           source->capture_clock_authority == 0u &&
           array->mic_count == s->n &&
           array->sample_rate_hz == 16000u &&
           array->active_mask == s->mask &&
           array->interpolation == FE_ARRAY_FIR33_HANN &&
           source->requested_state_bytes == s->source_bytes &&
           array->state_bytes == s->array_bytes;
}

fe_b1b1_status fe_b1b1_transpose_clamp(const float *major, size_t input_count,
    uint32_t n, float *inter, size_t output_count, uint64_t *clipped) {
    uint64_t count = 0u;
    size_t index;
    uint32_t k, mic;
    size_t bytes;
    if (!major || !inter || !clipped ||
        (n != 1u && n != 2u && n != 4u) ||
        input_count != (size_t)n * 160u || output_count != input_count)
        return FE_B1B1_EINVAL;
    bytes = input_count * sizeof(float);
    if (intersects(major, bytes, inter, bytes) ||
        intersects(major, bytes, clipped, sizeof(*clipped)) ||
        intersects(inter, bytes, clipped, sizeof(*clipped)))
        return FE_B1B1_EINVAL;
    for (index = 0u; index < input_count; ++index)
        if (!isfinite(major[index])) return FE_B1B1_EINVAL;
    for (k = 0u; k < 160u; ++k) {
        for (mic = 0u; mic < n; ++mic) {
            const float v = major[(size_t)mic * 160u + k];
            const float sat = v < -1.0f ? -1.0f :
                              (v > 1.0f ? 1.0f : v);
            if (sat != v) ++count;
            inter[(size_t)k * n + mic] = sat;
        }
    }
    *clipped = count;
    return FE_B1B1_OK;
}

fe_b1b1_status fe_b1b1_process(fe_b1b1 *s, const int16_t *capture,
    size_t capture_count, const int16_t *render, size_t render_count,
    float *beamformed, size_t beamformed_count,
    float *reference, size_t reference_count, void *work, size_t work_bytes) {
    fe_b1b0_info si;
    fe_array_info ai;
    const void *ptrs[6];
    size_t len[6], k, j;
    size_t cap, ref, scalars, needed;
    unsigned char *backup;
    float *major, *inter, *rtmp, *btmp;
    uint64_t clipped = 0u;
    if (!authorities_agree(s, &si, &ai)) return FE_B1B1_ESTATE;
    cap = (size_t)(s->rate / 100u) * s->n;
    ref = (size_t)(s->rate / 100u) * s->render;
    scalars = (size_t)s->n * FE_B1B1_INTERNAL_FRAMES;
    needed = s->allocated +
             (2u * scalars + 2u * FE_B1B1_INTERNAL_FRAMES) * sizeof(float);
    if (!capture || !beamformed || !work ||
        (uintptr_t)work % FE_B1B1_ALIGNMENT ||
        capture_count != cap || render_count != ref ||
        beamformed_count != 160u || reference_count != 160u * s->render ||
        (s->render ? (!render || !reference) : (render || reference)) ||
        work_bytes < needed || work_bytes > 1048576u ||
        s->accepted == UINT64_MAX ||
        s->clips > UINT64_MAX - scalars ||
        si.capture_frames_in_epoch == UINT64_MAX ||
        (s->render && si.render_frames_in_epoch == UINT64_MAX) ||
        ai.samples_processed > UINT64_MAX - FE_B1B1_INTERNAL_FRAMES)
        return FE_B1B1_EINVAL;
    ptrs[0] = s; ptrs[1] = work; ptrs[2] = capture;
    ptrs[3] = beamformed; ptrs[4] = render; ptrs[5] = reference;
    len[0] = s->allocated; len[1] = work_bytes;
    len[2] = cap * sizeof(int16_t);
    len[3] = 160u * sizeof(float);
    len[4] = ref * sizeof(int16_t);
    len[5] = (size_t)s->render * 160u * sizeof(float);
    for (k = 0u; k < 6u; ++k)
        for (j = k + 1u; j < 6u; ++j)
            if (intersects(ptrs[k], len[k], ptrs[j], len[j]))
                return FE_B1B1_EINVAL;
    backup = (unsigned char *)work;
    major = (float *)(void *)(backup + s->allocated);
    inter = major + scalars;
    rtmp = inter + scalars;
    btmp = rtmp + 160u;
    /* An unexpected internal failure cannot partially commit external output.
     * The full caller-owned state snapshot permits exact rollback on rejection.
     */
    memcpy(backup, s, s->allocated);
    if (fe_b1b0_process(s->source, capture, cap, render, ref,
                        major, scalars, s->render ? rtmp : NULL,
                        160u * s->render) != FE_B1B0_OK ||
        fe_b1b1_transpose_clamp(major, scalars, s->n,
                               inter, scalars, &clipped) != FE_B1B1_OK ||
        fe_array_process(s->array, inter, scalars, btmp, 160u) != FE_ARRAY_OK) {
        memcpy(s, backup, s->allocated);
        return FE_B1B1_ESTATE;
    }
    for (k = 0u; k < 160u; ++k) {
        if (!isfinite(btmp[k])) {
            memcpy(s, backup, s->allocated);
            return FE_B1B1_ESTATE;
        }
    }
    memcpy(beamformed, btmp, 160u * sizeof(float));
    if (s->render) memcpy(reference, rtmp, 160u * sizeof(float));
    s->clips += clipped;
    ++s->accepted;
    return FE_B1B1_OK;
}

fe_b1b1_status fe_b1b1_set_active_mask(fe_b1b1 *s, uint32_t mask) {
    fe_b1b0_info si;
    fe_array_info ai;
    if (!authorities_agree(s, &si, &ai)) return FE_B1B1_ESTATE;
    if (!mask || (mask & ~((1u << s->n) - 1u))) return FE_B1B1_EINVAL;
    if (fe_array_set_active_mask(s->array, mask) != FE_ARRAY_OK ||
        fe_b1b0_set_active_mask(s->source, mask) != FE_B1B0_OK)
        return FE_B1B1_ESTATE;
    s->mask = mask;
    return FE_B1B1_OK;
}

fe_b1b1_status fe_b1b1_notify_gap(fe_b1b1 *s, uint32_t flags) {
    fe_b1b0_info si;
    fe_array_info ai;
    uint32_t f = FE_B1B0_CAPTURE_GAP | FE_B1B0_RENDER_GAP |
                 FE_B1B0_CLOCK_RESET;
    if (!authorities_agree(s, &si, &ai)) return FE_B1B1_ESTATE;
    if (!flags || (flags & ~f) ||
        ((flags & FE_B1B0_RENDER_GAP) && !s->render) ||
        ((flags & (FE_B1B0_CAPTURE_GAP | FE_B1B0_CLOCK_RESET)) &&
         si.capture_epoch == UINT64_MAX) ||
        ((flags & (FE_B1B0_RENDER_GAP | FE_B1B0_CLOCK_RESET)) &&
         s->render && si.render_epoch == UINT64_MAX) ||
        ((flags & FE_B1B0_CLOCK_RESET) && si.clock_epoch == UINT64_MAX))
        return FE_B1B1_EINVAL;
    /* The first-party resets are nonfailing for a validated state. */
    if (fe_b1b0_notify_gap(s->source, flags) != FE_B1B0_OK)
        return FE_B1B1_ESTATE;
    if ((flags & (FE_B1B0_CAPTURE_GAP | FE_B1B0_CLOCK_RESET)) &&
        fe_array_reset(s->array) != FE_ARRAY_OK)
        return FE_B1B1_ESTATE;
    return FE_B1B1_OK;
}

fe_b1b1_status fe_b1b1_request_steer(fe_b1b1 *s,
                                      const double direction[3],
                                      uint32_t duration) {
    fe_b1b0_info si;
    fe_array_info ai;
    if (!authorities_agree(s, &si, &ai)) return FE_B1B1_ESTATE;
    if (!direction || intersects(s, s->allocated, direction,
                                  3u * sizeof(double))) return FE_B1B1_EINVAL;
    return fe_array_request_steer(s->array, direction, duration) ==
           FE_ARRAY_OK ? FE_B1B1_OK : FE_B1B1_EINVAL;
}

fe_b1b1_status fe_b1b1_reset(fe_b1b1 *s) {
    fe_b1b0_info si;
    fe_array_info ai;
    if (!authorities_agree(s, &si, &ai)) return FE_B1B1_ESTATE;
    if (fe_b1b0_reset(s->source) != FE_B1B0_OK ||
        fe_array_reset(s->array) != FE_ARRAY_OK) return FE_B1B1_ESTATE;
    s->accepted = s->clips = 0u;
    return FE_B1B1_OK;
}

fe_b1b1_status fe_b1b1_get_info(const fe_b1b1 *s, fe_b1b1_info *out) {
    fe_b1b0_info si;
    fe_array_info ai;
    if (!authorities_agree(s, &si, &ai)) return FE_B1B1_ESTATE;
    if (!out || intersects(s, s->allocated, out, sizeof(*out)))
        return FE_B1B1_EINVAL;
    memset(out, 0, sizeof(*out));
    out->state_bytes = s->allocated;
    out->work_bytes = s->allocated +
        (2u * (size_t)s->n + 2u) * 160u * sizeof(float);
    out->source_state_bytes = s->source_bytes;
    out->array_state_bytes = s->array_bytes;
    out->physical_mics = s->n;
    out->render_channels = s->render;
    out->input_rate_hz = s->rate;
    out->accepted_frames = s->accepted;
    out->clipped_samples = s->clips;
    out->source = si;
    out->array = ai;
    return FE_B1B1_OK;
}
