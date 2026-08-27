#include "core/ap_pipeline_internal.h"
#include "frontend/ap_resampler.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define AP_DTD_HANGOVER_FRAMES 3u
#define AP_HAS_STAGE(p, bit) (((p)->cfg.stages & (bit)) != 0u)

#if AP_BUILD_STAGE_RES || AP_BUILD_STAGE_NS
static ap_enhance_mode_t ap_pipeline_enhance_mode(ap_quality_t quality) {
    if (quality == AP_QUALITY_FULL) return AP_ENHANCE_FULL;
    if (quality == AP_QUALITY_LITE) return AP_ENHANCE_LITE;
    return AP_ENHANCE_SAFE;
}
#endif

static float ap_pipeline_rms_dbfs(const float *x, uint32_t n) {
    float e = 1.0e-18f;
    uint32_t i;
    for (i = 0u; i < n; ++i) e += x[i] * x[i];
    e /= n ? (float)n : 1.0f;
    return 10.0f * log10f(e);
}

ap_stage_mask_t ap_pipeline_compiled_stages(void) {
    ap_stage_mask_t mask = 0u;
#if AP_BUILD_STAGE_HPF
    mask |= AP_STAGE_HPF;
#endif
#if AP_BUILD_STAGE_BF
    mask |= AP_STAGE_BF;
#endif
#if AP_BUILD_STAGE_SYNC
    mask |= AP_STAGE_SYNC;
#endif
#if AP_BUILD_STAGE_AEC
    mask |= AP_STAGE_AEC;
#endif
#if AP_BUILD_STAGE_RES
    mask |= AP_STAGE_RES;
#endif
#if AP_BUILD_STAGE_NS
    mask |= AP_STAGE_NS;
#endif
#if AP_BUILD_STAGE_AGC
    mask |= AP_STAGE_AGC;
#endif
#if AP_BUILD_STAGE_VAD
    mask |= AP_STAGE_VAD;
#endif
    return mask;
}

static ap_stage_mask_t ap_pipeline_default_stages(void) {
    ap_stage_mask_t mask = ap_pipeline_compiled_stages();
    if ((mask & AP_STAGE_SYNC) == 0u) mask &= ~(AP_STAGE_AEC | AP_STAGE_RES);
    if ((mask & AP_STAGE_AEC) == 0u) mask &= ~AP_STAGE_RES;
    return mask;
}

ap_status_t ap_pipeline_validate_config(const ap_config_t *c) {
    const ap_stage_mask_t compiled = ap_pipeline_compiled_stages();
    if (!c) return AP_EINVAL;
    if (!ap_supported_io_rate(c->io_sample_rate_hz)) return AP_EINVAL;
    if (c->internal_sample_rate_hz != 8000u && c->internal_sample_rate_hz != 16000u)
        return AP_EINVAL;
    if (c->mic_channels < 1u || c->mic_channels > 2u) return AP_EINVAL;
    if (c->resource_class < AP_RESOURCE_TINY || c->resource_class > AP_RESOURCE_STANDARD)
        return AP_EINVAL;
    if ((c->stages & ~compiled) != 0u) return AP_ESTATE;
    if ((c->stages & AP_STAGE_BF) && c->mic_channels != 2u) return AP_EINVAL;
    if ((c->stages & AP_STAGE_AEC) && !(c->stages & AP_STAGE_SYNC)) return AP_EINVAL;
    if ((c->stages & AP_STAGE_RES) && !(c->stages & AP_STAGE_AEC)) return AP_EINVAL;
    if ((c->enable_delay_tracking || c->enable_clock_drift_compensation) &&
        !(c->stages & AP_STAGE_SYNC)) return AP_EINVAL;
    if (c->stages & AP_STAGE_AEC) {
        if (c->aec_adapt_stride == 0u || c->aec_filter_ms < 20u || c->aec_filter_ms > 120u)
            return AP_EINVAL;
        if (!(c->aec_mu > 0.0f && c->aec_mu <= 1.0f)) return AP_EINVAL;
    }
    if (c->stages & AP_STAGE_SYNC) {
        if (c->max_delay_ms > 300u || c->initial_delay_ms > c->max_delay_ms)
            return AP_EINVAL;
    }
    if ((c->stages & AP_STAGE_NS) && (c->ns_floor < 0.02f || c->ns_floor > 1.0f))
        return AP_EINVAL;
    return AP_OK;
}

