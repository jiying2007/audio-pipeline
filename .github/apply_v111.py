#!/usr/bin/env python3
from pathlib import Path
import json


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1))


# Version and SDK legal/docs payload.
replace_once('CMakeLists.txt',
             'project(audio_pipeline VERSION 1.1.0 LANGUAGES C)',
             'project(audio_pipeline VERSION 1.1.1 LANGUAGES C)')
cmake = Path('CMakeLists.txt').read_text()
marker = 'install(EXPORT AudioPipelineTargets\n'
if 'LICENSE THIRD_PARTY.md README.md CHANGELOG.md' not in cmake:
    block = ('install(FILES LICENSE THIRD_PARTY.md README.md CHANGELOG.md\n'
             '        DESTINATION ${CMAKE_INSTALL_DOCDIR})\n')
    if marker not in cmake:
        raise SystemExit('CMake install export marker missing')
    Path('CMakeLists.txt').write_text(cmake.replace(marker, block + marker, 1))

# Diagnostics event and privacy-safe default.
replace_once('include/audio_pipeline/audio_diag.h',
             '    AP_EVENT_DIAG_TRIGGERED = 50\n',
             '    AP_EVENT_DIAG_TRIGGERED = 50,\n    AP_EVENT_COMMAND_REJECTED = 51\n')

runtime_path = Path('src/platform/linux/ap_runtime.c')
runtime = runtime_path.read_text()
runtime = runtime.replace('#include <limits.h>\n', '#include <limits.h>\n#include <math.h>\n', 1)
runtime = runtime.replace('    config.record_mask = AP_DIAG_RECORD_ALL;\n',
                          '    config.record_mask = AP_DIAG_RECORD_METRICS;\n', 1)
old = """size_t ap_flight_recorder_state_size(const ap_flight_recorder_config_t *config) {
    size_t capacity;
    size_t stride;
    if (!config || config->struct_size < sizeof(*config) ||
        config->api_version != AP_DIAG_API_VERSION || !config->frame_samples ||
        !config->mic_channels || config->mic_channels > 2u ||
        (config->record_mask & ~AP_DIAG_RECORD_ALL) != 0u)
        return 0u;
    capacity = (size_t)config->pre_roll_frames +
               (size_t)config->post_roll_frames + 1u;
    stride = recorder_slot_stride(config);
    if (!capacity || stride > SIZE_MAX / capacity) return 0u;
    if (sizeof(ap_flight_recorder_t) > SIZE_MAX - capacity * stride) return 0u;
    return sizeof(ap_flight_recorder_t) + capacity * stride;
}
"""
new = """static int recorder_rate_supported(uint32_t rate) {
    return rate == 8000u || rate == 16000u || rate == 24000u ||
           rate == 32000u || rate == 48000u;
}

static int recorder_config_valid(const ap_flight_recorder_config_t *config) {
    size_t capacity;
    size_t stride;
    if (!config || config->struct_size < sizeof(*config) ||
        config->api_version != AP_DIAG_API_VERSION ||
        !recorder_rate_supported(config->io_sample_rate_hz) ||
        config->frame_samples != config->io_sample_rate_hz / 100u ||
        !config->mic_channels || config->mic_channels > 2u ||
        (config->record_mask & ~AP_DIAG_RECORD_ALL) != 0u)
        return 0;
    capacity = (size_t)config->pre_roll_frames +
               (size_t)config->post_roll_frames + 1u;
    if (!capacity || capacity > UINT32_MAX) return 0;
    stride = recorder_slot_stride(config);
    if (!stride || stride > UINT32_MAX || stride > SIZE_MAX / capacity) return 0;
    if (sizeof(ap_flight_recorder_t) > SIZE_MAX - capacity * stride) return 0;
    return 1;
}

size_t ap_flight_recorder_state_size(const ap_flight_recorder_config_t *config) {
    size_t capacity;
    size_t stride;
    if (!recorder_config_valid(config)) return 0u;
    capacity = (size_t)config->pre_roll_frames +
               (size_t)config->post_roll_frames + 1u;
    stride = recorder_slot_stride(config);
    return sizeof(ap_flight_recorder_t) + capacity * stride;
}
"""
if old not in runtime:
    raise SystemExit('flight-recorder validation block missing')
runtime = runtime.replace(old, new, 1)

