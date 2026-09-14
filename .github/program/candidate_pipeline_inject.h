#ifndef AP_CANDIDATE_PIPELINE_INJECT_H
#define AP_CANDIDATE_PIPELINE_INJECT_H

#include "audio_pipeline/audio_pipeline.h"
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int ap_candidate_env_float(const char *name, float *value) {
    const char *text = getenv(name);
    char *end = NULL;
    float parsed;
    if (!text || !*text) return 0;
    errno = 0;
    parsed = strtof(text, &end);
    if (errno != 0 || !end || *end != '\0' || !isfinite(parsed)) {
        fprintf(stderr, "invalid %s=%s\n", name, text);
        return -1;
    }
    *value = parsed;
    return 1;
}

static ap_status_t ap_candidate_pipeline_init(void *memory, size_t memory_size,
                                               const ap_config_t *config,
                                               ap_pipeline_t **out_pipeline) {
    ap_tuning_t tuning;
    ap_status_t status;
    int present;

    status = ap_pipeline_init(memory, memory_size, config, out_pipeline);
    if (status != AP_OK) return status;

    memset(&tuning, 0, sizeof(tuning));
    tuning.struct_size = sizeof(tuning);
    tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;

    present = ap_candidate_env_float("AP_TUNING_AEC_MU", &tuning.aec_mu);
    if (present < 0) return AP_EINVAL;
    if (present) tuning.mask |= AP_TUNING_AEC_MU;
    present = ap_candidate_env_float("AP_TUNING_NS_FLOOR", &tuning.ns_floor);
    if (present < 0) return AP_EINVAL;
    if (present) tuning.mask |= AP_TUNING_NS_FLOOR;
    present = ap_candidate_env_float("AP_TUNING_AGC_TARGET_DBFS", &tuning.agc_target_dbfs);
    if (present < 0) return AP_EINVAL;
    if (present) tuning.mask |= AP_TUNING_AGC_TARGET;
    present = ap_candidate_env_float("AP_TUNING_LIMITER_DBFS", &tuning.limiter_dbfs);
    if (present < 0) return AP_EINVAL;
    if (present) tuning.mask |= AP_TUNING_LIMITER;

    if (tuning.mask == 0u) return AP_OK;
    status = ap_pipeline_apply_tuning(*out_pipeline, &tuning);
    if (status != AP_OK) fprintf(stderr, "invalid non-shipping candidate tuning\n");
    return status;
}

#endif
