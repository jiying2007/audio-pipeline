#!/usr/bin/env python3
from pathlib import Path

p = Path('src/core/ap_pipeline.c')
s = p.read_text()
old1 = '''#if AP_BUILD_STAGE_NS || AP_BUILD_STAGE_VAD
    float ns_speech_probability = 0.0f;
#endif

    ap_resample_input_channel(&pipeline->resampler,
'''
new1 = '''#if AP_BUILD_STAGE_NS || AP_BUILD_STAGE_VAD
    float ns_speech_probability = 0.0f;
#endif
#if AP_BUILD_ACTIVITY && AP_BUILD_STAGE_AEC
    float previous_residual_energy = 1.0e-12f;
    float previous_echo_energy = 1.0e-12f;
    int previous_residual_echo_valid = 0;
    if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC)) {
        for (i = 0u; i < pipeline->internal_frame; ++i) {
            previous_residual_energy += pipeline->aec_out[i] * pipeline->aec_out[i];
            previous_echo_energy += pipeline->echo_estimate[i] * pipeline->echo_estimate[i];
        }
        previous_residual_energy /= pipeline->internal_frame;
        previous_echo_energy /= pipeline->internal_frame;
        previous_residual_echo_valid = pipeline->metrics.aec_converged != 0u;
    }
#endif

    ap_resample_input_channel(&pipeline->resampler,
'''
old2 = '''#if AP_BUILD_ACTIVITY
    {
        ap_activity_result_t activity;
        ap_activity_process(&pipeline->activity, mic_energy, ref_energy, &activity);
        far_end_active = activity.far_end_active;
        double_talk_active = activity.double_talk_active;
    }
#endif
'''
new2 = '''#if AP_BUILD_ACTIVITY
    {
        ap_activity_result_t activity;
#if AP_BUILD_STAGE_AEC
        if (AP_HAS_STAGE(pipeline, AP_STAGE_AEC)) {
            ap_activity_process_with_residual_echo(&pipeline->activity,
                                                   mic_energy,
                                                   ref_energy,
                                                   previous_residual_energy,
                                                   previous_echo_energy,
                                                   previous_residual_echo_valid,
                                                   &activity);
        } else
#endif
        {
            ap_activity_process(&pipeline->activity, mic_energy, ref_energy, &activity);
        }
        far_end_active = activity.far_end_active;
        double_talk_active = activity.double_talk_active;
    }
#endif
'''
assert s.count(old1) == 1, s.count(old1)
assert s.count(old2) == 1, s.count(old2)
p.write_text(s.replace(old1, new1).replace(old2, new2))