command_marker = 'ap_status_t ap_runtime_command(ap_runtime_t *runtime,\n'
helper = """static ap_status_t runtime_validate_command(const ap_runtime_command_t *command) {
    const ap_discontinuity_flags_t discontinuity_all =
        AP_DISCONTINUITY_CAPTURE_GAP | AP_DISCONTINUITY_RENDER_GAP |
        AP_DISCONTINUITY_CLOCK_RESET | AP_DISCONTINUITY_XRUN |
        AP_DISCONTINUITY_CODEC_REOPEN | AP_DISCONTINUITY_ROUTE_CHANGE;
    const ap_tuning_mask_t tuning_all =
        AP_TUNING_AEC_MU | AP_TUNING_NS_FLOOR |
        AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER;
    if (!command || command->struct_size < sizeof(*command) ||
        command->api_version != AP_RUNTIME_CONTROL_API_VERSION)
        return AP_EINVAL;
    switch ((ap_runtime_command_kind_t)command->kind) {
    case AP_RUNTIME_COMMAND_ECHO_PATH_CHANGE:
    case AP_RUNTIME_COMMAND_RESET:
        return AP_OK;
    case AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY:
        if (command->data.discontinuity.flags == 0u ||
            (command->data.discontinuity.flags & ~discontinuity_all) != 0u)
            return AP_EINVAL;
        return AP_OK;
    case AP_RUNTIME_COMMAND_SET_QUALITY:
        if (command->data.set_quality.quality < AP_QUALITY_SAFE ||
            command->data.set_quality.quality > AP_QUALITY_FULL)
            return AP_EINVAL;
        return AP_OK;
    case AP_RUNTIME_COMMAND_SET_TUNING: {
        const ap_tuning_t *t = &command->data.tuning;
        if (t->struct_size < sizeof(*t) ||
            t->api_version != AP_PIPELINE_CONTROL_API_VERSION ||
            t->mask == 0u || (t->mask & ~tuning_all) != 0u)
            return AP_EINVAL;
        if ((t->mask & AP_TUNING_AEC_MU) &&
            (!isfinite(t->aec_mu) || t->aec_mu <= 0.0f || t->aec_mu > 1.0f))
            return AP_EINVAL;
        if ((t->mask & AP_TUNING_NS_FLOOR) &&
            (!isfinite(t->ns_floor) || t->ns_floor < 0.02f || t->ns_floor > 1.0f))
            return AP_EINVAL;
        if ((t->mask & AP_TUNING_AGC_TARGET) &&
            (!isfinite(t->agc_target_dbfs) || t->agc_target_dbfs < -60.0f ||
             t->agc_target_dbfs > -1.0f))
            return AP_EINVAL;
        if ((t->mask & AP_TUNING_LIMITER) &&
            (!isfinite(t->limiter_dbfs) || t->limiter_dbfs < -20.0f ||
             t->limiter_dbfs > -0.1f))
            return AP_EINVAL;
        if ((t->mask & (AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER)) ==
            (AP_TUNING_AGC_TARGET | AP_TUNING_LIMITER) &&
            t->agc_target_dbfs >= t->limiter_dbfs)
            return AP_EINVAL;
        return AP_OK;
    }
    default:
        return AP_EINVAL;
    }
}

"""
if helper not in runtime:
    if command_marker not in runtime:
        raise SystemExit('runtime command marker missing')
    runtime = runtime.replace(command_marker, helper + command_marker, 1)
runtime = runtime.replace("""    if (!runtime || !command || command->struct_size < sizeof(*command) ||
        command->api_version != AP_RUNTIME_CONTROL_API_VERSION)
        return AP_EINVAL;
    head = atomic_load_explicit(&runtime->command_head, memory_order_relaxed);
""", """    if (!runtime || runtime_validate_command(command) != AP_OK)
        return AP_EINVAL;
    head = atomic_load_explicit(&runtime->command_head, memory_order_relaxed);
""", 1)
runtime = runtime.replace("""    case AP_RUNTIME_COMMAND_SET_TUNING:
        if (command->data.tuning.struct_size < sizeof(command->data.tuning) ||
            command->data.tuning.api_version != AP_PIPELINE_CONTROL_API_VERSION)
            return AP_EINVAL;
        dst->data.tuning.mask = command->data.tuning.mask;
""", """    case AP_RUNTIME_COMMAND_SET_TUNING:
        dst->data.tuning.mask = command->data.tuning.mask;
""", 1)
runtime = runtime.replace("""        tuning.limiter_dbfs = command->data.tuning.limiter_dbfs;
        (void)ap_pipeline_apply_tuning(runtime->pipeline, &tuning);
        break;
""", """        tuning.limiter_dbfs = command->data.tuning.limiter_dbfs;
        if (ap_pipeline_apply_tuning(runtime->pipeline, &tuning) != AP_OK)
            runtime_emit_event(runtime,
                               AP_EVENT_COMMAND_REJECTED,
                               AP_EVENT_WARN,
                               (int32_t)command->kind,
                               AP_EINVAL,
                               1u);
        break;
""", 1)
runtime = runtime.replace("""    if (atomic_load_explicit(&runtime->running, memory_order_acquire))
        return AP_ESTATE;
    runtime->recorder = recorder;
""", """    if (atomic_load_explicit(&runtime->running, memory_order_acquire))
        return AP_ESTATE;
    if (recorder &&
        (recorder->cfg.frame_samples != runtime->io_frames ||
         recorder->cfg.mic_channels != runtime->mic_channels ||
         recorder->cfg.io_sample_rate_hz != runtime->io_frames * 100u))
        return AP_EINVAL;
    runtime->recorder = recorder;
""", 1)
runtime_path.write_text(runtime)

