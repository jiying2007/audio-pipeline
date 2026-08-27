#include "ap_internal.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

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
    c.enable_hpf = 1u;
    c.enable_beamformer = 1u;
    c.enable_delay_tracking = 1u;
    c.enable_clock_drift_compensation = 1u;
    c.enable_aec = 1u;
    c.enable_residual_echo_suppression = 1u;
    c.enable_noise_suppression = 1u;
    c.enable_agc = 1u;
    c.enable_vad = 1u;
    c.resource_class = resource_class;

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
        c.enable_beamformer = 0u;
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
    uint32_t taps;
    if (!memory || !c || !out) return AP_EINVAL;
    *out = NULL;
    if (memory_size < sizeof(ap_pipeline_t)) return AP_ENOMEM;
    if (((uintptr_t)memory & (AP_PIPELINE_STATE_ALIGNMENT - 1u)) != 0u)
        return AP_EINVAL;
    if (!ap_supported_io_rate(c->io_sample_rate_hz)) return AP_EINVAL;
    if (c->internal_sample_rate_hz != 8000u && c->internal_sample_rate_hz != 16000u)
        return AP_EINVAL;
    if (c->mic_channels < 1u || c->mic_channels > 2u) return AP_EINVAL;
    if (c->resource_class < AP_RESOURCE_TINY || c->resource_class > AP_RESOURCE_STANDARD)
        return AP_EINVAL;
    if (c->aec_adapt_stride == 0u || c->aec_filter_ms < 20u || c->aec_filter_ms > 120u)
        return AP_EINVAL;
    if (!(c->aec_mu > 0.0f && c->aec_mu <= 1.0f)) return AP_EINVAL;
    if (c->max_delay_ms > 300u || c->initial_delay_ms > c->max_delay_ms)
        return AP_EINVAL;
    if (c->ns_floor < 0.02f || c->ns_floor > 1.0f) return AP_EINVAL;

    p = (ap_pipeline_t *)memory;
    memset(p, 0, sizeof(*p));
    p->cfg = *c;
    p->io_frame = c->io_sample_rate_hz / 100u;
    p->internal_frame = c->internal_sample_rate_hz / 100u;
    taps = c->aec_filter_ms * c->internal_sample_rate_hz / 1000u;
    if (taps > AP_AEC_CAP) taps = AP_AEC_CAP;
    p->aec_taps = taps;
    p->active_aec_taps = taps;
    p->active_aec_adapt_stride = c->aec_adapt_stride;
    p->delay_samples = c->initial_delay_ms * c->internal_sample_rate_hz / 1000u;
    p->quality = AP_QUALITY_FULL;
    p->metrics.quality = AP_QUALITY_FULL;
    p->metrics.residual_echo_gain = 1.0f;
    p->metrics.active_aec_taps = p->active_aec_taps;
    p->metrics.active_aec_adapt_stride = p->active_aec_adapt_stride;

    ap_frontend_init(p);
    ap_aec_backend_init(p);
    ap_enhance_init(p);
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
    uint32_t ms, stride;
    if (!p || q < AP_QUALITY_SAFE || q > AP_QUALITY_FULL) return AP_EINVAL;
    p->quality = q;
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
    p->active_aec_taps = ms * p->cfg.internal_sample_rate_hz / 1000u;
    if (p->active_aec_taps > p->aec_taps) p->active_aec_taps = p->aec_taps;
    p->active_aec_adapt_stride = stride;
    p->metrics.quality = q;
    p->metrics.active_aec_taps = p->active_aec_taps;
    p->metrics.active_aec_adapt_stride = stride;
    ap_aec_backend_set_active(p);
    return AP_OK;
}

ap_status_t ap_pipeline_push_render(ap_pipeline_t *p,
                                    const int16_t *render, size_t samples) {
    uint32_t i;
    if (!p || !render || samples != p->io_frame) return AP_EINVAL;
    ap_resample_input_channel(render, p->io_frame, 1u, 0u,
                              p->work, p->internal_frame);
    for (i = 0u; i < p->internal_frame; ++i) {
        p->render_ring[p->render_total & (AP_RENDER_CAP - 1u)] = p->work[i];
        p->render_total++;
    }
    p->last_render_capture_frame = p->metrics.processed_frames;
    return AP_OK;
}

