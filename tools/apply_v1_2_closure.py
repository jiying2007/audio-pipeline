#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def read(path): return (ROOT / path).read_text(encoding='utf-8')
def write(path, content):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
def replace_once(path, old, new):
    text = read(path)
    if old not in text:
        raise SystemExit(f'missing patch anchor in {path}: {old[:120]!r}')
    write(path, text.replace(old, new, 1))

# Version and build graph.
replace_once('CMakeLists.txt',
             'project(audio_pipeline VERSION 1.1.1 LANGUAGES C)',
             'project(audio_pipeline VERSION 1.2.0 LANGUAGES C)')
replace_once('CMakeLists.txt', '''if(AP_BUILD_FUZZ)\n    if(NOT AP_BUILD_PIPELINE OR NOT CMAKE_C_COMPILER_ID MATCHES "Clang")\n        message(FATAL_ERROR "AP_BUILD_FUZZ requires pipeline + Clang/libFuzzer")\n    endif()\n    add_executable(ap_fuzz fuzz/fuzz_pipeline.c)\n    target_link_libraries(ap_fuzz PRIVATE audio_pipeline)\n    target_compile_options(ap_fuzz PRIVATE\n        -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer)\n    target_link_options(ap_fuzz PRIVATE -fsanitize=fuzzer,address,undefined)\nendif()''', '''if(AP_BUILD_FUZZ)\n    if(NOT AP_BUILD_PIPELINE OR NOT CMAKE_C_COMPILER_ID MATCHES "Clang")\n        message(FATAL_ERROR "AP_BUILD_FUZZ requires pipeline + Clang/libFuzzer")\n    endif()\n    set(_AP_FUZZ_TARGETS ap_fuzz)\n    add_executable(ap_fuzz fuzz/fuzz_pipeline.c)\n    target_link_libraries(ap_fuzz PRIVATE audio_pipeline)\n    if(AP_ENABLE_LINUX_RUNTIME)\n        add_executable(ap_fuzz_runtime_commands fuzz/fuzz_runtime_commands.c)\n        target_link_libraries(ap_fuzz_runtime_commands PRIVATE audio_pipeline_runtime)\n        add_executable(ap_fuzz_flight_recorder fuzz/fuzz_flight_recorder.c)\n        target_link_libraries(ap_fuzz_flight_recorder PRIVATE audio_pipeline_runtime)\n        list(APPEND _AP_FUZZ_TARGETS ap_fuzz_runtime_commands ap_fuzz_flight_recorder)\n    endif()\n    foreach(_f IN LISTS _AP_FUZZ_TARGETS)\n        target_compile_options(${_f} PRIVATE\n            -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer)\n        target_link_options(${_f} PRIVATE -fsanitize=fuzzer,address,undefined)\n    endforeach()\nendif()''')

# Diagnostics events.
replace_once('include/audio_pipeline/audio_diag.h',
             '    AP_EVENT_DIAG_TRIGGERED = 50,\n    AP_EVENT_COMMAND_REJECTED = 51',
             '    AP_EVENT_DIAG_TRIGGERED = 50,\n    AP_EVENT_COMMAND_REJECTED = 51,\n    AP_EVENT_PIPELINE_ERROR = 52,\n    AP_EVENT_CPU_MIGRATION = 53')

# Additive runtime v3 telemetry and critical latch API. Existing v1/v2 layouts stay frozen.
runtime_h = read('include/audio_pipeline/audio_runtime.h')
anchor = '''typedef struct ap_runtime_metrics_v2 {\n    uint32_t struct_size;\n    uint32_t api_version;\n    uint64_t submitted_frames;\n    uint64_t processed_frames;\n    uint64_t input_full_events;\n    uint64_t output_drop_events;\n    uint64_t dsp_overruns;\n    uint64_t command_full_events;\n    uint64_t event_drop_events;\n    uint64_t stream_discontinuities;\n    uint64_t capture_gap_frames;\n    uint64_t render_gap_frames;\n    uint64_t timestamp_frames;\n    uint64_t scheduler_bind_failures;\n    uint64_t memory_lock_failures;\n    uint32_t input_queue_high_water;\n    uint32_t output_queue_high_water;\n    uint32_t last_dsp_us;\n    uint32_t max_dsp_us;\n    uint32_t p50_dsp_us;\n    uint32_t p95_dsp_us;\n    uint32_t p99_dsp_us;\n    int32_t actual_cpu;\n    int32_t actual_policy;\n    int32_t actual_priority;\n    ap_quality_t quality;\n    uint32_t reserved[8];\n} ap_runtime_metrics_v2_t;'''
addition = anchor + '''\n\n#define AP_RUNTIME_METRICS_V3_API_VERSION 1u\n#define AP_RUNTIME_CRITICAL_STATE_API_VERSION 1u\n\ntypedef struct ap_runtime_metrics_v3 {\n    uint32_t struct_size;\n    uint32_t api_version;\n    uint64_t submitted_frames;\n    uint64_t processed_frames;\n    uint64_t failed_frames;\n    uint64_t input_full_events;\n    uint64_t output_drop_events;\n    uint64_t dsp_overruns;\n    uint64_t command_full_events;\n    uint64_t event_drop_events;\n    uint64_t stream_discontinuities;\n    uint64_t capture_gap_frames;\n    uint64_t render_gap_frames;\n    uint64_t timestamp_frames;\n    uint64_t scheduler_bind_failures;\n    uint64_t memory_lock_failures;\n    uint64_t render_push_failures;\n    uint64_t capture_process_failures;\n    uint64_t observed_cpu_changes;\n    uint64_t critical_events;\n    uint32_t input_queue_high_water;\n    uint32_t output_queue_high_water;\n    uint32_t last_dsp_us;\n    uint32_t max_dsp_us;\n    uint32_t p50_dsp_us;\n    uint32_t p95_dsp_us;\n    uint32_t p99_dsp_us;\n    int32_t actual_cpu;\n    int32_t actual_policy;\n    int32_t actual_priority;\n    int32_t last_pipeline_error;\n    ap_quality_t quality;\n    uint32_t reserved[8];\n} ap_runtime_metrics_v3_t;\n\ntypedef struct ap_runtime_critical_state {\n    uint32_t struct_size;\n    uint32_t api_version;\n    uint64_t frame_sequence;\n    uint64_t total_events;\n    uint32_t kind;\n    uint8_t severity;\n    uint8_t reserved8[3];\n    int32_t arg0;\n    int32_t arg1;\n    uint32_t reserved[6];\n} ap_runtime_critical_state_t;'''
if anchor not in runtime_h: raise SystemExit('runtime header metrics anchor missing')
runtime_h = runtime_h.replace(anchor, addition, 1)
runtime_h = runtime_h.replace('''ap_status_t ap_runtime_get_metrics_v2(const ap_runtime_t *runtime,\n                                      ap_runtime_metrics_v2_t *metrics);''', '''ap_status_t ap_runtime_get_metrics_v2(const ap_runtime_t *runtime,\n                                      ap_runtime_metrics_v2_t *metrics);\nap_status_t ap_runtime_get_metrics_v3(const ap_runtime_t *runtime,\n                                      ap_runtime_metrics_v3_t *metrics);\n/* ERROR/FATAL events are latched independently from the bounded event queue. */\nap_status_t ap_runtime_get_critical_state(const ap_runtime_t *runtime,\n                                          ap_runtime_critical_state_t *state);''', 1)
write('include/audio_pipeline/audio_runtime.h', runtime_h)