replace_once('src/core/ap_pipeline_query.c',
             '    if (!pipeline || flags == 0u) return AP_EINVAL;\n',
             """    if (!pipeline || flags == 0u ||
        (flags & ~(AP_DISCONTINUITY_CAPTURE_GAP | AP_DISCONTINUITY_RENDER_GAP |
                   AP_DISCONTINUITY_CLOCK_RESET | AP_DISCONTINUITY_XRUN |
                   AP_DISCONTINUITY_CODEC_REOPEN | AP_DISCONTINUITY_ROUTE_CHANGE)) != 0u)
        return AP_EINVAL;
""")

# Replay fixture explicitly opts into PCM.
gen_path = Path('tests/generate_diag_dump.c')
gen = gen_path.read_text()
needle = 'ap_flight_recorder_config_t dcfg = ap_flight_recorder_config_default(16000u, 2u);\n'
if needle in gen and 'dcfg.record_mask = AP_DIAG_RECORD_ALL;' not in gen:
    gen_path.write_text(gen.replace(needle, needle + '    dcfg.record_mask = AP_DIAG_RECORD_ALL;\n', 1))

# Runtime negative contracts.
tests_path = Path('tests/test_runtime.c')
tests = tests_path.read_text()
if 'static void test_recorder_configuration_contract(void)' not in tests:
    insert = """
static void test_recorder_configuration_contract(void) {
    ap_config_t pcfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rcfg = ap_runtime_config_default();
    ap_flight_recorder_config_t dcfg = ap_flight_recorder_config_default(16000u, 2u);
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    ap_flight_recorder_t *recorder = NULL;

    assert(dcfg.record_mask == AP_DIAG_RECORD_METRICS);
    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    assert(ap_flight_recorder_state_size(&dcfg) > 0u);
    dcfg.frame_samples++;
    assert(ap_flight_recorder_state_size(&dcfg) == 0u);
    dcfg = ap_flight_recorder_config_default(11025u, 2u);
    assert(ap_flight_recorder_state_size(&dcfg) == 0u);
    dcfg = ap_flight_recorder_config_default(16000u, 2u);
    dcfg.pre_roll_frames = UINT32_MAX;
    dcfg.post_roll_frames = UINT32_MAX;
    assert(ap_flight_recorder_state_size(&dcfg) == 0u);

    assert(ap_pipeline_init(pipeline_state, sizeof(pipeline_state), &pcfg, &pipeline) == AP_OK);
    assert(ap_runtime_init(runtime_state, sizeof(runtime_state), pipeline, &rcfg, &runtime) == AP_OK);
    dcfg = ap_flight_recorder_config_default(8000u, 2u);
    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &dcfg, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_EINVAL);
    dcfg = ap_flight_recorder_config_default(16000u, 1u);
    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &dcfg, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_EINVAL);
    dcfg = ap_flight_recorder_config_default(16000u, 2u);
    dcfg.pre_roll_frames = 1u;
    dcfg.post_roll_frames = 0u;
    assert(ap_flight_recorder_init(recorder_state, sizeof(recorder_state), &dcfg, &recorder) == AP_OK);
    assert(ap_runtime_attach_flight_recorder(runtime, recorder) == AP_OK);
    ap_runtime_deinit(runtime);
}

"""
    tests = tests.replace('static void test_flight_recorder(void) {\n', insert + 'static void test_flight_recorder(void) {\n', 1)
tests = tests.replace('''    dcfg.pre_roll_frames = 2u;
    dcfg.post_roll_frames = 1u;
''', '''    dcfg.pre_roll_frames = 2u;
    dcfg.post_roll_frames = 1u;
    dcfg.record_mask = AP_DIAG_RECORD_ALL;
''', 1)
anchor = '''    memset(&cmd, 0, sizeof(cmd));
    cmd.struct_size = sizeof(cmd);
    cmd.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    cmd.kind = AP_RUNTIME_COMMAND_SET_QUALITY;
'''
invalid = '''    memset(&cmd, 0, sizeof(cmd));
    cmd.struct_size = sizeof(cmd);
    cmd.api_version = AP_RUNTIME_CONTROL_API_VERSION;
    cmd.kind = 0x7fffffffu;
    assert(ap_runtime_command(runtime, &cmd) == AP_EINVAL);
    cmd.kind = AP_RUNTIME_COMMAND_SET_QUALITY;
    cmd.data.set_quality.quality = (ap_quality_t)99;
    assert(ap_runtime_command(runtime, &cmd) == AP_EINVAL);
    cmd.kind = AP_RUNTIME_COMMAND_STREAM_DISCONTINUITY;
    cmd.data.discontinuity.flags = 1u << 31;
    assert(ap_runtime_command(runtime, &cmd) == AP_EINVAL);

'''
if invalid not in tests:
    if anchor not in tests:
        raise SystemExit('command-test anchor missing')
    tests = tests.replace(anchor, invalid + anchor, 1)
