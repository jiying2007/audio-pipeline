#include "audio_pipeline/audio_pipeline.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static _Alignas(16) unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
static uint32_t index_total;
static int16_t value(uint32_t n) {
    uint32_t x = n + 0x9e3779b9u;
    x ^= x >> 16u; x *= 0x7feb352du; x ^= x >> 15u; x *= 0x846ca68bu; x ^= x >> 16u;
    return (int16_t)((int32_t)(x >> 16u) - 32768);
}
static void feed(ap_pipeline_t *p, uint32_t delay, int capture) {
    int16_t render[160], mic[160], output[160];
    uint32_t i;
    for (i = 0u; i < 160u; ++i) {
        const uint32_t n = index_total++;
        render[i] = (int16_t)(value(n) / 2);
        mic[i] = n >= delay ? (int16_t)(value(n - delay) / 4) : 0;
    }
    assert(ap_pipeline_push_render(p, render, 160u) == AP_OK);
    if (capture) assert(ap_pipeline_process_capture(p, mic, 160u, output) == AP_OK);
}
int main(void) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    ap_metrics_t steady, mismatched, restored;
    uint32_t i;
    c.mic_channels = 1u; c.stages = AP_STAGE_SYNC | AP_STAGE_AEC;
    c.initial_delay_ms = 40u; c.max_delay_ms = 100u;
    c.enable_delay_tracking = 1u; c.enable_clock_drift_compensation = 1u;
    assert(ap_pipeline_init(state, sizeof(state), &c, &p) == AP_OK);
    for (i = 0u; i < 60u; ++i) feed(p, 640u, 1);
    ap_pipeline_get_metrics(p, &steady);
    assert(steady.estimated_delay_ms >= 39u && steady.estimated_delay_ms <= 41u);
    feed(p, 1280u, 0);
    for (i = 0u; i < 60u; ++i) feed(p, 1280u, 1);
    ap_pipeline_get_metrics(p, &mismatched);
    assert(mismatched.delay_jumps == steady.delay_jumps);
    assert(mismatched.estimated_delay_ms < 75u);
    assert(ap_pipeline_notify_stream_discontinuity(p, AP_DISCONTINUITY_CAPTURE_GAP, 1u) == AP_OK);
    for (i = 0u; i < 60u; ++i) feed(p, 1280u, 1);
    ap_pipeline_get_metrics(p, &restored);
    assert(restored.delay_jumps > mismatched.delay_jumps);
    assert(restored.estimated_delay_ms >= 75u && restored.estimated_delay_ms <= 85u);
    printf("D8_PUBLIC_RECOVERY_PASS steady=%u mismatched=%u restored=%u jumps=%llu/%llu/%llu\n",
           steady.estimated_delay_ms, mismatched.estimated_delay_ms, restored.estimated_delay_ms,
           (unsigned long long)steady.delay_jumps, (unsigned long long)mismatched.delay_jumps,
           (unsigned long long)restored.delay_jumps);
    return 0;
}