#if AP_BUILD_STAGE_AEC
static void ap_pipeline_update_aec_metrics(ap_pipeline_t *p) {
    ap_aec_status_t status;
    ap_aec_backend_get_status(&p->aec, &status);
    p->metrics.aec_backend = status.kind == AP_AEC_KIND_MDF ?
                             AP_AEC_BACKEND_MDF : AP_AEC_BACKEND_NLMS;
    p->metrics.active_aec_taps = status.active_taps;
    p->metrics.active_aec_adapt_stride = status.active_adapt_stride;
    p->metrics.active_aec_partitions = status.active_partitions;
    p->metrics.aec_block_samples = status.block_samples;
}
#endif

#if AP_BUILD_STAGE_SYNC
static void ap_pipeline_update_sync_metrics(ap_pipeline_t *p,
                                            const ap_sync_event_t *event) {
    ap_sync_status_t status;
    ap_sync_get_status(&p->sync, &status);
    p->metrics.estimated_drift_ppm = status.estimated_drift_ppm;
    p->metrics.estimated_delay_ms =
        status.delay_samples * 1000u / p->cfg.internal_sample_rate_hz;
    if (!event) return;
    if (event->delay_observed)
        p->metrics.delay_error_samples = event->delay_error_samples;
    p->metrics.reference_sample_slips += event->reference_sample_slips;
    if (event->route_jump) {
        p->metrics.delay_jumps++;
#if AP_BUILD_STAGE_AEC
        if (AP_HAS_STAGE(p, AP_STAGE_AEC)) {
            ap_aec_backend_reset(&p->aec);
            p->metrics.aec_resets++;
        }
#endif
    }
}
#endif

static void ap_pipeline_update_activity(ap_pipeline_t *p,
                                        float mic_energy,
                                        float ref_energy,
                                        int *far_end_active,
                                        int *double_talk_active) {
    const int far_now = ref_energy > 1.0e-7f;
    const int double_talk_now = far_now && mic_energy > ref_energy * 1.5f;
    if (double_talk_now)
        p->double_talk_hangover = AP_DTD_HANGOVER_FRAMES;
    else if (p->double_talk_hangover)
        p->double_talk_hangover--;
    *far_end_active = far_now;
    *double_talk_active = far_now && p->double_talk_hangover > 0u;
    p->metrics.far_end_active = (uint8_t)(*far_end_active ? 1u : 0u);
    p->metrics.double_talk_active = (uint8_t)(*double_talk_active ? 1u : 0u);
}