tests = tests.replace('''    test_metadata_commands_and_events();
    test_flight_recorder();
''', '''    test_metadata_commands_and_events();
    test_recorder_configuration_contract();
    test_flight_recorder();
''', 1)
tests_path.write_text(tests)

# Privacy docs.
diag_path = Path('docs/DIAGNOSTICS.md')
diag = diag_path.read_text()
diag = diag.replace('The recorder is a bounded circular buffer with configurable pre-roll and post-roll. Recording masks independently select microphone PCM, render PCM, processed output and per-frame metrics.',
                    'The recorder is a bounded circular buffer with configurable pre-roll and post-roll. The default policy records metrics only; microphone/render/output PCM require explicit opt-in. Recording masks independently select microphone PCM, render PCM, processed output and per-frame metrics.')
diag_path.write_text(diag)

# Product certification requires explicit policy and thermal/power evidence.
schema_path = Path('certification/record.schema.json')
schema = json.loads(schema_path.read_text())
schema['properties']['policy'] = {'type': 'string', 'minLength': 1}
for item in schema['allOf']:
    then = item.get('then', {})
    then['required'] = sorted(set(then.get('required', []) + ['policy', 'thermal_power']))
    then['properties']['thermal_power'] = {'required': ['ambient_c', 'max_soc_c', 'average_power_w']}
schema_path.write_text(json.dumps(schema, indent=2) + '\n')

policy_schema = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'title': 'audio-pipeline product certification policy',
    'type': 'object',
    'required': ['policy_id', 'max_active_cpu_percent', 'max_rss_kib', 'max_p95_us', 'max_p99_us', 'max_soc_c', 'max_average_power_w', 'min_far_end_erle_db', 'max_aec_convergence_ms', 'min_double_talk_near_si_sdr_db', 'min_noise_si_sdr_improvement_db', 'min_vad_f1', 'min_soak_hours'],
    'properties': {
        'policy_id': {'type': 'string', 'minLength': 1},
        'max_active_cpu_percent': {'type': 'number', 'minimum': 0},
        'max_rss_kib': {'type': 'integer', 'minimum': 1},
        'max_p95_us': {'type': 'number', 'exclusiveMinimum': 0},
        'max_p99_us': {'type': 'number', 'exclusiveMinimum': 0},
        'max_soc_c': {'type': 'number'},
        'max_average_power_w': {'type': 'number', 'exclusiveMinimum': 0},
        'min_far_end_erle_db': {'type': 'number'},
        'max_aec_convergence_ms': {'type': 'number', 'exclusiveMinimum': 0},
        'min_double_talk_near_si_sdr_db': {'type': 'number'},
        'min_noise_si_sdr_improvement_db': {'type': 'number'},
        'min_vad_f1': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'min_soak_hours': {'type': 'number', 'minimum': 8}
    },
    'additionalProperties': False
}
Path('certification/policy.schema.json').write_text(json.dumps(policy_schema, indent=2) + '\n')
Path('certification/policies').mkdir(exist_ok=True)
Path('certification/policies/example-cortex-a32-low.json').write_text(json.dumps({
    'policy_id': 'example-cortex-a32-low-not-for-shipping',
    'max_active_cpu_percent': 40, 'max_rss_kib': 4096,
    'max_p95_us': 7000, 'max_p99_us': 9000,
    'max_soc_c': 85, 'max_average_power_w': 2.0,
    'min_far_end_erle_db': 15, 'max_aec_convergence_ms': 1000,
    'min_double_talk_near_si_sdr_db': 5,
    'min_noise_si_sdr_improvement_db': 3,
    'min_vad_f1': 0.85, 'min_soak_hours': 8
}, indent=2) + '\n')
Path('certification/policies/README.md').write_text("""# Certification policies

A `product-certified` record must be validated against an explicit product/SKU policy. The checked-in Cortex-A32 policy is an example only and is deliberately named `not-for-shipping`; copy it, replace every threshold with product-owned requirements, and version/hash the resulting policy with the certification evidence.
""")

