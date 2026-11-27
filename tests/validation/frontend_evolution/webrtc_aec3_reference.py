#!/usr/bin/env python3
"""Fixed six-case AEC3/APM descriptive replay; no search, ranking or promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import stat
import subprocess
import sys
import time
import zipfile

from contracts import ROOT, hex_digest, load_json, require
import speexdsp_aec_reference as previous
import speech_spatial as speech

HERE = Path(__file__).resolve().parent
PLAN = ROOT / ".github/research/frontend-evolution-v1/webrtc-aec3-reference-v1.json"
PLAN_SHA256 = "667847601ae3709cded97d86989f8b65066d01363a1adfa40db1f2be4a522617"
ROLE = "DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT"
DECISION = "DESCRIPTIVE_ONLY_NO_PROMOTION_NO_RANKING_RULE"
MODES = ("aec3", "apm")
DELAYS = {"aec3": 128, "apm": 224}
REL = "tests/validation/frontend_evolution/"
# Capture the existing canonical readers' complete repository import closure,
# including modules imported for their helpers rather than reimplementing them.
METRIC_SOURCES = tuple(REL + name + ".py" for name in (
    "webrtc_aec3_reference", "speexdsp_aec_reference", "speech_spatial", "bf_aec_order",
    "contracts", "activity_gates", "array_fir_checks", "array_qualification",
    "array_steering_checks", "libfvad_reference", "spatial_weights", "speech_fir",
    "speech_source", "speech_spatial_weights", "speexdsp_source")) + tuple(
    "validation/tools/" + name + ".py" for name in (
        "authority", "render_corr_exact", "run_validation", "run_validation_engine", "stage_profile_support"))
ENGINEERING_SOURCE = REL + "test_webrtc_aec3_adapter.py"
RUNNER_SOURCE = REL + "webrtc_aec3_runner.cc"
RUNTIME_SOURCE = REL + "webrtc_aec3_ci.py"


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def write_json(path, value):
    with path.open("xb") as stream:
        stream.write(encoded(value))


def safe_path(path):
    path = Path(os.path.abspath(str(path)))
    require(not any(p.is_symlink() for p in (path,) + tuple(path.parents)), "symlink path forbidden")
    return path


def relative_name(name):
    require(isinstance(name, str) and 0 < len(name) <= 512 and "\\" not in name
            and not any(ord(c) < 32 or ord(c) == 127 for c in name), "unsafe relative path")
    parts = name.split("/")
    require(not PurePosixPath(name).is_absolute() and all(p and p not in (".", "..") and ":" not in p for p in parts),
            "unsafe relative path")
    return name


def regular(path, maximum=64 * 1024 * 1024):
    path = safe_path(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not info.st_mode & 0o7000 and info.st_size <= maximum,
            "regular bounded unlinked file required: " + str(path))
    return path


def read_json(path, maximum=16 * 1024 * 1024):
    return load_json(regular(path, maximum))


def file_set(root, excluded=()):
    root = safe_path(root)
    require(root.is_dir(), "missing evidence directory")
    result, total, directories = {}, 0, set()
    for directory, children, files in os.walk(root, followlinks=False):
        for name in children:
            path = Path(directory) / name
            require(not path.is_symlink(), "evidence directory symlink")
            directories.add(path.relative_to(root).as_posix())
            require(len(directories) <= 12000, "evidence directory bound")
        for name in files:
            path = regular(Path(directory) / name)
            relative = relative_name(path.relative_to(root).as_posix())
            total += path.stat().st_size
            require(len(result) < 12000 and total <= 512 * 1024 * 1024, "evidence file/byte bound")
            if relative not in excluded:
                result[relative] = sha_file(path)
    expected_dirs = {"/".join(name.split("/")[:n]) for name in result
                     for n in range(1, len(name.split("/")))}
    require(directories == expected_dirs, "unexpected empty evidence directory")
    return result


def frozen_plan():
    require(sha_file(regular(PLAN, 65536)) == PLAN_SHA256, "frozen reference plan changed")
    plan = read_json(PLAN)
    require(plan["data_role"] == ROLE and plan["metrics"]["disposition"] == DECISION
            and plan["budget"]["new_full_case_executions"] == 12
            and plan["budget"]["extra_new_acoustic_retries"] == 0
            and plan["rate_hz"] == 16000 and plan["hop_samples"] == 160
            and plan["mic_channels"] == plan["render_channels"] == 1
            and plan["channel_map"] == [0] and len(plan["cases"]) == 6,
            "reference plan scope changed")
    return plan


def git_bytes(revision, relative, repository=ROOT):
    require(hex_digest(revision, 40), "exact code revision required")
    relative_name(relative)
    value = subprocess.check_output(["git", "-C", str(repository), "show", revision + ":" + relative],
                                    stderr=subprocess.PIPE, timeout=15)
    require(len(value) <= 1024 * 1024, "committed source byte bound")
    return value


def current_sources():
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], timeout=10).decode().strip()
    hashes = {}
    for name in METRIC_SOURCES:
        raw = regular(ROOT / name).read_bytes()
        require(git_bytes(head, name) == raw, "uncommitted measurement implementation: " + name)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    return {"code_revision": head, "files": hashes}


def verify_measurement_sources(output, sources, repository=ROOT):
    require(set(sources["files"]) == set(METRIC_SOURCES), "measurement source closure")
    for name, digest in sources["files"].items():
        require(sha_file(regular(output / "measurement-source" / name)) == digest
                and hashlib.sha256(git_bytes(sources["code_revision"], name, repository)).hexdigest() == digest
                and sha_file(regular(repository / name)) == digest, "measurement implementation identity")


def archive_members(archive, plan):
    """Only authenticate/extract disclosed frozen bytes, never execute old tools."""
    spec = plan["predecessor"]
    archive = regular(archive, spec["archive_bytes"])
    require(archive.stat().st_size == spec["archive_bytes"] and sha_file(archive) == spec["archive_sha256"],
            "original predecessor ZIP identity mismatch")
    selected = {"cases/" + case["case_id"] + "/" + name: value
                for case in plan["cases"] for name, value in case["members"].items()}
    result = {}
    with zipfile.ZipFile(archive) as source:
        rows = source.infolist()
        require(len(rows) == 252 and len({r.filename for r in rows}) == 252, "predecessor ZIP membership")
        require(sum(r.file_size for r in rows) <= 32 * 1024 * 1024, "predecessor ZIP expanded bound")
        for row in rows:
            relative_name(row.filename[:-1] if row.is_dir() else row.filename)
            mode = row.external_attr >> 16
            require(stat.S_IFMT(mode) in (0, stat.S_IFDIR, stat.S_IFREG) and not row.flag_bits & 1,
                    "predecessor ZIP link/special/encrypted member")
            require(row.file_size <= 2 * 1024 * 1024, "predecessor ZIP member bound")
            if row.filename in selected:
                wanted = selected[row.filename]
                require(row.file_size == wanted["bytes"], "predecessor selected byte count")
                raw = source.read(row)
                require(hashlib.sha256(raw).hexdigest() == wanted["sha256"], "predecessor selected SHA256")
                result[row.filename] = raw
        require(hashlib.sha256(source.read("manifest.json")).hexdigest() == spec["manifest_sha256"],
                "predecessor manifest identity")
    require(set(result) == set(selected), "missing frozen predecessor case/member")
    return result


def split_mic_render(raw, samples):
    require(len(raw) == samples * 4, "interleaved mic/render cardinality")
    # Slice two-byte samples without converting, requantizing or normalizing.
    return (b"".join(raw[i:i + 2] for i in range(0, len(raw), 4)),
            b"".join(raw[i + 2:i + 4] for i in range(0, len(raw), 4)))


def normalized_runtime(identity):
    require(set(identity) >= {"system", "machine", "release", "os_release_sha256", "libraries", "library_names"},
            "missing runtime identity")
    require(identity["system"] == "Linux" and hex_digest(identity["os_release_sha256"]), "unsupported host identity")
    libraries = identity["libraries"]
    require(libraries and all(isinstance(p, str) and Path(p).is_absolute() and hex_digest(v)
                             for p, v in libraries.items()), "runtime library identity")
    by_name = {}
    for name, path in identity["library_names"].items():
        require(isinstance(name, str) and "/" not in name and path in libraries, "runtime SONAME identity")
        by_name[name] = libraries[path]
    require(by_name and set(libraries) == set(identity["library_names"].values()), "runtime dependency closure")
    return {**{k: identity[k] for k in ("system", "machine", "release", "os_release_sha256")}, "libraries": by_name}


def research_runtime_binding(identity, adapter, root=None):
    observed = normalized_runtime(identity)["libraries"]
    expected = {Path(name).name: value for name, value in adapter["runtime_libraries"].items()}
    actual = {name: digest for name, digest in observed.items() if name.startswith(("libwebrtc-", "libabsl"))}
    require(actual == expected and any(name.startswith("libwebrtc-audio-processing-2.so") for name in actual),
            "runtime research libraries differ from the portable bundle")
    if root is not None:
        require(all(Path(identity["library_names"][name]).parent == (root / "bin/lib").resolve()
                    for name in actual), "research library loaded outside portable bundle")


def engineering_record(path, revision, binary_sha, build_sha):
    record = read_json(path)
    require(record["schema_version"] == 1 and record["fixture_id"] == "webrtc-aec3-engineering-v1"
            and record["status"] == "PASS_ENGINEERING_ONLY" and record["failures"] == []
            and record["code_revision"] == revision and record["binary_sha256"] == binary_sha
            and record["build_receipt_sha256"] == build_sha, "engineering/binary/source binding")
    require(record["fixture_source_sha256"] == hashlib.sha256(git_bytes(revision, ENGINEERING_SOURCE)).hexdigest(),
            "engineering fixture source identity")
    require(record["runtime_identity_source_sha256"] == hashlib.sha256(git_bytes(revision, RUNTIME_SOURCE)).hexdigest(),
            "engineering runtime observer source identity")
    require(record["signal_delay_predeclared_samples"] == DELAYS
            and record["data_role"] == "synthetic_engineering_only_not_real_acoustic_evidence"
            and all(record[k] is False for k in ("acoustic_acceptance", "physical_target_measurement", "promotion_authority")),
            "engineering scope/latency changed")
    require(type(record["requested_capture_audio_seconds"]) in (int, float)
            and 0 < record["requested_capture_audio_seconds"] <= 10
            and type(record["wall_seconds"]) in (int, float) and 0 < record["wall_seconds"] <= 120,
            "engineering budget exceeded")
    checks = record["checks"]
    expected = {m + "-" + str(n) + "-geometry" for m in MODES for n in (1, 2, 4)}
    expected |= {m + "-" + suffix for m in MODES for suffix in ("tail", "latency")} | {"invalid-inputs"}
    expected |= {"runtime-identity-initial", "runtime-identity-stable"}
    require(len(checks) == len(expected) and {r["name"] for r in checks} == expected
            and all(r["status"] == "PASS" for r in checks), "missing engineering checks")
    require(len(record["calls"]) == 62 and len({call["case_id"] for call in record["calls"]}) == 62,
            "engineering call count/uniqueness")
    capture_samples, errors = 0, 0
    for call in record["calls"]:
        folder = path.parent / relative_name(call["case_id"])
        channels = call["mic_channels"]
        require(type(channels) is int and channels in (1, 2, 4) and call["mode"] in MODES
                and type(call["expected_error"]) is bool, "engineering call mode/geometry")
        mic, render = regular(folder / "mic.pcm", 32000 * channels), regular(folder / "render.pcm", 32000)
        require(sha_file(mic) == call["mic_sha256"] and sha_file(render) == call["render_sha256"], "engineering input hash")
        capture_samples += (mic.stat().st_size + 2 * channels - 1) // (2 * channels)
        errors += int(call["expected_error"])
        require(type(call["returncode"]) is int and call["returncode"] == (2 if call["expected_error"] else 0),
                "engineering process failed")
        if not call["expected_error"]:
            for filename, key in (("output.pcm", "output_sha256"), ("metadata.json", "metadata_sha256"),
                                  ("frames.jsonl", "frame_times_sha256")):
                require(sha_file(regular(folder / filename)) == call[key], "engineering output hash: " + key)
    require(errors == 20 and capture_samples / 16000 == record["requested_capture_audio_seconds"],
            "engineering actual input budget/call set differs from receipt")
    normalized_runtime(record["runtime_identity"])
    return record


def verify_bundle(root):
    root = safe_path(root)
    bundle = read_json(root / "bundle.json")
    require(bundle["schema_version"] == 1 and bundle["status"] == "PASS_ENGINEERING_ONLY"
            and hex_digest(bundle["code_revision"], 40), "engineering bundle identity/status")
    require(file_set(root, ("bundle.json",)) == bundle["files"], "engineering bundle file/hash set")
    paths = bundle["paths"]
    require(set(paths) >= {"runner", "prepared", "build_receipt", "engineering", "adapter_build"}, "missing bundle paths")
    for name in paths.values():
        relative_name(name)
    binary = regular(root / paths["runner"])
    build_path = regular(root / paths["build_receipt"])
    build, adapter = read_json(build_path), read_json(root / paths["adapter_build"])
    revision, binary_sha, build_sha = bundle["code_revision"], sha_file(binary), sha_file(build_path)
    require(build["status"] == "BUILT_FIXED_REFERENCE_NO_ACOUSTIC_MEASUREMENT"
            and build["controls"]["commit"] == revision and 0 < build["elapsed_seconds"] <= 600
            and build["parallel_jobs"] == 2 and build["steps"] ==
            [{"phase": "setup", "exit_code": 0}, {"phase": "compile", "exit_code": 0}], "source build result/budget")
    require(build["shipping_authority"] is False and build["acoustic_measurement"] == build["training"] == "NOT_RUN",
            "source build scope")
    for name, digest in build["controls"]["files_sha256"].items():
        require(hashlib.sha256(git_bytes(revision, name)).hexdigest() == digest
                and sha_file(regular(ROOT / name)) == digest, "source build committed controls")
    require(adapter["status"] == "BUILT_ADAPTER" and adapter["code_revision"] == revision
            and adapter["binary_sha256"] == binary_sha and adapter["build_receipt_sha256"] == build_sha
            and adapter["runner_source_sha256"] == hashlib.sha256(git_bytes(revision, RUNNER_SOURCE)).hexdigest(),
            "adapter binary/source/library binding")
    require(adapter["orchestration_source_sha256"] == hashlib.sha256(git_bytes(revision, RUNTIME_SOURCE)).hexdigest(),
            "adapter orchestration source identity")
    require(adapter["command"] and adapter["compiler"] and adapter["runtime_libraries"], "adapter build evidence missing")
    for name, digest in adapter["runtime_libraries"].items():
        relative_name(name)
        require(name.startswith("bin/lib/") and Path(name).name.startswith(("libwebrtc-", "libabsl"))
                and bundle["files"].get(name) == digest, "bundled research library identity")
    research_hashes = set(adapter["runtime_libraries"].values())
    require(all(row["sha256"] in research_hashes for row in build["link"]["libraries"]), "built library not in portable bundle")
    # Use the admitted source reader; do not create a second materialization policy.
    import webrtc_aec3_source as source
    expected_controls = {REL + "webrtc_aec3_source.py", REL + "contracts.py"} | {
        ".github/research/frontend-evolution-v1/" + name
        for name in ("webrtc-aec3-source-lock.json", "webrtc-aec3-admission.json", "sources.json")}
    require(set(build["controls"]["files_sha256"]) == expected_controls, "source build control closure")
    require(sha_file(Path(source.__file__)) == build["controls"]["files_sha256"][REL + "webrtc_aec3_source.py"],
            "use the exact source reader implementation recorded by the build")
    verified = source.admitted(root / paths["prepared"])
    require(verified == build["source_receipt"] == build["post_source_verification"], "source preparation/build mismatch")
    original = engineering_record(root / paths["engineering"], revision, binary_sha, build_sha)
    require(normalized_runtime(original["runtime_identity"]) == normalized_runtime(adapter["runtime_identity"]),
            "original engineering and adapter host/library identity differ")
    research_runtime_binding(original["runtime_identity"], adapter)
    recorded_system = {name: row["sha256"] for name, row in adapter["system_libraries"].items()}
    original_system = {name: value for name, value in normalized_runtime(original["runtime_identity"])["libraries"].items()
                       if name not in {Path(p).name for p in adapter["runtime_libraries"]}}
    require(recorded_system == original_system, "adapter system-library receipt differs from original engineering")
    return bundle, build, adapter, original


def config_for(mode):
    apm = mode == "apm"
    return {"echo_canceller": {"enabled": True, "mobile_mode": False, "export_linear_aec_output": False,
                               "enforce_high_pass_filtering": False},
            "high_pass_filter": {"enabled": apm, "apply_in_full_band": True},
            "noise_suppression": {"enabled": apm, "level": "moderate", "analyze_linear_aec_output_when_available": False},
            "gain_controller1": {"enabled": False},
            "gain_controller2": {"enabled": apm, "input_volume_controller_enabled": False,
                "adaptive_digital": {"enabled": apm, "headroom_db": 5, "max_gain_db": 50, "initial_gain_db": 15,
                    "max_gain_change_db_per_second": 6, "max_output_noise_level_dbfs": -50}, "fixed_digital_gain_db": 0},
            "pre_amplifier_enabled": False, "capture_level_adjustment_enabled": False,
            "transient_suppression_enabled": False, "multi_channel_capture": True,
            "multi_channel_render": False, "capture_downmix_method": "average_channels",
            "maximum_internal_processing_rate": 48000}


def verify_metadata(meta, rows, mode, samples):
    frames = samples // 160
    required = {"schema_version": 1, "adapter": "webrtc-aec3-offline-v1", "status": "OK", "detail": "", "mode": mode,
                "sample_format": "S16LE", "sample_rate_hz": 16000, "frame_samples": 160,
                "mic_channels": 1, "render_channels": 1, "output_channels": 1, "channel_map": [0],
                "actual_processing_channels": 1, "actual_processing_sample_rate_hz": 16000,
                "input_frames": frames, "completed_frames": frames, "output_sample_frames": samples,
                "stream_delay_ms": 0, "adapter_lookahead_frames": 0, "padded_samples": 0, "tail_flush_samples": 0,
                "algorithmic_latency_samples": DELAYS[mode], "algorithmic_latency_ms": DELAYS[mode] / 16,
                "first_output_frame_input_samples_required": 160, "reset_before_frame": None,
                "call_order": "ProcessReverseStream,set_stream_delay_ms(0),ProcessStream",
                "adapter_normalization": False, "host_timing_only": True, "physical_target_measurement": False,
                "acoustic_acceptance": False, "promotion_authority": False,
                "requested_config": config_for(mode), "applied_config": config_for(mode)}
    def same(actual, expected):
        if isinstance(expected, dict):
            return type(actual) is dict and set(actual) == set(expected) and all(same(actual[k], v) for k, v in expected.items())
        if isinstance(expected, list):
            return type(actual) is list and len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
        if type(expected) in (int, float):
            return type(actual) in (int, float) and math.isfinite(actual) and actual == expected
        return type(actual) is type(expected) and actual == expected
    require(all(same(meta.get(k), v) for k, v in required.items()), "runner mode/geometry/config/latency metadata")
    require(len(rows) == frames and frames > 0, "runner frame trace cardinality")
    prior = 0
    for index, row in enumerate(rows):
        for key in ("frame_index", "input_sample_frames_available", "output_sample_frames_emitted",
                    "host_processing_begin_ns", "host_processing_completed_ns", "host_processing_duration_ns"):
            require(type(row.get(key)) is int and row[key] >= 0, "invalid frame integer/timing")
        require(row["frame_index"] == index and row["input_sample_frames_available"] == (index + 1) * 160
                and row["output_sample_frames_emitted"] == (index + 1) * 160
                and row["algorithmic_latency_samples"] == DELAYS[mode]
                and row["algorithmic_latency_ms"] == DELAYS[mode] / 16
                and row["reset_before_frame"] is False and row["host_timing_only"] is True,
                "frame sequence/latency/reset changed")
        begin, end = row["host_processing_begin_ns"], row["host_processing_completed_ns"]
        require(prior <= begin <= end and end - begin == row["host_processing_duration_ns"], "frame timing sequence")
        prior = end
    require(meta["first_output_frame_host_completion_ns"] == rows[0]["host_processing_completed_ns"], "first output timing mismatch")


def aligned_metrics(target, echo, actual, delay, plan):
    require(type(delay) is int and delay >= 0 and len(target) == len(echo) == len(actual), "aligned signal cardinality")
    rate, phases = plan["rate_hz"], {}
    windows = {}
    for name, (start, stop) in plan["metrics"]["near_phase_seconds"].items():
        lo, hi = int(start * rate), int(stop * rate)
        require(0 <= lo < hi and hi + delay <= len(actual), "aligned near window exceeds observed output")
        phases[name] = speech.si_sdr_span(target, actual, lo, lo + delay, hi - lo)
        windows[name] = {"target_start": lo, "output_start": lo + delay, "samples": hi - lo}
    start, stop = plan["metrics"]["final_far_seconds"]
    lo, hi = int(start * rate), int(stop * rate)
    require(0 <= lo < hi and hi + delay <= len(actual), "aligned far window exceeds observed output")
    # Preserve the canonical 100-ms mean-square aggregation AND its floor.
    # A whole-window unnormalized sum has the same finite ratio, but would
    # inflate a zero-residual result by 10*log10(1600) at this sample rate.
    block = rate // 10
    require(block > 0 and (hi - lo) % block == 0, "incomplete canonical far energy window")
    ee = sum(sum(v * v for v in echo[k:k + block]) / block for k in range(lo, hi, block))
    rr = sum(sum(v * v for v in actual[k + delay:k + delay + block]) / block for k in range(lo, hi, block))
    ratio = 10 * math.log10(ee / max(rr, 1e-30)) if ee / ((hi - lo) // block) > 1e-12 else None
    return {"declared_delay_samples": delay, "near_windows": windows,
            "phases_si_sdr_relative_to_quantized_bf_target_db": phases,
            "final_far_window": {"echo_start": lo, "output_start": lo + delay, "samples": hi - lo},
            "far_energy_window_samples": block, "final_far_ratio_db": ratio,
            "unobserved_tail": "EXCLUDED_NOT_ZERO_FILLED"}


def score_case(folder, case, plan):
    count = case["samples"]
    target = previous.f16(previous.i16_values(regular(folder / "target.s16"), count))
    echo = previous.f16(previous.i16_values(regular(folder / "echo.s16"), count))
    scores = {}
    for arm, spec in plan["arms"].items():
        name = {"archived_ap": "ap.s16", "archived_speex": "speex.s16"}.get(arm)
        path = folder / name if name else folder / spec["mode"] / "output.pcm"
        actual = previous.f16(previous.i16_values(regular(path), count))
        scores[arm] = {"raw": previous.metrics(target, echo, actual),
                       "aligned": aligned_metrics(target, echo, actual, spec["declared_delay_samples"], plan)}
    return {"case_id": case["case_id"], "pair": case["pair"], "event": case["event"], "samples": count,
            "data_role": ROLE, "metrics": scores}


def runner_command(binary, folder, mode):
    return [str(binary), "--mode", mode, "--mic-channels", "1", "--channel-map", "0",
            "--mic", str(folder / "mic.pcm"), "--render", str(folder / "render.pcm"),
            "--output", str(folder / mode / "output.pcm"), "--metadata", str(folder / mode / "metadata.json"),
            "--frame-times", str(folder / mode / "frames.jsonl")]


def run_process(command, folder, env, deadline):
    remaining = deadline - time.monotonic()
    require(remaining > 0, "300-second experiment budget exhausted")
    start = time.monotonic_ns()
    record = {"command": command, "started_monotonic_ns": start, "environment_overrides": {"LD_LIBRARY_PATH": env["LD_LIBRARY_PATH"]}}
    with (folder / "run.log").open("xb") as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
            record["returncode"] = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            record.update(returncode=process.returncode, error="WALL_BUDGET_EXHAUSTED")
        except OSError as error:
            record.update(returncode=None, error=str(error))
            raise
        finally:
            record["finished_monotonic_ns"] = time.monotonic_ns()
            write_json(folder / "command.json", record)
    require(record["returncode"] == 0, "reference process failed; evidence retained and no retry authorized")


def trace_rows(path, expected):
    raw = regular(path, expected * 2048).read_text()
    lines = raw.splitlines()
    require(len(lines) == expected and all(len(line) <= 2048 for line in lines), "frame trace length/line bound")
    rows = []
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate frame trace key")
            result[key] = value
        return result
    for line in lines:
        row = json.loads(line, object_pairs_hook=pairs,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite frame trace")))
        require(isinstance(row, dict), "frame trace object required")
        rows.append(row)
    return rows


def result_body(plan, sources, bundle, selected_engineering, runtime, cases, calls, elapsed, execution_root):
    return {"schema_version": 1, "experiment_id": plan["experiment_id"], "status": "EXECUTED_DESCRIPTIVE_REFERENCE",
            "decision": DECISION, "data_role": ROLE, "independent_confirmation": False,
            "acoustic_acceptance": False, "promotion_allowed": False, "training_allowed": False,
            "parameter_search_allowed": False, "target_timing_authority": False,
            "frozen_plan_sha256": PLAN_SHA256, "comparison_sources": sources,
            "bundle_code_revision": bundle["code_revision"], "engineering_receipt": selected_engineering,
            "runtime_identity": runtime, "execution_root": execution_root,
            "archived_baseline_source_revision": plan["predecessor"]["execution_source_revision"],
            "baseline_scope": "ORIGINAL_DISCLOSED_POST_BF_AP_MDF_AND_SPEEX_NOT_CURRENT_WHOLE_PIPELINE",
            "new_full_case_executions": len(calls), "extra_new_acoustic_retries": 0,
            "harness_elapsed_seconds": elapsed, "calls": calls, "cases": cases}


def check_result(report, expected, plan):
    require(report["status"] == "EXECUTED_DESCRIPTIVE_REFERENCE" and report["decision"] == DECISION
            and report["data_role"] == ROLE and all(report[k] is False for k in (
                "independent_confirmation", "acoustic_acceptance", "promotion_allowed", "training_allowed",
                "parameter_search_allowed", "target_timing_authority")), "result must remain descriptive with no promotion")
    identities = {case["case_id"] for case in plan["cases"]}
    require(len(report["cases"]) == 6 and {row["case_id"] for row in report["cases"]} == identities
            and all(row["data_role"] == ROLE for row in report["cases"]), "descriptive case count/role")
    require(len(report["calls"]) == 12 and {(row["case_id"], row["mode"]) for row in report["calls"]} ==
            {(identity, mode) for identity in identities for mode in MODES}, "exact twelve new executions required")
    require(encoded(report) == encoded(expected), "descriptive result/score/role/decision changed")


def run(bundle_dir, archive, output, engineering_receipt=None):
    started = time.monotonic()
    plan = frozen_plan()
    output, bundle_dir, archive = safe_path(output), safe_path(bundle_dir), safe_path(archive)
    require(not output.exists() and all(output != p and output not in p.parents and p not in output.parents
                                       for p in (bundle_dir, archive)), "fresh disjoint comparison output required")
    sources = current_sources()
    verify_bundle(bundle_dir)
    members = archive_members(archive, plan)
    output.mkdir(parents=True)
    shutil.copytree(bundle_dir, output / "bundle", symlinks=False)
    shutil.copyfile(archive, output / "predecessor.zip")
    shutil.copyfile(PLAN, output / "experiment.json")
    for name in sources["files"]:
        target = output / "measurement-source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    bundle, build, adapter, original = verify_bundle(output / "bundle")
    selected_name = "bundle/" + bundle["paths"]["engineering"]
    if engineering_receipt is not None:
        engineering_receipt = regular(engineering_receipt)
        require(engineering_receipt.name == "engineering.json", "host receipt must be engineering.json")
        file_set(engineering_receipt.parent)
        shutil.copytree(engineering_receipt.parent, output / "host-engineering")
        selected_name = "host-engineering/" + engineering_receipt.name
    selected = engineering_record(output / selected_name, bundle["code_revision"], adapter["binary_sha256"], adapter["build_receipt_sha256"])
    binary = output / "bundle" / bundle["paths"]["runner"]
    require(os.access(binary, os.X_OK), "portable runner is not executable")
    env = {"PATH": os.defpath, "LC_ALL": "C", "LD_LIBRARY_PATH": str(output / "bundle/bin/lib")}
    import webrtc_aec3_ci as ci
    require(sha_file(Path(ci.__file__)) == hashlib.sha256(git_bytes(bundle["code_revision"], REL + "webrtc_aec3_ci.py")).hexdigest(),
            "use the same host identity helper as the engineering bundle")
    runtime = ci.runtime_identity(binary, env)
    require(normalized_runtime(runtime) == normalized_runtime(selected["runtime_identity"]),
            "new host/runtime requires a fresh bounded engineering receipt; CI is not this host")
    research_runtime_binding(runtime, adapter, output / "bundle")
    calls, scores = [], []
    try:
        for case in plan["cases"]:
            folder = output / "cases" / case["case_id"]
            folder.mkdir(parents=True)
            for name in case["members"]:
                (folder / name).write_bytes(members["cases/" + case["case_id"] + "/" + name])
            mic, render = split_mic_render((folder / "input.s16").read_bytes(), case["samples"])
            (folder / "mic.pcm").write_bytes(mic)
            (folder / "render.pcm").write_bytes(render)
            for mode in MODES:
                destination = folder / mode
                destination.mkdir()
                command = runner_command(binary, folder, mode)
                calls.append({"case_id": case["case_id"], "mode": mode,
                              "command_receipt": (destination / "command.json").relative_to(output).as_posix()})
                run_process(command, destination, env, started + plan["budget"]["wall_seconds"])
                verify_metadata(read_json(destination / "metadata.json"),
                                trace_rows(destination / "frames.jsonl", case["samples"] // 160), mode, case["samples"])
            scores.append(score_case(folder, case, plan))
        require(time.monotonic() - started <= 300, "300-second experiment budget exhausted")
        require(normalized_runtime(ci.runtime_identity(binary, env)) == normalized_runtime(runtime), "runtime changed during comparison")
        result = result_body(plan, sources, bundle, selected_name, runtime, scores, calls,
                             time.monotonic() - started, str(output))
        write_json(output / "result.json", result)
        write_json(output / "manifest.json", {"schema_version": 1, "files": file_set(output)})
        require(time.monotonic() - started <= 300, "300-second experiment budget exhausted while sealing")
        return {"status": result["status"], "decision": DECISION, "cases": 6, "new_full_case_executions": 12,
                "independent_verification": "RUN_VERIFY_SUBCOMMAND", "acoustic_acceptance": False, "promotion_allowed": False}
    except Exception as error:
        if not (output / "failure.json").exists():
            write_json(output / "failure.json", {"status": "FAILED_OR_PARTIAL_NO_ACOUSTIC_ACCEPTANCE", "error": str(error),
                       "data_role": ROLE, "decision": DECISION, "calls": calls, "elapsed_seconds": time.monotonic() - started})
        raise


def verify(output):
    output = safe_path(output)
    require(not (output / "failure.json").exists(), "failed or partial experiment cannot be verified as successful")
    plan = frozen_plan()
    require(sha_file(regular(output / "experiment.json")) == PLAN_SHA256, "saved experiment identity")
    manifest = read_json(output / "manifest.json")
    require(manifest == {"schema_version": 1, "files": file_set(output, ("manifest.json",))}, "comparison file/hash set")
    report = read_json(output / "result.json")
    sources = report["comparison_sources"]
    verify_measurement_sources(output, sources)
    bundle, build, adapter, original = verify_bundle(output / "bundle")
    selected_name = relative_name(report["engineering_receipt"])
    require(selected_name == "bundle/" + bundle["paths"]["engineering"] or selected_name == "host-engineering/engineering.json",
            "unregistered engineering receipt location")
    selected = engineering_record(output / selected_name, bundle["code_revision"], adapter["binary_sha256"], adapter["build_receipt_sha256"])
    require(normalized_runtime(report["runtime_identity"]) == normalized_runtime(selected["runtime_identity"]), "comparison host/engineering mismatch")
    research_runtime_binding(report["runtime_identity"], adapter)
    members = archive_members(output / "predecessor.zip", plan)
    scores, calls = [], []
    original_root = Path(report["execution_root"])
    require(original_root.is_absolute(), "execution root identity")
    last_finished, first_started = 0, None
    expected_cases = {case["case_id"] for case in plan["cases"]}
    require({p.name for p in (output / "cases").iterdir()} == expected_cases, "case membership changed")
    for case in plan["cases"]:
        folder = output / "cases" / case["case_id"]
        require({p.name for p in folder.iterdir()} == set(case["members"]) | {"mic.pcm", "render.pcm", *MODES}, "case file membership")
        for name in case["members"]:
            require(regular(folder / name).read_bytes() == members["cases/" + case["case_id"] + "/" + name], "frozen case bytes changed")
        mic, render = split_mic_render((folder / "input.s16").read_bytes(), case["samples"])
        require((folder / "mic.pcm").read_bytes() == mic and (folder / "render.pcm").read_bytes() == render, "input role/split bytes changed")
        for mode in MODES:
            destination = folder / mode
            require({p.name for p in destination.iterdir()} == {"output.pcm", "metadata.json", "frames.jsonl", "run.log", "command.json"}, "runner evidence file membership")
            record = read_json(destination / "command.json")
            expected_command = runner_command(original_root / "bundle" / bundle["paths"]["runner"],
                                              original_root / "cases" / case["case_id"], mode)
            require(record["command"] == expected_command and record["returncode"] == 0
                    and record["environment_overrides"] == {"LD_LIBRARY_PATH": str(original_root / "bundle/bin/lib")},
                    "reference command/input/exit identity")
            start, finish = record["started_monotonic_ns"], record["finished_monotonic_ns"]
            require(type(start) is int and type(finish) is int and last_finished <= start <= finish, "call timing/order")
            first_started = start if first_started is None else first_started
            last_finished = finish
            verify_metadata(read_json(destination / "metadata.json"),
                            trace_rows(destination / "frames.jsonl", case["samples"] // 160), mode, case["samples"])
            calls.append({"case_id": case["case_id"], "mode": mode,
                          "command_receipt": (destination / "command.json").relative_to(output).as_posix()})
        scores.append(score_case(folder, case, plan))
    elapsed = report["harness_elapsed_seconds"]
    require(type(elapsed) in (float, int) and math.isfinite(elapsed) and 0 < elapsed <= 300
            and (last_finished - first_started) / 1e9 <= elapsed, "comparison wall budget")
    expected = result_body(plan, sources, bundle, selected_name, report["runtime_identity"], scores, calls, elapsed, str(original_root))
    check_result(report, expected, plan)
    return {"status": "VERIFIED_DESCRIPTIVE_REFERENCE", "decision": DECISION, "cases": 6,
            "new_full_case_executions": 12, "acoustic_acceptance": False, "promotion_allowed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="command", required=True)
    execute = modes.add_parser("run")
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--archive", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--engineering-receipt", type=Path)
    check = modes.add_parser("verify")
    check.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (verify(args.output) if args.command == "verify" else
                  run(args.bundle, args.archive, args.output, args.engineering_receipt))
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, ImportError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print("webrtc-aec3-reference: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