ap_config_t ap_config_for_resource(ap_profile_t profile,
                                   ap_resource_class_t resource_class) {
    ap_config_t c;
    memset(&c, 0, sizeof(c));
    if (profile != AP_PROFILE_CALL && profile != AP_PROFILE_ASSISTANT)
        profile = AP_PROFILE_CALL;
    if (resource_class < AP_RESOURCE_TINY || resource_class > AP_RESOURCE_STANDARD)
        resource_class = AP_RESOURCE_STANDARD;

    c.io_sample_rate_hz = 16000u;
    c.internal_sample_rate_hz = 16000u;
    c.mic_channels = 2u;
    c.mic_spacing_mm = 35.0f;
    c.max_delay_ms = 180u;
    c.initial_delay_ms = 40u;
    c.aec_adapt_stride = 2u;
    c.enable_delay_tracking = 1u;
    c.enable_clock_drift_compensation = 1u;
    c.resource_class = resource_class;
    c.stages = ap_pipeline_default_stages();

    if (profile == AP_PROFILE_CALL) {
        c.aec_filter_ms = 96u;
        c.aec_mu = 0.22f;
        c.ns_floor = 0.12f;
        c.agc_target_dbfs = -20.0f;
        c.limiter_dbfs = -2.0f;
    } else {
        c.aec_filter_ms = 80u;
        c.aec_mu = 0.18f;
        c.ns_floor = 0.18f;
        c.agc_target_dbfs = -18.0f;
        c.limiter_dbfs = -2.0f;
    }

    if (resource_class == AP_RESOURCE_LOW) {
        c.aec_filter_ms = profile == AP_PROFILE_CALL ? 64u : 56u;
        c.max_delay_ms = 160u;
    } else if (resource_class == AP_RESOURCE_TINY) {
        c.internal_sample_rate_hz = 8000u;
        c.aec_filter_ms = profile == AP_PROFILE_CALL ? 48u : 40u;
        c.max_delay_ms = 120u;
        c.aec_adapt_stride = 3u;
        c.stages &= ~AP_STAGE_BF;
    }
    if ((c.stages & AP_STAGE_SYNC) == 0u) {
        c.enable_delay_tracking = 0u;
        c.enable_clock_drift_compensation = 0u;
    }
    return c;
}

ap_config_t ap_config_default(ap_profile_t profile) {
    return ap_config_for_resource(profile, AP_RESOURCE_STANDARD);
}

size_t ap_pipeline_state_size(void) { return sizeof(ap_pipeline_t); }
size_t ap_pipeline_state_alignment(void) { return AP_PIPELINE_STATE_ALIGNMENT; }
size_t ap_pipeline_io_frame_samples(const ap_config_t *c) {
    return c ? c->io_sample_rate_hz / 100u : 0u;
}
size_t ap_pipeline_internal_frame_samples(const ap_config_t *c) {
    return c ? c->internal_sample_rate_hz / 100u : 0u;
}
size_t ap_pipeline_frame_samples(const ap_pipeline_t *p) { return p ? p->io_frame : 0u; }
uint32_t ap_pipeline_mic_channels(const ap_pipeline_t *p) {
    return p ? p->cfg.mic_channels : 0u;
}
uint32_t ap_pipeline_sample_rate_hz(const ap_pipeline_t *p) {
    return p ? p->cfg.io_sample_rate_hz : 0u;
}

ap_status_t ap_pipeline_init(void *memory, size_t memory_size,
                             const ap_config_t *c, ap_pipeline_t **out) {
    ap_pipeline_t *p;
    ap_status_t valid;
    if (!memory || !c || !out) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_pipeline_t)) return AP_ENOMEM;
    if (((uintptr_t)memory & (AP_PIPELINE_STATE_ALIGNMENT - 1u)) != 0u)
        return AP_EINVAL;
    valid = ap_pipeline_validate_config(c);
    if (valid != AP_OK) return valid;

    p = (ap_pipeline_t *)memory;
    memset(p, 0, sizeof(*p));
    p->cfg = *c;
    p->io_frame = c->io_sample_rate_hz / 100u;
    p->internal_frame = c->internal_sample_rate_hz / 100u;
    p->quality = AP_QUALITY_FULL;
    p->metrics.quality = AP_QUALITY_FULL;
    p->metrics.residual_echo_gain = 1.0f;
    p->metrics.noise_rms_dbfs = -90.0f;

#if AP_BUILD_STAGE_HPF
    if (AP_HAS_STAGE(p, AP_STAGE_HPF))
        ap_hpf_init(&p->hpf, c->internal_sample_rate_hz, c->mic_channels);
#endif
#if AP_BUILD_STAGE_BF
    if (AP_HAS_STAGE(p, AP_STAGE_BF))
        ap_beamformer_init(&p->beamformer, c->internal_sample_rate_hz, c->mic_spacing_mm);
