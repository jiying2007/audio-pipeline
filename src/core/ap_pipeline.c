#include "core/ap_pipeline_internal.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define AP_HAS_STAGE(p, bit) (((p)->cfg.stages & (bit)) != 0u)
#define AP_ACTIVITY_FAR_THRESHOLD 1.0e-7f
#define AP_ACTIVITY_DT_RATIO 1.5f
#define AP_ACTIVITY_HANGOVER 3u
#define AP_AEC_CONVERGED_FRAMES 50u

#if AP_BUILD_STAGE_RES || AP_BUILD_STAGE_NS
static ap_enhance_mode_t ap_pipeline_enhance_mode(ap_quality_t quality) {
    if (quality == AP_QUALITY_FULL) return AP_ENHANCE_FULL;
    if (quality == AP_QUALITY_LITE) return AP_ENHANCE_LITE;
    return AP_ENHANCE_SAFE;
}
#endif

static float ap_pipeline_rms_dbfs(const float *samples, uint32_t count) {
    float energy = 1.0e-18f;
    uint32_t i;
    for (i = 0u; i < count; ++i) energy += samples[i] * samples[i];
    energy /= count ? (float)count : 1.0f;
    return 10.0f * log10f(energy);
}

static uint32_t ap_min_u32(uint32_t a, uint32_t b) {
    return a < b ? a : b;
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

ap_status_t ap_pipeline_validate_config(const ap_config_t *config) {
    const ap_stage_mask_t compiled = ap_pipeline_compiled_stages();
    if (!config) return AP_EINVAL;
    if (!ap_supported_io_rate(config->io_sample_rate_hz) ||
        config->io_sample_rate_hz > AP_BUILD_MAX_IO_RATE_HZ)
        return AP_EINVAL;
    if ((config->internal_sample_rate_hz != 8000u &&
         config->internal_sample_rate_hz != 16000u) ||
        config->internal_sample_rate_hz > AP_BUILD_MAX_INTERNAL_RATE_HZ)
        return AP_EINVAL;
    if (config->mic_channels < 1u || config->mic_channels > AP_BUILD_MAX_MIC_CHANNELS)
        return AP_EINVAL;
    if (config->resource_class < AP_RESOURCE_TINY ||
        config->resource_class > AP_RESOURCE_STANDARD)
        return AP_EINVAL;
    if ((config->stages & ~compiled) != 0u) return AP_ESTATE;

    if (config->stages & AP_STAGE_BF) {
        if (config->mic_channels != 2u || !isfinite(config->mic_spacing_mm) ||
            config->mic_spacing_mm < 5.0f || config->mic_spacing_mm > 200.0f)
            return AP_EINVAL;
    }
    if ((config->stages & AP_STAGE_AEC) && !(config->stages & AP_STAGE_SYNC))
        return AP_EINVAL;
    if ((config->stages & AP_STAGE_RES) && !(config->stages & AP_STAGE_AEC))
        return AP_EINVAL;
    if ((config->enable_delay_tracking || config->enable_clock_drift_compensation) &&
        !(config->stages & AP_STAGE_SYNC))
        return AP_EINVAL;

    if (config->stages & AP_STAGE_AEC) {
        if (config->aec_adapt_stride == 0u || config->aec_filter_ms < 20u ||
            config->aec_filter_ms > AP_BUILD_MAX_AEC_TAIL_MS ||
            !isfinite(config->aec_mu) || !(config->aec_mu > 0.0f && config->aec_mu <= 1.0f))
            return AP_EINVAL;
    }
    if (config->stages & AP_STAGE_SYNC) {
        if (config->max_delay_ms > AP_BUILD_MAX_DELAY_MS ||
            config->initial_delay_ms > config->max_delay_ms)
            return AP_EINVAL;
    }
    if ((config->stages & AP_STAGE_NS) &&
        (!isfinite(config->ns_floor) || config->ns_floor < 0.02f || config->ns_floor > 1.0f))
        return AP_EINVAL;
    if (config->stages & AP_STAGE_AGC) {
        if (!isfinite(config->agc_target_dbfs) || !isfinite(config->limiter_dbfs) ||
            config->agc_target_dbfs < -60.0f || config->agc_target_dbfs > -1.0f ||
            config->limiter_dbfs < -20.0f || config->limiter_dbfs > -0.1f ||
            config->agc_target_dbfs >= config->limiter_dbfs)
            return AP_EINVAL;
    }
    return AP_OK;
}

static void ap_pipeline_reset_aec_epoch(ap_pipeline_t *pipeline) {
    pipeline->aec_convergence_frames = 0u;
    pipeline->metrics.aec_convergence_frames = 0u;
    pipeline->metrics.aec_converged = 0u;
    pipeline->metrics.erle_valid = 0u;
    pipeline->metrics.erle_db = 0.0f;
}

#if AP_BUILD_STAGE_AEC
static void ap_pipeline_update_aec_metrics(ap_pipeline_t *pipeline) {
    ap_aec_status_t status;
    ap_aec_backend_get_status(&pipeline->aec, &status);
    pipeline->metrics.aec_backend = status.kind == AP_AEC_KIND_MDF ?
                                    AP_AEC_BACKEND_MDF : AP_AEC_BACKEND_NLMS;
    pipeline->metrics.active_aec_taps = status.active_taps;
    pipeline->metrics.active_aec_adapt_stride = status.active_adapt_stride;
    pipeline->metrics.active_aec_partitions = status.active_partitions;
    pipeline->metrics.aec_block_samples = status.block_samples;
}
#endif

#if AP_BUILD_STAGE_SYNC
static void ap_pipeline_update_sync_metrics(ap_pipeline_t *pipeline,
                                            const ap_sync_event_t *event) {
    ap_sync_status_t status;
    ap_sync_get_status(&pipeline->sync, &status);
    pipeline->metrics.estimated_drift_ppm = status.estimated_drift_ppm;
    pipeline->metrics.estimated_delay_ms =
        status.delay_samples * 1000u / pipeline->cfg.internal_sample_rate_hz;
    if (!event) return;

    if (event->delay_observed)
        pipeline->metrics.delay_error_samples = event->delay_error_samples;
    pipeline->metrics.reference_sample_slips += event->reference_sample_slips;
    if (event->timestamp_observed) pipeline->metrics.timestamp_observations++;
    if (event->route_jump) {
        pipeline->metrics.delay_jumps++;
#if AP_BUILD_STAGE_AEC
        if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC)) {
            ap_aec_backend_reset(&pipeline->aec);
            pipeline->metrics.aec_resets++;
            ap_pipeline_reset_aec_epoch(pipeline);
        }
#endif
    }
}
#endif

