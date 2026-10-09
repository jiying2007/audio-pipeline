#include "mic_fault_control.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

#ifdef __FAST_MATH__
#error "FE06 hard signatures require finite-input validation"
#endif

#define FE_MIC_FAULT_MAGIC UINT32_C(0x464d4636)

static int disjoint(const void *a, size_t na, const void *b, size_t nb) {
    const uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 0;
    return x + na <= y || y + nb <= x;
}

int fe_mic_fault_init(fe_mic_fault_control *control) {
    if (!control) return -1;
    memset(control, 0, sizeof(*control));
    control->initialized = FE_MIC_FAULT_MAGIC;
    return 0;
}

int fe_mic_fault_observe(fe_mic_fault_control *control, const float *pcm,
                         size_t count, uint32_t active_mask,
                         fe_mic_fault_observation *observation) {
    double squares[FE_MIC_FAULT_CHANNELS] = {0.0};
    float first[FE_MIC_FAULT_CHANNELS] = {0.0f};
    unsigned zero[FE_MIC_FAULT_CHANNELS] = {1u, 1u, 1u, 1u};
    unsigned positive_rail[FE_MIC_FAULT_CHANNELS] = {1u, 1u, 1u, 1u};
    unsigned negative_rail[FE_MIC_FAULT_CHANNELS] = {1u, 1u, 1u, 1u};
    unsigned varies[FE_MIC_FAULT_CHANNELS] = {0u};
    uint32_t zero_bits = 0u, rail_bits = 0u, suspected = 0u, c;
    fe_mic_fault_observation result;
    size_t t;

    if (!control || control->initialized != FE_MIC_FAULT_MAGIC ||
        !pcm || !observation || count != FE_MIC_FAULT_FRAME_SAMPLES * FE_MIC_FAULT_CHANNELS ||
        !active_mask || (active_mask & ~FE_MIC_FAULT_ALL_MASK) != 0u ||
        control->complete_frames == UINT64_MAX ||
        !disjoint(control, sizeof(*control), pcm, count*sizeof(*pcm)) ||
        !disjoint(control, sizeof(*control), observation, sizeof(*observation)) ||
        !disjoint(pcm, count*sizeof(*pcm), observation, sizeof(*observation))) return -1;

    /* Validate the entire submitted frame before touching control/output. */
    for (t = 0u; t < FE_MIC_FAULT_FRAME_SAMPLES; ++t) {
        for (c = 0u; c < FE_MIC_FAULT_CHANNELS; ++c) {
            const float value = pcm[t*FE_MIC_FAULT_CHANNELS + c];
            if (!isfinite(value) || fabsf(value) > 1.0f) return -1;
            if (t == 0u) first[c] = value;
            else if (value != first[c]) varies[c] = 1u;
            if (value != 0.0f) zero[c] = 0u;
            if (value != 1.0f) positive_rail[c] = 0u;
            if (value != -1.0f) negative_rail[c] = 0u;
            squares[c] += (double)value*(double)value;
        }
    }
    for (c = 0u; c < FE_MIC_FAULT_CHANNELS; ++c) {
        unsigned others_active = 0u, others_not_rail = 0u;
        uint32_t other;
        const unsigned stuck_rail = positive_rail[c] || negative_rail[c];
        for (other = 0u; other < FE_MIC_FAULT_CHANNELS; ++other) {
            if (other == c) continue;
            if (squares[other] >= (double)FE_MIC_FAULT_FRAME_SAMPLES * 0.01 * 0.01 &&
                varies[other]) ++others_active;
            if (!(positive_rail[other] || negative_rail[other])) ++others_not_rail;
        }
        if (zero[c] && others_active >= 2u) {
            if (control->signature_zero_frames[c] < 3u) ++control->signature_zero_frames[c];
        } else control->signature_zero_frames[c] = 0u;
        if (stuck_rail && others_not_rail >= 2u) {
            if (control->signature_rail_frames[c] < 3u) ++control->signature_rail_frames[c];
        } else control->signature_rail_frames[c] = 0u;
        if (control->signature_zero_frames[c] == 3u) zero_bits |= UINT32_C(1) << c;
        if (control->signature_rail_frames[c] == 3u) rail_bits |= UINT32_C(1) << c;
    }
    suspected = (zero_bits | rail_bits) & active_mask;
    /* An all-channel mute request is never emitted. */
    if (suspected == active_mask) suspected = 0u;
    memset(&result, 0, sizeof(result));
    result.complete_frames = ++control->complete_frames;
    result.observed_mask = active_mask;
    result.proposed_mask = active_mask & ~suspected;
    result.newly_suspected_mask = suspected;
    result.zero_signature_mask = zero_bits;
    result.rail_signature_mask = rail_bits;
    *observation = result;
    return 0;
}
