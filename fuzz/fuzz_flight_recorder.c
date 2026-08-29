#include "audio_pipeline/audio_diag.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    ap_flight_recorder_config_t cfg;
    if (size < 16u) return 0;
    memset(&cfg, 0, sizeof(cfg));
    cfg.struct_size = sizeof(cfg);
    cfg.api_version = AP_DIAG_API_VERSION;
    cfg.io_sample_rate_hz = ((uint32_t)data[0] << 8u) | data[1];
    cfg.mic_channels = data[2];
    cfg.frame_samples = ((uint32_t)data[3] << 8u) | data[4];
    cfg.pre_roll_frames = ((uint32_t)data[5] << 24u) | ((uint32_t)data[6] << 16u) | ((uint32_t)data[7] << 8u) | data[8];
    cfg.post_roll_frames = ((uint32_t)data[9] << 24u) | ((uint32_t)data[10] << 16u) | ((uint32_t)data[11] << 8u) | data[12];
    cfg.record_mask = data[13];
    cfg.trigger_severity = (ap_event_severity_t)data[14];
    (void)ap_flight_recorder_state_size(&cfg);
    return 0;
}