ap_config_t ap_config_for_resource(ap_profile_t profile,
                                   ap_resource_class_t resource_class) {
    ap_config_t config;
    memset(&config, 0, sizeof(config));
    if (profile != AP_PROFILE_CALL && profile != AP_PROFILE_ASSISTANT)
        profile = AP_PROFILE_CALL;
    if (resource_class < AP_RESOURCE_TINY || resource_class > AP_RESOURCE_STANDARD)
        resource_class = AP_RESOURCE_STANDARD;

    config.io_sample_rate_hz = ap_min_u32(16000u, AP_BUILD_MAX_IO_RATE_HZ);
    config.internal_sample_rate_hz = ap_min_u32(16000u, AP_BUILD_MAX_INTERNAL_RATE_HZ);
    config.mic_channels = ap_min_u32(2u, AP_BUILD_MAX_MIC_CHANNELS);
    config.mic_spacing_mm = 35.0f;
    config.max_delay_ms = ap_min_u32(180u, AP_BUILD_MAX_DELAY_MS);
    config.initial_delay_ms = ap_min_u32(40u, config.max_delay_ms);
    config.aec_adapt_stride = 2u;
    config.enable_delay_tracking = 1u;
    config.enable_clock_drift_compensation = 1u;
    config.resource_class = resource_class;
    config.stages = ap_pipeline_default_stages();

    if (profile == AP_PROFILE_CALL) {
        config.aec_filter_ms = 96u;
        config.aec_mu = 0.22f;
        config.ns_floor = 0.12f;
        config.agc_target_dbfs = -20.0f;
        config.limiter_dbfs = -2.0f;
    } else {
        config.aec_filter_ms = 80u;
        config.aec_mu = 0.18f;
        config.ns_floor = 0.18f;
        config.agc_target_dbfs = -18.0f;
        config.limiter_dbfs = -2.0f;
    }

    if (resource_class == AP_RESOURCE_LOW) {
        config.aec_filter_ms = profile == AP_PROFILE_CALL ? 64u : 56u;
        config.max_delay_ms = ap_min_u32(160u, AP_BUILD_MAX_DELAY_MS);
    } else if (resource_class == AP_RESOURCE_TINY) {
        config.internal_sample_rate_hz = 8000u;
        config.aec_filter_ms = profile == AP_PROFILE_CALL ? 48u : 40u;
        config.max_delay_ms = ap_min_u32(120u, AP_BUILD_MAX_DELAY_MS);
        config.aec_adapt_stride = 3u;
        config.stages &= ~AP_STAGE_BF;
    }

    config.aec_filter_ms = ap_min_u32(config.aec_filter_ms, AP_BUILD_MAX_AEC_TAIL_MS);
    config.initial_delay_ms = ap_min_u32(config.initial_delay_ms, config.max_delay_ms);
    if (config.mic_channels < 2u) config.stages &= ~AP_STAGE_BF;
    if ((config.stages & AP_STAGE_SYNC) == 0u) {
        config.enable_delay_tracking = 0u;
        config.enable_clock_drift_compensation = 0u;
    }
    return config;
}