#endif
#if AP_BUILD_STAGE_SYNC
    if (AP_HAS_STAGE(p, AP_STAGE_SYNC)) {
        ap_sync_init(&p->sync,
                     c->initial_delay_ms * c->internal_sample_rate_hz / 1000u);
        ap_pipeline_update_sync_metrics(p, NULL);
    }
#endif
#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(p, AP_STAGE_AEC)) {
        uint32_t taps = c->aec_filter_ms * c->internal_sample_rate_hz / 1000u;
        if (taps > AP_AEC_CAP) taps = AP_AEC_CAP;
        ap_aec_backend_init(&p->aec, p->internal_frame, taps, c->aec_adapt_stride);
        ap_pipeline_update_aec_metrics(p);
    }
#endif
#if AP_BUILD_STAGE_RES
    if (AP_HAS_STAGE(p, AP_STAGE_RES)) ap_res_init(&p->res);
#endif
#if AP_BUILD_STAGE_NS
    if (AP_HAS_STAGE(p, AP_STAGE_NS)) ap_ns_init(&p->ns, p->internal_frame);
#endif
#if AP_BUILD_STAGE_AGC
    if (AP_HAS_STAGE(p, AP_STAGE_AGC))
        ap_agc_init(&p->agc, c->agc_target_dbfs, c->limiter_dbfs);
#endif
#if AP_BUILD_STAGE_VAD
    if (AP_HAS_STAGE(p, AP_STAGE_VAD)) ap_vad_init(&p->vad);
#endif
    *out = p;
    return AP_OK;
}

void ap_pipeline_reset(ap_pipeline_t *p) {
    ap_pipeline_t *out = NULL;
    ap_config_t c;
    if (!p) return;
    c = p->cfg;
    (void)ap_pipeline_init(p, sizeof(*p), &c, &out);
}

ap_status_t ap_pipeline_set_quality(ap_pipeline_t *p, ap_quality_t q) {
    if (!p || q < AP_QUALITY_SAFE || q > AP_QUALITY_FULL) return AP_EINVAL;
#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(p, AP_STAGE_AEC)) {
        uint32_t ms, stride, active_taps;
        if (q == AP_QUALITY_FULL) {
            ms = p->cfg.aec_filter_ms;
            stride = p->cfg.aec_adapt_stride;
        } else if (q == AP_QUALITY_LITE) {
            ms = p->cfg.aec_filter_ms < 64u ? p->cfg.aec_filter_ms : 64u;
            stride = p->cfg.aec_adapt_stride < 2u ? 2u : p->cfg.aec_adapt_stride;
        } else {
            ms = p->cfg.aec_filter_ms < 40u ? p->cfg.aec_filter_ms : 40u;
            stride = p->cfg.aec_adapt_stride < 4u ? 4u : p->cfg.aec_adapt_stride;
        }
        active_taps = ms * p->cfg.internal_sample_rate_hz / 1000u;
        ap_aec_backend_set_active(&p->aec, active_taps, stride);
        ap_pipeline_update_aec_metrics(p);
    }
#endif
    p->quality = q;
    p->metrics.quality = q;
    return AP_OK;
}

ap_status_t ap_pipeline_push_render(ap_pipeline_t *p,
                                    const int16_t *render, size_t samples) {
    if (!p || !render || samples != p->io_frame) return AP_EINVAL;
#if AP_BUILD_STAGE_SYNC
    if (!AP_HAS_STAGE(p, AP_STAGE_SYNC)) return AP_ESTATE;
    ap_resample_input_channel(render, p->io_frame, 1u, 0u,
                              p->work, p->internal_frame);
    ap_sync_push_render(&p->sync, p->work, p->internal_frame,
                        p->metrics.processed_frames);
    return AP_OK;
#else
    (void)samples;
    return AP_ESTATE;
#endif
}