# Runtime internals: completion status, failure counters, critical latch, sampled CPU migration telemetry.
replace_once('src/platform/linux/ap_runtime.c', '''typedef struct ap_rt_output {\n    int16_t audio[AP_BUILD_IO_FRAME_MAX];\n    ap_metrics_t metrics;\n} ap_rt_output_t;''', '''typedef struct ap_rt_output {\n    int16_t audio[AP_BUILD_IO_FRAME_MAX];\n    ap_metrics_t metrics;\n    ap_status_t status;\n} ap_rt_output_t;''')
replace_once('src/platform/linux/ap_runtime.c', '''    ap_counter64_t scheduler_bind_failures;\n    ap_counter64_t memory_lock_failures;''', '''    ap_counter64_t scheduler_bind_failures;\n    ap_counter64_t memory_lock_failures;\n    ap_counter64_t failed_frames;\n    ap_counter64_t render_push_failures;\n    ap_counter64_t capture_process_failures;\n    ap_counter64_t observed_cpu_changes;\n    ap_counter64_t critical_events;''')
replace_once('src/platform/linux/ap_runtime.c', '''    atomic_int actual_cpu;\n    atomic_int actual_policy;\n    atomic_int actual_priority;''', '''    atomic_int actual_cpu;\n    atomic_int actual_policy;\n    atomic_int actual_priority;\n    atomic_int last_pipeline_error;\n    atomic_uint critical_seq;\n    atomic_uint critical_frame_lo;\n    atomic_uint critical_frame_hi;\n    atomic_uint critical_kind;\n    atomic_uint critical_severity;\n    atomic_int critical_arg0;\n    atomic_int critical_arg1;''')
replace_once('src/platform/linux/ap_runtime.c', '''    uint64_t worker_sequence;\n    uint64_t last_render_underruns;''', '''    uint64_t worker_sequence;\n    uint32_t cpu_sample_countdown;\n    uint64_t last_render_underruns;''')
replace_once('src/platform/linux/ap_runtime.c', '''    counter64_init(&runtime->scheduler_bind_failures);\n    counter64_init(&runtime->memory_lock_failures);''', '''    counter64_init(&runtime->scheduler_bind_failures);\n    counter64_init(&runtime->memory_lock_failures);\n    counter64_init(&runtime->failed_frames);\n    counter64_init(&runtime->render_push_failures);\n    counter64_init(&runtime->capture_process_failures);\n    counter64_init(&runtime->observed_cpu_changes);\n    counter64_init(&runtime->critical_events);''')
replace_once('src/platform/linux/ap_runtime.c', '''    atomic_init(&runtime->actual_cpu, -1);\n    atomic_init(&runtime->actual_policy, SCHED_OTHER);\n    atomic_init(&runtime->actual_priority, 0);''', '''    atomic_init(&runtime->actual_cpu, -1);\n    atomic_init(&runtime->actual_policy, SCHED_OTHER);\n    atomic_init(&runtime->actual_priority, 0);\n    atomic_init(&runtime->last_pipeline_error, AP_OK);\n    atomic_init(&runtime->critical_seq, 0u);\n    atomic_init(&runtime->critical_frame_lo, 0u);\n    atomic_init(&runtime->critical_frame_hi, 0u);\n    atomic_init(&runtime->critical_kind, 0u);\n    atomic_init(&runtime->critical_severity, 0u);\n    atomic_init(&runtime->critical_arg0, 0);\n    atomic_init(&runtime->critical_arg1, 0);''')

replace_once('src/platform/linux/ap_runtime.c', '''static void runtime_emit_event(ap_runtime_t *runtime,\n                               ap_event_kind_t kind,\n                               ap_event_severity_t severity,\n                               int32_t arg0,\n                               int32_t arg1,\n                               uint32_t count) {''', '''static void runtime_latch_critical(ap_runtime_t *runtime,\n                                   ap_event_kind_t kind,\n                                   ap_event_severity_t severity,\n                                   int32_t arg0,\n                                   int32_t arg1) {\n    uint64_t frame;\n    if (severity < AP_EVENT_ERROR) return;\n    frame = runtime->worker_sequence;\n    counter64_add(&runtime->critical_events, 1u);\n    atomic_fetch_add_explicit(&runtime->critical_seq, 1u, memory_order_acq_rel);\n    atomic_store_explicit(&runtime->critical_frame_lo, (uint32_t)frame, memory_order_relaxed);\n    atomic_store_explicit(&runtime->critical_frame_hi, (uint32_t)(frame >> 32u), memory_order_relaxed);\n    atomic_store_explicit(&runtime->critical_kind, (unsigned)kind, memory_order_relaxed);\n    atomic_store_explicit(&runtime->critical_severity, (unsigned)severity, memory_order_relaxed);\n    atomic_store_explicit(&runtime->critical_arg0, arg0, memory_order_relaxed);\n    atomic_store_explicit(&runtime->critical_arg1, arg1, memory_order_relaxed);\n    atomic_fetch_add_explicit(&runtime->critical_seq, 1u, memory_order_release);\n}\n\nstatic void runtime_emit_event(ap_runtime_t *runtime,\n                               ap_event_kind_t kind,\n                               ap_event_severity_t severity,\n                               int32_t arg0,\n                               int32_t arg1,\n                               uint32_t count) {''')
replace_once('src/platform/linux/ap_runtime.c', '''    if (runtime->recorder)\n        (void)ap_flight_recorder_trigger(runtime->recorder, kind, severity);\n\n    if (head - tail >= AP_RUNTIME_EVENT_QUEUE_DEPTH) {''', '''    runtime_latch_critical(runtime, kind, severity, arg0, arg1);\n    if (runtime->recorder)\n        (void)ap_flight_recorder_trigger(runtime->recorder, kind, severity);\n\n    if (head - tail >= AP_RUNTIME_EVENT_QUEUE_DEPTH) {''')