ap_config_t ap_config_default(ap_profile_t profile) {
    return ap_config_for_resource(profile, AP_RESOURCE_STANDARD);
}

size_t ap_pipeline_state_size(void) { return sizeof(ap_pipeline_t); }
size_t ap_pipeline_state_alignment(void) { return AP_PIPELINE_STATE_ALIGNMENT; }
size_t ap_pipeline_io_frame_samples(const ap_config_t *config) {
    return config ? config->io_sample_rate_hz / 100u : 0u;
}
size_t ap_pipeline_internal_frame_samples(const ap_config_t *config) {
    return config ? config->internal_sample_rate_hz / 100u : 0u;
}
size_t ap_pipeline_frame_samples(const ap_pipeline_t *pipeline) {
    return pipeline ? pipeline->io_frame : 0u;
}
uint32_t ap_pipeline_mic_channels(const ap_pipeline_t *pipeline) {
    return pipeline ? pipeline->cfg.mic_channels : 0u;
}
uint32_t ap_pipeline_sample_rate_hz(const ap_pipeline_t *pipeline) {
    return pipeline ? pipeline->cfg.io_sample_rate_hz : 0u;
}

ap_status_t ap_pipeline_init(void *memory,
                             size_t memory_size,
                             const ap_config_t *config,
                             ap_pipeline_t **out_pipeline) {
    ap_pipeline_t *pipeline;
    ap_status_t status;
    if (!memory || !config || !out_pipeline) return AP_EINVAL;
    *out_pipeline = NULL;
    if (memory_size < sizeof(ap_pipeline_t)) return AP_ENOMEM;
    if (((uintptr_t)memory & (AP_PIPELINE_STATE_ALIGNMENT - 1u)) != 0u)
        return AP_EINVAL;
    status = ap_pipeline_validate_config(config);
    if (status != AP_OK) return status;

    pipeline = (ap_pipeline_t *)memory;
    memset(pipeline, 0, sizeof(*pipeline));
    pipeline->cfg = *config;
    pipeline->io_frame = config->io_sample_rate_hz / 100u;
    pipeline->internal_frame = config->internal_sample_rate_hz / 100u;
    pipeline->quality = AP_QUALITY_FULL;
    pipeline->metrics.quality = AP_QUALITY_FULL;
    pipeline->metrics.residual_echo_gain = 1.0f;
    pipeline->metrics.noise_rms_dbfs = -90.0f;
    ap_resampler_init(&pipeline->resampler);

#if AP_BUILD_STAGE_HPF
    if (AP_HAS_STAGE(pipeline, AP_STAGE_HPF))
        ap_hpf_init(&pipeline->hpf, config->internal_sample_rate_hz, config->mic_channels);
#endif
#if AP_BUILD_STAGE_BF
    if (AP_HAS_STAGE(pipeline, AP_STAGE_BF))
        ap_beamformer_init(&pipeline->beamformer,
                           config->internal_sample_rate_hz,
                           config->mic_spacing_mm);
#endif
#if AP_BUILD_STAGE_SYNC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_SYNC)) {
        ap_sync_init(&pipeline->sync,
                     config->initial_delay_ms * config->internal_sample_rate_hz / 1000u);
        ap_pipeline_update_sync_metrics(pipeline, NULL);
    }
