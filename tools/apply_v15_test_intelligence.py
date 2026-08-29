#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


cmake = Path("CMakeLists.txt")
replace_once(cmake,
             "project(audio_pipeline VERSION 1.4.0 LANGUAGES C)",
             "project(audio_pipeline VERSION 1.5.0 LANGUAGES C)")
replace_once(
    cmake,
    """        add_test(NAME ap_contract_tests COMMAND ap_contract_tests)\n        add_executable(ap_state_size tests/print_pipeline_state.c)\n""",
    """        add_test(NAME ap_contract_tests COMMAND ap_contract_tests)\n        if(AP_HAVE_BF AND AP_HAVE_NS AND AP_HAVE_VAD)\n            add_executable(ap_metamorphic_tests tests/test_metamorphic.c)\n            target_link_libraries(ap_metamorphic_tests PRIVATE audio_pipeline)\n            add_test(NAME ap_metamorphic_tests COMMAND ap_metamorphic_tests)\n        endif()\n        add_executable(ap_state_size tests/print_pipeline_state.c)\n""",
)

alsa = Path("examples/alsa_runtime_duplex.c")
replace_once(
    alsa,
    """static void nap_100us(void) {\n    const struct timespec t = {0, 100000};\n    (void)nanosleep(&t, NULL);\n}\n\nstatic void usage(const char *argv0) {\n""",
    """static void nap_100us(void) {\n    const struct timespec t = {0, 100000};\n    (void)nanosleep(&t, NULL);\n}\n\nstatic void nap_ms(unsigned ms) {\n    struct timespec t;\n    t.tv_sec = (time_t)(ms / 1000u);\n    t.tv_nsec = (long)(ms % 1000u) * 1000000L;\n    (void)nanosleep(&t, NULL);\n}\n\nstatic unsigned env_u32(const char *name, unsigned default_value) {\n    const char *value = getenv(name);\n    char *end = NULL;\n    unsigned long parsed;\n    if (!value || !*value) return default_value;\n    errno = 0;\n    parsed = strtoul(value, &end, 10);\n    if (errno != 0 || !end || *end != '\\0' || parsed > 0xfffffffful) {\n        fprintf(stderr, \"invalid %s=%s\\n\", name, value);\n        exit(2);\n    }\n    return (unsigned)parsed;\n}\n\nstatic int restart_pcm(snd_pcm_t *pcm) {\n    int rc;\n    if (!pcm) return 0;\n    rc = snd_pcm_drop(pcm);\n    if (rc < 0) return -1;\n    rc = snd_pcm_prepare(pcm);\n    return rc < 0 ? -1 : 0;\n}\n\nstatic void usage(const char *argv0) {\n""",
)
replace_once(
    alsa,
    """    uint64_t xruns = 0u;\n    int silence_render;\n""",
    """    uint64_t xruns = 0u;\n    uint64_t injected_route_restarts = 0u;\n    uint64_t injected_render_gap_frames = 0u;\n    uint64_t injected_cpu_stalls = 0u;\n    const unsigned fault_route_restart_every = env_u32(\"AP_FAULT_ROUTE_RESTART_EVERY\", 0u);\n    const unsigned fault_render_gap_every = env_u32(\"AP_FAULT_RENDER_GAP_EVERY\", 0u);\n    const unsigned fault_render_gap_frames = env_u32(\"AP_FAULT_RENDER_GAP_FRAMES\", 0u);\n    const unsigned fault_cpu_stall_every = env_u32(\"AP_FAULT_CPU_STALL_EVERY\", 0u);\n    const unsigned fault_cpu_stall_ms = env_u32(\"AP_FAULT_CPU_STALL_MS\", 0u);\n    unsigned render_gap_remaining = 0u;\n    int silence_render;\n""",
)
replace_once(
    alsa,
    """    cfg.io_sample_rate_hz = rate;\n    cfg.mic_channels = mic_channels;\n    if (ap_pipeline_validate_config(&cfg) != AP_OK) {\n""",
    """    cfg.io_sample_rate_hz = rate;\n    cfg.internal_sample_rate_hz = rate < 16000u ? rate : 16000u;\n    cfg.mic_channels = mic_channels;\n    if (mic_channels == 1u) cfg.stages &= ~AP_STAGE_BF;\n    if (ap_pipeline_validate_config(&cfg) != AP_OK) {\n""",
)
replace_once(
    alsa,
    """    while (!max_frames || produced < max_frames) {\n        ap_status_t s;\n        int ended = 0;\n        if (fill_render(far, silence_render, max_frames != 0u,\n                        render, frame, &ended) != 0) {\n""",
    """    while (!max_frames || produced < max_frames) {\n        ap_status_t s;\n        ap_frame_metadata_t metadata;\n        const ap_frame_metadata_t *metadata_ptr = NULL;\n        int ended = 0;\n        int gap_started = 0;\n        memset(&metadata, 0, sizeof(metadata));\n        metadata.struct_size = sizeof(metadata);\n        metadata.api_version = AP_RUNTIME_CONTROL_API_VERSION;\n        metadata.stream_sequence = produced;\n\n        if (fault_route_restart_every && produced > 0u &&\n            produced % fault_route_restart_every == 0u) {\n            if (restart_pcm(capture) != 0 || restart_pcm(playback) != 0) {\n                fprintf(stderr, \"injected ALSA route restart failed\\n\");\n                goto done;\n            }\n            metadata.flags |= AP_FRAME_CAPTURE_DISCONTINUITY | AP_FRAME_CODEC_REOPEN;\n            metadata.lost_capture_frames = 1u;\n            if (playback) {\n                metadata.flags |= AP_FRAME_RENDER_DISCONTINUITY;\n                metadata.lost_render_frames = 1u;\n            }\n            metadata_ptr = &metadata;\n            injected_route_restarts++;\n        }\n\n        if (fill_render(far, silence_render, max_frames != 0u,\n                        render, frame, &ended) != 0) {\n""",
)
replace_once(
    alsa,
    """            goto done;\n        }\n        if (playback && write_all(playback, render, frame, &xruns) != 0) {\n""",
    """            goto done;\n        }\n        if (playback && fault_render_gap_every && fault_render_gap_frames &&\n            render_gap_remaining == 0u && produced > 0u &&\n            produced % fault_render_gap_every == 0u) {\n            render_gap_remaining = fault_render_gap_frames;\n            gap_started = 1;\n        }\n        if (playback && render_gap_remaining > 0u) {\n            memset(render, 0, frame * sizeof(render[0]));\n            render_gap_remaining--;\n            injected_render_gap_frames++;\n            if (gap_started) {\n                metadata.flags |= AP_FRAME_RENDER_DISCONTINUITY;\n                metadata.lost_render_frames = fault_render_gap_frames;\n                metadata_ptr = &metadata;\n            }\n        }\n        if (playback && write_all(playback, render, frame, &xruns) != 0) {\n""",
)
replace_once(
    alsa,
    """        s = ap_runtime_submit(runtime, mic, playback ? render : NULL);\n""",
    """        if (fault_cpu_stall_every && fault_cpu_stall_ms && produced > 0u &&\n            produced % fault_cpu_stall_every == 0u) {\n            nap_ms(fault_cpu_stall_ms);\n            injected_cpu_stalls++;\n        }\n        s = ap_runtime_submit_ex(runtime, mic, playback ? render : NULL, metadata_ptr);\n""",
)
replace_once(
    alsa,
    """                \"actual_cpu=%d actual_policy=%d actual_priority=%d quality=%d \"\n                \"backend=%d delay_ms=%u resets=%llu\\n\",\n""",
    """                \"actual_cpu=%d actual_policy=%d actual_priority=%d quality=%d \"\n                \"backend=%d delay_ms=%u resets=%llu injected_route_restarts=%llu \"\n                \"injected_render_gap_frames=%llu injected_cpu_stalls=%llu\\n\",\n""",
)
replace_once(
    alsa,
    """                rm.actual_cpu, rm.actual_policy, rm.actual_priority,\n                (int)rm.quality, (int)pm.aec_backend, pm.estimated_delay_ms,\n                (unsigned long long)pm.aec_resets);\n""",
    """                rm.actual_cpu, rm.actual_policy, rm.actual_priority,\n                (int)rm.quality, (int)pm.aec_backend, pm.estimated_delay_ms,\n                (unsigned long long)pm.aec_resets,\n                (unsigned long long)injected_route_restarts,\n                (unsigned long long)injected_render_gap_frames,\n                (unsigned long long)injected_cpu_stalls);\n""",
)