# Sample CPU changes every 64 frames to avoid adding a syscall/vDSO lookup to every 10 ms frame.
replace_once('src/platform/linux/ap_runtime.c', '''static void *worker(void *arg) {\n    ap_runtime_t *runtime = (ap_runtime_t *)arg;''', '''static void runtime_sample_cpu(ap_runtime_t *runtime) {\n    int cpu;\n    int old;\n    if (runtime->cpu_sample_countdown) {\n        runtime->cpu_sample_countdown--;\n        return;\n    }\n    runtime->cpu_sample_countdown = 63u;\n    cpu = sched_getcpu();\n    if (cpu < 0) return;\n    old = atomic_load_explicit(&runtime->actual_cpu, memory_order_relaxed);\n    if (old >= 0 && old != cpu) {\n        counter64_add(&runtime->observed_cpu_changes, 1u);\n        runtime_emit_event(runtime, AP_EVENT_CPU_MIGRATION, AP_EVENT_INFO, old, cpu, 1u);\n    }\n    atomic_store_explicit(&runtime->actual_cpu, cpu, memory_order_release);\n}\n\nstatic void runtime_publish_failure(ap_runtime_t *runtime,\n                                    ap_rt_input_t *input,\n                                    int publish,\n                                    ap_rt_output_t *slot,\n                                    unsigned out_head,\n                                    unsigned out_tail,\n                                    int16_t *audio,\n                                    ap_status_t status,\n                                    int stage) {\n    ap_metrics_t metrics;\n    memset(audio, 0, (size_t)runtime->io_frames * sizeof(int16_t));\n    counter64_add(&runtime->failed_frames, 1u);\n    if (stage == 1) counter64_add(&runtime->render_push_failures, 1u);\n    if (stage == 2) counter64_add(&runtime->capture_process_failures, 1u);\n    atomic_store_explicit(&runtime->last_pipeline_error, status, memory_order_release);\n    runtime_emit_event(runtime, AP_EVENT_PIPELINE_ERROR, AP_EVENT_ERROR, stage, status, 1u);\n    ap_pipeline_get_metrics(runtime->pipeline, &metrics);\n    runtime_record_frame(runtime, input, audio, &metrics);\n    if (publish) {\n        slot->metrics = metrics;\n        slot->status = status;\n        atomic_store_explicit(&runtime->out_head, out_head + 1u, memory_order_release);\n        update_max(&runtime->output_queue_high_water, out_head + 1u - out_tail);\n    } else {\n        counter64_add(&runtime->output_drop_events, 1u);\n        runtime_emit_event(runtime, AP_EVENT_OUTPUT_DROPPED, AP_EVENT_WARN, 0, 0, 1u);\n    }\n}\n\nstatic void *worker(void *arg) {\n    ap_runtime_t *runtime = (ap_runtime_t *)arg;''')
replace_once('src/platform/linux/ap_runtime.c', '''            runtime_apply_metadata(runtime, input);\n            t0 = now_ns();''', '''            runtime_apply_metadata(runtime, input);\n            runtime_sample_cpu(runtime);\n            t0 = now_ns();''')
replace_once('src/platform/linux/ap_runtime.c', '''                if (ap_pipeline_push_render(runtime->pipeline,\n                                            input->render,\n                                            runtime->io_frames) != AP_OK) {\n                    atomic_store_explicit(&runtime->in_tail,\n                                          tail + 1u,\n                                          memory_order_release);\n                    continue;\n                }''', '''                {\n                    const ap_status_t status = ap_pipeline_push_render(runtime->pipeline,\n                                                                       input->render,\n                                                                       runtime->io_frames);\n                    if (status != AP_OK) {\n                        runtime_publish_failure(runtime, input, publish, slot, out_head,\n                                                out_tail, audio, status, 1);\n                        atomic_store_explicit(&runtime->in_tail, tail + 1u, memory_order_release);\n                        continue;\n                    }\n                }''')
replace_once('src/platform/linux/ap_runtime.c', '''            if (ap_pipeline_process_capture(runtime->pipeline,\n                                            input->mic,\n                                            runtime->io_frames,\n                                            audio) != AP_OK) {\n                atomic_store_explicit(&runtime->in_tail,\n                                      tail + 1u,\n                                      memory_order_release);\n                continue;\n            }''', '''            {\n                const ap_status_t status = ap_pipeline_process_capture(runtime->pipeline,\n                                                                       input->mic,\n                                                                       runtime->io_frames,\n                                                                       audio);\n                if (status != AP_OK) {\n                    runtime_publish_failure(runtime, input, publish, slot, out_head,\n                                            out_tail, audio, status, 2);\n                    atomic_store_explicit(&runtime->in_tail, tail + 1u, memory_order_release);\n                    continue;\n                }\n            }''')
replace_once('src/platform/linux/ap_runtime.c', '''            if (publish) {\n                slot->metrics = metrics;''', '''            if (publish) {\n                slot->metrics = metrics;\n                slot->status = AP_OK;''')
replace_once('src/platform/linux/ap_runtime.c', '''    if (metrics) *metrics = src->metrics;\n    atomic_store_explicit(&runtime->out_tail, tail + 1u, memory_order_release);\n    return AP_OK;''', '''    if (metrics) *metrics = src->metrics;\n    atomic_store_explicit(&runtime->out_tail, tail + 1u, memory_order_release);\n    return src->status;''')