Path('certification/validate_record.py').write_text(r'''#!/usr/bin/env python3
"""Validate audio-pipeline SKU certification evidence and product policy."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
PRODUCT_PERF_REQUIRED={"active_cpu_percent","p95_us","p99_us","deadline_misses","rss_kib","xruns","overruns","input_full_events","output_drop_events"}
PRODUCT_ACOUSTIC_REQUIRED={"corpus_revision","cases_total","cases_passed","far_end_erle_db","aec_convergence_ms","double_talk_near_si_sdr_db","noise_si_sdr_improvement_db","vad_f1","threshold_report"}
POLICY_REQUIRED={"policy_id","max_active_cpu_percent","max_rss_kib","max_p95_us","max_p99_us","max_soc_c","max_average_power_w","min_far_end_erle_db","max_aec_convergence_ms","min_double_talk_near_si_sdr_db","min_noise_si_sdr_improvement_db","min_vad_f1","min_soak_hours"}
def require_keys(obj,keys,where,errors):
    missing=sorted(k for k in keys if k not in obj)
    if missing: errors.append(f"{where}: missing {', '.join(missing)}")
def validate(record,policy=None):
    errors=[]; require_keys(record,{"sku","status","build","platform","audio_route","performance","acoustic","soak","artifacts"},"record",errors)
    if errors:return errors
    status=record["status"]
    if status not in {"pending","board-validated","product-certified","failed"}: errors.append(f"status: unsupported value {status!r}")
    require_keys(record["build"],{"commit","version","fingerprint","compiler","abi"},"build",errors); require_keys(record["platform"],{"soc","kernel","governor","cpuset"},"platform",errors); require_keys(record["audio_route"],{"capture_device","playback_device","sample_rate_hz","mic_channels"},"audio_route",errors); require_keys(record["soak"],{"hours","passed"},"soak",errors)
    if record["audio_route"].get("sample_rate_hz") not in {8000,16000,24000,32000,48000}: errors.append("audio_route.sample_rate_hz: unsupported rate")
    if record["audio_route"].get("mic_channels") not in {1,2}: errors.append("audio_route.mic_channels: must be 1 or 2")
    if status!="product-certified":return errors
    if policy is None: errors.append("policy: product-certified requires an explicit --policy"); return errors
    require_keys(policy,POLICY_REQUIRED,"policy",errors)
    if errors:return errors
    if record.get("policy")!=policy.get("policy_id"): errors.append("policy: record policy id must match supplied policy")
    perf,acoustic,soak,artifacts=record["performance"],record["acoustic"],record["soak"],record["artifacts"]; thermal=record.get("thermal_power",{})
    require_keys(perf,PRODUCT_PERF_REQUIRED,"performance",errors); require_keys(acoustic,PRODUCT_ACOUSTIC_REQUIRED,"acoustic",errors); require_keys(thermal,{"ambient_c","max_soc_c","average_power_w"},"thermal_power",errors); require_keys(soak,{"hours","passed","xruns","deadline_misses","output_drop_events"},"soak",errors); require_keys(artifacts,{"result_json","benchmark_json","sha256"},"artifacts",errors)
    if errors:return errors
    for key in {"deadline_misses","xruns","overruns","input_full_events","output_drop_events"}:
        if int(perf[key])!=0: errors.append(f"performance.{key}: nominal gate requires 0")
    for key in {"xruns","deadline_misses","output_drop_events"}:
        if int(soak[key])!=0: errors.append(f"soak.{key}: nominal gate requires 0")
    checks=[(float(perf["active_cpu_percent"])<=float(policy["max_active_cpu_percent"]),"performance.active_cpu_percent"),(int(perf["rss_kib"])<=int(policy["max_rss_kib"]),"performance.rss_kib"),(float(perf["p95_us"])<=float(policy["max_p95_us"]),"performance.p95_us"),(float(perf["p99_us"])<=float(policy["max_p99_us"]),"performance.p99_us"),(float(thermal["max_soc_c"])<=float(policy["max_soc_c"]),"thermal_power.max_soc_c"),(float(thermal["average_power_w"])<=float(policy["max_average_power_w"]),"thermal_power.average_power_w"),(float(acoustic["far_end_erle_db"])>=float(policy["min_far_end_erle_db"]),"acoustic.far_end_erle_db"),(float(acoustic["aec_convergence_ms"])<=float(policy["max_aec_convergence_ms"]),"acoustic.aec_convergence_ms"),(float(acoustic["double_talk_near_si_sdr_db"])>=float(policy["min_double_talk_near_si_sdr_db"]),"acoustic.double_talk_near_si_sdr_db"),(float(acoustic["noise_si_sdr_improvement_db"])>=float(policy["min_noise_si_sdr_improvement_db"]),"acoustic.noise_si_sdr_improvement_db"),(float(acoustic["vad_f1"])>=float(policy["min_vad_f1"]),"acoustic.vad_f1"),(float(soak["hours"])>=float(policy["min_soak_hours"]),"soak.hours")]
    for passed,name in checks:
        if not passed:errors.append(f"{name}: violates certification policy")
    if soak.get("passed") is not True:errors.append("soak.passed: product-certified requires true")
    if int(acoustic["cases_passed"])!=int(acoustic["cases_total"]):errors.append("acoustic: every certification corpus case must pass")
    if not re.fullmatch(r"[0-9a-fA-F]{64}",str(artifacts.get("sha256",""))):errors.append("artifacts.sha256: must be exactly 64 hexadecimal characters")
    return errors
def self_test():
    policy={"policy_id":"test-policy","max_active_cpu_percent":40,"max_rss_kib":4096,"max_p95_us":7000,"max_p99_us":9000,"max_soc_c":85,"max_average_power_w":2,"min_far_end_erle_db":15,"max_aec_convergence_ms":1000,"min_double_talk_near_si_sdr_db":5,"min_noise_si_sdr_improvement_db":3,"min_vad_f1":0.85,"min_soak_hours":8}
    record={"sku":"test","status":"product-certified","policy":"test-policy","build":{"commit":"abcdef0","version":"1.1.1","fingerprint":"x","compiler":"gcc","abi":"armv7"},"platform":{"soc":"test","kernel":"6.6","governor":"performance","cpuset":"1"},"audio_route":{"capture_device":"hw:0,0","playback_device":"hw:0,0","sample_rate_hz":16000,"mic_channels":2},"performance":{"active_cpu_percent":20,"p95_us":3000,"p99_us":5000,"deadline_misses":0,"rss_kib":512,"xruns":0,"overruns":0,"input_full_events":0,"output_drop_events":0},"acoustic":{"corpus_revision":"r1","cases_total":10,"cases_passed":10,"far_end_erle_db":20,"aec_convergence_ms":500,"double_talk_near_si_sdr_db":8,"noise_si_sdr_improvement_db":4,"vad_f1":0.9,"threshold_report":"result.json"},"thermal_power":{"ambient_c":25,"max_soc_c":60,"average_power_w":1},"soak":{"hours":8,"passed":True,"xruns":0,"deadline_misses":0,"output_drop_events":0},"artifacts":{"result_json":"result.json","benchmark_json":"bench.json","sha256":"0"*64}}
    assert validate(record,policy)==[]; bad=json.loads(json.dumps(record)); bad["performance"]["active_cpu_percent"]=50; assert validate(bad,policy); assert validate(record,None); print("audio-pipeline certification validator self-test: OK")
def main():
    p=argparse.ArgumentParser();p.add_argument("record",type=Path,nargs="?");p.add_argument("--policy",type=Path);p.add_argument("--self-test",action="store_true");a=p.parse_args()
    if a.self_test:self_test();return 0
    if a.record is None:p.error("record is required unless --self-test is used")
    record=json.loads(a.record.read_text(encoding="utf-8"));policy=json.loads(a.policy.read_text(encoding="utf-8")) if a.policy else None;errors=validate(record,policy)
    if errors:
        [print(f"ERROR: {e}") for e in errors];return 1
    print(f"certification record OK: {a.record}");return 0
if __name__=="__main__":raise SystemExit(main())
''')

