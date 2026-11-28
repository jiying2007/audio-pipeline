#!/usr/bin/env python3
"""Six preregistered disclosed AEC3 observations; no search or promotion.

Only ``run`` invokes the admitted runner. ``verify`` authenticates saved bytes
and recomputes the declared Python metrics, with no SDK/codec/compiler/ldd.
The previous experiment and all its output bytes remain separate evidence.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import webrtc_aec3_reference as reference
import webrtc_aec3_linear_tap_ci as ci
import test_webrtc_aec3_linear_tap_adapter as fixture
from contracts import ROOT, hex_digest, require

REL = "tests/validation/frontend_evolution/"
PLAN = ROOT / ci.PLAN
PLAN_SHA256 = "b144f634e11df08569215903e3832f91dbeee5c3c609b19bcffba60de0cf6e6f"
EXPERIMENT = "FE04-WEBRTC-AEC3-LINEAR-TAP-V1"
ROLE = "DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT"
STATUS = "EXECUTED_DISCLOSED_LINEAR_OBSERVATION"
DECISION = "DIAGNOSTIC_DIRECTION_ONLY_NO_PROMOTION"
EPSILON = 1.0e-12
SAMPLES, RATE, HOP = 256000, 16000, 160
DELAYS = {"linear": 64, "final": 128}
FAILURE_NAMES = ("failure.json", "failed-result.json", "result-before-failure.json",
                 "manifest-before-failure.json")
OBSERVATION_FILES = {"output.pcm", "linear.f32", "metadata.json", "frames.jsonl",
                     "invocation-start.json", "command.json", "stdout.log", "stderr.log"}
TRACE_KEYS = {"frame_index", "input_sample_frames_available", "output_sample_frames_emitted",
              "host_processing_begin_ns", "host_processing_completed_ns", "host_processing_duration_ns",
              "algorithmic_latency_samples", "algorithmic_latency_ms", "reset_before_frame",
              "aec3_export_mode", "linear_output_sample_frames_emitted", "linear_signal_delay_samples",
              "linear_getter_completed_ns", "host_timing_only"}
ARCHIVED_FILES = {
    "manifest.json": "manifest.json", "result.json": "result.json", "experiment.json": "experiment.json",
    "bundle.json": "bundle/bundle.json", "runner-build.json": "bundle/build/runner-build.json",
    "build-receipt.json": "bundle/build/build-receipt.json",
    "source-receipt.json": "bundle/prepared/source-receipt.json",
}
CONTROL_FILES = tuple(sorted(set(reference.METRIC_SOURCES) | set(ci.CONTROL_FILES) | {
    REL + "webrtc_aec3_source.py", ".github/research/frontend-evolution-v1/webrtc-aec3-source-lock.json",
    ".github/research/frontend-evolution-v1/webrtc-aec3-admission.json",
    ".github/research/frontend-evolution-v1/sources.json",
}))
regular, safe_path, sha_file = reference.regular, reference.safe_path, reference.sha_file
read_json, write_json, encoded = reference.read_json, reference.write_json, reference.encoded


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def remaining(deadline):
    value = deadline - time.monotonic()
    require(value > 0, "frozen 300-second stage budget exhausted")
    return value


@contextmanager
def bounded_stage(deadline):
    """One Linux wall deadline covers hashing, copying, calls, scoring and seal."""
    seconds = remaining(deadline)
    require(finite(seconds) and 0 < seconds <= 300, "invalid remaining stage budget")
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "existing wall timer is not replaced")
    handler = signal.getsignal(signal.SIGALRM)
    def expired(signum, frame):
        raise TimeoutError("frozen 300-second stage budget exhausted")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield deadline
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, handler)


def frozen_plan():
    require(sha_file(regular(PLAN, 65536)) == PLAN_SHA256, "new frozen plan bytes changed")
    plan = read_json(PLAN)
    ids = ["p%d-ula4-70-fir33-%s" % (pair, event) for pair in (0, 1) for event in ("none", "steer", "path")]
    require(plan["experiment_id"] == EXPERIMENT and plan["data_role"] == ROLE
            and plan["status"] == "PREREGISTERED_NOT_EXECUTED"
            and [row["case_id"] for row in plan["cases"]] == ids
            and all(row["samples"] == SAMPLES for row in plan["cases"]), "fixed six-case disclosed source contract")
    require(all(plan[key] is False for key in ("independent_confirmation", "training_allowed",
            "parameter_search_allowed", "promotion_allowed", "target_timing_authority")), "data role cannot be promoted")
    require(plan["budget"]["wall_seconds"] == plan["budget"]["independent_readback_wall_seconds"] == 300
            and plan["budget"]["per_case_wall_seconds"] == 30
            and plan["budget"]["new_full_case_executions"] == 6
            and plan["budget"]["extra_new_acoustic_retries"] == 0
            and plan["budget"]["processed_frames"] == 9600
            and plan["budget"]["total_capture_audio_seconds"] == 96, "fixed execution budget changed")
    require(plan["observation"]["export_mode"] == "factory-on"
            and plan["observation"]["linear_path"] == "linear.f32"
            and plan["observation"]["final_path"] == "output.pcm"
            and plan["timing_contract"]["common_target_span"] == [0, SAMPLES - 128]
            and {name: value["declared_delay_samples"] for name, value in plan["arms"].items()} == DELAYS,
            "fixed tap/final units or source-derived offsets changed")
    require(plan["metrics"]["disposition"] == DECISION
            and plan["metrics"]["float_tap_must_not_be_quantized_to_s16"] is True,
            "metric contract changed")
    require(plan["primary"]["correlated_output_windows_must_be_byte_equal"] is True
            and plan["primary"]["on_consistency_failure"] == "STOP_METHOD_PRESERVE_OUTPUTS",
            "correlated observation consistency contract changed")
    return plan


def code_identity(revision):
    require(hex_digest(revision, 40), "exact public measurement source revision required")
    command = ["git", "-C", str(ROOT), "-c", "core.fsmonitor=false", "-c", "safe.directory=" + str(ROOT.resolve())]
    require(subprocess.check_output(command + ["rev-parse", "HEAD"], timeout=10).decode().strip() == revision,
            "execute/read from the exact frozen source checkout")
    records = {}
    for name in CONTROL_FILES:
        data = regular(ROOT / name).read_bytes()
        require(data == ci.git_bytes(revision, name), "uncommitted or wrong measurement source: " + name)
        records[name] = hashlib.sha256(data).hexdigest()
    # No late-loaded first-party implementation may silently escape the list.
    loaded = set()
    for module in tuple(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and Path(path).suffix == ".py":
            try:
                loaded.add(Path(path).resolve().relative_to(ROOT.resolve()).as_posix())
            except ValueError:
                pass
    require(loaded <= set(CONTROL_FILES), "unbound first-party module: " + repr(sorted(loaded - set(CONTROL_FILES))))
    return {"code_revision": revision, "files_sha256": records}


def copy_file(source, target):
    regular(source)
    require(not target.exists(), "no evidence file replacement")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    require(sha_file(regular(target)) == sha_file(source), "copy changed source bytes")


def copy_tree(source, target):
    original = reference.file_set(source)
    require(not target.exists(), "fresh evidence subtree required")
    shutil.copytree(source, target, symlinks=False)
    require(reference.file_set(target) == original, "copied evidence subtree differs")


def locked_file(path, spec):
    path = regular(path, spec["bytes"])
    require(path.stat().st_size == spec["bytes"] and sha_file(path) == spec["sha256"],
            "frozen byte lock differs: " + path.name)
    return path.read_bytes()


def original_metadata(folder, plan, saved=False):
    """Check original identities, without rerunning the previous matrix/reader."""
    paths = {key: folder / (key if saved else value) for key, value in ARCHIVED_FILES.items()}
    wanted = plan["archived_reference"]
    for name, key in (("manifest.json", "manifest_sha256"), ("result.json", "result_sha256"),
                      ("experiment.json", "plan_sha256")):
        require(sha_file(regular(paths[name])) == wanted[key], "archived reference metadata identity: " + name)
    manifest, result = read_json(paths["manifest.json"]), read_json(paths["result.json"])
    require(manifest["schema_version"] == 1 and result["data_role"] == ROLE
            and result["bundle_code_revision"] == wanted["execution_source_revision"]
            and result["comparison_sources"]["code_revision"] == wanted["execution_source_revision"],
            "archived source/role differs")
    for name, original in ARCHIVED_FILES.items():
        if name != "manifest.json":
            require(manifest["files"][original] == sha_file(paths[name]), "archived metadata manifest binding")
    adapter, bundle = read_json(paths["runner-build.json"]), read_json(paths["bundle.json"])
    require(adapter["code_revision"] == bundle["code_revision"] == wanted["execution_source_revision"]
            and adapter["binary_sha256"] == bundle["files"]["bin/webrtc-aec3-runner"]
            and adapter["build_receipt_sha256"] == sha_file(paths["build-receipt.json"]),
            "archived adapter/binary/build identity")
    return {"execution_source_revision": wanted["execution_source_revision"],
            "manifest_sha256": wanted["manifest_sha256"], "result_sha256": wanted["result_sha256"],
            "binary_sha256": adapter["binary_sha256"], "runner_source_sha256": adapter["runner_source_sha256"],
            "original_new_calls": 12, "new_execution_in_this_study": False}, manifest


def validate_case_sources(folder, case, archive_members, old_manifest):
    for name, spec in case["members"].items():
        value = locked_file(folder / name, spec)
        require(value == archive_members["cases/" + case["case_id"] + "/" + name], "source ZIP/member differs")
        require(old_manifest["files"]["cases/" + case["case_id"] + "/" + name] == spec["sha256"],
                "original manifest/member binding")
    mic, render = reference.split_mic_render((folder / "input.s16").read_bytes(), case["samples"])
    for name, value in (("mic.pcm", mic), ("render.pcm", render)):
        require(locked_file(folder / name, case["prepared_inputs"][name]) == value,
                "prepared mic/render is not the exact original sample split")
        require(old_manifest["files"]["cases/" + case["case_id"] + "/" + name] == case["prepared_inputs"][name]["sha256"],
                "original manifest/prepared input binding")
    locked_file(folder / "archived-final.pcm", case["archived_aec3_final"])
    require(old_manifest["files"]["cases/" + case["case_id"] + "/aec3/output.pcm"] == case["archived_aec3_final"]["sha256"],
            "original manifest/final binding")


def primary_input_identity(root, plan):
    ids = [plan["primary"]["case_id"]] + plan["primary"]["correlated_consistency_cases"]
    # The complete capture frame that contains final's last required sample is
    # included. Hashes alone describe equality; no acoustic score is used here.
    start, stop = plan["primary"]["target_window_samples"]
    consumed = ((stop + max(DELAYS.values()) + HOP - 1) // HOP) * HOP
    rows = []
    for case_id in ids:
        folder = root / "cases" / case_id
        prefixes = {name: hashlib.sha256(regular(folder / name).read_bytes()[:2 * consumed]).hexdigest()
                    for name in ("mic.pcm", "render.pcm", "target.s16", "echo.s16")}
        window = {name: hashlib.sha256(regular(folder / name).read_bytes()[2 * start:2 * stop]).hexdigest()
                  for name in ("mic.pcm", "render.pcm", "target.s16", "echo.s16")}
        rows.append({"case_id": case_id, "required_capture_prefix_samples": consumed,
                     "prefix_sha256": prefixes, "window_sha256": window})
    require(all(row["prefix_sha256"] == rows[0]["prefix_sha256"] and row["window_sha256"] == rows[0]["window_sha256"]
                for row in rows), "preregistered primary input-prefix identity changed")
    return {"unique_primary_input_conditions": 1, "independent_replicates": False, "rows": rows}


def runner_command(binary, folder):
    observation = folder / "observation"
    return [str(binary), "--mode", "aec3", "--mic-channels", "1", "--channel-map", "0",
            "--mic", str(folder / "mic.pcm"), "--render", str(folder / "render.pcm"),
            "--output", str(observation / "output.pcm"), "--metadata", str(observation / "metadata.json"),
            "--frame-times", str(observation / "frames.jsonl"), "--aec3-export-mode", "factory-on",
            "--linear-output", str(observation / "linear.f32")]


def run_process(command, folder, environment, deadline):
    timeout = min(30.0, remaining(deadline))
    started = time.monotonic_ns()
    begin = {"command": command, "environment": environment, "started_monotonic_ns": started,
             "per_case_timeout_seconds": timeout, "retry_index": 0}
    write_json(folder / "invocation-start.json", begin)
    process = None
    record = dict(begin, returncode=None)
    with (folder / "stdout.log").open("xb") as stdout, (folder / "stderr.log").open("xb") as stderr:
        try:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=environment, start_new_session=True)
            record["returncode"] = process.wait(timeout=timeout)
        except BaseException as error:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            if process is not None:
                record["returncode"] = process.returncode
            record["failure"] = type(error).__name__ + ": " + str(error)
            raise
        finally:
            record["finished_monotonic_ns"] = time.monotonic_ns()
            record["elapsed_seconds"] = (record["finished_monotonic_ns"] - started) / 1e9
            write_json(folder / "command.json", record)
    require(type(record["returncode"]) is int and record["returncode"] == 0
            and record["elapsed_seconds"] <= timeout, "runner failed or exceeded its fixed case budget; no retry")
    return record


def observation_outputs(folder, case):
    observed = folder / "observation"
    require({p.name for p in observed.iterdir()} == OBSERVATION_FILES
            and all(p.is_file() for p in observed.iterdir()), "unexpected/missing observation files")
    final = regular(observed / "output.pcm", 2 * case["samples"]).read_bytes()
    require(final == locked_file(folder / "archived-final.pcm", case["archived_aec3_final"]),
            "NEW_FINAL_DIFFERS_FROM_ARCHIVED_FINAL: stop; no replacement baseline or tolerance")
    require(len(final) == 2 * case["samples"], "final cardinality")
    raw = regular(observed / "frames.jsonl", (case["samples"] // HOP) * 4096).read_bytes()
    require(raw.endswith(b"\n"), "truncated frame trace")
    rows = reference.trace_rows(observed / "frames.jsonl", case["samples"] // HOP)
    require(all(set(row) == TRACE_KEYS for row in rows), "frame trace schema changed")
    for row in rows:
        for key in ("algorithmic_latency_samples", "linear_signal_delay_samples", "linear_getter_completed_ns",
                    "linear_output_sample_frames_emitted"):
            require(type(row[key]) is int and row[key] >= 0, "frame integer type changed")
    meta = read_json(observed / "metadata.json")  # duplicate/nonfinite JSON keys rejected first
    expected_config = reference.config_for("aec3")
    expected_config["echo_canceller"]["export_linear_aec_output"] = True
    require(meta["schema_version"] == 1 and meta["adapter"] == "webrtc-aec3-offline-v1"
            and meta["detail"] == "" and meta["requested_config"] == meta["applied_config"] == expected_config
            and meta["call_order"] == "ProcessReverseStream,set_stream_delay_ms(0),ProcessStream,GetLinearAecOutput",
            "source-default AEC3 config or process/getter order changed")
    paths = {"--mic": folder / "mic.pcm", "--render": folder / "render.pcm",
             "--output": observed / "output.pcm", "--metadata": observed / "metadata.json",
             "--frame-times": observed / "frames.jsonl", "--linear-output": observed / "linear.f32"}
    regular(paths["--linear-output"], 4 * case["samples"])
    interpreted = fixture.inspect_outputs(paths, "factory-on", regular(paths["--mic"]).read_bytes(), None)
    require(interpreted["metadata"] == meta and interpreted["trace"] == rows, "strict metadata interpretation differs")
    return interpreted


def s16_normalized(data, count):
    require(len(data) == 2 * count, "complete S16 source required")
    return [value[0] / 32768.0 for value in struct.iter_unpack("<h", data)]


def span_metrics(target, actual, start, stop, delay):
    require(type(start) is int and type(stop) is int and type(delay) is int and delay >= 0
            and 0 <= start < stop <= len(target) and stop + delay <= len(actual), "fixed scoring span outside observed signal")
    reference_energy = cross = estimate_energy = squared_error = 0.0
    identical = True
    for index in range(start, stop):
        ref, est = float(target[index]), float(actual[index + delay])
        require(math.isfinite(ref) and math.isfinite(est), "nonfinite scoring sample")
        reference_energy += ref * ref
        cross += ref * est
        estimate_energy += est * est
        squared_error += (ref - est) ** 2
        identical = identical and ref == est  # never int(float), never requantize tap
    alpha = cross / reference_energy if reference_energy > EPSILON else None
    projected = None
    if alpha is not None:
        projected = 0.0
        for index in range(start, stop):
            projected_value = alpha * float(target[index])
            projected += projected_value * projected_value
    identifiable = projected is not None and finite(projected) and projected > EPSILON
    value = reference.speech.si_sdr_span(target, actual, start, start + delay, stop - start)
    require(value is None or finite(value), "nonfinite canonical score")
    return {"target_start": start, "output_start": start + delay, "samples": stop - start,
            "si_sdr_db": value, "normalized_mse": squared_error / reference_energy if reference_energy > EPSILON else None,
            "exact_float_identity": identical, "reference_energy": reference_energy,
            "output_energy": estimate_energy, "estimate_energy": estimate_energy, "projected_target_energy": projected,
            "projection_scale": alpha, "projection_identifiable": identifiable,
            "degenerate_projection": not identifiable, "canonical_epsilon": EPSILON}


def amplitude(values, endpoint_high):
    require(values and all(math.isfinite(x) for x in values), "finite complete amplitude input required")
    return {"samples": len(values), "minimum": min(values), "maximum": max(values),
            "peak": max(abs(x) for x in values), "rms": math.sqrt(sum(x * x for x in values) / len(values)),
            "negative_endpoint_count": sum(x == -1.0 for x in values),
            "positive_endpoint_count": sum(x == endpoint_high for x in values),
            "negative_endpoint": -1.0, "positive_endpoint": endpoint_high,
            "all_finite": True, "endpoint_counts_are_proven_clipping_events": False}


def far_metrics(echo, actual, delay, plan):
    lo, hi = plan["metrics"]["final_far_samples"]
    block = plan["metrics"]["far_block_samples"]
    require((hi - lo) // block == 19 and (hi - lo) % block == 0
            and hi + delay <= len(actual) and hi <= len(echo), "fixed far block span")
    rows = []
    for start in range(lo, hi, block):
        ee = sum(x * x for x in echo[start:start + block]) / block
        rr = sum(x * x for x in actual[start + delay:start + delay + block]) / block
        rows.append({"echo_start": start, "output_start": start + delay, "samples": block,
                     "echo_mean_square": ee, "output_mean_square": rr,
                     "echo_to_output_ratio_db": 10 * math.log10(ee / max(rr, 1e-30)) if ee > EPSILON else None})
    ee, rr = sum(row["echo_mean_square"] for row in rows), sum(row["output_mean_square"] for row in rows)
    return {"blocks": rows, "aggregate_ratio_db": 10 * math.log10(ee / max(rr, 1e-30)) if ee / len(rows) > EPSILON else None,
            "interpretation": "FAR_ONLY_ECHO_TO_OUTPUT_ENERGY_RATIO_NOT_DOUBLE_TALK_ERLE"}


def score_case(folder, case, plan, outputs):
    count = case["samples"]
    target = s16_normalized(regular(folder / "target.s16").read_bytes(), count)
    echo = s16_normalized(regular(folder / "echo.s16").read_bytes(), count)
    views = {"linear": fixture.linear_samples(outputs["linear"]), "final": s16_normalized(outputs["final"], count)}
    require(all(len(values) == count for values in views.values()), "two complete observation views required")
    metrics = {}
    for name, values in views.items():
        delay = DELAYS[name]
        start, stop = plan["timing_contract"]["common_target_span"]
        metrics[name] = {"declared_delay_samples": delay,
                         "common_aligned": span_metrics(target, values, start, stop, delay),
                         "near": {phase: span_metrics(target, values, a, b, delay)
                                  for phase, (a, b) in plan["metrics"]["near_phase_samples"].items()},
                         "far": far_metrics(echo, values, delay, plan),
                         "raw_amplitude": amplitude(values, 1.0 if name == "linear" else 32767 / 32768.0),
                         "unobserved_tail": "EXCLUDED_NOT_ZERO_FILLED"}
    delta = {}
    for phase in plan["metrics"]["near_phase_samples"]:
        tap, final = metrics["linear"]["near"][phase], metrics["final"]["near"][phase]
        delta[phase] = {key: tap[key] - final[key] if tap[key] is not None and final[key] is not None else None
                        for key in ("si_sdr_db", "normalized_mse")}
    return {"case_id": case["case_id"], "pair": case["pair"], "event": case["event"], "samples": count,
            "data_role": ROLE, "final_equals_archived_bytes": True,
            "final_sha256": hashlib.sha256(outputs["final"]).hexdigest(),
            "linear_sha256": hashlib.sha256(outputs["linear"]).hexdigest(),
            "metrics": metrics, "linear_minus_final_near": delta}


def primary_decision(linear, final):
    keys = ("si_sdr_db", "normalized_mse")
    if not all(finite(row[key]) for row in (linear, final) for key in keys):
        return "NOT_IDENTIFIABLE"
    if not all(row["projection_identifiable"] is True for row in (linear, final)):
        return "NOT_IDENTIFIABLE"
    delta = linear["si_sdr_db"] - final["si_sdr_db"]
    if delta > 0 and linear["normalized_mse"] < final["normalized_mse"]:
        return "SUPPORTED_IN_DISCLOSED_WINDOW"
    if delta <= 0 and linear["normalized_mse"] >= final["normalized_mse"]:
        return "NOT_SUPPORTED_IN_DISCLOSED_WINDOW"
    return "INCONCLUSIVE_MIXED_INDICATORS"


def primary_summary(cases, plan, root):
    by_id = {row["case_id"]: row for row in cases}
    phase = plan["primary"]["phase"]
    chosen = by_id[plan["primary"]["case_id"]]
    views = {name: chosen["metrics"][name]["near"][phase] for name in DELAYS}
    start, stop = plan["primary"]["target_window_samples"]
    consistency = []
    first = None
    for identity in [plan["primary"]["case_id"]] + plan["primary"]["correlated_consistency_cases"]:
        folder = root / "cases" / identity / "observation"
        hashes = {}
        for name, filename, size in (("linear", "linear.f32", 4), ("final", "output.pcm", 2)):
            data = regular(folder / filename).read_bytes()
            hashes[name] = hashlib.sha256(data[(start + DELAYS[name]) * size:(stop + DELAYS[name]) * size]).hexdigest()
        first = first or hashes
        consistency.append({"case_id": identity, "aligned_output_window_sha256": hashes,
                            "same_aligned_output_bytes_as_primary": hashes == first,
                            "metrics": {name: by_id[identity]["metrics"][name]["near"][phase] for name in DELAYS}})
    require(all(row["same_aligned_output_bytes_as_primary"] for row in consistency),
            "CORRELATED_PREFIX_OBSERVATION_MISMATCH: stop method; preserve all outputs")
    return {"case_id": chosen["case_id"], "phase": phase, "target_window_samples": [start, stop],
            "decision": primary_decision(views["linear"], views["final"]), "views": views,
            "linear_minus_final": chosen["linear_minus_final_near"][phase],
            "effective_unique_conditions": 1, "statistical_significance_claim": False,
            "promotion_allowed": False, "correlated_consistency_checks": consistency}


def validate_call(record, begin, command, environment):
    require(set(begin) == {"command", "environment", "started_monotonic_ns", "per_case_timeout_seconds", "retry_index"}
            and set(record) == set(begin) | {"returncode", "finished_monotonic_ns", "elapsed_seconds"},
            "call receipt schema/failure")
    require(all(record[key] == value for key, value in begin.items())
            and record["command"] == command and record["environment"] == environment
            and type(record["returncode"]) is int and record["returncode"] == 0
            and type(record["retry_index"]) is int and record["retry_index"] == 0, "exact invocation/clean environment changed")
    start, stop = record["started_monotonic_ns"], record["finished_monotonic_ns"]
    require(type(start) is int and type(stop) is int and 0 < start < stop
            and finite(record["per_case_timeout_seconds"]) and 0 < record["per_case_timeout_seconds"] <= 30
            and finite(record["elapsed_seconds"]) and 0 < record["elapsed_seconds"] <= record["per_case_timeout_seconds"]
            and record["elapsed_seconds"] == (stop - start) / 1e9, "call timing/budget changed")


def execution_paths(report, bundle):
    raw = report["execution_root"]
    require(isinstance(raw, str) and Path(raw).is_absolute() and str(Path(os.path.abspath(raw))) == raw,
            "original execution root must be a canonical absolute path")
    root = Path(raw)
    binary = root / "bundle" / bundle["manifest"]["paths"]["runner"]
    require(report["processor_execution_path"] == str(binary), "command binary not bound to original bundle path")
    return root, binary


def report_body(plan, sources, archived, bundle, engineering_name, engineering, runtime_before,
                runtime_after, execution_root, calls, cases, input_identity, wall, root):
    return {"schema_version": 1, "experiment_id": EXPERIMENT, "status": STATUS, "decision": DECISION,
            "data_role": ROLE, "independent_confirmation": False, "training_allowed": False,
            "parameter_search_allowed": False, "promotion_allowed": False, "target_timing_authority": False,
            "acoustic_acceptance": False, "source_revision": sources["code_revision"], "measurement_sources": sources,
            "plan_sha256": PLAN_SHA256, "archived_reference": archived,
            "bundle_code_revision": bundle["manifest"]["code_revision"],
            "binary_sha256": bundle["reference"][2]["binary_sha256"],
            "engineering_receipt": engineering_name, "engineering_receipt_sha256": sha_file(root / engineering_name),
            "engineering_fixture_id": engineering["fixture_id"],
            "runtime_identity_before": runtime_before, "runtime_identity_after": runtime_after,
            "execution_root": str(execution_root),
            "processor_execution_path": str(execution_root / "bundle" / bundle["manifest"]["paths"]["runner"]),
            "new_full_case_executions": 6, "processed_frames": 9600, "capture_audio_seconds": 96,
            "new_views_per_call": 2, "extra_new_acoustic_retries": 0, "parameter_searches": 0,
            "speech_target_lag_searches": 0, "local_compilations": 0, "decoder_calls": 0,
            "elapsed_before_seal_seconds": wall, "stage_hard_wall_seconds": 300,
            "calls": calls, "cases": cases, "primary_input_identity": input_identity,
            "primary": primary_summary(cases, plan, root), "limitations": plan["limits"]}


def fail_output(output, error):
    if not output.exists():
        return
    for name, preserved in (("result.json", "result-before-failure.json"), ("manifest.json", "manifest-before-failure.json")):
        if (output / name).exists():
            require(not (output / preserved).exists(), "failure preservation destination already exists")
            (output / name).rename(output / preserved)
    marker = {"schema_version": 1, "experiment_id": EXPERIMENT, "status": "FAIL_PRESERVED_PREFIX",
              "error": type(error).__name__ + ": " + str(error), "retry_allowed": False,
              "promotion_allowed": False, "previous_bytes_preserved": True}
    if not (output / "failure.json").exists():
        write_json(output / "failure.json", marker)


def reject_failure(output):
    require(not any((output / name).exists() for name in FAILURE_NAMES), "failed prefix is not successful evidence")


def retained_inputs(output, plan):
    require(sha_file(regular(output / "experiment.json")) == PLAN_SHA256, "retained new plan differs")
    archived, old_manifest = original_metadata(output / "archived-reference", plan, saved=True)
    members = reference.archive_members(output / "predecessor.zip", plan)
    require({p.name for p in (output / "data-preflight").iterdir()} == set(plan["pre_execution_byte_only_receipts"]),
            "preflight receipt set")
    for name, spec in plan["pre_execution_byte_only_receipts"].items():
        locked_file(output / "data-preflight" / name, spec)
    require({p.name for p in (output / "archived-reference").iterdir()} == set(ARCHIVED_FILES), "archived metadata set")
    expected = {case["case_id"] for case in plan["cases"]}
    require({p.name for p in (output / "cases").iterdir()} == expected, "exact six cases required")
    for case in plan["cases"]:
        folder = output / "cases" / case["case_id"]
        require({p.name for p in folder.iterdir()} == set(case["members"]) | set(case["prepared_inputs"]) |
                {"archived-final.pcm", "observation"}, "case member/call set changed")
        validate_case_sources(folder, case, members, old_manifest)
    return archived


def run(bundle_dir, original_comparison, preflight, output, engineering_receipt=None):
    started = time.monotonic()
    output, bundle_dir, original_comparison, preflight = map(safe_path, (output, bundle_dir, original_comparison, preflight))
    inputs = [bundle_dir, original_comparison, preflight, ROOT]
    if engineering_receipt is not None:
        engineering_receipt = regular(engineering_receipt)
        require(engineering_receipt.name == "engineering.json" and engineering_receipt.parent.name == "engineering",
                "host receipt must be HOST/engineering/engineering.json")
        inputs.append(engineering_receipt.parent.parent)
    require(not output.exists() and all(output != item and output not in item.parents and item not in output.parents for item in inputs),
            "fresh disjoint output outside all retained sources required")
    output.mkdir(parents=True)
    try:
        with bounded_stage(started + 300) as deadline:
            plan = frozen_plan()
            verified = ci.verify_bundle(bundle_dir)
            sources = code_identity(verified["manifest"]["code_revision"])
            original_metadata(original_comparison, plan)
            reference.archive_members(original_comparison / "predecessor.zip", plan)
            copy_tree(bundle_dir, output / "bundle")
            copy_file(PLAN, output / "experiment.json")
            copy_file(original_comparison / "predecessor.zip", output / "predecessor.zip")
            for name, original in ARCHIVED_FILES.items():
                copy_file(original_comparison / original, output / "archived-reference" / name)
            for name, spec in plan["pre_execution_byte_only_receipts"].items():
                locked_file(preflight / name, spec)
                copy_file(preflight / name, output / "data-preflight" / name)
            for name in CONTROL_FILES:
                copy_file(ROOT / name, output / "measurement-source" / name)
            for case in plan["cases"]:
                before, after = original_comparison / "cases" / case["case_id"], output / "cases" / case["case_id"]
                for name in tuple(case["members"]) + tuple(case["prepared_inputs"]):
                    copy_file(before / name, after / name)
                copy_file(before / "aec3/output.pcm", after / "archived-final.pcm")
                (after / "observation").mkdir()
            archived = retained_inputs(output, plan)
            input_identity = primary_input_identity(output, plan)
            engineering_name = "bundle/" + verified["manifest"]["paths"]["engineering"]
            if engineering_receipt is not None:
                copy_tree(engineering_receipt.parent.parent, output / "host-engineering")
                engineering_name = "host-engineering/engineering/engineering.json"
            verified = ci.verify_bundle(output / "bundle")
            selected = ci.require_host_engineering(output / "bundle", output / engineering_name)
            binary = verified["paths"]["runner"]
            require(os.access(binary, os.X_OK), "sealed runner executable permission missing")
            environment = ci.execution_environment(output / "bundle")
            runtime = ci.previous.runtime_identity(binary, environment)
            require(reference.normalized_runtime(runtime) == reference.normalized_runtime(selected["runtime_identity"]),
                    "selected host engineering differs from actual runner libraries")
            reference.research_runtime_binding(runtime, verified["reference"][2], output / "bundle/reference")
            calls, scores = [], []
            for case in plan["cases"]:
                remaining(deadline)
                folder = output / "cases" / case["case_id"]
                command = runner_command(binary, folder)
                record = run_process(command, folder / "observation", environment, deadline)
                validate_call(record, read_json(folder / "observation/invocation-start.json"), command, environment)
                observed = observation_outputs(folder, case)  # final equality BEFORE the next speech call
                calls.append({"case_id": case["case_id"], "command_receipt": "cases/" + case["case_id"] + "/observation/command.json"})
                scores.append(score_case(folder, case, plan, observed))
            runtime_after = ci.previous.runtime_identity(binary, environment)
            require(runtime_after == runtime, "actual runtime changed during the fixed six calls")
            require(code_identity(sources["code_revision"]) == sources, "measurement source changed during execution")
            ci.verify_bundle(output / "bundle")
            ci.verify_engineering(output / "bundle", output / engineering_name)
            require(retained_inputs(output, plan) == archived, "retained source bytes changed")
            wall = time.monotonic() - started
            result = report_body(plan, sources, archived, verified, engineering_name, selected, runtime, runtime_after,
                                 output, calls, scores, input_identity, wall, output)
            write_json(output / "result.json", result)
            write_json(output / "manifest.json", {"schema_version": 1, "files": reference.file_set(output)})
            remaining(deadline)
            receipt = {"status": STATUS, "experiment_id": EXPERIMENT, "result_sha256": sha_file(output / "result.json"),
                       "manifest_sha256": sha_file(output / "manifest.json"), "output": str(output),
                       "new_full_case_executions": 6, "wall_seconds": time.monotonic() - started,
                       "primary": result["primary"], "independent_readback": "NOT_YET_RUN"}
            remaining(started + 300)
        return receipt
    except BaseException as error:
        fail_output(output, error)
        raise


def verify(output):
    """Independent archived-byte and Python-metric readback; never executes SDK."""
    started = time.monotonic()
    output = safe_path(output)
    reject_failure(output)
    with bounded_stage(started + 300) as deadline:
        plan = frozen_plan()
        manifest, report = read_json(output / "manifest.json"), read_json(output / "result.json")
        require(set(manifest) == {"schema_version", "files"} and manifest["schema_version"] == 1
                and reference.file_set(output, ("manifest.json",)) == manifest["files"], "evidence file/hash closure")
        allowed = {"bundle", "archived-reference", "data-preflight", "measurement-source", "cases",
                   "predecessor.zip", "experiment.json", "result.json", "manifest.json"}
        if report["engineering_receipt"] == "host-engineering/engineering/engineering.json":
            allowed.add("host-engineering")
        require({p.name for p in output.iterdir()} == allowed, "unexpected top-level evidence member")
        bundle = ci.verify_bundle(output / "bundle")
        sources = code_identity(bundle["manifest"]["code_revision"])
        require(reference.file_set(output / "measurement-source") == sources["files_sha256"], "saved measurement source closure")
        archived = retained_inputs(output, plan)
        allowed_engineering = {"bundle/" + bundle["manifest"]["paths"]["engineering"], "host-engineering/engineering/engineering.json"}
        require(report["engineering_receipt"] in allowed_engineering, "selected engineering path")
        selected = ci.verify_engineering(output / "bundle", output / report["engineering_receipt"])
        for key in ("runtime_identity_before", "runtime_identity_after"):
            require(reference.normalized_runtime(report[key]) == reference.normalized_runtime(selected["runtime_identity"]),
                    "recorded measurement host/libraries differ from its engineering")
            reference.research_runtime_binding(report[key], bundle["reference"][2])
        require(report["runtime_identity_before"] == report["runtime_identity_after"], "recorded runtime changed")
        execution_root, binary = execution_paths(report, bundle)
        environment = ci.execution_environment(execution_root / "bundle")
        for name, path in report["runtime_identity_before"]["library_names"].items():
            if name.startswith(("libwebrtc-", "libabsl")):
                require(Path(path).parent == execution_root / "bundle/reference/bin/lib", "historical runtime research-library path")
        calls, scores, times, previous_end = [], [], [], 0
        for case in plan["cases"]:
            remaining(deadline)
            folder = output / "cases" / case["case_id"]
            record = read_json(folder / "observation/command.json")
            begin = read_json(folder / "observation/invocation-start.json")
            command = runner_command(binary, execution_root / "cases" / case["case_id"])
            validate_call(record, begin, command, environment)
            require(previous_end <= record["started_monotonic_ns"], "sequential call order changed")
            previous_end = record["finished_monotonic_ns"]
            times.append(record["elapsed_seconds"])
            observed = observation_outputs(folder, case)
            calls.append({"case_id": case["case_id"], "command_receipt": "cases/" + case["case_id"] + "/observation/command.json"})
            scores.append(score_case(folder, case, plan, observed))
        wall = report["elapsed_before_seal_seconds"]
        require(finite(wall) and 0 < math.fsum(times) <= wall <= 300, "six call times exceed recorded stage budget")
        expected = report_body(plan, sources, archived, bundle, report["engineering_receipt"], selected,
                               report["runtime_identity_before"], report["runtime_identity_after"], execution_root,
                               calls, scores, primary_input_identity(output, plan), wall, output)
        require(encoded(report) == encoded(expected), "saved metrics/primary/roles/identities differ from independent readback")
        require(reference.file_set(output, ("manifest.json",)) == manifest["files"], "evidence changed during readback")
        require(code_identity(sources["code_revision"]) == sources, "readback implementation changed")
        remaining(deadline)
        receipt = {"schema_version": 1, "experiment_id": EXPERIMENT, "status": "PASS_INDEPENDENT_READBACK",
                   "source_revision": sources["code_revision"], "plan_sha256": PLAN_SHA256,
                   "result_sha256": sha_file(output / "result.json"), "manifest_sha256": sha_file(output / "manifest.json"),
                   "files_verified": len(manifest["files"]), "wall_seconds": time.monotonic() - started,
                   "sdk_calls": 0, "decoder_calls": 0, "compiler_calls": 0, "native_metric_calls": 0, "ldd_calls": 0,
                   "read_only_git_identity_checks": True, "metrics": "UNCHANGED_CANONICAL_PYTHON_SI_SDR_AND_DECLARED_ARITHMETIC",
                   "primary": expected["primary"], "decision": DECISION, "data_role": ROLE,
                   "independent_confirmation": False, "promotion_allowed": False}
        remaining(started + 300)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("--bundle", type=Path, required=True)
    runner.add_argument("--original-comparison", type=Path, required=True)
    runner.add_argument("--data-preflight", type=Path, required=True)
    runner.add_argument("--engineering-receipt", type=Path)
    runner.add_argument("--output", type=Path, required=True)
    reader = commands.add_parser("verify")
    reader.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = (run(args.bundle, args.original_comparison, args.data_preflight, args.output, args.engineering_receipt)
             if args.command == "run" else verify(args.output))
    print(encoded(value).decode(), end="")


if __name__ == "__main__":
    main()