ap_status_t ap_pipeline_process_capture(ap_pipeline_t *p, const int16_t *mic,
                                        size_t frames, int16_t *output) {
    uint32_t i;
    float mic_e = 1.0e-12f, ref_e = 1.0e-12f;
    float res_e = 1.0e-12f, echo_e = 0.0f;
    const int use_frequency_res = p && p->cfg.enable_residual_echo_suppression &&
                                  p->cfg.enable_noise_suppression &&
                                  p->quality != AP_QUALITY_SAFE;
    if (!p || !mic || !output || frames != p->io_frame) return AP_EINVAL;

    ap_resample_input_channel(mic, p->io_frame, p->cfg.mic_channels,
                              0u, p->mic0, p->internal_frame);
    if (p->cfg.mic_channels == 2u)
        ap_resample_input_channel(mic, p->io_frame, 2u, 1u,
                                  p->mic1, p->internal_frame);
    if (p->cfg.enable_hpf) {
        ap_hpf_process(p, p->mic0, p->internal_frame, 0u);
        if (p->cfg.mic_channels == 2u)
            ap_hpf_process(p, p->mic1, p->internal_frame, 1u);
    }
    if (p->cfg.mic_channels == 2u && p->cfg.enable_beamformer &&
        p->quality != AP_QUALITY_SAFE)
        ap_beamform(p, p->mic0, p->mic1, p->mono, p->internal_frame);
    else
        memcpy(p->mono, p->mic0, p->internal_frame * sizeof(float));

    ap_sync_track_delay(p, p->mono);
    ap_sync_get_reference(p, p->delay_samples, p->reference);
    for (i = 0u; i < p->internal_frame; ++i) {
        mic_e += p->mono[i] * p->mono[i];
        ref_e += p->reference[i] * p->reference[i];
    }
    mic_e /= p->internal_frame;
    ref_e /= p->internal_frame;

    ap_aec_backend_process(p, p->mono, p->reference, p->aec_out, p->echo_estimate,
                           mic_e, ref_e, &echo_e);
    for (i = 0u; i < p->internal_frame; ++i)
        res_e += p->aec_out[i] * p->aec_out[i];
    res_e /= p->internal_frame;

    if (!use_frequency_res) {
        p->metrics.residual_echo_gain = ap_apply_broadband_res(
            p, p->aec_out, echo_e, res_e, ref_e, mic_e);
    } else {
        p->metrics.residual_echo_gain = 1.0f;
    }
    ap_ns_process(p, p->aec_out, p->echo_estimate, p->ns_out, ref_e, mic_e);
    ap_agc_process(p, p->ns_out, p->internal_frame);
    ap_vad_process(p, p->ns_out, p->internal_frame);

    p->metrics.input_rms_dbfs = 10.0f * log10f(mic_e + 1.0e-18f);
    p->metrics.output_rms_dbfs = ap_rms_dbfs(p->ns_out, p->internal_frame);
    p->metrics.noise_rms_dbfs = p->ns.noise_rms_dbfs;
    if (ref_e > 1.0e-7f && res_e > 1.0e-12f) {
        const float erle = 10.0f * log10f(
            (mic_e + 1.0e-12f) / (res_e + 1.0e-12f));
        p->metrics.erle_db = p->metrics.processed_frames ?
            0.95f * p->metrics.erle_db + 0.05f * erle : erle;
    }
    p->metrics.estimated_delay_ms =
        p->delay_samples * 1000u / p->cfg.internal_sample_rate_hz;
    p->metrics.active_aec_taps = p->active_aec_taps;
    p->metrics.active_aec_adapt_stride = p->active_aec_adapt_stride;
    p->metrics.processed_frames++;
    if (p->metrics.processed_frames > p->last_render_capture_frame + 2u)
        p->metrics.render_underruns++;
    ap_resample_output(p->ns_out, p->internal_frame, output, p->io_frame);
    return AP_OK;
}

void ap_pipeline_get_metrics(const ap_pipeline_t *p, ap_metrics_t *m) {
    if (p && m) *m = p->metrics;
}

uint32_t ap_pipeline_algorithmic_latency_ms(const ap_pipeline_t *p) {
    if (!p) return 0u;
    return p->cfg.enable_noise_suppression ? AP_FRAME_MS : 0u;
}
