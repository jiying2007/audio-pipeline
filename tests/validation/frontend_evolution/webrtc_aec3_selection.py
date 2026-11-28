#!/usr/bin/env python3
"""Bounded E/Y synthesis-selection observation and conditional intervention.

The source transform is a research-only adapted upstream variant.  Saved F07
bytes are development evidence, never a new holdout.  No scoring target is
passed to the runner.  A primary support interval containing only E stops the
experiment before the conditional force-E call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import webrtc_aec3_linear_tap as prior
from contracts import ROOT, hex_digest, require

EXPERIMENT = "FE04-WEBRTC-AEC3-SYNTHESIS-SELECTION-V1"
ROLE = "DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT"
DISPOSITION = "DIAGNOSTIC_DIRECTION_ONLY_NO_PROMOTION"
CASE = "p1-ula4-70-fir33-none"
SAMPLES, RATE, HOP, BLOCK = 256000, 16000, 160, 64
PRIMARY = (97600, 126400)
SUPPORT = (1525, 1976)
TRACE_KEYS = {"kind", "block_index", "source_linear", "applied_linear", "forced", "capture_output_used",
              "gain_bits", "high_bands_gain_bits", "dominant_nearend_after_gain"}
REL = "tests/validation/frontend_evolution/"
PLAN_REL = ".github/research/frontend-evolution-v1/webrtc-aec3-synthesis-selection-v1.json"
PLAN_SHA256 = "42f650eec3f9dd793cf9d859fc973d831a7aa62224f6023eceb8f83ad2b93d5c"
NEW_FILES = (
    REL + "webrtc_aec3_selection.py", REL + "test_webrtc_aec3_selection.py",
    REL + "webrtc_aec3_selection_ci.py", REL + "webrtc_aec3_selection_source.py",
    REL + "test_webrtc_aec3_selection_source.py", REL + "test_webrtc_aec3_selection_adapter.py",
    PLAN_REL,
    REL + "webrtc_aec3_selection_scope.py", REL + "test_webrtc_aec3_selection_scope.py",
)
regular, safe_path, sha_file = prior.regular, prior.safe_path, prior.sha_file
read_json, write_json = prior.read_json, prior.write_json


def synthesis_support(target_start, target_stop):
    """Source-derived 64-point overlap-add support, end exclusive.

    Input block q appears at final stream block q+2.  The synthesizer's block
    k appears at stream block k+1 and includes the tail saved from k-1.
    """
    require(type(target_start) is int and type(target_stop) is int
            and 0 <= target_start < target_stop <= SAMPLES - 128,
            "bounded integer target interval required")
    first_synthesis = (target_start + 128) // BLOCK - 1
    last_synthesis = (target_stop + 128 - 1) // BLOCK - 1
    return max(0, first_synthesis - 1), last_synthesis + 1


def parse_trace(data, mode, expected_blocks=SAMPLES // BLOCK):
    require(mode in ("observe", "force-linear"), "unknown selection observation mode")
    require(isinstance(data, bytes) and len(data) <= 16 * 1024 * 1024,
            "bounded original stderr bytes required")
    require(type(expected_blocks) is int and 0 < expected_blocks <= SAMPLES // BLOCK,
            "bounded exact block count required")
    rows = []
    for raw in data.decode("utf-8", errors="strict").splitlines():
        if "aec3_synthesis_selection" not in raw:
            continue
        require(len(raw) <= 4096, "bounded selector trace line required")
        try:
            row = strict_json_line(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("malformed synthesis-selection trace") from error
        require(isinstance(row, dict) and set(row) == TRACE_KEYS,
                "exact selection trace fields required")
        require(row["kind"] == "aec3_synthesis_selection"
                and type(row["block_index"]) is int and row["block_index"] == len(rows),
                "missing, duplicate, reordered or reset selector block")
        require(all(type(row[key]) is bool for key in ("source_linear", "applied_linear", "forced",
                                                     "capture_output_used", "dominant_nearend_after_gain")),
                "selector flags must be JSON booleans")
        require(type(row["gain_bits"]) is list and len(row["gain_bits"]) == 65,
                "all 65 raw gain words required")
        for word in row["gain_bits"] + [row["high_bands_gain_bits"]]:
            gain_value(word)
        force = mode == "force-linear"
        require(row["forced"] is (force and not row["source_linear"]) and row["capture_output_used"] is True
                and row["applied_linear"] is (row["source_linear"] or force),
                "selector mode, inactive synthesis or actual branch mismatch")
        rows.append(row)
        require(len(rows) <= expected_blocks, "extra selector blocks")
    require(len(rows) == expected_blocks, "incomplete selector block coverage")
    return rows


def strict_json_line(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate trace JSON key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("nonfinite trace JSON constant: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def gain_value(word):
    require(type(word) is int and 0 <= word < 2**32, "raw binary32 word required")
    value = struct.unpack("<f", struct.pack("<I", word))[0]
    require(math.isfinite(value) and 0 <= value <= 1, "finite suppression gain in [0,1] required")
    return value


def selection_summary(rows):
    require(len(rows) == SAMPLES // BLOCK, "complete primary observation required")
    lo, hi = synthesis_support(*PRIMARY)
    require((lo, hi) == SUPPORT, "source-derived support differs from frozen interval")
    counts = {}
    for label, begin, end in (("whole", 0, len(rows)), ("primary_with_ola", lo, hi)):
        selected = rows[begin:end]
        raw_indices = [row["block_index"] for row in selected if not row["source_linear"]]
        counts[label] = {"block_start": begin, "block_stop": end, "blocks": end - begin,
                         "source_E": len(selected) - len(raw_indices), "source_Y": len(raw_indices),
                         "source_Y_block_indices": raw_indices}
    all_linear = counts["primary_with_ola"]["source_Y"] == 0
    gains = [gain_value(word) for row in rows[lo:hi] for word in row["gain_bits"]]
    return {"counts": counts, "force_linear_permitted": not all_linear,
            "decision": ("NO_SELECTOR_Y_EXPOSURE_IN_PRIMARY_SUPPORT" if all_linear
                         else "SELECTOR_Y_EXPOSURE_OBSERVED"),
            "scope": "ONE_DISCLOSED_PRIMARY_WINDOW_WITH_ONE_PREVIOUS_OLA_BLOCK",
            "secondary_readonly_control": {
                "primary_support_gain_words": len(gains), "minimum_gain": min(gains),
                "maximum_gain": max(gains), "mean_squared_gain": math.fsum(x*x for x in gains) / len(gains),
                "dominant_nearend_after_gain_blocks": sum(row["dominant_nearend_after_gain"] for row in rows[lo:hi]),
                "interpretation": "UNWEIGHTED_CONTROL_DESCRIPTION_NOT_ACOUSTIC_EFFECT_OR_CAUSAL_ATTRIBUTION"},
            "other_causes_identified": False, "promotion_allowed": False}


def intervention_decision(observe, candidate):
    """Use the already canonical SI-SDR/NMSE directions; never select a metric."""
    result = prior.primary_decision(candidate, observe)
    mapping = {"SUPPORTED_IN_DISCLOSED_WINDOW": "SUPPORTED_IN_DISCLOSED_WINDOW",
               "NOT_SUPPORTED_IN_DISCLOSED_WINDOW": "NOT_SUPPORTED_IN_DISCLOSED_WINDOW",
               "INCONCLUSIVE_MIXED_INDICATORS": "INCONCLUSIVE_MIXED_INDICATORS",
               "NOT_IDENTIFIABLE": "NOT_IDENTIFIABLE"}
    return mapping[result]


def frozen_plan():
    path = regular(ROOT / PLAN_REL, 65536)
    require(hex_digest(PLAN_SHA256, 64) and sha_file(path) == PLAN_SHA256,
            "selection plan must be frozen before execution or readback")
    plan = read_json(path)
    require(plan["experiment_id"] == EXPERIMENT and plan["data_role"] == ROLE,
            "wrong selection experiment or data role")
    return plan


def code_identity(revision):
    import webrtc_aec3_selection_ci as ci
    require(hex_digest(revision, 40), "full public execution SHA required")
    command = ["git", "-C", str(ROOT), "-c", "core.fsmonitor=false", "-c", "safe.directory=" + str(ROOT.resolve())]
    require(subprocess.check_output(command + ["rev-parse", "HEAD"], timeout=10).decode().strip() == revision,
            "measurement/readback must use its exact source checkout")
    paths = set(prior.CONTROL_FILES) | set(NEW_FILES) | set(getattr(ci, "CONTROL_FILES", ()))
    records = {}
    for name in sorted(paths):
        data = regular(ROOT / name).read_bytes()
        require(data == prior.ci.git_bytes(revision, name), "uncommitted measurement control: " + name)
        records[name] = hashlib.sha256(data).hexdigest()
    loaded = set()
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename and Path(filename).suffix == ".py":
            try:
                loaded.add(Path(filename).resolve().relative_to(ROOT.resolve()).as_posix())
            except ValueError:
                pass
    require(loaded <= paths, "unbound first-party measurement module: " + repr(sorted(loaded - paths)))
    return {"code_revision": revision, "files_sha256": records}


def run_command(binary, inputs, output, mode):
    require(mode in ("observe", "force-linear"), "single frozen selector mode required")
    return [str(binary), "--mode", "aec3", "--mic-channels", "1", "--channel-map", "0",
            "--mic", str(inputs / "mic.pcm"), "--render", str(inputs / "render.pcm"),
            "--output", str(output / "output.pcm"), "--metadata", str(output / "metadata.json"),
            "--frame-times", str(output / "frames.jsonl"), "--aec3-export-mode", "factory-on",
            "--linear-output", str(output / "linear.f32"), "--aec3-synthesis-selection", mode]


def retained_file(path, spec):
    path = regular(path)
    require(path.stat().st_size == spec["bytes"] and sha_file(path) == spec["sha256"],
            "retained source identity mismatch: " + str(path))
    return path


def read_observation(folder, mode):
    require({p.name for p in folder.iterdir()} == prior.OBSERVATION_FILES,
            "missing or unexpected observation members")
    final = regular(folder / "output.pcm", SAMPLES * 2).read_bytes()
    linear = regular(folder / "linear.f32", SAMPLES * 4).read_bytes()
    require(len(final) == SAMPLES * 2 and len(linear) == SAMPLES * 4, "partial PCM observation")
    values = [item[0] for item in struct.iter_unpack("<f", linear)]
    require(all(math.isfinite(value) and -1 <= value <= 1 for value in values), "invalid linear float output")
    rows = parse_trace(regular(folder / "stderr.log", 16 * 1024 * 1024).read_bytes(), mode)
    metadata = read_json(folder / "metadata.json")
    require(metadata.get("status") == "OK", "runner did not finish successfully")
    require(metadata["aec3_synthesis_selection"]["mode"] == mode
            and metadata["input_frames"] == metadata["completed_frames"] == SAMPLES // HOP
            and metadata["output_sample_frames"] == SAMPLES
            and metadata["algorithmic_latency_samples"] == 128
            and metadata["reset_before_frame"] is None,
            "wrong mode, sample count, declared latency or reset metadata")
    frame_rows = prior.reference.trace_rows(folder / "frames.jsonl", SAMPLES // HOP)
    require(len(frame_rows) == SAMPLES // HOP, "incomplete adapter frame coverage")
    for index, row in enumerate(frame_rows):
        require(set(row) == prior.TRACE_KEYS and all(type(row[key]) is int and row[key] >= 0 for key in
                    ("frame_index", "algorithmic_latency_samples", "linear_signal_delay_samples",
                     "linear_getter_completed_ns", "linear_output_sample_frames_emitted")),
                "frame schema or integer type drift")
        require(row["frame_index"] == index and row["reset_before_frame"] is False
                and row["output_sample_frames_emitted"] == (index + 1) * HOP
                and row["linear_output_sample_frames_emitted"] == (index + 1) * HOP,
                "frame discontinuity or reset")
    expected = prior.reference.config_for("aec3")
    expected["echo_canceller"]["export_linear_aec_output"] = True
    require(metadata["schema_version"] == 1 and metadata["adapter"] == "webrtc-aec3-offline-v1"
            and metadata["detail"] == "" and metadata["requested_config"] == metadata["applied_config"] == expected,
            "source-default processing configuration drift")
    paths = {"--mic": folder.parent / "inputs/mic.pcm", "--render": folder.parent / "inputs/render.pcm",
             "--output": folder / "output.pcm", "--metadata": folder / "metadata.json",
             "--frame-times": folder / "frames.jsonl", "--linear-output": folder / "linear.f32"}
    interpreted = prior.fixture.inspect_outputs(paths, "factory-on", regular(paths["--mic"]).read_bytes(), None)
    require(interpreted["metadata"] == metadata and interpreted["trace"] == frame_rows,
            "canonical metadata or frame interpretation differs")
    return {"final": final, "linear": linear, "rows": rows, "metadata": metadata}


def score_observation(inputs, observed):
    target = prior.s16_normalized(regular(inputs / "target.s16").read_bytes(), SAMPLES)
    echo = prior.s16_normalized(regular(inputs / "echo.s16").read_bytes(), SAMPLES)
    old_plan = prior.frozen_plan()
    result = {}
    views = {"linear": [v[0] for v in struct.iter_unpack("<f", observed["linear"])],
             "final": prior.s16_normalized(observed["final"], SAMPLES)}
    for name, values in views.items():
        delay = prior.DELAYS[name]
        result[name] = {
            "near": {label: prior.span_metrics(target, values, lo, hi, delay)
                     for label, (lo, hi) in old_plan["metrics"]["near_phase_samples"].items()},
            "far": prior.far_metrics(echo, values, delay, old_plan),
            "common_aligned": prior.span_metrics(target, values, 0, SAMPLES - 128, delay),
            "raw_amplitude": prior.amplitude(values, 1.0 if name == "linear" else 32767 / 32768.0),
        }
    return result


def fail_output(output, error):
    prior.fail_output(output, error)


def input_specs(plan):
    case = plan["cases"][0]
    require(len(plan["cases"]) == 1 and case["case_id"] == CASE and case["samples"] == SAMPLES,
            "only the frozen single primary case is admitted")
    return dict(case["prepared_inputs"], **{name: case["members"][name]
                                          for name in ("target.s16", "echo.s16")})


def original_inputs(original, output, plan):
    """Read exact old evidence; do not invoke its SDK or reinterpret its role."""
    legacy = plan["legacy_evidence"]
    for name, expected in (("manifest.json", legacy["f07_manifest_sha256"]),
                           ("result.json", legacy["f07_result_sha256"])):
        require(sha_file(regular(original / name)) == expected, "wrong F07 evidence root")
        prior.copy_file(original / name, output / "archived-f07" / name)
    previous_manifest = read_json(original / "manifest.json")["files"]
    before = original / "cases" / CASE
    for name, spec in input_specs(plan).items():
        retained_file(before / name, spec)
        require(previous_manifest["cases/" + CASE + "/" + name] == spec["sha256"], "F07 member binding")
        prior.copy_file(before / name, output / "inputs" / name)
    for name, spec in (("output.pcm", legacy["final_s16"]), ("linear.f32", legacy["linear_f32"])):
        source = before / "observation" / name
        retained_file(source, spec)
        require(previous_manifest["cases/" + CASE + "/observation/" + name] == spec["sha256"], "F07 output binding")
        prior.copy_file(source, output / "archived-f07" / name)
    metadata = before / "observation" / "metadata.json"
    require(sha_file(regular(metadata)) == previous_manifest["cases/" + CASE + "/observation/metadata.json"],
            "F07 metadata identity")
    prior.copy_file(metadata, output / "archived-f07" / "metadata.json")


def validate_retained(output, plan):
    legacy = plan["legacy_evidence"]
    for name, spec in input_specs(plan).items():
        retained_file(output / "inputs" / name, spec)
    for name, key in (("output.pcm", "final_s16"), ("linear.f32", "linear_f32")):
        retained_file(output / "archived-f07" / name, legacy[key])
    for name, expected in (("manifest.json", legacy["f07_manifest_sha256"]),
                           ("result.json", legacy["f07_result_sha256"])):
        require(sha_file(regular(output / "archived-f07" / name)) == expected, "retained F07 metadata changed")
    old_manifest = read_json(output / "archived-f07/manifest.json")["files"]
    require(sha_file(regular(output / "archived-f07/metadata.json"))
            == old_manifest["cases/" + CASE + "/observation/metadata.json"], "retained original F07 processing metadata changed")
    require(sha_file(regular(output / "experiment.json")) == PLAN_SHA256, "retained new plan changed")


def check_neutral_metadata(actual, original):
    """Compare effective processing semantics; actual host clocks may differ."""
    fields = ("mode", "sample_format", "sample_rate_hz", "frame_samples", "mic_channels",
              "render_channels", "output_channels", "channel_map", "stream_delay_ms", "adapter_lookahead_frames",
              "padded_samples", "tail_flush_samples", "latency_components_samples", "call_order",
              "aec3_includes_internal_residual_suppression", "pure_linear_aec", "adapter_normalization",
              "requested_config", "applied_config", "actual_processing_channels", "actual_processing_sample_rate_hz")
    require(all(actual[field] == original[field] for field in fields), "non-selection processing semantics changed")


def compare_upstream(observed, forced):
    require(forced["linear"] == observed["linear"], "force-E changed the upstream linear witness")
    keys = ("block_index", "source_linear", "gain_bits", "high_bands_gain_bits", "dominant_nearend_after_gain")
    require(all(all(a[key] == b[key] for key in keys) for a, b in zip(observed["rows"], forced["rows"])),
            "force-E changed source selection, applied gain or recorded nearend control")


def results_from_outputs(output, plan):
    """Pure result computation, shared by execution and byte-only readback."""
    validate_retained(output, plan)
    observed = read_observation(output / "observe", "observe")
    require(observed["final"] == (output / "archived-f07/output.pcm").read_bytes()
            and observed["linear"] == (output / "archived-f07/linear.f32").read_bytes(),
            "neutral observer does not reproduce complete F07 final and linear bytes")
    old_metadata = read_json(output / "archived-f07/metadata.json")
    check_neutral_metadata(observed["metadata"], old_metadata)
    selection = selection_summary(observed["rows"])
    scores = {"observe": score_observation(output / "inputs", observed)}
    result = {"neutral_final_equals_f07": True, "neutral_linear_equals_f07": True,
              "selection": selection, "scores": scores,
              "conditional_force_linear": {"status": "NOT_RUN_STOP_RULE", "calls": 0},
              "primary_decision": selection["decision"]}
    candidate_path = output / "force-linear"
    if selection["force_linear_permitted"]:
        forced = read_observation(candidate_path, "force-linear")
        compare_upstream(observed, forced)
        check_neutral_metadata(forced["metadata"], old_metadata)
        scores["force-linear"] = score_observation(output / "inputs", forced)
        phase = plan["primary"]["phase"]
        result["primary_decision"] = intervention_decision(scores["observe"]["final"]["near"][phase],
                                                          scores["force-linear"]["final"]["near"][phase])
        result["conditional_force_linear"] = {
            "status": "EXECUTED_ON_PREREGISTERED_EXPOSURE", "calls": 1,
            "whole_linear_equal": True, "all_recorded_upstream_control_words_equal": True,
            "no_claim_all_hidden_states_were_exported": True,
            "changed_final_samples": sum(a != b for a, b in zip(struct.iter_unpack("<h", observed["final"]),
                                                                 struct.iter_unpack("<h", forced["final"]))),
            "primary_delta": {key: (scores["force-linear"]["final"]["near"][phase][key]
                                      - scores["observe"]["final"]["near"][phase][key])
                              if all(scores[m]["final"]["near"][phase][key] is not None for m in scores) else None
                              for key in ("si_sdr_db", "normalized_mse")},
        }
    else:
        require(not candidate_path.exists(), "stop rule prohibits an extra conditional arm")
    return result


def runner_paths(bundle, manifest):
    return {name: bundle / prior.reference.relative_name(value) for name, value in manifest["paths"].items()}


def run(bundle, original, engineering, output):
    import webrtc_aec3_selection_ci as ci
    started = time.monotonic()
    bundle, original, engineering, output = map(safe_path, (bundle, original, engineering, output))
    require(not output.exists() and all(output != source and output not in source.parents and source not in output.parents
                                      for source in (bundle, original, engineering.parent, ROOT)),
            "fresh disjoint experiment output required")
    output.mkdir(parents=True)
    try:
        with prior.bounded_stage(started + 300) as deadline:
            plan = frozen_plan()
            manifest = ci.verify_bundle(bundle)
            identity = code_identity(manifest["code_revision"])
            host = ci.require_host_engineering(bundle, engineering)
            prior.copy_tree(bundle, output / "bundle")
            prior.copy_tree(engineering.parent, output / "host-engineering")
            prior.copy_file(ROOT / PLAN_REL, output / "experiment.json")
            for name in identity["files_sha256"]:
                prior.copy_file(ROOT / name, output / "measurement-source" / name)
            original_inputs(original, output, plan)
            validate_retained(output, plan)
            copied = output / "bundle"
            manifest = ci.verify_bundle(copied)
            host_receipt = output / "host-engineering" / engineering.name
            paths = runner_paths(copied, manifest)
            adapter = read_json(paths["adapter_build"])
            copied_host = ci.engineering_record(host_receipt, adapter["binary_sha256"],
                                                adapter["build_receipt_sha256"], manifest["code_revision"])
            require(copied_host == host, "copied host engineering evidence changed")
            binary = paths["runner"]
            require(os.access(binary, os.X_OK), "runner executable mode missing")
            environment = ci.execution_environment(copied)
            runtime = prior.ci.previous.runtime_identity(binary, environment)
            require(prior.reference.normalized_runtime(runtime) == prior.reference.normalized_runtime(host["runtime_identity"]),
                    "host qualification does not match actual runtime")
            prior.reference.research_runtime_binding(runtime, adapter, copied)
            inputs = output / "inputs"
            (output / "observe").mkdir()
            command = run_command(binary, inputs, output / "observe", "observe")
            prior.run_process(command, output / "observe", environment, deadline)
            observed = read_observation(output / "observe", "observe")
            require(observed["final"] == (output / "archived-f07/output.pcm").read_bytes()
                    and observed["linear"] == (output / "archived-f07/linear.f32").read_bytes(),
                    "neutrality failed before conditional admission")
            check_neutral_metadata(observed["metadata"], read_json(output / "archived-f07/metadata.json"))
            selection = selection_summary(observed["rows"])
            write_json(output / "support-gate.json", {"summary": selection, "decided_monotonic_ns": time.monotonic_ns()})
            if selection["force_linear_permitted"]:
                (output / "force-linear").mkdir()
                command = run_command(binary, inputs, output / "force-linear", "force-linear")
                prior.run_process(command, output / "force-linear", environment, deadline)
            measurements = results_from_outputs(output, plan)
            runtime_after = prior.ci.previous.runtime_identity(binary, environment)
            require(runtime_after == runtime and code_identity(identity["code_revision"]) == identity,
                    "source or actual runtime changed during measurement")
            ci.verify_bundle(copied)
            validate_retained(output, plan)
            calls = 1 + measurements["conditional_force_linear"]["calls"]
            result = {"schema_version": 1, "experiment_id": EXPERIMENT, "status": "EXECUTED_BOUNDED_SELECTION_DIAGNOSTIC",
                      "disposition": DISPOSITION, "data_role": ROLE, "promotion_allowed": False,
                      "independent_confirmation": False, "effective_unique_conditions": 1,
                      "code_identity": identity, "plan_sha256": PLAN_SHA256, "execution_root": str(output),
                      "bundle_manifest_sha256": sha_file(copied / "bundle.json"),
                      "host_engineering_receipt": "host-engineering/" + engineering.name,
                      "host_engineering_sha256": sha_file(host_receipt),
                      "runtime_before": runtime, "runtime_after": runtime_after,
                      "execution_environment": environment, "measurements": measurements,
                      "actual_budget": {"speech_calls": calls, "capture_seconds": 16 * calls,
                                        "api_frames": 1600 * calls, "internal_blocks": 4000 * calls,
                                        "acoustic_retries": 0, "training_runs": 0, "local_compiler_calls": 0,
                                        "wall_seconds_before_seal": time.monotonic() - started}}
            write_json(output / "result.json", result)
            write_json(output / "manifest.json", {"schema_version": 1, "files": prior.reference.file_set(output)})
            prior.remaining(deadline)
        return {"status": result["status"], "result_sha256": sha_file(output / "result.json"),
                "manifest_sha256": sha_file(output / "manifest.json"), "actual_budget": result["actual_budget"],
                "primary_decision": measurements["primary_decision"]}
    except BaseException as error:
        fail_output(output, error)
        raise


def verify(output):
    """No SDK, codec, compiler, ldd or external metric execution."""
    import webrtc_aec3_selection_ci as ci
    started = time.monotonic()
    output = safe_path(output)
    with prior.bounded_stage(started + 300) as deadline:
        prior.reject_failure(output)
        plan = frozen_plan()
        result = read_json(output / "result.json")
        require(result["experiment_id"] == EXPERIMENT and result["disposition"] == DISPOSITION
                and result["data_role"] == ROLE and result["promotion_allowed"] is False
                and result["independent_confirmation"] is False and result["effective_unique_conditions"] == 1,
                "result role or experiment drift")
        files = read_json(output / "manifest.json")["files"]
        require(files == prior.reference.file_set(output, excluded=("manifest.json",)), "complete evidence inventory mismatch")
        require(result["plan_sha256"] == PLAN_SHA256, "measurement plan identity changed")
        identity = code_identity(result["code_identity"]["code_revision"])
        require(identity == result["code_identity"], "measurement code identity mismatch")
        for name, digest in identity["files_sha256"].items():
            require(sha_file(regular(output / "measurement-source" / name)) == digest, "sealed source changed")
        manifest = ci.verify_bundle(output / "bundle")
        require(manifest["code_revision"] == identity["code_revision"]
                and sha_file(output / "bundle/bundle.json") == result["bundle_manifest_sha256"], "bundle identity mismatch")
        host_path = prior.reference.relative_name(result["host_engineering_receipt"])
        require(sha_file(regular(output / host_path)) == result["host_engineering_sha256"], "host qualification changed")
        adapter = read_json(runner_paths(output / "bundle", manifest)["adapter_build"])
        host = ci.engineering_record(output / host_path, adapter["binary_sha256"],
                                     adapter["build_receipt_sha256"], manifest["code_revision"])
        require(result["runtime_before"] == result["runtime_after"]
                and prior.reference.normalized_runtime(result["runtime_before"])
                == prior.reference.normalized_runtime(host["runtime_identity"]), "recorded host/runtime mismatch")
        measured = results_from_outputs(output, plan)
        gate = read_json(output / "support-gate.json")
        require(set(gate) == {"summary", "decided_monotonic_ns"} and type(gate["decided_monotonic_ns"]) is int
                and result["measurements"] == measured and gate["summary"] == measured["selection"],
                "reported measurements do not reproduce from original bytes")
        calls = 1 + measured["conditional_force_linear"]["calls"]
        budget = result["actual_budget"]
        require(budget["speech_calls"] == calls and budget["capture_seconds"] == 16 * calls
                and budget["api_frames"] == 1600 * calls and budget["internal_blocks"] == 4000 * calls
                and budget["acoustic_retries"] == budget["training_runs"] == budget["local_compiler_calls"] == 0
                and 0 < budget["wall_seconds_before_seal"] <= 300, "actual bounded call accounting mismatch")
        original_root = Path(result["execution_root"])
        require(original_root.is_absolute() and str(Path(os.path.abspath(original_root))) == str(original_root),
                "canonical original execution path required")
        prior.reference.research_runtime_binding(result["runtime_before"], adapter, original_root / "bundle")
        require(result["execution_environment"] == ci.execution_environment(original_root / "bundle"),
                "execution environment contains an unbound override or library path")
        binary = runner_paths(original_root / "bundle", manifest)["runner"]
        for mode in (["observe", "force-linear"] if calls == 2 else ["observe"]):
            folder = output / mode
            command = run_command(binary, original_root / "inputs", original_root / mode, mode)
            prior.validate_call(read_json(folder / "command.json"), read_json(folder / "invocation-start.json"),
                                command, result["execution_environment"])
        require(read_json(output / "observe/command.json")["finished_monotonic_ns"] <= gate["decided_monotonic_ns"],
                "support gate predates completed observation")
        if calls == 2:
            require(gate["decided_monotonic_ns"] < read_json(output / "force-linear/invocation-start.json")["started_monotonic_ns"],
                    "conditional intervention was started before the support gate")
        prior.remaining(deadline)
        return {"status": "PASS_INDEPENDENT_SELECTION_READBACK", "experiment_id": EXPERIMENT,
                "code_revision": identity["code_revision"], "result_sha256": sha_file(output / "result.json"),
                "manifest_sha256": sha_file(output / "manifest.json"), "members": len(files),
                "primary_decision": measured["primary_decision"], "speech_calls": calls,
                "sdk_calls": 0, "codec_calls": 0, "compiler_calls": 0, "ldd_calls": 0,
                "native_metric_calls": 0, "wall_seconds": time.monotonic() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    execute = sub.add_parser("run")
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--original-f07", type=Path, required=True)
    execute.add_argument("--host-engineering", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        value = run(args.bundle, args.original_f07, args.host_engineering, args.output)
    else:
        value = verify(args.output)
    print(json.dumps(value, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()

