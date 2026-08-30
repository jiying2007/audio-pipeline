#include "core/ap_pipeline_internal.h"
#include <math.h>
#include <stddef.h>

#define AP_HAS_STAGE(p, bit) (((p)->cfg.stages & (bit)) != 0u)

ap_stage_mask_t ap_pipeline_stages(const ap_pipeline_t *pipeline) {
    return pipeline ? pipeline->cfg.stages : 0u;
}

ap_status_t ap_pipeline_notify_stream_discontinuity(ap_pipeline_t *pipeline,
                                                    ap_discontinuity_flags_t flags,
                                                    uint32_t lost_frames) {
    (void)lost_frames;
    if (!pipeline || flags == 0u ||
        (flags & ~(AP_DISCONTINUITY_CAPTURE_GAP | AP_DISCONTINUITY_RENDER_GAP |
                   AP_DISCONTINUITY_CLOCK_RESET | AP_DISCONTINUITY_XRUN |
                   AP_DISCONTINUITY_CODEC_REOPEN | AP_DISCONTINUITY_ROUTE_CHANGE)) != 0u)
        return AP_EINVAL;

    /* Boundary SRC history must never bridge a known PCM discontinuity. */
    ap_resampler_reset(&pipeline->resampler);

#if AP_BUILD_STAGE_HPF
    if (AP_HAS_STAGE(pipeline, AP_STAGE_HPF))
        ap_hpf_init(&pipeline->hpf,
                    pipeline->cfg.internal_sample_rate_hz,
                    pipeline->cfg.mic_channels);
#endif
#if AP_BUILD_STAGE_BF
    if (AP_HAS_STAGE(pipeline, AP_STAGE_BF))
        ap_beamformer_init(&pipeline->beamformer,
                           pipeline->cfg.internal_sample_rate_hz,
                           pipeline->cfg.mic_spacing_mm);
#endif

#if AP_BUILD_STAGE_SYNC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_SYNC)) {
        ap_sync_reset(&pipeline->sync);
        pipeline->metrics.delay_error_samples = 0;
        pipeline->metrics.estimated_delay_ms = pipeline->cfg.initial_delay_ms;
        pipeline->metrics.estimated_drift_ppm = 0.0f;
    }
#endif
#if AP_BUILD_ACTIVITY
    ap_activity_reset(&pipeline->activity);
#endif
#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC)) {
        ap_aec_backend_reset(&pipeline->aec);
        pipeline->metrics.aec_resets++;
        pipeline->aec_convergence_frames = 0u;
        pipeline->metrics.aec_convergence_frames = 0u;
        pipeline->metrics.aec_converged = 0u;
        pipeline->metrics.erle_valid = 0u;
        pipeline->metrics.erle_db = 0.0f;
    }
#endif
#if AP_BUILD_STAGE_RES
    if (AP_HAS_STAGE(pipeline, AP_STAGE_RES)) ap_res_init(&pipeline->res);
#endif
#if AP_BUILD_STAGE_NS
    if (AP_HAS_STAGE(pipeline, AP_STAGE_NS))
        ap_ns_init(&pipeline->ns, pipeline->internal_frame);
#endif
#if AP_BUILD_STAGE_AGC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AGC))
        ap_agc_init(&pipeline->agc,
                    pipeline->cfg.agc_target_dbfs,
                    pipeline->cfg.limiter_dbfs);
#endif
#if AP_BUILD_STAGE_VAD
    if (AP_HAS_STAGE(pipeline, AP_STAGE_VAD)) ap_vad_init(&pipeline->vad);
#endif

    pipeline->metrics.far_end_active = 0u;
    pipeline->metrics.double_talk_active = 0u;
    pipeline->metrics.frequency_res_active = 0u;
    pipeline->metrics.residual_echo_gain = 1.0f;
    pipeline->metrics.noise_rms_dbfs = -90.0f;
    pipeline->metrics.vad_probability = 0.0f;
    pipeline->metrics.vad_active = 0u;

    return AP_OK;
}

ap_status_t ap_pipeline_apply_tuning(ap_pipeline_t *pipeline,
                                     const ap_tuning_t *tuning) {
    float next_aec_mu;
    float next_ns_floor;
    float next_agc_target;
    float next_limiter;
    if (!pipeline || !tuning) return AP_EINVAL;
    if (tuning->struct_size < sizeof(*tuning) ||
        tuning->api_version != AP_PIPELINE_CONTROL_API_VERSION || tuning->mask == 0u)
        return AP_EINVAL;
    if ((tuning->mask & ~(AP_TUNING_AEC_MU | AP_TUNING_NS_FLOOR |
                          AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER)) != 0u)
        return AP_EINVAL;

    next_aec_mu = (tuning->mask & AP_TUNING_AEC_MU) ? tuning->aec_mu : pipeline->cfg.aec_mu;
    next_ns_floor = (tuning->mask & AP_TUNING_NS_FLOOR) ? tuning->ns_floor : pipeline->cfg.ns_floor;
    next_agc_target = (tuning->mask & AP_TUNING_AGC_TARGET) ?
                      tuning->agc_target_dbfs : pipeline->cfg.agc_target_dbfs;
    next_limiter = (tuning->mask & AP_TUNING_LIMITER) ?
                   tuning->limiter_dbfs : pipeline->cfg.limiter_dbfs;

    if ((tuning->mask & AP_TUNING_AEC_MU) &&
        (!isfinite(next_aec_mu) || next_aec_mu <= 0.0f || next_aec_mu > 1.0f))
        return AP_EINVAL;
    if ((tuning->mask & AP_TUNING_NS_FLOOR) &&
        (!isfinite(next_ns_floor) || next_ns_floor < 0.02f || next_ns_floor > 1.0f))
        return AP_EINVAL;
    if (tuning->mask & (AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER)) {
        if (!isfinite(next_agc_target) || !isfinite(next_limiter) ||
            next_agc_target < -60.0f || next_agc_target > -1.0f ||
            next_limiter < -20.0f || next_limiter > -0.1f ||
            next_agc_target >= next_limiter)
            return AP_EINVAL;
    }

    if (tuning->mask & AP_TUNING_AEC_MU) pipeline->cfg.aec_mu = next_aec_mu;
    if (tuning->mask & AP_TUNING_NS_FLOOR) pipeline->cfg.ns_floor = next_ns_floor;
    if (tuning->mask & AP_TUNING_AGC_TARGET) pipeline->cfg.agc_target_dbfs = next_agc_target;
    if (tuning->mask & AP_TUNING_LIMITER) pipeline->cfg.limiter_dbfs = next_limiter;

#if AP_BUILD_STAGE_AGC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AGC) &&
        (tuning->mask & (AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER))) {
        const float gain = pipeline->agc.gain;
        ap_agc_init(&pipeline->agc,
                    pipeline->cfg.agc_target_dbfs,
                    pipeline->cfg.limiter_dbfs);
        pipeline->agc.gain = gain;
    }
#endif
    return AP_OK;
}