#endif
#if AP_BUILD_ACTIVITY
    ap_activity_init(&pipeline->activity,
                     AP_ACTIVITY_FAR_THRESHOLD,
                     AP_ACTIVITY_DT_RATIO,
                     AP_ACTIVITY_HANGOVER);
#endif
#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC)) {
        uint32_t taps = config->aec_filter_ms * config->internal_sample_rate_hz / 1000u;
        if (taps > AP_AEC_CAP) taps = AP_AEC_CAP;
        ap_aec_backend_init(&pipeline->aec,
                            pipeline->internal_frame,
                            taps,
                            config->aec_adapt_stride);
        ap_pipeline_update_aec_metrics(pipeline);
    }
#endif
#if AP_BUILD_STAGE_RES
    if (AP_HAS_STAGE(pipeline, AP_STAGE_RES)) ap_res_init(&pipeline->res);
#endif
#if AP_BUILD_STAGE_NS
    if (AP_HAS_STAGE(pipeline, AP_STAGE_NS)) ap_ns_init(&pipeline->ns, pipeline->internal_frame);
#endif
#if AP_BUILD_STAGE_AGC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AGC))
        ap_agc_init(&pipeline->agc, config->agc_target_dbfs, config->limiter_dbfs);
#endif
#if AP_BUILD_STAGE_VAD
    if (AP_HAS_STAGE(pipeline, AP_STAGE_VAD)) ap_vad_init(&pipeline->vad);
#endif

    ap_pipeline_reset_aec_epoch(pipeline);
    *out_pipeline = pipeline;
    return AP_OK;
}

void ap_pipeline_reset(ap_pipeline_t *pipeline) {
    ap_pipeline_t *out = NULL;
    ap_config_t config;
    if (!pipeline) return;
    config = pipeline->cfg;
    (void)ap_pipeline_init(pipeline, sizeof(*pipeline), &config, &out);
}

ap_status_t ap_pipeline_set_quality(ap_pipeline_t *pipeline, ap_quality_t quality) {
    if (!pipeline || quality < AP_QUALITY_SAFE || quality > AP_QUALITY_FULL)
        return AP_EINVAL;
#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC)) {
        uint32_t tail_ms;
        uint32_t stride;
        uint32_t active_taps;
        if (quality == AP_QUALITY_FULL) {
            tail_ms = pipeline->cfg.aec_filter_ms;
            stride = pipeline->cfg.aec_adapt_stride;
        } else if (quality == AP_QUALITY_LITE) {
            tail_ms = pipeline->cfg.aec_filter_ms < 64u ? pipeline->cfg.aec_filter_ms : 64u;
            stride = pipeline->cfg.aec_adapt_stride < 2u ? 2u : pipeline->cfg.aec_adapt_stride;
        } else {
            tail_ms = pipeline->cfg.aec_filter_ms < 40u ? pipeline->cfg.aec_filter_ms : 40u;
            stride = pipeline->cfg.aec_adapt_stride < 4u ? 4u : pipeline->cfg.aec_adapt_stride;
        }
        active_taps = tail_ms * pipeline->cfg.internal_sample_rate_hz / 1000u;
        ap_aec_backend_set_active(&pipeline->aec, active_taps, stride);
        ap_pipeline_update_aec_metrics(pipeline);
    }
