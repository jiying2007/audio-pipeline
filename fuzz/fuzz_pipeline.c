#include "audio_pipeline/audio_pipeline.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(__clang__)
#define AP_ALIGN16 _Alignas(16)
#else
#define AP_ALIGN16
#endif

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    static const uint32_t rates[] = {8000u, 16000u, 24000u, 32000u, 48000u};
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    ap_config_t c;
    ap_pipeline_t *p = NULL;
    size_t frame, mic_bytes, render_bytes, copy;
    uint8_t selector;
    if (size == 0u) return 0;
    selector = data[0];
    c = ap_config_default((selector & 1u) ? AP_PROFILE_ASSISTANT : AP_PROFILE_CALL);
    c.io_sample_rate_hz = rates[(selector >> 1u) % (sizeof(rates) / sizeof(rates[0]))];
    c.internal_sample_rate_hz = c.io_sample_rate_hz == 8000u ? 8000u : 16000u;
    c.mic_channels = ((selector >> 4u) & 1u) + 1u;
    c.enable_delay_tracking = (selector >> 5u) & 1u;
    frame = c.io_sample_rate_hz / 100u;
    mic_bytes = frame * c.mic_channels * sizeof(int16_t);
    render_bytes = frame * sizeof(int16_t);
    memset(mic, 0, sizeof(mic));
    memset(render, 0, sizeof(render));
    if (size > 1u) {
        copy = size - 1u < mic_bytes ? size - 1u : mic_bytes;
        memcpy(mic, data + 1u, copy);
        if (size > 1u + copy) {
            size_t left = size - 1u - copy;
            if (left > render_bytes) left = render_bytes;
            memcpy(render, data + 1u + copy, left);
        }
    }
    if (ap_pipeline_init(state, sizeof(state), &c, &p) != AP_OK) return 0;
    (void)ap_pipeline_push_render(p, render, frame);
    (void)ap_pipeline_process_capture(p, mic, frame, out);
    if ((selector & 0xc0u) == 0x40u) (void)ap_pipeline_set_quality(p, AP_QUALITY_LITE);
    if ((selector & 0xc0u) == 0x80u) (void)ap_pipeline_set_quality(p, AP_QUALITY_SAFE);
    (void)ap_pipeline_process_capture(p, mic, frame, out);
    return 0;
}