cert_path = Path('certification/README.md')
cert = cert_path.read_text()
if '## Product policy gate' not in cert:
    cert += """
## Product policy gate

`product-certified` now requires an explicit SKU policy and thermal/power evidence. Validate with:

```bash
python3 certification/validate_record.py record.json --policy product-policy.json
```

The repository example policy is not a shipping requirement; product owners must define and version their own thresholds.
"""
cert_path.write_text(cert)

# Consolidate verification and pin external Actions.
child_workflows = ['.github/workflows/ci.yml', '.github/workflows/quality.yml', '.github/workflows/audio-quality-gates.yml', '.github/workflows/resource-gates.yml']
for path in child_workflows:
    p=Path(path); text=p.read_text()
    old_on='on:\n  push:\n  pull_request:\n  workflow_dispatch:\n'
    if old_on not in text: raise SystemExit(f'workflow trigger block missing: {path}')
    text=text.replace(old_on,'on:\n  workflow_call:\n',1)
    text=text.replace('uses: actions/checkout@v5','uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5')
    p.write_text(text)

quality_path=Path('.github/workflows/quality.yml');quality=quality_path.read_text()
quality=quality.replace("          -DAP_ENABLE_LINUX_RUNTIME=OFF -DAP_BUILD_BENCH=OFF\n          -DCMAKE_C_FLAGS='--coverage -O0 -g'\n","          -DAP_BUILD_BENCH=OFF\n          -DCMAKE_C_FLAGS='--coverage -O0 -g'\n",1)
quality=quality.replace("          -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF\n          -DAP_ENABLE_LINUX_RUNTIME=OFF\n","          -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF\n",1)
quality=quality.replace("          -DAP_SIMD_BACKEND=${{ matrix.simd }}\n          -DAP_ENABLE_LINUX_RUNTIME=OFF -DAP_BUILD_BENCH=OFF\n          -DAP_BUILD_EXAMPLES=OFF -DAP_BUILD_TESTS=ON\n","          -DAP_SIMD_BACKEND=${{ matrix.simd }}\n          -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF -DAP_BUILD_TESTS=ON\n",1)
quality=quality.replace('          --target ap_module_tests ap_contract_tests ap_fft_tests ap_resampler_tests\n','          --target ap_module_tests ap_contract_tests ap_fft_tests ap_resampler_tests ap_runtime_tests\n',1)
quality=quality.replace('          $Q ./build/qemu-${{ matrix.name }}/ap_resampler_tests\n','          $Q ./build/qemu-${{ matrix.name }}/ap_resampler_tests\n          $Q ./build/qemu-${{ matrix.name }}/ap_runtime_tests\n',1)
quality_path.write_text(quality)