#endif
    pipeline->quality = quality;
    pipeline->metrics.quality = quality;
    return AP_OK;
}

ap_status_t ap_pipeline_push_render(ap_pipeline_t *pipeline,
                                    const int16_t *render,
                                    size_t samples) {
    if (!pipeline || !render || samples != pipeline->io_frame) return AP_EINVAL;
#if AP_BUILD_STAGE_SYNC
    if (!AP_HAS_STAGE(pipeline, AP_STAGE_SYNC)) return AP_ESTATE;
    ap_resample_input_channel(&pipeline->resampler,
                              2u,
                              render,
                              pipeline->io_frame,
                              1u,
                              0u,
                              pipeline->work,
                              pipeline->internal_frame);
    ap_sync_push_render(&pipeline->sync,
                        pipeline->work,
                        pipeline->internal_frame,
                        pipeline->metrics.processed_frames);
    return AP_OK;
#else
    (void)samples;
    return AP_ESTATE;
#endif
}

ap_status_t ap_pipeline_observe_io_timestamps(ap_pipeline_t *pipeline,
                                              uint64_t capture_timestamp_ns,
                                              uint64_t render_timestamp_ns) {
#if AP_BUILD_STAGE_SYNC
    ap_sync_event_t event;
    if (!pipeline) return AP_EINVAL;
    if (!AP_HAS_STAGE(pipeline, AP_STAGE_SYNC)) return AP_ESTATE;
    if (!ap_sync_observe_timestamps(&pipeline->sync,
                                    capture_timestamp_ns,
                                    render_timestamp_ns,
                                    pipeline->cfg.internal_sample_rate_hz,
                                    pipeline->cfg.max_delay_ms,
                                    &event))
        return AP_EINVAL;
    ap_pipeline_update_sync_metrics(pipeline, &event);
    return AP_OK;
#else
    (void)pipeline;
    (void)capture_timestamp_ns;
    (void)render_timestamp_ns;
    return AP_ESTATE;
#endif
}

ap_status_t ap_pipeline_notify_echo_path_change(ap_pipeline_t *pipeline) {
    if (!pipeline) return AP_EINVAL;
#if AP_BUILD_STAGE_SYNC
    if (!AP_HAS_STAGE(pipeline, AP_STAGE_SYNC)) return AP_ESTATE;
    ap_sync_reset(&pipeline->sync);
    ap_resampler_reset(&pipeline->resampler);
    ap_pipeline_update_sync_metrics(pipeline, NULL);
#if AP_BUILD_ACTIVITY
    ap_activity_reset(&pipeline->activity);
#endif
#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC)) {
        ap_aec_backend_reset(&pipeline->aec);
        pipeline->metrics.aec_resets++;
        ap_pipeline_reset_aec_epoch(pipeline);
    }
#endif
    return AP_OK;
#else
    return AP_ESTATE;
#endif
}