ap_status_t ap_pipeline_process_capture(ap_pipeline_t *p, const int16_t *mic,
                                        size_t frames, int16_t *output) {
    uint32_t i;
    float mic_e = 1.0e-12f, ref_e = 1.0e-12f, res_e = 1.0e-12f;
#if AP_BUILD_STAGE_RES
    float echo_energy = 0.0f;
#endif
#if AP_BUILD_STAGE_NS || AP_BUILD_STAGE_VAD
    float ns_speech_probability = 0.0f;
#endif
    int far_end_active = 0, double_talk_active = 0;
    if (!p || !mic || !output || frames != p->io_frame) return AP_EINVAL;

    ap_resample_input_channel(mic, p->io_frame, p->cfg.mic_channels,
                              0u, p->mic0, p->internal_frame);
#if AP_BUILD_STAGE_BF
    if (AP_HAS_STAGE(p, AP_STAGE_BF))
        ap_resample_input_channel(mic, p->io_frame, 2u, 1u,
                                  p->mic1, p->internal_frame);
#endif
#if AP_BUILD_STAGE_HPF
    if (AP_HAS_STAGE(p, AP_STAGE_HPF)) {
        ap_hpf_process(&p->hpf, p->mic0, p->internal_frame, 0u);
#if AP_BUILD_STAGE_BF
        if (AP_HAS_STAGE(p, AP_STAGE_BF))
            ap_hpf_process(&p->hpf, p->mic1, p->internal_frame, 1u);
#endif
    }
#endif
#if AP_BUILD_STAGE_BF
    if (AP_HAS_STAGE(p, AP_STAGE_BF) && p->quality != AP_QUALITY_SAFE)
        ap_beamformer_process(&p->beamformer, p->quality == AP_QUALITY_FULL,
                              p->mic0, p->mic1, p->mono, p->internal_frame);
    else
#endif
        memcpy(p->mono, p->mic0, p->internal_frame * sizeof(float));

#if AP_BUILD_STAGE_SYNC
    if (AP_HAS_STAGE(p, AP_STAGE_SYNC)) {
        ap_sync_event_t event;
        ap_sync_track_delay(&p->sync, p->mono, p->internal_frame,
                            p->cfg.internal_sample_rate_hz, p->cfg.max_delay_ms,
                            p->cfg.enable_delay_tracking,
                            p->cfg.enable_clock_drift_compensation, &event);
        ap_pipeline_update_sync_metrics(p, &event);
        if (ap_sync_get_reference(&p->sync, p->internal_frame, p->reference))
            p->metrics.render_underruns++;
    } else
#endif
        memset(p->reference, 0, p->internal_frame * sizeof(float));

    for (i = 0u; i < p->internal_frame; ++i) {
        mic_e += p->mono[i] * p->mono[i];
        ref_e += p->reference[i] * p->reference[i];
    }
    mic_e /= p->internal_frame;
    ref_e /= p->internal_frame;
    ap_pipeline_update_activity(p, mic_e, ref_e,
                                &far_end_active, &double_talk_active);

#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(p, AP_STAGE_AEC)) {
        ap_aec_result_t aec_result;
        ap_aec_backend_process(&p->aec, 1, p->cfg.aec_mu,
                               p->internal_frame, p->mono, p->reference,
                               p->aec_out, p->echo_estimate,
                               far_end_active, double_talk_active, &aec_result);
#if AP_BUILD_STAGE_RES
        echo_energy = aec_result.echo_energy;
#endif
        ap_pipeline_update_aec_metrics(p);
    } else
#endif
    {
        memcpy(p->aec_out, p->mono, p->internal_frame * sizeof(float));
        memset(p->echo_estimate, 0, p->internal_frame * sizeof(float));
    }

    for (i = 0u; i < p->internal_frame; ++i)
        res_e += p->aec_out[i] * p->aec_out[i];
    res_e /= p->internal_frame;