nightly_path=Path('.github/workflows/nightly.yml');nightly=nightly_path.read_text().replace('uses: actions/checkout@v5','uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5').replace('-max_total_time=300','-max_total_time=900');nightly_path.write_text(nightly)

Path('.github/workflows/codeql.yml').write_text('''name: CodeQL

on:
  workflow_call:

permissions:
  contents: read
  security-events: write
  packages: read

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5
      - uses: github/codeql-action/init@cdf488f595d80d6e07e03d4674febd5ab45fa938 # v4
        with:
          languages: c-cpp
          build-mode: manual
      - name: Build analyzed configuration
        run: |
          cmake -S . -B build-codeql -DCMAKE_BUILD_TYPE=RelWithDebInfo -DAP_BUILD_BENCH=OFF
          cmake --build build-codeql --parallel
      - uses: github/codeql-action/analyze@cdf488f595d80d6e07e03d4674febd5ab45fa938 # v4
''')
Path('.github/workflows/verify.yml').write_text('''name: Verify

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  security-events: write
  packages: read

concurrency:
  group: verify-${{ github.ref }}
  cancel-in-progress: true

jobs:
  ci:
    uses: ./.github/workflows/ci.yml
  quality:
    uses: ./.github/workflows/quality.yml
  audio-quality:
    uses: ./.github/workflows/audio-quality-gates.yml
  resource-gates:
    uses: ./.github/workflows/resource-gates.yml
  codeql:
    uses: ./.github/workflows/codeql.yml
  summary:
    if: always()
    needs: [ci, quality, audio-quality, resource-gates, codeql]
    runs-on: ubuntu-latest
    steps:
      - name: Enforce aggregate verification
        env:
          CI_RESULT: ${{ needs.ci.result }}
          QUALITY_RESULT: ${{ needs.quality.result }}
          AUDIO_RESULT: ${{ needs.audio-quality.result }}
          RESOURCE_RESULT: ${{ needs.resource-gates.result }}
          CODEQL_RESULT: ${{ needs.codeql.result }}
        run: |
          printf 'ci=%s quality=%s audio=%s resource=%s codeql=%s\n' "$CI_RESULT" "$QUALITY_RESULT" "$AUDIO_RESULT" "$RESOURCE_RESULT" "$CODEQL_RESULT"
          test "$CI_RESULT" = success
          test "$QUALITY_RESULT" = success
          test "$AUDIO_RESULT" = success
          test "$RESOURCE_RESULT" = success
          test "$CODEQL_RESULT" = success
''')
Path('.github/workflows/release.yml').write_text('''name: Release

on:
  workflow_run:
    workflows: [Verify]
    types: [completed]

permissions:
  contents: write
  id-token: write
  attestations: write

concurrency:
  group: release
  cancel-in-progress: false

jobs:
  release:
    if: github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push' && github.event.workflow_run.head_branch == 'main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5
        with:
          ref: ${{ github.event.workflow_run.head_sha }}
          fetch-depth: 0
      - name: Verify exact release SHA
        env:
          VERIFIED_SHA: ${{ github.event.workflow_run.head_sha }}
        run: test "$(git rev-parse HEAD)" = "$VERIFIED_SHA"
      - name: Resolve project version
        id: version
        run: |
          version=$(sed -n 's/^project(audio_pipeline VERSION \([0-9][0-9.]*\).*/\1/p' CMakeLists.txt)
          test -n "$version"
          echo "version=$version" >> "$GITHUB_OUTPUT"
          echo "tag=v$version" >> "$GITHUB_OUTPUT"
      - name: Check existing release
        id: existing
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ steps.version.outputs.tag }}
        run: |
          if gh release view "$TAG" >/dev/null 2>&1; then echo "release=true" >> "$GITHUB_OUTPUT"; else echo "release=false" >> "$GITHUB_OUTPUT"; fi
      - name: Build, test and install SDK
        if: steps.existing.outputs.release != 'true'
        run: |
          cmake -S . -B build-release -DCMAKE_BUILD_TYPE=Release
          cmake --build build-release --parallel
          ctest --test-dir build-release --output-on-failure
          cmake --install build-release --prefix "$PWD/stage"
      - name: Package SDK and checksums
        if: steps.existing.outputs.release != 'true'
        env:
          TAG: ${{ steps.version.outputs.tag }}
        run: |
          tar -C stage -czf "audio-pipeline-${TAG}-sdk.tar.gz" .
          git archive --format=tar.gz -o "audio-pipeline-${TAG}-source.tar.gz" "$GITHUB_SHA"
          sha256sum "audio-pipeline-${TAG}-sdk.tar.gz" "audio-pipeline-${TAG}-source.tar.gz" > SHA256SUMS
      - name: Attest release artifacts
        if: steps.existing.outputs.release != 'true'
        uses: actions/attest-build-provenance@977bb373ede98d70efdf65b84cb5f73e068dcc2a # v3
        with:
          subject-path: |
            audio-pipeline-${{ steps.version.outputs.tag }}-sdk.tar.gz
            audio-pipeline-${{ steps.version.outputs.tag }}-source.tar.gz
            SHA256SUMS
      - name: Create exact-SHA release tag
        if: steps.existing.outputs.release != 'true'
        env:
          TAG: ${{ steps.version.outputs.tag }}
        run: |
          if git rev-parse "$TAG" >/dev/null 2>&1; then
            test "$(git rev-list -n1 "$TAG")" = "$GITHUB_SHA"
          else
            git config user.name github-actions[bot]
            git config user.email 41898282+github-actions[bot]@users.noreply.github.com
            git tag -a "$TAG" -m "audio-pipeline $TAG" "$GITHUB_SHA"
            git push origin "$TAG"
          fi
      - name: Create GitHub Release
        if: steps.existing.outputs.release != 'true'
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ steps.version.outputs.tag }}
        run: >-
          gh release create "$TAG"
          "audio-pipeline-${TAG}-sdk.tar.gz"
          "audio-pipeline-${TAG}-source.tar.gz"
          SHA256SUMS --verify-tag --generate-notes
''')
Path('.github/dependabot.yml').write_text('''version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
''')