ap_status_t ap_pipeline_process_capture(ap_pipeline_t *pipeline,
                                        const int16_t *mic_interleaved,
                                        size_t frames,
                                        int16_t *output) {
    if (!pipeline || !mic_interleaved || !output || frames != pipeline->io_frame)
        return AP_EINVAL;

#if !AP_ANY_DSP_STAGE
    ap_resample_input_channel(&pipeline->resampler,
                              0u,
                              mic_interleaved,
                              pipeline->io_frame,
                              pipeline->cfg.mic_channels,
                              0u,
                              pipeline->raw_scratch,
                              pipeline->internal_frame);
    pipeline->metrics.input_rms_dbfs =
        ap_pipeline_rms_dbfs(pipeline->raw_scratch, pipeline->internal_frame);
    pipeline->metrics.output_rms_dbfs = pipeline->metrics.input_rms_dbfs;
    pipeline->metrics.processed_frames++;
    ap_resample_output(&pipeline->resampler,
                       pipeline->raw_scratch,
                       pipeline->internal_frame,
                       output,
                       pipeline->io_frame);
    return AP_OK;
#else
    uint32_t i;
    float mic_energy = 1.0e-12f;
    float ref_energy = 1.0e-12f;
    float residual_energy = 1.0e-12f;
    int far_end_active = 0;
    int double_talk_active = 0;
#if AP_BUILD_STAGE_RES
    float echo_energy = 0.0f;
#endif
#if AP_BUILD_STAGE_NS || AP_BUILD_STAGE_VAD
    float ns_speech_probability = 0.0f;
#endif

    ap_resample_input_channel(&pipeline->resampler,
                              0u,
                              mic_interleaved,
                              pipeline->io_frame,
                              pipeline->cfg.mic_channels,
                              0u,
                              pipeline->mic0,
                              pipeline->internal_frame);
#if AP_BUILD_STAGE_BF
    if (AP_HAS_STAGE(pipeline, AP_STAGE_BF)) {
        ap_resample_input_channel(&pipeline->resampler,
                                  1u,
                                  mic_interleaved,
                                  pipeline->io_frame,
                                  2u,
                                  1u,
                                  pipeline->mic1,
                                  pipeline->internal_frame);
    }
#endif
#if AP_BUILD_STAGE_HPF
    if (AP_HAS_STAGE(pipeline, AP_STAGE_HPF)) {
        ap_hpf_process(&pipeline->hpf, pipeline->mic0, pipeline->internal_frame, 0u);
#if AP_BUILD_STAGE_BF
        if (AP_HAS_STAGE(pipeline, AP_STAGE_BF))
            ap_hpf_process(&pipeline->hpf, pipeline->mic1, pipeline->internal_frame, 1u);
#endif
    }
#endif
#if AP_BUILD_STAGE_BF
    if (AP_HAS_STAGE(pipeline, AP_STAGE_BF) && pipeline->quality != AP_QUALITY_SAFE) {
        ap_beamformer_process(&pipeline->beamformer,
                              pipeline->quality == AP_QUALITY_FULL,
                              pipeline->mic0,
                              pipeline->mic1,
                              pipeline->mono,
                              pipeline->internal_frame);
    } else
#endif
    {
        memcpy(pipeline->mono,
               pipeline->mic0,
               pipeline->internal_frame * sizeof(float));
    }

#if AP_BUILD_STAGE_SYNC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_SYNC)) {
        ap_sync_event_t event;
        ap_sync_track_delay(&pipeline->sync,
                            pipeline->mono,
                            pipeline->internal_frame,
                            pipeline->cfg.internal_sample_rate_hz,
                            pipeline->cfg.max_delay_ms,
                            pipeline->cfg.enable_delay_tracking,
                            pipeline->cfg.enable_clock_drift_compensation,
                            &event);
        ap_pipeline_update_sync_metrics(pipeline, &event);
        if (ap_sync_get_reference(&pipeline->sync,
                                  pipeline->internal_frame,
                                  pipeline->reference))
            pipeline->metrics.render_underruns++;
    } else
#endif
    {
        memset(pipeline->reference, 0, pipeline->internal_frame * sizeof(float));
    }

    for (i = 0u; i < pipeline->internal_frame; ++i) {
        mic_energy += pipeline->mono[i] * pipeline->mono[i];
        ref_energy += pipeline->reference[i] * pipeline->reference[i];
    }
    mic_energy /= pipeline->internal_frame;
    ref_energy /= pipeline->internal_frame;