# v3 telemetry and critical state getters.
runtime_c = read('src/platform/linux/ap_runtime.c')
append = '''\n\nap_status_t ap_runtime_get_metrics_v3(const ap_runtime_t *runtime,\n                                      ap_runtime_metrics_v3_t *metrics) {\n    ap_runtime_metrics_v2_t v2;\n    if (!runtime || !metrics || metrics->struct_size < sizeof(*metrics) ||\n        metrics->api_version != AP_RUNTIME_METRICS_V3_API_VERSION)\n        return AP_EINVAL;\n    memset(&v2, 0, sizeof(v2));\n    v2.struct_size = sizeof(v2);\n    v2.api_version = AP_RUNTIME_CONTROL_API_VERSION;\n    if (ap_runtime_get_metrics_v2(runtime, &v2) != AP_OK) return AP_ESTATE;\n    metrics->submitted_frames = v2.submitted_frames;\n    metrics->processed_frames = v2.processed_frames;\n    metrics->failed_frames = counter64_read(&runtime->failed_frames);\n    metrics->input_full_events = v2.input_full_events;\n    metrics->output_drop_events = v2.output_drop_events;\n    metrics->dsp_overruns = v2.dsp_overruns;\n    metrics->command_full_events = v2.command_full_events;\n    metrics->event_drop_events = v2.event_drop_events;\n    metrics->stream_discontinuities = v2.stream_discontinuities;\n    metrics->capture_gap_frames = v2.capture_gap_frames;\n    metrics->render_gap_frames = v2.render_gap_frames;\n    metrics->timestamp_frames = v2.timestamp_frames;\n    metrics->scheduler_bind_failures = v2.scheduler_bind_failures;\n    metrics->memory_lock_failures = v2.memory_lock_failures;\n    metrics->render_push_failures = counter64_read(&runtime->render_push_failures);\n    metrics->capture_process_failures = counter64_read(&runtime->capture_process_failures);\n    metrics->observed_cpu_changes = counter64_read(&runtime->observed_cpu_changes);\n    metrics->critical_events = counter64_read(&runtime->critical_events);\n    metrics->input_queue_high_water = v2.input_queue_high_water;\n    metrics->output_queue_high_water = v2.output_queue_high_water;\n    metrics->last_dsp_us = v2.last_dsp_us;\n    metrics->max_dsp_us = v2.max_dsp_us;\n    metrics->p50_dsp_us = v2.p50_dsp_us;\n    metrics->p95_dsp_us = v2.p95_dsp_us;\n    metrics->p99_dsp_us = v2.p99_dsp_us;\n    metrics->actual_cpu = v2.actual_cpu;\n    metrics->actual_policy = v2.actual_policy;\n    metrics->actual_priority = v2.actual_priority;\n    metrics->last_pipeline_error = atomic_load_explicit(&runtime->last_pipeline_error, memory_order_acquire);\n    metrics->quality = v2.quality;\n    return AP_OK;\n}\n\nap_status_t ap_runtime_get_critical_state(const ap_runtime_t *runtime,\n                                          ap_runtime_critical_state_t *state) {\n    unsigned seq0, seq1;\n    unsigned lo, hi;\n    if (!runtime || !state || state->struct_size < sizeof(*state) ||\n        state->api_version != AP_RUNTIME_CRITICAL_STATE_API_VERSION)\n        return AP_EINVAL;\n    do {\n        seq0 = atomic_load_explicit(&runtime->critical_seq, memory_order_acquire);\n        if (seq0 & 1u) continue;\n        lo = atomic_load_explicit(&runtime->critical_frame_lo, memory_order_relaxed);\n        hi = atomic_load_explicit(&runtime->critical_frame_hi, memory_order_relaxed);\n        state->kind = atomic_load_explicit(&runtime->critical_kind, memory_order_relaxed);\n        state->severity = (uint8_t)atomic_load_explicit(&runtime->critical_severity, memory_order_relaxed);\n        state->arg0 = atomic_load_explicit(&runtime->critical_arg0, memory_order_relaxed);\n        state->arg1 = atomic_load_explicit(&runtime->critical_arg1, memory_order_relaxed);\n        seq1 = atomic_load_explicit(&runtime->critical_seq, memory_order_acquire);\n    } while (seq0 != seq1);\n    state->frame_sequence = ((uint64_t)hi << 32u) | lo;\n    state->total_events = counter64_read(&runtime->critical_events);\n    return AP_OK;\n}\n'''
if not runtime_c.rstrip().endswith('}'):
    raise SystemExit('unexpected runtime.c ending')
write('src/platform/linux/ap_runtime.c', runtime_c.rstrip() + append + '\n')

# Runtime tests for additive telemetry and critical-latch survival beyond event-ring capacity.
test = read('tests/test_runtime.c')
test = test.replace('''static ap_runtime_metrics_v2_t metrics_v2(ap_runtime_t *runtime) {''', '''static ap_runtime_metrics_v3_t metrics_v3(ap_runtime_t *runtime) {\n    ap_runtime_metrics_v3_t m;\n    memset(&m, 0, sizeof(m));\n    m.struct_size = sizeof(m);\n    m.api_version = AP_RUNTIME_METRICS_V3_API_VERSION;\n    assert(ap_runtime_get_metrics_v3(runtime, &m) == AP_OK);\n    return m;\n}\n\nstatic ap_runtime_metrics_v2_t metrics_v2(ap_runtime_t *runtime) {''', 1)
test = test.replace('''    rm2 = metrics_v2(runtime);\n    assert(rm2.event_drop_events >= 1u);\n    assert(ap_flight_recorder_is_frozen(recorder));''', '''    rm2 = metrics_v2(runtime);\n    assert(rm2.event_drop_events >= 1u);\n    assert(ap_flight_recorder_is_frozen(recorder));\n    {\n        ap_runtime_critical_state_t critical;\n        ap_runtime_metrics_v3_t rm3 = metrics_v3(runtime);\n        memset(&critical, 0, sizeof(critical));\n        critical.struct_size = sizeof(critical);\n        critical.api_version = AP_RUNTIME_CRITICAL_STATE_API_VERSION;\n        assert(ap_runtime_get_critical_state(runtime, &critical) == AP_OK);\n        assert(critical.total_events >= 1u);\n        assert(critical.severity >= AP_EVENT_ERROR);\n        assert(rm3.critical_events >= 1u);\n        assert(rm3.failed_frames == 0u);\n    }''', 1)
write('tests/test_runtime.c', test)