# Changelog and public behavior notes.
changelog_path=Path('CHANGELOG.md');changelog=changelog_path.read_text()
entry="""## [1.1.1] - 2026-08-29

- validate Flight Recorder rate/frame/channel geometry and reject runtime/recorder mismatches before diagnostic copies;
- make Flight Recorder defaults metrics-only so private microphone/render/output PCM is explicit opt-in;
- reject unknown/invalid runtime commands before enqueue and surface apply-time tuning rejection as a bounded diagnostic event;
- consolidate PR/main verification behind one `Verify` workflow, include runtime in coverage/static analysis and execute runtime tests under Arm QEMU;
- gate Release on a successful exact-SHA main Verify run, add provenance attestations and pin third-party Actions to immutable commit SHAs with Dependabot maintenance;
- require explicit per-SKU certification policy plus CPU/RSS/latency/thermal/power/acoustic/soak thresholds for `product-certified` evidence;
- package LICENSE, third-party notice, README and changelog in the installed SDK.

"""
if '## [1.1.1]' not in changelog: changelog_path.write_text(changelog.replace('## [1.1.0]',entry+'## [1.1.0]',1))
api_path=Path('docs/API_CONTRACT.md');api=api_path.read_text()
if '## v1.1.1 hardening notes' not in api:
    api += """
## v1.1.1 hardening notes

Flight Recorder defaults are metrics-only; audio PCM recording is explicit opt-in. `ap_runtime_attach_flight_recorder()` rejects sample-rate/frame/channel geometry that does not match the runtime. `ap_runtime_command()` rejects unknown kinds and invalid payloads before enqueue; a command accepted into the bounded queue may still emit `AP_EVENT_COMMAND_REJECTED` if a frame-boundary state-dependent tuning application is rejected.
"""
api_path.write_text(api)

# Bootstrap assets self-delete before the final commit.
Path('.github/workflows/apply-v1.1.1-hardening.yml').unlink(missing_ok=True)
Path('.github/apply_v111.py').unlink(missing_ok=True)