#if AP_BUILD_STAGE_RES
    if (AP_HAS_STAGE(p, AP_STAGE_RES) &&
        (!AP_HAS_STAGE(p, AP_STAGE_NS) || p->quality == AP_QUALITY_SAFE)) {
        p->metrics.residual_echo_gain = ap_res_process(
            &p->res, ap_pipeline_enhance_mode(p->quality), p->aec_out,
            p->internal_frame, echo_energy, res_e,
            far_end_active, double_talk_active);
    } else {
        p->metrics.residual_echo_gain = 1.0f;
    }
#else
    p->metrics.residual_echo_gain = 1.0f;
#endif

#if AP_BUILD_STAGE_NS
    if (AP_HAS_STAGE(p, AP_STAGE_NS)) {
        ap_ns_result_t ns_result;
        const int frequency_res =
#if AP_BUILD_STAGE_RES
            AP_HAS_STAGE(p, AP_STAGE_RES) && p->quality != AP_QUALITY_SAFE;
#else
            0;
#endif
        ap_ns_process(&p->ns, ap_pipeline_enhance_mode(p->quality),
                      p->cfg.ns_floor, p->aec_out, p->echo_estimate,
                      p->processed, p->internal_frame, frequency_res,
                      far_end_active, double_talk_active, &ns_result);
        p->metrics.noise_rms_dbfs = ns_result.noise_rms_dbfs;
        p->metrics.frequency_res_active = ns_result.frequency_res_active;
        ns_speech_probability = ns_result.speech_probability;
        if (ns_result.frequency_res_active)
            p->metrics.residual_echo_gain = ns_result.residual_echo_gain;
    } else
#endif
    {
        memcpy(p->processed, p->aec_out, p->internal_frame * sizeof(float));
        p->metrics.frequency_res_active = 0u;
        p->metrics.noise_rms_dbfs = -90.0f;
    }

#if AP_BUILD_STAGE_AGC
    if (AP_HAS_STAGE(p, AP_STAGE_AGC))
        ap_agc_process(&p->agc, p->processed, p->internal_frame);
#endif

#if AP_BUILD_STAGE_VAD
    if (AP_HAS_STAGE(p, AP_STAGE_VAD)) {
        ap_vad_result_t vad_result;
        ap_vad_process(&p->vad, p->processed, p->internal_frame,
                       ns_speech_probability, AP_HAS_STAGE(p, AP_STAGE_NS),
                       &vad_result);
        p->metrics.vad_probability = vad_result.probability;
        p->metrics.vad_active = vad_result.active;
    } else
#endif
    {
        p->metrics.vad_probability = 0.0f;
        p->metrics.vad_active = 0u;
    }

    p->metrics.input_rms_dbfs = 10.0f * log10f(mic_e + 1.0e-18f);
    p->metrics.output_rms_dbfs = ap_pipeline_rms_dbfs(p->processed, p->internal_frame);
    if (ref_e > 1.0e-7f && res_e > 1.0e-12f) {
        const float erle = 10.0f * log10f(
            (mic_e + 1.0e-12f) / (res_e + 1.0e-12f));
        p->metrics.erle_db = p->metrics.processed_frames ?
            0.95f * p->metrics.erle_db + 0.05f * erle : erle;
    }
    p->metrics.processed_frames++;
#if AP_BUILD_STAGE_SYNC
    if (AP_HAS_STAGE(p, AP_STAGE_SYNC) &&
        ap_sync_note_capture(&p->sync, p->metrics.processed_frames))
        p->metrics.render_underruns++;
#endif
    ap_resample_output(p->processed, p->internal_frame, output, p->io_frame);
    return AP_OK;
}

void ap_pipeline_get_metrics(const ap_pipeline_t *p, ap_metrics_t *m) {
    if (p && m) *m = p->metrics;
}

uint32_t ap_pipeline_algorithmic_latency_ms(const ap_pipeline_t *p) {
    if (!p) return 0u;
    return AP_HAS_STAGE(p, AP_STAGE_NS) ? AP_FRAME_MS : 0u;
}
