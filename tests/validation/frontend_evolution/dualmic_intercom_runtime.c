/* Research-only finite file adapter for the unchanged public CALL/Runtime API.
 * No device I/O, codec, network implementation or alternative DSP lives here. */
#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { FRAME = 160, MIC_VALUES = 320, MAX_FRAMES = 10000 };
static _Alignas(16) unsigned char pipeline_memory[AP_PIPELINE_STATE_MAX_BYTES];
static _Alignas(16) unsigned char runtime_memory[AP_RUNTIME_STATE_MAX_BYTES];

static uint64_t monotonic_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) return 0;
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}

static void identity(FILE *file, const ap_config_t *cfg, const ap_tuning_t *tuning,
                     int readback_complete) {
    const ap_build_info_t *b = ap_build_info();
    fprintf(file, "{\"version\":\"%s\",\"source_revision\":\"%s\","
            "\"compiler_id\":\"%s\",\"compiler_version\":\"%s\","
            "\"target_triple\":\"%s\",\"build_type\":\"%s\","
            "\"config_digest\":\"%s\",\"module_mask\":%u,"
            "\"simd_backend\":\"%s\",\"aec_backend\":\"%s\","
            "\"ns_estimator\":\"%s\",\"resampler_mode\":\"%s\","
            "\"fast_math\":%u,\"has_linux_runtime\":%u,"
            "\"pipeline_state_bytes\":%zu,\"runtime_state_bytes\":%zu,"
            "\"config\":{\"io_sample_rate_hz\":%u,\"mic_channels\":%u,"
            "\"aec_filter_ms\":%u,\"aec_mu\":%.9g,\"ns_floor\":%.9g,"
            "\"agc_target_dbfs\":%.9g,\"limiter_dbfs\":%.9g,"
            "\"stages\":%u,\"runtime_queue_depth\":%u},"
            "\"effective_readback\":%s,\"readback_phase\":\"post_init_before_worker\","
            "\"tuning\":{\"mask\":%u,\"aec_mu\":%.9g,\"ns_floor\":%.9g,"
            "\"agc_target_dbfs\":%.9g,\"limiter_dbfs\":%.9g}}",
            b->version, b->source_revision, b->compiler_id, b->compiler_version,
            b->target_triple, b->build_type, b->config_digest, (unsigned)b->module_mask,
            b->simd_backend, b->aec_backend, b->ns_estimator, b->resampler_mode,
            (unsigned)b->fast_math, (unsigned)b->has_linux_runtime,
            ap_pipeline_state_size(), ap_runtime_state_size(),
            (unsigned)cfg->io_sample_rate_hz, (unsigned)cfg->mic_channels,
            (unsigned)cfg->aec_filter_ms, (double)cfg->aec_mu, (double)cfg->ns_floor,
            (double)cfg->agc_target_dbfs, (double)cfg->limiter_dbfs,
            (unsigned)cfg->stages, (unsigned)b->runtime_queue_depth,
            readback_complete ? "true" : "false", (unsigned)tuning->mask,
            (double)tuning->aec_mu, (double)tuning->ns_floor,
            (double)tuning->agc_target_dbfs, (double)tuning->limiter_dbfs);
}

static int finite_metrics(const ap_metrics_t *m) {
    return isfinite(m->input_rms_dbfs) && isfinite(m->output_rms_dbfs) &&
           isfinite(m->noise_rms_dbfs) && isfinite(m->erle_db) &&
           isfinite(m->residual_echo_gain) && isfinite(m->vad_probability) &&
           isfinite(m->estimated_drift_ppm);
}

static int receive_one(ap_runtime_t *runtime, int16_t *output, ap_metrics_t *metrics) {
    const uint64_t start = monotonic_ns();
    const struct timespec pause = {0, 100000};
    if (!start) return 0;
    for (;;) {
        const ap_status_t result = ap_runtime_receive(runtime, output, metrics);
        if (result != AP_EEMPTY) return result == AP_OK;
        if (monotonic_ns() - start >= UINT64_C(2000000000)) return 0;
        (void)nanosleep(&pause, NULL);
    }
}

static int close_file(FILE **file) {
    int result = 0;
    if (*file) result = fclose(*file);
    *file = NULL;
    return result;
}