# Fuzz targets.
write('fuzz/fuzz_runtime_commands.c', r'''#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#if defined(__GNUC__) || defined(__clang__)
#define AP_ALIGN(N) __attribute__((aligned(N)))
#else
#define AP_ALIGN(N)
#endif
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    static AP_ALIGN(AP_PIPELINE_STATE_ALIGNMENT) unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
    static AP_ALIGN(AP_RUNTIME_STATE_ALIGNMENT) unsigned char runtime_mem[AP_RUNTIME_STATE_MAX_BYTES];
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_runtime_command_t cmd;
    if (size < 4u) return 0;
    if (ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &pcfg, &pipeline) != AP_OK) return 0;
    if (ap_runtime_init(runtime_mem, sizeof(runtime_mem), pipeline, &rcfg, &runtime) != AP_OK) return 0;
    memset(&cmd, 0, sizeof(cmd));
    cmd.struct_size = sizeof(cmd);
    cmd.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    cmd.kind = 1u + (data[0] % 7u);
    if (cmd.kind == AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY) {
        cmd.data.discontinuity.flags = size > 1u ? data[1] : 0u;
        cmd.data.discontinuity.lost_frames = size > 3u ? ((uint32_t)data[2] << 8u) | data[3] : 0u;
    } else if (cmd.kind == AP_RUNTIME_COMMAND_SET_QUALITY) {
        cmd.data.set_quality.quality = (ap_quality_t)(size > 1u ? data[1] : 0u);
    } else if (cmd.kind == AP_RUNTIME_COMMAND_SET_TUNING) {
        cmd.data.tuning.struct_size = sizeof(cmd.data.tuning);
        cmd.data.tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
        cmd.data.tuning.mask = size > 1u ? data[1] : 0u;
        if (size >= 6u) memcpy(&cmd.data.tuning.aec_mu, data + 2u, 4u);
    }
    (void)ap_runtime_command(runtime, &cmd);
    ap_runtime_deinit(runtime);
    return 0;
}
''')
write('fuzz/fuzz_flight_recorder.c', r'''#include "audio_pipeline/audio_diag.h"
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
''')

# ABI probe + comparator against released v1.1.1.
write('tests/abi_probe.c', r'''#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <stddef.h>
#include <stdio.h>
int main(void) {
    printf("ap_config_t=%zu\n", sizeof(ap_config_t));
    printf("ap_config_t.stages=%zu\n", offsetof(ap_config_t, stages));
    printf("ap_metrics_t=%zu\n", sizeof(ap_metrics_t));
    printf("ap_metrics_t.processed_frames=%zu\n", offsetof(ap_metrics_t, processed_frames));
    printf("ap_runtime_config_t=%zu\n", sizeof(ap_runtime_config_t));
    printf("ap_runtime_metrics_t=%zu\n", sizeof(ap_runtime_metrics_t));
    printf("AP_OK=%d\n", (int)AP_OK);
    printf("AP_EINVAL=%d\n", (int)AP_EINVAL);
    printf("AP_EFULL=%d\n", (int)AP_EFULL);
    printf("AP_EEMPTY=%d\n", (int)AP_EEMPTY);
    return 0;
}
''')
write('scripts/check-abi-contract.sh', r'''#!/bin/sh
set -eu
BASE_REF=${1:-v1.1.1}
ROOT=$(pwd)
TMP=$(mktemp -d)
trap 'git worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT INT TERM
git fetch origin "refs/tags/$BASE_REF:refs/tags/$BASE_REF" --force >/dev/null 2>&1 || true
git worktree add --detach "$TMP/base" "$BASE_REF" >/dev/null
for side in base head; do
  src="$ROOT"; [ "$side" = base ] && src="$TMP/base"
  cmake -S "$src" -B "$TMP/$side-build" -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF >/dev/null
  cmake --build "$TMP/$side-build" --parallel >/dev/null
  cc "$ROOT/tests/abi_probe.c" -I"$src/include" -I"$TMP/$side-build/generated" -o "$TMP/$side-probe"
  "$TMP/$side-probe" | sort > "$TMP/$side-abi"
  nm -g --defined-only "$TMP/$side-build/libaudio_pipeline.a" | awk '{print $3}' | grep '^ap_' | sort -u > "$TMP/$side-core-symbols"
  nm -g --defined-only "$TMP/$side-build/libaudio_pipeline_runtime.a" | awk '{print $3}' | grep '^ap_' | sort -u > "$TMP/$side-runtime-symbols"
done
diff -u "$TMP/base-abi" "$TMP/head-abi"
comm -23 "$TMP/base-core-symbols" "$TMP/head-core-symbols" > "$TMP/missing-core"
comm -23 "$TMP/base-runtime-symbols" "$TMP/head-runtime-symbols" > "$TMP/missing-runtime"
if [ -s "$TMP/missing-core" ] || [ -s "$TMP/missing-runtime" ]; then
  echo 'ABI/API regression: released symbols disappeared' >&2
  cat "$TMP/missing-core" "$TMP/missing-runtime" >&2
  exit 3
fi
echo "ABI/API additive contract OK against $BASE_REF"
''')