#if AP_BUILD_ACTIVITY
    {
        ap_activity_result_t activity;
        ap_activity_process(&pipeline->activity, mic_energy, ref_energy, &activity);
        far_end_active = activity.far_end_active;
        double_talk_active = activity.double_talk_active;
    }
#endif
    pipeline->metrics.far_end_active = (uint8_t)far_end_active;
    pipeline->metrics.double_talk_active = (uint8_t)double_talk_active;

#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC)) {
        ap_aec_result_t aec_result;
        ap_aec_backend_process(&pipeline->aec,
                               1,
                               pipeline->cfg.aec_mu,
                               pipeline->internal_frame,
                               pipeline->mono,
                               pipeline->reference,
                               pipeline->aec_out,
                               pipeline->echo_estimate,
                               far_end_active,
                               double_talk_active,
                               &aec_result);
#if AP_BUILD_STAGE_RES
        echo_energy = aec_result.echo_energy;
#endif
        ap_pipeline_update_aec_metrics(pipeline);
    } else
#endif
    {
        memcpy(pipeline->aec_out,
               pipeline->mono,
               pipeline->internal_frame * sizeof(float));
#if AP_BUILD_STAGE_AEC
        memset(pipeline->echo_estimate, 0, pipeline->internal_frame * sizeof(float));
#endif
    }

    for (i = 0u; i < pipeline->internal_frame; ++i)
        residual_energy += pipeline->aec_out[i] * pipeline->aec_out[i];
    residual_energy /= pipeline->internal_frame;

#if AP_BUILD_STAGE_RES
    if (AP_HAS_STAGE(pipeline, AP_STAGE_RES) &&
        (!AP_HAS_STAGE(pipeline, AP_STAGE_NS) || pipeline->quality == AP_QUALITY_SAFE)) {
        pipeline->metrics.residual_echo_gain = ap_res_process(
            &pipeline->res,
            ap_pipeline_enhance_mode(pipeline->quality),
            pipeline->aec_out,
            pipeline->internal_frame,
            echo_energy,
            residual_energy,
            far_end_active,
            double_talk_active);
    } else {
        pipeline->metrics.residual_echo_gain = 1.0f;
    }
#else
    pipeline->metrics.residual_echo_gain = 1.0f;
#endif

#if AP_BUILD_STAGE_NS
    if (AP_HAS_STAGE(pipeline, AP_STAGE_NS)) {
        ap_ns_result_t ns_result;
        const int frequency_res =
#if AP_BUILD_STAGE_RES
            AP_HAS_STAGE(pipeline, AP_STAGE_RES) && pipeline->quality != AP_QUALITY_SAFE;
#else
            0;
#endif
        const float *echo_ptr =
#if AP_BUILD_STAGE_AEC
            pipeline->echo_estimate;
#else
            NULL;
#endif
        ap_ns_process(&pipeline->ns,
                      ap_pipeline_enhance_mode(pipeline->quality),
                      pipeline->cfg.ns_floor,
                      pipeline->aec_out,
                      echo_ptr,
                      pipeline->processed,
                      pipeline->internal_frame,
                      frequency_res,
                      far_end_active,
                      double_talk_active,
                      &ns_result);
        pipeline->metrics.noise_rms_dbfs = ns_result.noise_rms_dbfs;
        pipeline->metrics.frequency_res_active = ns_result.frequency_res_active;
        ns_speech_probability = ns_result.speech_probability;
        if (ns_result.frequency_res_active)
            pipeline->metrics.residual_echo_gain = ns_result.residual_echo_gain;
    } else
#endif
    {
        memcpy(pipeline->processed,
               pipeline->aec_out,
               pipeline->internal_frame * sizeof(float));
        pipeline->metrics.frequency_res_active = 0u;
        pipeline->metrics.noise_rms_dbfs = -90.0f;
    }