evidence = Path("tools/target_evidence.py")
replace_once(evidence, 'VERSION = "2.0"', 'VERSION = "2.1"')
replace_once(
    evidence,
    """def run_monitored(command: list[str], power_input: Path | None, power_scale: float,\n                  sample_period: float = 0.10) -> tuple[subprocess.CompletedProcess[str], dict]:\n    process = subprocess.Popen(\n        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True\n    )\n""",
    """def run_monitored(command: list[str], power_input: Path | None, power_scale: float,\n                  sample_period: float = 0.10, extra_env: dict[str, str] | None = None\n                  ) -> tuple[subprocess.CompletedProcess[str], dict]:\n    environment = os.environ.copy()\n    if extra_env:\n        environment.update(extra_env)\n    process = subprocess.Popen(\n        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment\n    )\n""",
)
replace_once(
    evidence,
    """    result, sensors = run_monitored(\n        command, args.power_input, args.power_scale, args.sample_period\n    )\n""",
    """    fault_profiles = {\n        \"none\": {},\n        \"accelerated\": {\n            \"AP_FAULT_ROUTE_RESTART_EVERY\": \"3000\",\n            \"AP_FAULT_RENDER_GAP_EVERY\": \"6000\",\n            \"AP_FAULT_RENDER_GAP_FRAMES\": \"5\",\n            \"AP_FAULT_CPU_STALL_EVERY\": \"9000\",\n            \"AP_FAULT_CPU_STALL_MS\": \"15\",\n        },\n        \"stress\": {\n            \"AP_FAULT_ROUTE_RESTART_EVERY\": \"1000\",\n            \"AP_FAULT_RENDER_GAP_EVERY\": \"2000\",\n            \"AP_FAULT_RENDER_GAP_FRAMES\": \"10\",\n            \"AP_FAULT_CPU_STALL_EVERY\": \"3000\",\n            \"AP_FAULT_CPU_STALL_MS\": \"25\",\n        },\n    }\n    fault_env = dict(fault_profiles[args.fault_profile])\n    if playback == \"-\":\n        fault_env.pop(\"AP_FAULT_RENDER_GAP_EVERY\", None)\n        fault_env.pop(\"AP_FAULT_RENDER_GAP_FRAMES\", None)\n    result, sensors = run_monitored(\n        command, args.power_input, args.power_scale, args.sample_period, fault_env\n    )\n""",
)
replace_once(
    evidence,
    """    required = {\n        \"produced\", \"received\", \"xruns\", \"dsp_overruns\", \"input_full\",\n        \"output_drop\", \"p95_dsp_us\", \"p99_dsp_us\", \"failed_frames\",\n    }\n""",
    """    required = {\n        \"produced\", \"received\", \"xruns\", \"dsp_overruns\", \"input_full\",\n        \"output_drop\", \"p95_dsp_us\", \"p99_dsp_us\", \"failed_frames\",\n        \"injected_route_restarts\", \"injected_render_gap_frames\",\n        \"injected_cpu_stalls\",\n    }\n""",
)
replace_once(
    evidence,
    """    failed_frames = as_int(values, \"failed_frames\")\n    passed = (\n        result.returncode == 0 and produced == received\n        and xruns <= args.max_xruns and overruns <= args.max_overruns\n        and input_full == 0 and output_drop == 0 and failed_frames == 0\n    )\n""",
    """    failed_frames = as_int(values, \"failed_frames\")\n    injected_restarts = as_int(values, \"injected_route_restarts\")\n    injected_gaps = as_int(values, \"injected_render_gap_frames\")\n    injected_stalls = as_int(values, \"injected_cpu_stalls\")\n    injection_ok = True\n    if args.fault_profile != \"none\":\n        injection_ok = injected_restarts > 0 and injected_stalls > 0\n        if playback != \"-\":\n            injection_ok = injection_ok and injected_gaps > 0\n    passed = (\n        result.returncode == 0 and produced == received and injection_ok\n        and xruns <= args.max_xruns and overruns <= args.max_overruns\n        and input_full == 0 and output_drop == 0 and failed_frames == 0\n    )\n""",
)
replace_once(
    evidence,
    """        \"soak\": {\n            \"hours\": args.seconds / 3600.0,\n""",
    """        \"fault_injection\": {\n            \"profile\": args.fault_profile,\n            \"route_restarts\": injected_restarts,\n            \"render_gap_frames\": injected_gaps,\n            \"cpu_stalls\": injected_stalls,\n            \"observed_required_faults\": injection_ok,\n        },\n        \"soak\": {\n            \"hours\": args.seconds / 3600.0,\n""",
)
replace_once(
    evidence,
    """        \"max_dsp_us=40 failed_frames=0 critical_events=0\\n\"\n""",
    """        \"max_dsp_us=40 failed_frames=0 critical_events=0 \"\n        \"injected_route_restarts=0 injected_render_gap_frames=0 injected_cpu_stalls=0\\n\"\n""",
)
replace_once(
    evidence,
    """    assert as_int(r, \"p95_dsp_us\") == 20\n    print(\"target evidence collector self-test: OK\")\n""",
    """    assert as_int(r, \"p95_dsp_us\") == 20\n    assert as_int(r, \"injected_route_restarts\") == 0\n    print(\"target evidence collector self-test: OK\")\n""",
)
replace_once(
    evidence,
    """    s.add_argument(\"--sample-period\", type=float, default=1.0)\n""",
    """    s.add_argument(\"--sample-period\", type=float, default=1.0)\n    s.add_argument(\"--fault-profile\", choices=(\"none\", \"accelerated\", \"stress\"),\n                   default=\"none\")\n""",
)

print("v1.5 test-intelligence ordinary patches applied")