# Deterministic SPDX 2.3 SBOM generator without third-party runtime dependencies.
write('tools/generate_spdx_sbom.py', r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--name',required=True); p.add_argument('--version',required=True); p.add_argument('--revision',required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--created-epoch',type=int,required=True); a=p.parse_args()
    files=[]
    for path in sorted(x for x in a.root.rglob('*') if x.is_file()):
        rel=path.relative_to(a.root).as_posix(); sid='SPDXRef-File-'+hashlib.sha256(rel.encode()).hexdigest()[:16]
        files.append({'SPDXID':sid,'fileName':'./'+rel,'checksums':[{'algorithm':'SHA256','checksumValue':sha256(path)}]})
    created=datetime.fromtimestamp(a.created_epoch,tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    doc={'spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0','SPDXID':'SPDXRef-DOCUMENT','name':f'{a.name}-{a.version}','documentNamespace':f'https://github.com/jiying2007/audio-pipeline/releases/tag/v{a.version}#{a.revision}','creationInfo':{'created':created,'creators':['Tool: audio-pipeline/generate_spdx_sbom.py']},'packages':[{'name':a.name,'SPDXID':'SPDXRef-Package','versionInfo':a.version,'downloadLocation':'NOASSERTION','filesAnalyzed':True,'packageVerificationCode':{'packageVerificationCodeValue':hashlib.sha1("".join(x['checksums'][0]['checksumValue'] for x in files).encode()).hexdigest()}}],'files':files,'relationships':[{'spdxElementId':'SPDXRef-DOCUMENT','relationshipType':'DESCRIBES','relatedSpdxElement':'SPDXRef-Package'}]+[{'spdxElementId':'SPDXRef-Package','relationshipType':'CONTAINS','relatedSpdxElement':f['SPDXID']} for f in files]}
    a.output.write_text(json.dumps(doc,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
if __name__=='__main__': main()
''')

# Certification evidence schemas and collector.
write('certification/evidence-manifest.schema.json', json.dumps({
  '$schema':'https://json-schema.org/draft/2020-12/schema','title':'audio-pipeline certification evidence manifest','type':'object','required':['schema_version','collector_version','generated_at','artifacts'],'properties':{
    'schema_version':{'const':1},'collector_version':{'type':'string','minLength':1},'generated_at':{'type':'string','minLength':1},
    'artifacts':{'type':'array','minItems':1,'items':{'type':'object','required':['path','type','size','sha256'],'properties':{'path':{'type':'string','minLength':1},'type':{'type':'string','minLength':1},'size':{'type':'integer','minimum':0},'sha256':{'type':'string','pattern':'^[0-9a-fA-F]{64}$'}},'additionalProperties':False}}
  },'additionalProperties':False}, indent=2)+'\n')
write('certification/corpus-manifest.schema.json', json.dumps({
  '$schema':'https://json-schema.org/draft/2020-12/schema','title':'audio-pipeline acoustic corpus manifest','type':'object','required':['schema_version','corpus_id','revision','cases'],'properties':{'schema_version':{'const':1},'corpus_id':{'type':'string','minLength':1},'revision':{'type':'string','minLength':1},'cases':{'type':'array','minItems':1,'items':{'type':'object','required':['case_id','scenario'],'properties':{'case_id':{'type':'string','minLength':1},'scenario':{'type':'string','minLength':1},'mic_angle_deg':{'type':'number'},'distance_m':{'type':'number','minimum':0},'snr_db':{'type':'number'},'ser_db':{'type':'number'},'motion':{'type':'string'},'noise':{'type':'string'},'echo_path_change':{'type':'boolean'}},'additionalProperties':True}}},'additionalProperties':False}, indent=2)+'\n')
write('tools/ap_certify.py', r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, time
from pathlib import Path
VERSION='1.0'
def digest(path: Path) -> str:
    h=hashlib.sha256();
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()
def text(path, default='unknown'):
    try:return Path(path).read_text().strip()
    except OSError:return default
def cmd(args, default='unknown'):
    try:return subprocess.check_output(args,text=True,stderr=subprocess.DEVNULL).strip()
    except Exception:return default
def thermal_max():
    vals=[]
    for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        try:
            v=float(p.read_text().strip()); vals.append(v/1000.0 if v>1000 else v)
        except Exception:pass
    return max(vals) if vals else None
def manifest(paths, output: Path):
    items=[]
    for typ,p in paths:
        p=Path(p); items.append({'path':str(p),'type':typ,'size':p.stat().st_size,'sha256':digest(p)})
    obj={'schema_version':1,'collector_version':VERSION,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'artifacts':items}
    output.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); return obj
def main():
    p=argparse.ArgumentParser(); p.add_argument('--sku',required=True); p.add_argument('--policy',type=Path,required=True); p.add_argument('--corpus-manifest',type=Path,required=True); p.add_argument('--benchmark-json',type=Path,required=True); p.add_argument('--acoustic-json',type=Path,required=True); p.add_argument('--soak-json',type=Path,required=True); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--capture-device',required=True); p.add_argument('--playback-device'); p.add_argument('--sample-rate',type=int,default=16000); p.add_argument('--mic-channels',type=int,default=2); a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    bench=json.loads(a.benchmark_json.read_text()); acoustic=json.loads(a.acoustic_json.read_text()); soak=json.loads(a.soak_json.read_text())
    commit=cmd(['git','rev-parse','HEAD']); version='unknown'
    for line in Path('CMakeLists.txt').read_text().splitlines():
        if line.startswith('project(audio_pipeline VERSION '): version=line.split()[2]
    governor=text('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')
    cpuset=text('/proc/self/status'); cpuset=next((x.split(':',1)[1].strip() for x in cpuset.splitlines() if x.startswith('Cpus_allowed_list:')),'unknown')
    compiler=cmd(['cc','--version']).splitlines()[0]
    toolchain_digest=hashlib.sha256((compiler+'\n'+platform.machine()+'\n'+platform.libc_ver()[0]+' '+platform.libc_ver()[1]).encode()).hexdigest()
    evidence_path=a.output_dir/'evidence-manifest.json'
    manifest([('benchmark',a.benchmark_json),('acoustic',a.acoustic_json),('soak',a.soak_json),('corpus-manifest',a.corpus_manifest),('policy',a.policy)], evidence_path)
    record={'schema_version':2,'sku':a.sku,'status':'product-certified','policy':json.loads(a.policy.read_text())['policy_id'],'policy_sha256':digest(a.policy),'corpus_manifest_sha256':digest(a.corpus_manifest),'evidence_manifest_sha256':digest(evidence_path),'collector_version':VERSION,'toolchain_digest':toolchain_digest,'build':{'commit':commit,'version':version,'fingerprint':commit,'compiler':compiler,'abi':platform.machine()},'platform':{'soc':platform.machine(),'kernel':platform.release(),'governor':governor,'cpuset':cpuset},'audio_route':{'capture_device':a.capture_device,'playback_device':a.playback_device,'sample_rate_hz':a.sample_rate,'mic_channels':a.mic_channels},'performance':bench['performance'],'acoustic':acoustic['acoustic'],'thermal_power':bench.get('thermal_power',{'ambient_c':bench.get('ambient_c',25.0),'max_soc_c':thermal_max() or 0.0,'average_power_w':bench.get('average_power_w',0.0)}),'soak':soak['soak'],'artifacts':{'result_json':str(a.output_dir/'record.json'),'benchmark_json':str(a.benchmark_json),'evidence_manifest':str(evidence_path),'sha256':digest(evidence_path)}}
    out=a.output_dir/'record.json'; out.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n'); print(out)
if __name__=='__main__': main()
''')

# Replace certification validator with v2 evidence binding while retaining self-test.
write('certification/validate_record.py', r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
PRODUCT_PERF_REQUIRED={"active_cpu_percent","p95_us","p99_us","deadline_misses","rss_kib","xruns","overruns","input_full_events","output_drop_events"}
PRODUCT_ACOUSTIC_REQUIRED={"corpus_revision","cases_total","cases_passed","far_end_erle_db","aec_convergence_ms","double_talk_near_si_sdr_db","noise_si_sdr_improvement_db","vad_f1","threshold_report"}
POLICY_REQUIRED={"policy_id","max_active_cpu_percent","max_rss_kib","max_p95_us","max_p99_us","max_soc_c","max_average_power_w","min_far_end_erle_db","max_aec_convergence_ms","min_double_talk_near_si_sdr_db","min_noise_si_sdr_improvement_db","min_vad_f1","min_soak_hours"}
def sha256(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()
def require_keys(obj,keys,where,errors):
    missing=sorted(k for k in keys if k not in obj)
    if missing:errors.append(f"{where}: missing {', '.join(missing)}")
def validate_manifest(manifest,errors):
    require_keys(manifest,{"schema_version","collector_version","generated_at","artifacts"},"evidence_manifest",errors)
    if errors:return
    if manifest["schema_version"]!=1:errors.append("evidence_manifest.schema_version: expected 1")
    for i,item in enumerate(manifest["artifacts"]):
        require_keys(item,{"path","type","size","sha256"},f"evidence_manifest.artifacts[{i}]",errors)
        if not re.fullmatch(r"[0-9a-fA-F]{64}",str(item.get("sha256",""))):errors.append(f"evidence_manifest.artifacts[{i}].sha256: invalid")
def validate(record,policy=None,policy_hash=None,evidence=None,evidence_hash=None,corpus_hash=None):
    errors=[]; require_keys(record,{"sku","status","build","platform","audio_route","performance","acoustic","soak","artifacts"},"record",errors)
    if errors:return errors
    status=record["status"]
    if status not in {"pending","board-validated","product-certified","failed"}:errors.append(f"status: unsupported value {status!r}")
    require_keys(record["build"],{"commit","version","fingerprint","compiler","abi"},"build",errors); require_keys(record["platform"],{"soc","kernel","governor","cpuset"},"platform",errors); require_keys(record["audio_route"],{"capture_device","playback_device","sample_rate_hz","mic_channels"},"audio_route",errors); require_keys(record["soak"],{"hours","passed"},"soak",errors)
    if record["audio_route"].get("sample_rate_hz") not in {8000,16000,24000,32000,48000}:errors.append("audio_route.sample_rate_hz: unsupported rate")
    if record["audio_route"].get("mic_channels") not in {1,2}:errors.append("audio_route.mic_channels: must be 1 or 2")
    if status!="product-certified":return errors
    require_keys(record,{"schema_version","policy","policy_sha256","corpus_manifest_sha256","evidence_manifest_sha256","collector_version","toolchain_digest","thermal_power"},"record",errors)
    if record.get("schema_version")!=2:errors.append("schema_version: product-certified records require v2")
    for key in ("policy_sha256","corpus_manifest_sha256","evidence_manifest_sha256","toolchain_digest"):
        if not re.fullmatch(r"[0-9a-fA-F]{64}",str(record.get(key,""))):errors.append(f"{key}: must be 64 hexadecimal characters")
    if policy is None:errors.append("policy: product-certified requires --policy"); return errors
    require_keys(policy,POLICY_REQUIRED,"policy",errors)
    if policy_hash and record.get("policy_sha256")!=policy_hash:errors.append("policy_sha256: does not match supplied policy bytes")
    if corpus_hash and record.get("corpus_manifest_sha256")!=corpus_hash:errors.append("corpus_manifest_sha256: does not match supplied corpus manifest")
    if evidence is None:errors.append("evidence_manifest: product-certified requires --evidence-manifest")
    else:
        validate_manifest(evidence,errors)
        if evidence_hash and record.get("evidence_manifest_sha256")!=evidence_hash:errors.append("evidence_manifest_sha256: does not match supplied manifest")
    if errors:return errors
    if record.get("policy")!=policy.get("policy_id"):errors.append("policy: record policy id must match supplied policy")
    perf,acoustic,soak,artifacts=record["performance"],record["acoustic"],record["soak"],record["artifacts"]; thermal=record["thermal_power"]
    require_keys(perf,PRODUCT_PERF_REQUIRED,"performance",errors); require_keys(acoustic,PRODUCT_ACOUSTIC_REQUIRED,"acoustic",errors); require_keys(thermal,{"ambient_c","max_soc_c","average_power_w"},"thermal_power",errors); require_keys(soak,{"hours","passed","xruns","deadline_misses","output_drop_events"},"soak",errors); require_keys(artifacts,{"result_json","benchmark_json","evidence_manifest","sha256"},"artifacts",errors)
    if errors:return errors
    for key in {"deadline_misses","xruns","overruns","input_full_events","output_drop_events"}:
        if int(perf[key])!=0:errors.append(f"performance.{key}: nominal gate requires 0")
    for key in {"xruns","deadline_misses","output_drop_events"}:
        if int(soak[key])!=0:errors.append(f"soak.{key}: nominal gate requires 0")
    checks=[(float(perf["active_cpu_percent"])<=float(policy["max_active_cpu_percent"]),"performance.active_cpu_percent"),(int(perf["rss_kib"])<=int(policy["max_rss_kib"]),"performance.rss_kib"),(float(perf["p95_us"])<=float(policy["max_p95_us"]),"performance.p95_us"),(float(perf["p99_us"])<=float(policy["max_p99_us"]),"performance.p99_us"),(float(thermal["max_soc_c"])<=float(policy["max_soc_c"]),"thermal_power.max_soc_c"),(float(thermal["average_power_w"])<=float(policy["max_average_power_w"]),"thermal_power.average_power_w"),(float(acoustic["far_end_erle_db"])>=float(policy["min_far_end_erle_db"]),"acoustic.far_end_erle_db"),(float(acoustic["aec_convergence_ms"])<=float(policy["max_aec_convergence_ms"]),"acoustic.aec_convergence_ms"),(float(acoustic["double_talk_near_si_sdr_db"])>=float(policy["min_double_talk_near_si_sdr_db"]),"acoustic.double_talk_near_si_sdr_db"),(float(acoustic["noise_si_sdr_improvement_db"])>=float(policy["min_noise_si_sdr_improvement_db"]),"acoustic.noise_si_sdr_improvement_db"),(float(acoustic["vad_f1"])>=float(policy["min_vad_f1"]),"acoustic.vad_f1"),(float(soak["hours"])>=float(policy["min_soak_hours"]),"soak.hours")]
    for passed,name in checks:
        if not passed:errors.append(f"{name}: violates certification policy")
    if soak.get("passed") is not True:errors.append("soak.passed: product-certified requires true")
    if int(acoustic["cases_passed"])!=int(acoustic["cases_total"]):errors.append("acoustic: every certification corpus case must pass")
    return errors
def self_test():
    policy={"policy_id":"test-policy","max_active_cpu_percent":40,"max_rss_kib":4096,"max_p95_us":7000,"max_p99_us":9000,"max_soc_c":85,"max_average_power_w":2,"min_far_end_erle_db":15,"max_aec_convergence_ms":1000,"min_double_talk_near_si_sdr_db":5,"min_noise_si_sdr_improvement_db":3,"min_vad_f1":0.85,"min_soak_hours":8}; ph="1"*64; ch="2"*64; eh="3"*64
    evidence={"schema_version":1,"collector_version":"1","generated_at":"now","artifacts":[{"path":"x","type":"benchmark","size":1,"sha256":"4"*64}]}
    record={"schema_version":2,"sku":"test","status":"product-certified","policy":"test-policy","policy_sha256":ph,"corpus_manifest_sha256":ch,"evidence_manifest_sha256":eh,"collector_version":"1","toolchain_digest":"5"*64,"build":{"commit":"abcdef0","version":"1.2.0","fingerprint":"x","compiler":"gcc","abi":"armv7"},"platform":{"soc":"test","kernel":"6.6","governor":"performance","cpuset":"1"},"audio_route":{"capture_device":"hw:0,0","playback_device":"hw:0,0","sample_rate_hz":16000,"mic_channels":2},"performance":{"active_cpu_percent":20,"p95_us":3000,"p99_us":5000,"deadline_misses":0,"rss_kib":512,"xruns":0,"overruns":0,"input_full_events":0,"output_drop_events":0},"acoustic":{"corpus_revision":"r1","cases_total":10,"cases_passed":10,"far_end_erle_db":20,"aec_convergence_ms":500,"double_talk_near_si_sdr_db":8,"noise_si_sdr_improvement_db":4,"vad_f1":0.9,"threshold_report":"result.json"},"thermal_power":{"ambient_c":25,"max_soc_c":60,"average_power_w":1},"soak":{"hours":8,"passed":True,"xruns":0,"deadline_misses":0,"output_drop_events":0},"artifacts":{"result_json":"result.json","benchmark_json":"bench.json","evidence_manifest":"evidence.json","sha256":"0"*64}}
    assert validate(record,policy,ph,evidence,eh,ch)==[]; bad=json.loads(json.dumps(record));bad["policy_sha256"]="0"*64;assert validate(bad,policy,ph,evidence,eh,ch);print("audio-pipeline certification validator self-test: OK")
def main():
    p=argparse.ArgumentParser();p.add_argument("record",type=Path,nargs="?");p.add_argument("--policy",type=Path);p.add_argument("--evidence-manifest",type=Path);p.add_argument("--corpus-manifest",type=Path);p.add_argument("--self-test",action="store_true");a=p.parse_args()
    if a.self_test:self_test();return 0
    if a.record is None:p.error("record is required unless --self-test is used")
    rec=json.loads(a.record.read_text());pol=json.loads(a.policy.read_text()) if a.policy else None;ev=json.loads(a.evidence_manifest.read_text()) if a.evidence_manifest else None
    errors=validate(rec,pol,sha256(a.policy) if a.policy else None,ev,sha256(a.evidence_manifest) if a.evidence_manifest else None,sha256(a.corpus_manifest) if a.corpus_manifest else None)
    if errors:
        [print(f"ERROR: {e}") for e in errors];return 1
    print(f"certification record OK: {a.record}");return 0
if __name__=="__main__":raise SystemExit(main())
''')

# Record schema v2 binding fields (product-certified only).
schema=json.loads(read('certification/record.schema.json'))
props=schema['properties']
props.update({
 'schema_version':{'type':'integer','minimum':1},
 'policy_sha256':{'type':'string','pattern':'^[A-Fa-f0-9]{64}$'},
 'corpus_manifest_sha256':{'type':'string','pattern':'^[A-Fa-f0-9]{64}$'},
 'evidence_manifest_sha256':{'type':'string','pattern':'^[A-Fa-f0-9]{64}$'},
 'collector_version':{'type':'string','minLength':1},
 'toolchain_digest':{'type':'string','pattern':'^[A-Fa-f0-9]{64}$'}
})
then=schema['allOf'][0]['then']
req=then.setdefault('required',[])
for key in ['schema_version','policy','policy_sha256','corpus_manifest_sha256','evidence_manifest_sha256','collector_version','toolchain_digest','thermal_power']:
    if key not in req:req.append(key)
then.setdefault('properties',{})['schema_version']={'const':2}
write('certification/record.schema.json',json.dumps(schema,indent=2)+'\n')

# Documentation/changelog.
changelog=read('CHANGELOG.md')
entry='''# 1.2.0\n\n- Close runtime async failure semantics: failed DSP submissions publish a bounded completion status when output capacity exists, increment failure counters, emit `AP_EVENT_PIPELINE_ERROR`, and latch ERROR/FATAL state independently from the event queue.\n- Add additive runtime metrics v3 with pipeline-failure, critical-event, and sampled CPU-migration telemetry.\n- Bind product certification records to exact policy/corpus/evidence bytes and add `ap_certify.py` plus machine-readable evidence/corpus manifests.\n- Add ABI/API compatibility comparison against released v1.1.1, expanded runtime/recorder fuzzing, deterministic SPDX SBOM generation, reproducible release packaging, and supply-chain attestation hooks.\n\n'''
if not changelog.startswith('# 1.2.0'):
    write('CHANGELOG.md',entry+changelog)
readme=read('certification/README.md')
if 'ap_certify.py' not in readme:
    readme += '''\n## v1.2 evidence binding\n\n`product-certified` records use schema version 2 and bind the exact certification policy, acoustic corpus manifest and evidence manifest by SHA-256. Use `tools/ap_certify.py` on the shipping board to assemble a record from benchmark, acoustic and soak JSON, then validate with `certification/validate_record.py --policy ... --corpus-manifest ... --evidence-manifest ...`.\n'''
    write('certification/README.md',readme)
perf=read('docs/PERFORMANCE.md')
if 'sampled CPU migration' not in perf:
    perf += '''\n## v1.2 runtime health telemetry\n\nRuntime metrics v3 distinguishes successful and failed DSP frames, render-push/capture-process failures, the last pipeline error, critical ERROR/FATAL events, and sampled CPU migration. CPU identity is sampled every 64 frames when the worker runs, keeping scheduler diagnostics low-overhead; the counter therefore represents observed CPU changes rather than an exact scheduler migration trace.\n'''
    write('docs/PERFORMANCE.md',perf)

print('v1.2 non-workflow closure patch applied')
