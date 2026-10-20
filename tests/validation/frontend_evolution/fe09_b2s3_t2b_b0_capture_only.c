/* FE09 T2-B/B0 #771: first-party independent capture BF and Render SRC.
 * No duplicated resampler/FIR DSP, no recorder, no fabricated reference.
 */
#include "fe09_b2s3_t2b_b0_capture_only.h"
#include <stdint.h>
#include <string.h>

static int disjoint(const void *a, size_t na, const void *b, size_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    if (!a || !b || !na || !nb) return 1;
    if (na > UINTPTR_MAX - x || nb > UINTPTR_MAX - y) return 0;
    return x + na <= y || y + nb <= x;
}
static int rate_ok(uint32_t rate) {
    return rate == 16000u || rate == 32000u || rate == 48000u;
}
static int adapter_ok(const fe_t2b_b0 *a) {
    return a && a->capture_bf &&
        rate_ok(a->input_hz) &&
        (a->physical_mics == 1u || a->physical_mics == 2u ||
         a->physical_mics == 4u) &&
        a->capture_state_bytes > 0u && a->capture_state_bytes <= 16384u &&
        a->capture_work_bytes > 0u && a->capture_work_bytes <= 32768u &&
        a->render_epoch != 0u &&
        disjoint(a, sizeof(*a), a->capture_bf, a->capture_state_bytes);
}
fe_t2b_b0_status fe_t2b_b0_bind(fe_t2b_b0 *a,
    fe_b1b1 *capture_only, uint32_t input_hz, uint32_t physical_mics) {
    fe_b1b1_info info;
    fe_t2b_b0 next;
    if (!a || !capture_only || !rate_ok(input_hz) ||
        (physical_mics != 1u && physical_mics != 2u &&
         physical_mics != 4u) ||
        fe_b1b1_get_info(capture_only, &info) != FE_B1B1_OK ||
        info.input_rate_hz != input_hz ||
        info.physical_mics != physical_mics ||
        info.render_channels != 0u ||
        info.accepted_frames != 0u ||
        info.source.accepted_frames != 0u ||
        info.source.capture_clock_authority != 0u ||
        info.state_bytes == 0u || info.state_bytes > 16384u ||
        info.work_bytes == 0u || info.work_bytes > 32768u ||
        !disjoint(a, sizeof(*a), capture_only, info.state_bytes))
        return FE_T2B_B0_REJECT;
    memset(&next, 0, sizeof(next));
    next.capture_bf = capture_only;
    next.capture_state_bytes = info.state_bytes;
    next.capture_work_bytes = info.work_bytes;
    next.input_hz = input_hz;
    next.physical_mics = physical_mics;
    next.render_epoch = 1u;
    /* Reuse exactly the unchanged first-party resampler implementation. */
    ap_resampler_init(&next.render_src);
    *a = next;
    return FE_T2B_B0_OK;
}

fe_t2b_b0_status fe_t2b_b0_capture(fe_t2b_b0 *a,
    uint64_t seq, const int16_t *pcm, size_t samples,
    float *beam, size_t beam_count, void *work, size_t work_bytes) {
    size_t frame_count;
    if (!adapter_ok(a)) return FE_T2B_B0_REJECT;
    /* Validate physical mic count BEFORE arithmetic on 32-bit size_t. */
    frame_count = (size_t)(a->input_hz / 100u) * a->physical_mics;
    if (!seq || a->capture_sequence == UINT64_MAX ||
        seq != a->capture_sequence + UINT64_C(1) ||
        a->accepted_capture == UINT64_MAX ||
        !pcm || samples != frame_count ||
        !beam || beam_count != FE_T2B_B0_FRAMES ||
        !work || (uintptr_t)work % FE_B1B1_ALIGNMENT ||
        work_bytes < a->capture_work_bytes ||
        work_bytes > 32768u ||
        !disjoint(a, sizeof(*a), pcm, frame_count * sizeof(int16_t)) ||
        !disjoint(a, sizeof(*a), beam, beam_count * sizeof(float)) ||
        !disjoint(a, sizeof(*a), work, work_bytes))
        return FE_T2B_B0_REJECT;
    /* The exact unchanged first-party B1B1 validates every remaining alias
     * and transactionally commits the real N SRC + FIR33 only on success.
     */
    if (fe_b1b1_process(a->capture_bf, pcm, samples, NULL, 0u,
                        beam, beam_count, NULL, 0u, work, work_bytes) !=
        FE_B1B1_OK)
        return FE_T2B_B0_CORE;
    a->capture_sequence = seq;
    ++a->accepted_capture;
    return FE_T2B_B0_OK;
}

fe_t2b_b0_status fe_t2b_b0_render(fe_t2b_b0 *a,
    uint64_t seq, uint32_t flags, const int16_t *pcm, size_t samples,
    float *reference, size_t reference_count) {
    size_t frame_count;
    const int gap = flags == FE_T2B_B0_RENDER_GAP;
    if (!adapter_ok(a)) return FE_T2B_B0_REJECT;
    frame_count = (size_t)(a->input_hz / 100u);
    if ((flags != 0u && !gap) ||
        !seq || a->render_sequence == UINT64_MAX ||
        a->accepted_render == UINT64_MAX ||
        (a->render_sequence == 0u ?
            (seq != UINT64_C(1) || flags != 0u) :
            (seq <= a->render_sequence ||
             (seq != a->render_sequence + UINT64_C(1) && !gap))) ||
        (gap && a->render_epoch == UINT32_MAX) ||
        !pcm || samples != frame_count ||
        !reference || reference_count != FE_T2B_B0_FRAMES ||
        !disjoint(a, sizeof(*a), pcm, frame_count * sizeof(int16_t)) ||
        !disjoint(a, sizeof(*a), reference,
                  FE_T2B_B0_FRAMES * sizeof(float)) ||
        !disjoint(a->capture_bf, a->capture_state_bytes,
                  pcm, frame_count * sizeof(int16_t)) ||
        !disjoint(a->capture_bf, a->capture_state_bytes,
                  reference, FE_T2B_B0_FRAMES * sizeof(float)) ||
        !disjoint(pcm, frame_count * sizeof(int16_t),
                  reference, FE_T2B_B0_FRAMES * sizeof(float)))
        return FE_T2B_B0_REJECT;
    /* The only resampler invoked below is original first-party C. The
     * independent render history sees NO calls for missing samples.
     */
    if (gap) ap_resampler_reset(&a->render_src);
    ap_resample_input_channel(&a->render_src, 0u,
        pcm, a->input_hz / 100u, 1u, 0u,
        reference, FE_T2B_B0_FRAMES);
    a->render_sequence = seq;
    a->render_epoch += (uint32_t)gap;
    ++a->accepted_render;
    return FE_T2B_B0_OK;
}