int main(int argc, char **argv) {
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_tuning_t tuning = {0};
    ap_runtime_config_t runtime_cfg = ap_runtime_config_default();
    ap_runtime_options_t runtime_options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_runtime_metrics_t rm = {0};
    FILE *mic_file = NULL, *render_file = NULL, *out_file = NULL;
    FILE *consumed_file = NULL, *trace_file = NULL, *report_file = NULL;
    int16_t mic[MIC_VALUES], render[FRAME], output[FRAME];
    uint64_t frames = 0, events = 0;
    const uint16_t endian = 1;
    unsigned long reopen_frame = 0;
    int use_runtime = 0, failed = 1, readback_complete = 0;
    const char *error = "initialization";
    uint32_t latency = 0;
    char *end = NULL;
    cfg.io_sample_rate_hz = 16000;
    cfg.internal_sample_rate_hz = 16000;
    cfg.mic_channels = 2;
    if (*(const unsigned char *)&endian != 1) {
        fprintf(stderr, "this research adapter requires a little-endian host\n");
        return 2;
    }
    if (argc == 2 && strcmp(argv[1], "--identity") == 0) {
        if (ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory), &cfg, &pipeline) != AP_OK ||
            ap_pipeline_get_config(pipeline, &cfg) != AP_OK ||
            ap_pipeline_get_tuning(pipeline, &tuning) != AP_OK) return 1;
        identity(stdout, &cfg, &tuning, 1);
        return fputs("\n", stdout) < 0 || fflush(stdout) != 0 ? 1 : 0;
    }
    if (argc != 9 || (strcmp(argv[1], "runtime") != 0 && strcmp(argv[1], "direct") != 0)) {
        fprintf(stderr, "usage: bridge runtime|direct mic.pcm render.pcm output.pcm "
                "consumed-render.pcm trace.jsonl report.json reopen-frame-or-0\n");
        return 2;
    }
    errno = 0;
    reopen_frame = strtoul(argv[8], &end, 10);
    if (errno || !*argv[8] || *end || reopen_frame >= MAX_FRAMES) return 2;
    use_runtime = strcmp(argv[1], "runtime") == 0;
    report_file = fopen(argv[7], "wb");
    if (!report_file) return 1;
    if (ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory), &cfg, &pipeline) != AP_OK)
        goto done;
    error = "effective_config_readback";
    if (ap_pipeline_get_config(pipeline, &cfg) != AP_OK ||
        ap_pipeline_get_tuning(pipeline, &tuning) != AP_OK) goto done;
    readback_complete = 1;
    latency = ap_pipeline_algorithmic_latency_ms(pipeline);
    if (use_runtime) {
        if (ap_runtime_open(runtime_memory, sizeof(runtime_memory), pipeline,
                            &runtime_cfg, &runtime_options, &runtime) != AP_OK ||
            ap_runtime_start(runtime) != AP_OK) goto done;
    }
    mic_file = fopen(argv[2], "rb");
    render_file = fopen(argv[3], "rb");
    out_file = fopen(argv[4], "wb");
    consumed_file = fopen(argv[5], "wb");
    trace_file = fopen(argv[6], "wb");
    error = "file_open";
    if (!mic_file || !render_file || !out_file || !consumed_file || !trace_file) goto done;
    for (;;) {
        ap_metrics_t metrics;
        ap_frame_metadata_t metadata = {0};
        size_t bytes = fread(mic, 1, sizeof(mic), mic_file);
        error = "capture_completeness";
        if (bytes == 0) {
            if (ferror(mic_file) || !feof(mic_file)) goto done;
            break;
        }
        if (bytes != sizeof(mic) || frames >= MAX_FRAMES) goto done;
        error = "render_completeness";
        if (fread(render, 1, sizeof(render), render_file) != sizeof(render)) goto done;
        metadata.struct_size = sizeof(metadata);
        metadata.api_version = AP_RUNTIME_API_VERSION;
        metadata.stream_sequence = frames;
        if (reopen_frame && frames == reopen_frame) {
            metadata.flags = AP_FRAME_RENDER_DISCONTINUITY | AP_FRAME_CODEC_REOPEN;
            metadata.lost_render_frames = 2;
        }
        error = "pipeline_execution";
        if (use_runtime) {
            /* This exact render argument is copied by successful submit and is
             * retained below. A network PLC frame stays PRESENT. */
            if (ap_runtime_submit_frame(runtime, mic, render, &metadata) != AP_OK ||
                !receive_one(runtime, output, &metrics)) goto done;
            for (;;) {
                ap_event_t event;
                const ap_status_t status = ap_runtime_receive_event(runtime, &event);
                if (status == AP_EEMPTY) break;
                if (status != AP_OK || events >= MAX_FRAMES * UINT64_C(32)) goto done;
                ++events;
            }
        } else {
            if (metadata.flags &&
                ap_pipeline_notify_stream_discontinuity(pipeline,
                    AP_DISCONTINUITY_RENDER_GAP | AP_DISCONTINUITY_CODEC_REOPEN, 2) != AP_OK)
                goto done;
            if (ap_pipeline_push_render(pipeline, render, FRAME) != AP_OK ||
                ap_pipeline_process_capture(pipeline, mic, FRAME, output) != AP_OK)
                goto done;
            ap_pipeline_get_metrics(pipeline, &metrics);
        }
        error = "metrics_or_quality";
        if (!finite_metrics(&metrics) || metrics.quality != AP_QUALITY_FULL) goto done;
        error = "output_write";
        if (fwrite(output, 1, sizeof(output), out_file) != sizeof(output) ||
            fwrite(render, 1, sizeof(render), consumed_file) != sizeof(render)) goto done;
        if (fprintf(trace_file, "{\"frame\":%" PRIu64 ",\"render_present\":true,"
                    "\"metadata_flags\":%u,\"quality\":%d,\"vad_active\":%u,"
                    "\"processed_frames\":%" PRIu64 ",\"erle_db\":%.9g,"
                    "\"output_rms_dbfs\":%.9g,\"estimated_delay_ms\":%u,"
                    "\"aec_resets\":%" PRIu64 ",\"timestamp_observations\":%" PRIu64 "}\n",
                    frames, (unsigned)metadata.flags, (int)metrics.quality,
                    (unsigned)metrics.vad_active, metrics.processed_frames,
                    (double)metrics.erle_db, (double)metrics.output_rms_dbfs,
                    (unsigned)metrics.estimated_delay_ms, metrics.aec_resets,
                    metrics.timestamp_observations) < 0) goto done;
        ++frames;
    }
    error = "render_suffix_or_empty_capture";
    if (!frames || fgetc(render_file) != EOF || ferror(render_file)) goto done;
    if (reopen_frame && reopen_frame >= frames) goto done;
    failed = 0;
    error = "NONE";