#if AP_BUILD_STAGE_AGC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AGC))
        ap_agc_process(&pipeline->agc, pipeline->processed, pipeline->internal_frame);
#endif
#if AP_BUILD_STAGE_VAD
    if (AP_HAS_STAGE(pipeline, AP_STAGE_VAD)) {
        ap_vad_result_t vad_result;
        ap_vad_process(&pipeline->vad,
                       pipeline->processed,
                       pipeline->internal_frame,
                       ns_speech_probability,
                       AP_HAS_STAGE(pipeline, AP_STAGE_NS),
                       &vad_result);
        pipeline->metrics.vad_probability = vad_result.probability;
        pipeline->metrics.vad_active = vad_result.active;
    } else
#endif
    {
        pipeline->metrics.vad_probability = 0.0f;
        pipeline->metrics.vad_active = 0u;
    }

    pipeline->metrics.input_rms_dbfs = 10.0f * log10f(mic_energy + 1.0e-18f);
    pipeline->metrics.output_rms_dbfs =
        ap_pipeline_rms_dbfs(pipeline->processed, pipeline->internal_frame);
    pipeline->metrics.erle_valid = 0u;
#if AP_BUILD_STAGE_AEC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC) && far_end_active &&
        !double_talk_active && ref_energy > 1.0e-7f && residual_energy > 1.0e-12f) {
        const float erle = 10.0f * log10f(
            (mic_energy + 1.0e-12f) / (residual_energy + 1.0e-12f));
        pipeline->metrics.erle_db = pipeline->aec_convergence_frames ?
            0.95f * pipeline->metrics.erle_db + 0.05f * erle : erle;
        if (pipeline->aec_convergence_frames < UINT32_MAX)
            pipeline->aec_convergence_frames++;
        pipeline->metrics.aec_convergence_frames = pipeline->aec_convergence_frames;
        pipeline->metrics.aec_converged =
            (uint8_t)(pipeline->aec_convergence_frames >= AP_AEC_CONVERGED_FRAMES);
        pipeline->metrics.erle_valid = 1u;
    }
#endif

    pipeline->metrics.processed_frames++;
#if AP_BUILD_STAGE_SYNC
    if (AP_HAS_STAGE(pipeline, AP_STAGE_SYNC) &&
        ap_sync_note_capture(&pipeline->sync, pipeline->metrics.processed_frames))
        pipeline->metrics.render_underruns++;
#endif
    ap_resample_output(&pipeline->resampler,
                       pipeline->processed,
                       pipeline->internal_frame,
                       output,
                       pipeline->io_frame);
    return AP_OK;
#endif
}

void ap_pipeline_get_metrics(const ap_pipeline_t *pipeline, ap_metrics_t *metrics) {
    if (pipeline && metrics) *metrics = pipeline->metrics;
}

uint32_t ap_pipeline_algorithmic_latency_ms(const ap_pipeline_t *pipeline) {
    uint32_t latency_ms = 0u;
    uint32_t delay_samples;
    if (!pipeline) return 0u;
    if (AP_HAS_STAGE(pipeline, AP_STAGE_NS)) latency_ms += AP_FRAME_MS;
    delay_samples = ap_resampler_filter_delay_samples(pipeline->io_frame,
                                                      pipeline->internal_frame);
    if (delay_samples) {
        latency_ms += (delay_samples * 1000u + pipeline->cfg.io_sample_rate_hz - 1u) /
                      pipeline->cfg.io_sample_rate_hz;
    }
    delay_samples = ap_resampler_filter_delay_samples(pipeline->internal_frame,
                                                      pipeline->io_frame);
    if (delay_samples) {
        latency_ms += (delay_samples * 1000u + pipeline->cfg.internal_sample_rate_hz - 1u) /
                      pipeline->cfg.internal_sample_rate_hz;
    }
    return latency_ms;
}
