/* Fixed synthetic event contract; public pipeline plus independently checked SYNC shadow. */
#define main d13_unused_d9_main
#include "device_acquisition_d9.c"
#undef main
#include "sync/ap_sync.h"

static ap_sync_state_t shadow;
static const uint32_t targets[3] = {1u, 7u, 80u};

static void contract_case(const char *directory, uint32_t rate, uint32_t seed,
                          uint32_t scenario) {
    ap_config_t c = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    ap_metrics_t m;
    ap_sync_event_t event;
    int16_t render[160], mic[160], output[160];
    float rf[160], mf[160];
    const uint32_t hop = rate / 100u;
    const uint32_t target = scenario < 9u ? targets[scenario % 3u] : 40u;
    const uint32_t initial = scenario >= 3u && scenario < 6u ? target : 40u;
    const uint32_t phase = scenario >= 6u && scenario < 12u ? 120u : 0u;
    const uint32_t pulse_frames = scenario >= 9u && scenario < 12u ? (scenario - 8u) * 10u : 0u;
    const uint32_t truth_valid = scenario < 12u;
    const char *family = scenario < 3u ? "acquire" : scenario < 6u ? "steady" :
                         scenario < 9u ? "path-switch" : scenario < 11u ? "pulse" :
                         scenario == 11u ? "pulse3" : scenario == 12u ? "silence" : "unrelated";
    char id[160];
    uint32_t frame, i, n = 0u;
    uint64_t jumps = 0u, slips = 0u;
    FILE *input, *metrics, *pcm, *config;
    const int length = snprintf(id, sizeof(id), "r%u-s%u-%s-d%u-p%u", rate, seed, family, target, pulse_frames);
    assert(length > 0 && (size_t)length < sizeof(id));
    c.io_sample_rate_hz = rate; c.internal_sample_rate_hz = rate;
    c.mic_channels = 1u; c.stages = AP_STAGE_SYNC | AP_STAGE_AEC;
    c.initial_delay_ms = initial; c.max_delay_ms = 100u;
    c.enable_delay_tracking = 1u; c.enable_clock_drift_compensation = 1u;
    assert(ap_pipeline_init(storage, sizeof(storage), &c, &p) == AP_OK);
    ap_sync_init(&shadow, initial * rate / 1000u);
    input = opened(directory, id, ".input.s16le"); metrics = opened(directory, id, ".metrics.csv");
    pcm = opened(directory, id, ".output.s16le"); config = opened(directory, id, ".config.json");
    assert(fprintf(config, "{\"profile\":\"CALL\",\"io_rate\":%u,\"internal_rate\":%u,\"channels\":%u,\"stages\":%u,\"initial_delay_ms\":%u,\"max_delay_ms\":%u,\"tracking\":%u,\"drift\":%u,\"aec_filter_ms\":%u,\"aec_mu\":%.9g,\"aec_adapt_stride\":%u}\n",
        c.io_sample_rate_hz, c.internal_sample_rate_hz, c.mic_channels, c.stages,
        c.initial_delay_ms, c.max_delay_ms, (uint32_t)c.enable_delay_tracking,
        (uint32_t)c.enable_clock_drift_compensation, c.aec_filter_ms, (double)c.aec_mu,
        c.aec_adapt_stride) > 0);
    assert(fclose(config) == 0);
    assert(fprintf(metrics, "frame,truth_valid,truth_ms,pulse_active,delay_ms,jumps,resets,slips,old_samples,new_samples,confirm_before,candidate_before,confirm_after,candidate_after,observed,route_jump,event_slips,error_samples\n") > 0);
    for (frame = 0u; frame < 300u; ++frame) {
        const uint32_t truth = scenario >= 6u && scenario < 9u && frame < phase ? 40u : target;
        const uint32_t delay = truth * rate / 1000u;
        const uint32_t decoy = 80u * rate / 1000u;
        const uint32_t pulse_active = pulse_frames && frame >= phase && frame < phase + pulse_frames;
        const uint32_t old = shadow.delay_samples;
        const uint32_t before = shadow.route_candidate_confirmations;
        const uint32_t candidate_before = shadow.route_candidate_delay;
        for (i = 0u; i < hop; ++i, ++n) {
            float v;
            render[i] = scenario == 12u ? 0 : render_value(n, rate, seed, 0u);
            v = n >= delay ? 0.4f * (float)render_value(n - delay, rate, seed, 0u) : 0.0f;
            if (pulse_active && n >= decoy) v += 0.9f * (float)render_value(n - decoy, rate, seed, 0u);
            if (scenario == 12u) v = 0.0f;
            if (scenario == 13u) v = 0.4f * (float)render_value(n, rate, seed + 100u, 0u);
            assert(isfinite(v) && fabsf(v) < 32767.0f);
            mic[i] = (int16_t)v;
            rf[i] = (float)render[i] * (1.0f / 32768.0f);
            mf[i] = (float)mic[i] * (1.0f / 32768.0f);
            s16(input, render[i]); s16(input, mic[i]);
        }
        assert(ap_pipeline_push_render(p, render, hop) == AP_OK);
        ap_sync_push_render(&shadow, rf, hop, frame);
        ap_sync_track_delay(&shadow, mf, hop, rate, 100u, 1, 1, &event);
        assert(ap_pipeline_process_capture(p, mic, hop, output) == AP_OK);
        ap_pipeline_get_metrics(p, &m);
        jumps += event.route_jump; slips += event.reference_sample_slips;
        assert(m.estimated_delay_ms == shadow.delay_samples * 1000u / rate);
        assert(m.delay_jumps == jumps && m.reference_sample_slips == slips);
        assert(m.aec_resets == jumps && isfinite(m.estimated_drift_ppm));
        if (event.delay_observed) assert(m.delay_error_samples == event.delay_error_samples);
        assert(fprintf(metrics, "%u,%u,%u,%u,%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%u,%u,%u,%u,%u,%u,%u,%u,%u,%d\n",
            frame, truth_valid, truth, pulse_active, m.estimated_delay_ms,
            m.delay_jumps, m.aec_resets, m.reference_sample_slips, old, shadow.delay_samples,
            before, candidate_before, (uint32_t)shadow.route_candidate_confirmations,
            shadow.route_candidate_delay, (uint32_t)event.delay_observed,
            (uint32_t)event.route_jump, event.reference_sample_slips, event.delay_error_samples) > 0);
        for (i = 0u; i < hop; ++i) s16(pcm, output[i]);
    }
    assert(fclose(input) == 0 && fclose(metrics) == 0 && fclose(pcm) == 0);
    printf("{\"case_id\":\"%s\",\"rate\":%u,\"seed\":%u,\"family\":\"%s\",\"target_ms\":%u,\"initial_ms\":%u,\"phase\":%u,\"pulse_frames\":%u,\"truth_valid\":%u,\"mandatory\":%s,\"capture_frames\":300,\"final_delay_ms\":%u,\"jumps\":%" PRIu64 ",\"resets\":%" PRIu64 ",\"slips\":%" PRIu64 "}\n",
        id, rate, seed, family, target, initial, phase, pulse_frames, truth_valid,
        scenario == 11u ? "false" : "true", m.estimated_delay_ms, m.delay_jumps,
        m.aec_resets, m.reference_sample_slips);
}

int main(int argc, char **argv) {
    const uint32_t rates[2] = {8000u, 16000u};
    uint32_t r, seed, scenario;
    if (argc != 2 && argc != 3) return 2;
    if (argc == 3) {
        if (strcmp(argv[2], "repeat") != 0) return 2;
        contract_case(argv[1], 16000u, 1u, 7u);
        return 0;
    }
    for (r = 0u; r < 2u; ++r) for (seed = 1u; seed <= 2u; ++seed)
        for (scenario = 0u; scenario < 14u; ++scenario)
            contract_case(argv[1], rates[r], seed, scenario);
    return 0;
}