done:
    if (runtime) {
        ap_runtime_stop(runtime);
        rm.struct_size = sizeof(rm);
        rm.api_version = AP_RUNTIME_API_VERSION;
        if (ap_runtime_read_metrics(runtime, &rm) != AP_OK ||
            rm.submitted_frames != frames || rm.processed_frames != frames ||
            rm.failed_frames || rm.input_full_events || rm.output_drop_events ||
            rm.capture_process_failures || rm.render_push_failures) {
            if (!failed) error = "runtime_integrity";
            failed = 1;
        }
        ap_runtime_deinit(runtime);
    }
    {
        const int a = close_file(&mic_file);
        const int b = close_file(&render_file);
        if (a || b) { failed = 1; error = "input_close"; }
    }
    /* Do not short-circuit closes: every successfully opened stream is closed. */
    {
        const int a = close_file(&out_file);
        const int b = close_file(&consumed_file);
        const int c = close_file(&trace_file);
        if (a || b || c) { failed = 1; error = "output_close"; }
    }
    fprintf(report_file, "{\"status\":\"%s\",\"error\":\"%s\",\"mode\":\"%s\","
            "\"frames\":%" PRIu64 ",\"events_received\":%" PRIu64 ","
            "\"algorithmic_latency_ms\":%u,\"build\":",
            failed ? "FAIL" : "PASS", error, argv[1], frames, events, (unsigned)latency);
    identity(report_file, &cfg, &tuning, readback_complete);
    fprintf(report_file, ",\"runtime\":{\"submitted_frames\":%" PRIu64
            ",\"processed_frames\":%" PRIu64 ",\"failed_frames\":%" PRIu64
            ",\"input_full_events\":%" PRIu64 ",\"output_drop_events\":%" PRIu64
            ",\"render_push_failures\":%" PRIu64 ",\"capture_process_failures\":%" PRIu64
            ",\"stream_discontinuities\":%" PRIu64 ",\"render_gap_frames\":%" PRIu64
            ",\"capture_gap_frames\":%" PRIu64 ",\"timestamp_frames\":%" PRIu64
            ",\"event_drop_events\":%" PRIu64 ",\"dsp_overruns\":%" PRIu64
            ",\"input_queue_high_water\":%u,\"output_queue_high_water\":%u,"
            "\"max_dsp_us\":%u,\"p50_dsp_us\":%u,\"p95_dsp_us\":%u,\"p99_dsp_us\":%u,"
            "\"overload_us\":%u,\"recover_frames\":%u}}\n",
            rm.submitted_frames, rm.processed_frames, rm.failed_frames,
            rm.input_full_events, rm.output_drop_events,
            rm.render_push_failures, rm.capture_process_failures,
            rm.stream_discontinuities, rm.render_gap_frames, rm.capture_gap_frames,
            rm.timestamp_frames, rm.event_drop_events, rm.dsp_overruns,
            (unsigned)rm.input_queue_high_water, (unsigned)rm.output_queue_high_water,
            (unsigned)rm.max_dsp_us, (unsigned)rm.p50_dsp_us, (unsigned)rm.p95_dsp_us,
            (unsigned)rm.p99_dsp_us, (unsigned)runtime_cfg.overload_us,
            (unsigned)runtime_cfg.recover_frames);
    if (close_file(&report_file) != 0) failed = 1;
    if (failed) fprintf(stderr, "intercom bridge failed: %s at frame %" PRIu64 "\n", error, frames);
    return failed ? 1 : 0;
}
