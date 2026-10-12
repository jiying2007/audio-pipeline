/* FE09-R2A nonshipping research adapter, not installed into public 2.x.
 * Single DSP authority: link array_native.c; do NOT fork FIR33 kernels.
 * Render is an independent observed reference, NOT an AEC implementation.
 */
#include "fe09_array_sdk_draft_r2a.h"
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#if defined(__FAST_MATH__)
#error "R2A source validation and clipping require strict finite math"
#endif

#define R2A_MAGIC UINT32_C(0x52324131)
#define R2A_FNV_OFFSET UINT64_C(14695981039346656037)
#define R2A_FNV_PRIME UINT64_C(1099511628211)
#define R2A_ALIGN_UP(x) (((x) + (FE_R2A_ALIGNMENT - 1u)) & ~(size_t)(FE_R2A_ALIGNMENT - 1u))

struct fe_r2a_adapter {
    uint32_t magic, physical_mics, render_channels, active_mask;
    size_t allocated_bytes, native_bytes;
    fe_array *core;
    uint64_t total_frames, capture_epoch, render_epoch;
    uint64_t observed_render_frames, clipped_samples, render_fnv64;
};

static int touches(const void *a, size_t n, const void *b, size_t m) {
    const uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || n > UINTPTR_MAX - x || m > UINTPTR_MAX - y) return 1;
    return x < y + m && y < x + n;
}
static int valid(const fe_r2a_adapter *state) {
    return state && state->magic == R2A_MAGIC &&
        (state->physical_mics == 1u || state->physical_mics == 2u ||
         state->physical_mics == 4u) &&
        state->render_channels <= 1u &&
        state->core && state->native_bytes != 0u &&
        state->allocated_bytes >= R2A_ALIGN_UP(sizeof(*state)) + state->native_bytes;
}
static int basic_cfg(const fe_r2a_config *cfg) {
    if (!cfg || cfg->struct_size != sizeof(*cfg) ||
        cfg->api_version != FE_R2A_DRAFT_VERSION ||
        cfg->sample_rate_hz != FE_R2A_RATE_HZ || cfg->frame_ms != FE_R2A_FRAME_MS ||
        (cfg->physical_mics != 1u && cfg->physical_mics != 2u &&
         cfg->physical_mics != 4u) ||
        cfg->render_channels > 1u ||
        cfg->reference_mic >= cfg->physical_mics ||
        !cfg->active_mic_mask ||
        (cfg->active_mic_mask & ~((1u << cfg->physical_mics) - 1u)) ||
        cfg->capture_clock_authority != 0u) return 0;
    return 1;
}
static fe_array_config to_native(const fe_r2a_config *cfg) {
    fe_array_config native;
    memset(&native, 0, sizeof(native));
    native.sample_rate_hz = cfg->sample_rate_hz;
    native.mic_count = cfg->physical_mics;
    native.reference_mic = cfg->reference_mic;
    native.active_mask = cfg->active_mic_mask;
    native.interpolation = FE_ARRAY_FIR33_HANN;
    memcpy(native.direction, cfg->source_direction, sizeof(native.direction));
    memcpy(native.microphones, cfg->microphones, sizeof(native.microphones));
    return native;
}
size_t fe_r2a_state_bytes(const fe_r2a_config *cfg) {
    size_t native;
    if (!basic_cfg(cfg)) return 0u;
    native = fe_array_state_bytes_for_mode(cfg->physical_mics, FE_ARRAY_FIR33_HANN);
    if (!native || native > SIZE_MAX - R2A_ALIGN_UP(sizeof(fe_r2a_adapter))) return 0u;
    return R2A_ALIGN_UP(sizeof(fe_r2a_adapter)) + native;
}
fe_r2a_status fe_r2a_init(void *memory, size_t bytes, const fe_r2a_config *cfg,
                           fe_r2a_adapter **out) {
    const size_t need = fe_r2a_state_bytes(cfg);
    const size_t header = R2A_ALIGN_UP(sizeof(fe_r2a_adapter));
    fe_array_config native;
    fe_array *core = NULL;
    fe_r2a_adapter *state;
    fe_array_status status;
    if (!out || (memory && touches(memory, bytes, out, sizeof(*out))) ||
        (cfg && touches(cfg, sizeof(*cfg), out, sizeof(*out))))
        return FE_R2A_EINVAL;
    *out = NULL;
    if (!memory || !need || ((uintptr_t)memory % FE_R2A_ALIGNMENT) != 0u ||
        (cfg && touches(memory, bytes, cfg, sizeof(*cfg))))
        return FE_R2A_EINVAL;
    if (bytes < need) return FE_R2A_ENOMEM;
    native = to_native(cfg);
    /* Native validates complete geometry/slot/finite/coefficient safety
     * before touching its caller-owned memory. */
    status = fe_array_init((unsigned char *)memory + header, need - header,
                           &native, &core);
    if (status != FE_ARRAY_OK) return FE_R2A_EINVAL;
    memset(memory, 0, header);
    state = (fe_r2a_adapter *)memory;
    state->magic = R2A_MAGIC;
    state->physical_mics = cfg->physical_mics;
    state->render_channels = cfg->render_channels;
    state->active_mask = cfg->active_mic_mask;
    state->allocated_bytes = need;
    state->native_bytes = need - header;
    state->core = core;
    state->render_fnv64 = R2A_FNV_OFFSET;
    *out = state;
    return FE_R2A_OK;
}
static void hash_s16(uint64_t *hash, int16_t sample) {
    const uint16_t x = (uint16_t)sample;
    *hash = (*hash ^ (uint8_t)(x & 255u)) * R2A_FNV_PRIME;
    *hash = (*hash ^ (uint8_t)(x >> 8u)) * R2A_FNV_PRIME;
}
static int16_t to_s16(float x, uint64_t *clipped) {
    long quantized;
    if (x >= 1.0f) { if (x > 1.0f) ++*clipped; return INT16_MAX; }
    if (x <= -1.0f) { if (x < -1.0f) ++*clipped; return INT16_MIN; }
    quantized = lrintf(x * 32768.0f);
    if (quantized > INT16_MAX) { ++*clipped; return INT16_MAX; }
    if (quantized < INT16_MIN) { ++*clipped; return INT16_MIN; }
    return (int16_t)quantized;
}
fe_r2a_status fe_r2a_process(fe_r2a_adapter *state,
                              const int16_t *capture_interleaved,
                              size_t capture_scalar_samples,
                              const int16_t *separate_render,
                              size_t render_scalar_samples,
                              int16_t *mono_output,
                              size_t mono_scalar_samples) {
    float mic_float[FE_R2A_FRAME_SAMPLES * FE_ARRAY_MAX_MICS];
    float mono_float[FE_R2A_FRAME_SAMPLES];
    uint64_t render_hash, clipped;
    size_t k;
    fe_array_status status;
    const size_t capture_required = valid(state) ?
        (size_t)FE_R2A_FRAME_SAMPLES * state->physical_mics : 0u;
    const size_t render_required = valid(state) ?
        (size_t)FE_R2A_FRAME_SAMPLES * state->render_channels : 0u;
    if (!valid(state)) return FE_R2A_ESTATE;
    if (!capture_interleaved || !mono_output ||
        capture_scalar_samples != capture_required ||
        mono_scalar_samples != FE_R2A_FRAME_SAMPLES ||
        render_scalar_samples != render_required ||
        (render_required ? !separate_render : separate_render != NULL) ||
        state->total_frames == UINT64_MAX ||
        state->observed_render_frames == UINT64_MAX)
        return FE_R2A_EINVAL;
    if (touches(capture_interleaved, capture_required * sizeof(int16_t),
                mono_output, mono_scalar_samples * sizeof(int16_t)) ||
        touches(capture_interleaved, capture_required * sizeof(int16_t),
                state, state->allocated_bytes) ||
        touches(mono_output, mono_scalar_samples * sizeof(int16_t),
                state, state->allocated_bytes) ||
        (render_required &&
         (touches(separate_render, render_required * sizeof(int16_t),
                  capture_interleaved, capture_required * sizeof(int16_t)) ||
          touches(separate_render, render_required * sizeof(int16_t),
                  mono_output, mono_scalar_samples * sizeof(int16_t)) ||
          touches(separate_render, render_required * sizeof(int16_t),
                  state, state->allocated_bytes))))
        return FE_R2A_EINVAL;
    for (k = 0u; k < capture_required; ++k)
        mic_float[k] = (float)capture_interleaved[k] / 32768.0f;
    status = fe_array_process(state->core, mic_float, capture_required,
                              mono_float, FE_R2A_FRAME_SAMPLES);
    if (status != FE_ARRAY_OK) return FE_R2A_ESTATE;
    render_hash = state->render_fnv64;
    for (k = 0u; k < render_required; ++k)
        hash_s16(&render_hash, separate_render[k]);
    clipped = state->clipped_samples;
    for (k = 0u; k < FE_R2A_FRAME_SAMPLES; ++k)
        mono_output[k] = to_s16(mono_float[k], &clipped);
    state->render_fnv64 = render_hash;
    state->clipped_samples = clipped;
    state->total_frames++;
    if (render_required) state->observed_render_frames++;
    return FE_R2A_OK;
}
fe_r2a_status fe_r2a_set_active_mask(fe_r2a_adapter *state, uint32_t mask) {
    if (!valid(state)) return FE_R2A_ESTATE;
    if (fe_array_set_active_mask(state->core, mask) != FE_ARRAY_OK)
        return FE_R2A_EINVAL;
    state->active_mask = mask;
    return FE_R2A_OK;
}
fe_r2a_status fe_r2a_request_steer(fe_r2a_adapter *state,
                                    const double direction[3],
                                    uint32_t duration_samples) {
    fe_array_status status;
    if (!valid(state)) return FE_R2A_ESTATE;
    status = fe_array_request_steer(state->core, direction, duration_samples);
    if (status == FE_ARRAY_EBUSY) return FE_R2A_EBUSY;
    return status == FE_ARRAY_OK ? FE_R2A_OK : FE_R2A_EINVAL;
}
fe_r2a_status fe_r2a_notify_gap(fe_r2a_adapter *state, uint32_t flags) {
    if (!valid(state)) return FE_R2A_ESTATE;
    if (!flags || (flags & ~(FE_R2A_CAPTURE_GAP | FE_R2A_RENDER_GAP)) ||
        ((flags & FE_R2A_RENDER_GAP) && !state->render_channels) ||
        state->capture_epoch == UINT64_MAX || state->render_epoch == UINT64_MAX)
        return FE_R2A_EINVAL;
    if (flags & FE_R2A_CAPTURE_GAP) {
        if (fe_array_reset(state->core) != FE_ARRAY_OK) return FE_R2A_ESTATE;
        state->capture_epoch++;
    }
    if (flags & FE_R2A_RENDER_GAP) state->render_epoch++;
    return FE_R2A_OK;
}
fe_r2a_status fe_r2a_reset(fe_r2a_adapter *state) {
    if (!valid(state)) return FE_R2A_ESTATE;
    if (fe_array_reset(state->core) != FE_ARRAY_OK) return FE_R2A_ESTATE;
    state->total_frames = 0u;
    state->capture_epoch = 0u;
    state->render_epoch = 0u;
    state->observed_render_frames = 0u;
    state->clipped_samples = 0u;
    state->render_fnv64 = R2A_FNV_OFFSET;
    return FE_R2A_OK;
}
fe_r2a_status fe_r2a_get_info(const fe_r2a_adapter *state, fe_r2a_info *out) {
    fe_array_info info;
    if (!valid(state) || !out || touches(out, sizeof(*out), state, state->allocated_bytes))
        return FE_R2A_EINVAL;
    if (fe_array_get_info(state->core, &info) != FE_ARRAY_OK) return FE_R2A_ESTATE;
    memset(out, 0, sizeof(*out));
    out->requested_state_bytes = state->allocated_bytes;
    out->native_fir33_state_bytes = state->native_bytes;
    out->physical_mics = state->physical_mics;
    out->render_channels = state->render_channels;
    out->active_mic_mask = state->active_mask;
    out->common_delay_samples = info.common_delay_samples;
    out->total_frames = state->total_frames;
    out->capture_epoch = state->capture_epoch;
    out->render_epoch = state->render_epoch;
    out->observed_render_frames = state->observed_render_frames;
    out->clipped_samples = state->clipped_samples;
    out->render_fnv64 = state->render_fnv64;
    return FE_R2A_OK;
}
