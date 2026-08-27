#include "core/ap_pipeline_internal.h"

ap_stage_mask_t ap_pipeline_stages(const ap_pipeline_t *pipeline) {
    return pipeline ? pipeline->cfg.stages : 0u;
}
