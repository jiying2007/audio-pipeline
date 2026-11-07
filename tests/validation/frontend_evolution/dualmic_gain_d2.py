#!/usr/bin/env python3
"""D2: exact production AGC replay and ordered, state-conditioned gain views.

The parent D1 result remains a required, separately retained artifact.  This
driver does not copy or regenerate it.  Only run executes the original AGC;
verify reads the saved output and uses the unchanged D1 measurement functions.
"""
from __future__ import annotations

import argparse
from array import array
import csv
import io
import math
import os
from pathlib import Path
import re
import shlex
import signal
import statistics
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dualmic_stages_d1 as d1

ROOT = d1.ROOT
EXPERIMENT = "FE-DUALMIC-GAIN-D2"
BUDGET = 300.0
RATE, HOP = d1.RATE, d1.HOP
LOCK_NAME = "docs/research/frontend-evolution-v1/dualmic-gain-d2-input-lock.json"
PLAN_NAME = "docs/research/frontend-evolution-v1/DUALMIC_GAIN_D2_PLAN.zh-CN.md"
SELF_NAME = "tests/validation/frontend_evolution/dualmic_gain_d2.py"
C_NAME = "tests/validation/frontend_evolution/dualmic_gain_d2.c"
TEST_NAME = "tests/validation/frontend_evolution/test_dualmic_gain_d2_integrity.py"
LANES = ("state_only", "gate_capped", "peak_capped", "replay_final")
VIEWS = ("pre_agc", *LANES)
STEPS = ("input_to_state_only", "state_to_gate", "gate_to_peak", "peak_to_final")
TRACE_FIELDS = (
    "frame,allow,reset,input_rms,input_peak,target_linear,limiter_linear,"
    "target_gain_raw,target_gain_bounded,target_gain,alpha,state_gain_before,"
    "state_gain_after,expected_state_gain_after,reference_gain_before,"
    "reference_gain_after,gate_cap_gain,peak_limit_gain,applied_gain,"
    "target_gate_cap_active,output_gate_cap_active,peak_cap_active,"
    "final_sample_clamp_count,state_gain_before_match,state_gain_after_match,"
    "formula_state_after_match,final_match,formula_final_match,state_only_peak,"
    "gate_capped_peak,peak_capped_peak,replay_final_peak"
).split(",")
MATCH_FIELDS = ("state_gain_before_match", "state_gain_after_match", "formula_state_after_match",
                "final_match", "formula_final_match")
CAP_FIELDS = ("target_gate_cap_active", "output_gate_cap_active", "peak_cap_active")
INT_FIELDS = {"frame", "allow", "reset", "final_sample_clamp_count", *MATCH_FIELDS, *CAP_FIELDS}
VERIFY_FILES = frozenset(("verify.log", "verify-phase.json", "verify-error.json", "readback.json"))
require, descriptor, digest = d1.require, d1.descriptor, d1.digest
safe, read_json, write_json, copy_exact = d1.safe, d1.read_json, d1.write_json, d1.copy_exact


def remaining(started, reserve=0.0):
    seconds = BUDGET - (time.monotonic() - started) - reserve
    if seconds <= 0:
        raise TimeoutError("frozen 300 second D2 phase budget exceeded")
    return seconds


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def bits(value):
    return struct.pack("<f", value)


def same_float(left, right):
    return bits(left) == bits(right)


def file_set(root):
    result = set()
    for path in Path(root).rglob("*"):
        require(not path.is_symlink(), "symlink in retained D2 evidence")
        if path.is_file():
            result.add(path.relative_to(root).as_posix())
    return result


def input_lock():
    lock = read_json(ROOT / LOCK_NAME)
    require(lock["schema_version"] == 1 and lock["experiment"] == EXPERIMENT and
            lock["base_sha"] == d1.BASE_SHA and lock["data_role"] == "disclosed-regression",
            "D2 input lock identity drift")
    require((lock["case_count"], lock["frames"], lock["samples"], lock["sample_rate_hz"],
             lock["frame_samples"], lock["offset_samples"]) == (60, 35916, 5746560, RATE, HOP, HOP),
            "D2 matrix/geometry drift")
    require(lock["profile_targets_dbfs"] == {"call": -20, "assistant": -18} and
            lock["limiter_dbfs"] == -2, "D2 original profile defaults drift")
    require(set(lock["D1_SOURCE_FILES"]) == set(d1.SOURCE_FILES), "D1 source dependency closure drift")
    for name, expected in lock["D1_SOURCE_FILES"].items():
        require(descriptor(ROOT / name) == expected, "frozen D1 implementation changed: " + name)
    cases = [entry["catalog"] for entry in lock["cases"]]
    keys = [case["key"] for case in cases]
    expected = {"A/pair-" + str(pair) + "-" + scene + "-" + profile for pair in range(4)
                for scene in d1.SCENES for profile in d1.PROFILES} | {"C/" + name for name in d1.C_CASES}
    require(len(keys) == len(set(keys)) == 60 and set(keys) == expected and
            sum(c["frames"] for c in cases) == lock["frames"] and
            sum(c["samples"] for c in cases) == lock["samples"], "D2 incomplete case catalog")
    for entry in lock["cases"]:
        case = entry["catalog"]
        require(case["samples"] == HOP * case["frames"] and case["profile"] in d1.PROFILES and
                set(entry["parent_taps"]) == {"ns_output.f32le", "agc_output.f32le", "control.csv"},
                "D2 parent lane/catalog closure drift")
        require((entry["clean_near"] is None) == (case["inputs"]["clean_near"] is None),
                "D2 clean reference binding drift")
    return lock


def parent_catalog(index, report, catalogs):
    require(index["status"] == "RUN_COMPLETE_BYTES_IDENTICAL" and index["cases"] == catalogs and
            index["completed_cases"] == [c["key"] for c in catalogs], "parent D1 exact catalog/order drift")
    require([c["key"] for c in report["cases"]] == [c["key"] for c in catalogs], "parent report case order")


def parent_binding(parent, lock, started):
    """Check the complete retained D1 seal plus the immutable D2 input subset."""
    require(parent.is_dir() and not parent.is_symlink(), "regular parent D1 directory required")
    manifest = read_json(parent / "artifact-manifest.json")
    require(manifest["experiment"] == d1.EXPERIMENT and
            manifest["files"] == d1.payload_inventory(parent), "parent D1 payload seal drift")
    remaining(started)
    report, index = read_json(parent / "report.json"), read_json(parent / "run-index.json")
    readback = read_json(parent / "readback.json")
    require(readback["status"] == "PASS" and readback["experiment"] == d1.EXPERIMENT and
            readback["DSP_executed"] is False and readback["models_executed"] is False and
            readback["report"] == descriptor(parent / "report.json") and
            readback["manifest"] == descriptor(parent / "artifact-manifest.json"), "parent D1 readback not bound")
    for phase in ("run", "analysis", "verify"):
        receipt = read_json(parent / (phase + "-phase.json"))
        require(receipt["status"] == "COMPLETE" and receipt["returncode"] == 0 and
                0 <= receipt["elapsed_seconds"] <= BUDGET and receipt["budget_seconds"] == BUDGET,
                "parent D1 phase/budget invalid: " + phase)
    catalogs = [entry["catalog"] for entry in lock["cases"]]
    require(report["status"] == "MEASUREMENT_VALID" and report["measurement_valid"] is True and
            report["case_count"] == 60 and report["matrix_totals"] == d1.TOTALS and
            report["models_executed"] is False and report["canonical_reports_recomputed"] is False,
            "parent D1 report not qualified")
    parent_catalog(index, report, catalogs)
    require(d1.catalog(parent / "originals/A", parent / "originals/C") == catalogs, "parent original catalog drift")
    identity = read_json(parent / "source/identity.json")
    build = read_json(parent / "build/build-manifest.json")
    require(report["source_revision"] == index["source_revision"] == identity["source_revision"] ==
            build["source_revision"] and report["source_tree"] == index["source_tree"] ==
            identity["source_tree"] == build["source_tree"], "fresh parent source identity mismatch")
    require(build["status"] == "BUILT" and build["experiment"] == d1.EXPERIMENT and
            build["base_sha"] == d1.BASE_SHA and build["production_source_unchanged"] is True,
            "parent plain production source drift")
    for name, expected in lock["D1_SOURCE_FILES"].items():
        require(identity["files"][name] == expected and descriptor(parent / "source" / name) == expected,
                "parent D1 implementation drift: " + name)
    for entry, measured in zip(lock["cases"], report["cases"]):
        case = entry["catalog"]
        remaining(started)
        for name, expected in entry["parent_taps"].items():
            path = safe(parent / "cases" / case["key"] / "taps", name)
            require(descriptor(path) == expected == measured["taps"][name],
                    "locked first-D1 tap differs: " + case["key"] + "/" + name)
        require(all(measured[k] == case[k] for k in
                    ("key", "group", "case_id", "profile", "scenario", "frames", "samples", "capture_only")),
                "parent report case metadata drift")
        require(measured["source_placement_metadata"] == case["dimensions"], "parent placement metadata drift")
        if entry["clean_near"] is not None:
            require(case["group"] == "A" and
                    descriptor(safe(parent / "originals/A", case["inputs"]["clean_near"])) == entry["clean_near"],
                    "locked clean-near reference differs")
        metrics = d1.metric_rows(parent / "cases" / case["key"] / "observed/metrics.jsonl", case["frames"])
        counts, events = d1.controls(parent / "cases" / case["key"] / "taps/control.csv", case, metrics)
        require(counts == measured["control_counts"] and events == measured["events"], "parent event trajectory drift")
    binding = {"first_parent": lock["first_parent"], "fresh_parent_source_revision": report["source_revision"],
               "fresh_parent_source_tree": report["source_tree"], "production_base_sha": d1.BASE_SHA,
               "report": descriptor(parent / "report.json"), "manifest": descriptor(parent / "artifact-manifest.json"),
               "readback": descriptor(parent / "readback.json"), "run_index": descriptor(parent / "run-index.json"),
               "build_manifest": descriptor(parent / "build/build-manifest.json"),
               "case_count": 60, "frames": lock["frames"], "samples": lock["samples"],
               "parent_payload_rehashed": True, "locked_inputs_equal_first_parent": True}
    remaining(started)
    return binding, report, build


def control_bytes(path, case):
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="ascii")))
    require(reader.fieldnames == d1.CONTROL_FIELDS, "parent control schema drift")
    rows = list(reader)
    require(len(rows) == case["frames"], "parent control frame count drift")
    resets = set()
    for event in case["input_events"]:
        require(event["kind"] in ("cli_discontinuity", "cli_echo_path_change"), "unfrozen parent event")
        if event["kind"] == "cli_discontinuity":
            require(event == {"frame": 300, "sample": 48000, "kind": "cli_discontinuity",
                              "flags": 2, "lost_frames": 4}, "discontinuity event drift")
            resets.add(event["frame"])
    payload, previous = bytearray(), None
    for frame, row in enumerate(rows):
        require(row["frame"] == str(frame) and row["agc_allow"] in ("0", "1"), "parent control index/flag drift")
        allow, reset = int(row["agc_allow"]), int(frame in resets)
        require(allow == int(not (int(row["far"]) and not int(row["dt"]))), "parent AGC rule drift")
        before, after = f32(float(row["gain_before"])), f32(float(row["gain_after"]))
        require(all(math.isfinite(x) and 0.25 <= x <= 8.0 for x in (before, after)), "invalid parent AGC state")
        require(same_float(before, 1.0 if frame == 0 or reset else previous), "parent AGC lifecycle drift")
        payload.extend(struct.pack("<IIff", allow, reset, before, after))
        previous = after
    require(len(payload) == case["frames"] * 16, "control record length")
    return bytes(payload)


def git_output(arguments, started):
    return subprocess.check_output(["git", *arguments], cwd=ROOT, timeout=min(30, remaining(started)),
                                   env=d1.process_environment())


def retained_sources(output, lock, started, parent_source):
    revision = git_output(["rev-parse", "HEAD"], started).decode().strip()
    tree = git_output(["rev-parse", "HEAD^{tree}"], started).decode().strip()
    require(re.fullmatch(r"[0-9a-f]{40}", revision) and revision == parent_source,
            "D2 driver and fresh D1 must use the actual current source")
    names = {*lock["D1_SOURCE_FILES"], SELF_NAME, C_NAME, TEST_NAME, LOCK_NAME, PLAN_NAME}
    sources = {}
    for name in sorted(names):
        raw = git_output(["show", revision + ":" + name], started)
        require((ROOT / name).read_bytes() == raw, "uncommitted D2 source: " + name)
        sources[name] = copy_exact(ROOT / name, safe(output / "source", name))
    return {"source_revision": revision, "source_tree": tree, "files": sources,
            "first_parent_source_revision": lock["first_parent"]["source_revision"],
            "fresh_parent_source_revision": parent_source, "python": sys.version}


def execute(command, directory, started):
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "command.json", command)
    environment = d1.process_environment()
    timeout, begin = min(BUDGET, remaining(started, 2.0)), time.monotonic()
    receipt = {"status": "FAILED", "returncode": None, "process_budget_seconds": BUDGET,
               "timeout_seconds": timeout, "environment": {"keys": sorted(environment), "LC_ALL": "C"}}
    try:
        with (directory / "stdout.txt").open("wb") as stdout, (directory / "stderr.txt").open("wb") as stderr:
            completed = subprocess.run(command, cwd=directory, env=environment, stdout=stdout,
                                       stderr=stderr, timeout=timeout, check=False)
        receipt.update(returncode=completed.returncode, status="COMPLETE" if completed.returncode == 0 else "FAILED")
    except subprocess.TimeoutExpired:
        receipt["status"] = "TIMEOUT"
        raise
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - begin
        write_json(directory / "execution.json", receipt)
    require(receipt["status"] == "COMPLETE" and receipt["elapsed_seconds"] <= timeout,
            "D2 command failed or exceeded budget: " + str(directory))
    remaining(started)


def worker_build(args):
    started, output, parent = time.monotonic(), args.output.resolve(), args.parent_result.resolve()
    lock = input_lock()
    binding, _, parent_build = parent_binding(parent, lock, started)
    copy_exact(ROOT / LOCK_NAME, output / "input-lock.json")
    write_json(output / "parent-binding.json", binding)
    identity = retained_sources(output, lock, started, binding["fresh_parent_source_revision"])
    build_dir = args.build_dir.resolve()
    require((build_dir / "build-manifest.json").read_bytes() ==
            (parent / "build/build-manifest.json").read_bytes(), "D1 execution build is not the retained parent build")
    plain = parent_build["builds"]["plain"]
    require(plain["source_revision"] == identity["source_revision"] and
            plain["build_info"]["source_revision"] == identity["source_revision"] and
            plain["build_info"]["fast_math"] == "0", "plain library source/float identity drift")
    proof = {}
    for name in ("library", "generated_header", "flags_make"):
        record = plain[name]
        source = safe(build_dir, record["path"])
        require(descriptor(source) == {k: record[k] for k in ("bytes", "sha256")} ==
                descriptor(safe(parent / "build", record["path"])), "plain build proof mismatch: " + name)
        destination = "proof/plain/" + record["path"]
        proof[destination] = copy_exact(source, safe(output, destination))
    compiler = Path(plain["compiler"]["path"])
    require(descriptor(compiler) == {k: plain["compiler"][k] for k in ("bytes", "sha256")}, "compiler identity drift")
    proof["proof/compiler"] = copy_exact(compiler, output / "proof/compiler")
    (output / "bin").mkdir()
    program = output / "bin/dualmic_gain_d2"
    depfile = output / "bin/dualmic_gain_d2.d"
    command = [str(compiler), *plain["definitions"], *plain["flags"], *plain["includes"],
               "-MMD", "-MF", str(depfile), str(output / "source" / C_NAME),
               str(safe(build_dir, plain["library"]["path"])), "-lm", "-o", str(program)]
    execute(command, output / "compile", started)
    dependencies = depfile.read_text(encoding="utf-8").replace("\\\n", " ")
    require(":" in dependencies, "compiler dependency inventory missing")
    dependencies = shlex.split(dependencies.split(":", 1)[1])
    require(str(output / "source" / C_NAME) in dependencies and dependencies, "C source missing from compile proof")
    dependency_records = []
    for number, name in enumerate(dict.fromkeys(dependencies)):
        path = Path(name).resolve()
        if path == (output / "source" / C_NAME).resolve():
            expected = identity["files"][C_NAME]
        elif path == safe(build_dir, plain["generated_header"]["path"]).resolve():
            expected = {k: plain["generated_header"][k] for k in ("bytes", "sha256")}
        else:
            relative = path.relative_to(safe(build_dir, plain["source_dir"]).resolve()).as_posix()
            require(relative in parent_build["source_files"], "untracked compile dependency")
            expected = descriptor(path)
            require(expected["sha256"] == parent_build["source_files"][relative], "parent source dependency changed")
        require(descriptor(path) == expected, "compile dependency changed")
        retained = "proof/dependencies/" + str(number) + "-" + path.name
        proof[retained] = copy_exact(path, safe(output, retained))
        dependency_records.append({"original_path": str(path), "retained_path": retained, **expected})
    for name, expected in parent_build["production_files"].items():
        require(digest(ROOT / name) == expected["sha256"], "production source changed: " + name)
        committed = git_output(["rev-parse", d1.BASE_SHA + ":" + name], started).decode().strip()
        require(committed == expected["git_blob"], "production blob differs from 4daa: " + name)
    identity["build_files"] = proof
    write_json(output / "source/identity.json", identity)
    manifest = {"schema_version": 1, "experiment": EXPERIMENT, "status": "BUILT",
                "source_revision": identity["source_revision"], "source_tree": identity["source_tree"],
                "fresh_parent_source_revision": binding["fresh_parent_source_revision"],
                "first_parent": lock["first_parent"], "base_sha": d1.BASE_SHA,
                "production_source_unchanged": True, "parent_build_manifest": binding["build_manifest"],
                "parent_plain": plain, "compiler": plain["compiler"], "command": command,
                "dependency_generation_flags": ["-MMD", "-MF", str(depfile)],
                "dependencies": dependency_records, "proof_files": proof,
                "program": {"path": "bin/dualmic_gain_d2", **descriptor(program)},
                "parent_source_archive": parent_build["source_archive"],
                "parent_source_archive_retained_in_parent": True,
                "DSP_or_model_executed": False}
    write_json(output / "build-manifest.json", manifest)
    remaining(started)


def verify_sources(output, lock):
    require((output / "input-lock.json").read_bytes() == (ROOT / LOCK_NAME).read_bytes(), "retained input lock changed")
    identity = read_json(output / "source/identity.json")
    expected_names = {*lock["D1_SOURCE_FILES"], SELF_NAME, C_NAME, TEST_NAME, LOCK_NAME, PLAN_NAME}
    require(set(identity["files"]) == expected_names and
            file_set(output / "source") == {*expected_names, "identity.json"}, "D2 source proof closure drift")
    for name, expected in identity["files"].items():
        require(descriptor(ROOT / name) == expected == descriptor(safe(output / "source", name)),
                "D2 measurement source drift: " + name)
    build = read_json(output / "build-manifest.json")
    require(build["status"] == "BUILT" and build["experiment"] == EXPERIMENT and
            build["source_revision"] == identity["source_revision"] and
            build["source_tree"] == identity["source_tree"] and build["production_source_unchanged"] is True and
            build["base_sha"] == d1.BASE_SHA, "D2 build identity drift")
    require(build["proof_files"] == identity["build_files"] and
            file_set(output / "proof") == {name[len("proof/"):] for name in build["proof_files"]},
            "D2 build proof closure drift")
    for name, expected in build["proof_files"].items():
        require(descriptor(safe(output, name)) == expected, "D2 build proof drift")
    program = build["program"]
    require(program["path"] == "bin/dualmic_gain_d2" and
            descriptor(safe(output, program["path"])) == {k: program[k] for k in ("bytes", "sha256")},
            "D2 executable identity drift")
    require(read_json(output / "compile/command.json") == build["command"], "retained compiler command differs")
    execution_receipt(output / "compile/execution.json")
    return identity, build


def worker_run(args):
    started, output, parent = time.monotonic(), args.output.resolve(), args.parent_result.resolve()
    lock = input_lock()
    binding, _, _ = parent_binding(parent, lock, started)
    require(binding == read_json(output / "parent-binding.json"), "parent changed after D2 build")
    identity, build = verify_sources(output, lock)
    executable = safe(output, build["program"]["path"])
    index = {"schema_version": 1, "experiment": EXPERIMENT, "status": "RUNNING",
             "source_revision": identity["source_revision"], "source_tree": identity["source_tree"],
             "parent_binding": binding, "cases": [entry["catalog"] for entry in lock["cases"]],
             "completed_cases": [], "DSP_scope": "original_AGC_only", "models_executed": False}
    write_json(output / "run-index.json", index)
    for entry in lock["cases"]:
        remaining(started)
        case = entry["catalog"]
        directory = safe(output / "cases", case["key"])
        directory.mkdir(parents=True, exist_ok=False)
        control = control_bytes(parent / "cases" / case["key"] / "taps/control.csv", case)
        (directory / "control.bin").write_bytes(control)
        taps = parent / "cases" / case["key"] / "taps"
        views = directory / "views"
        views.mkdir()
        command = [str(executable), "--profile", case["profile"], str(taps / "ns_output.f32le"),
                   str(taps / "agc_output.f32le"), str(directory / "control.bin"), str(views)]
        execute(command, directory / "execution", started)
        require((views / "replay_final.f32le").read_bytes() == (taps / "agc_output.f32le").read_bytes(),
                "original AGC replay was not byte exact: " + case["key"])
        index["completed_cases"].append(case["key"])
        write_json(output / "run-index.json", index)
    index["status"] = "RUN_COMPLETE_REPLAY_EXACT"
    write_json(output / "run-index.json", index)
    remaining(started)


def float_bytes(values):
    result = array("f", values)
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def differences(left, right):
    require(len(left) == len(right) and len(left) % 4 == 0, "view length mismatch")
    count, first = 0, None
    for sample, (a, b) in enumerate(zip(struct.iter_unpack("<I", left), struct.iter_unpack("<I", right))):
        if a != b:
            count += 1
            if first is None:
                first = {"frame": sample // HOP, "sample_in_frame": sample % HOP, "global_sample": sample,
                         "before_bits": "0x%08x" % a[0], "after_bits": "0x%08x" % b[0]}
    return count, first


def gain_observation(signal, before, allow, target_linear, limit):
    """Read-only float32 arithmetic audit, never an alternative state update."""
    energy, peak = f32(1e-12), 0.0
    for value in signal:
        energy = f32(energy + f32(value * value))
        peak = max(peak, abs(value))
    rms = f32(math.sqrt(f32(energy / HOP)))
    raw = f32(target_linear / f32(rms + f32(1e-6)))
    bounded = max(0.25, min(8.0, raw))
    target_cap = int(not allow and bounded > 1.0)
    target = 1.0 if target_cap else bounded
    alpha = f32(0.25 if target < before else 0.015)
    expected_after = f32(before + f32(alpha * f32(target - before)))
    gate = min(expected_after, 1.0) if not allow else expected_after
    peak_active = int(f32(peak * gate) > limit and peak > f32(1e-6))
    peak_limit = f32(limit / peak) if peak > f32(1e-6) else None
    applied = peak_limit if peak_active else gate
    floats = {"input_rms": rms, "input_peak": peak, "target_gain_raw": raw,
              "target_gain_bounded": bounded, "target_gain": target, "alpha": alpha,
              "expected_state_gain_after": expected_after, "gate_cap_gain": gate, "applied_gain": applied}
    if peak_limit is not None:
        floats["peak_limit_gain"] = peak_limit
    integers = {"target_gate_cap_active": target_cap,
                "output_gate_cap_active": int(not allow and expected_after > 1.0), "peak_cap_active": peak_active}
    return floats, integers


def audit_gain_observation(signal, before, after, allow, floats, integers):
    expected, flags = gain_observation(signal, before, allow, floats["target_linear"], floats["limiter_linear"])
    require(same_float(expected["expected_state_gain_after"], after), "observed state formula differs from parent")
    require(("peak_limit_gain" in expected) == ("peak_limit_gain" in floats), "peak limit applicability drift")
    for name, value in expected.items():
        require(name in floats and same_float(floats[name], value), "D2 diagnostic arithmetic mismatch: " + name)
    for name, value in flags.items():
        require(integers[name] == value, "D2 diagnostic control mismatch: " + name)
    return expected["gate_cap_gain"], expected["applied_gain"]


def trace_evidence(directory, parent_taps, case, controls, source_revision):
    views = directory / "views"
    require(file_set(views) == {name + ".f32le" for name in LANES} | {"gain.csv", "gain.json"},
            "D2 output view closure drift")
    receipt = read_json(views / "gain.json")
    require(receipt["schema_version"] == 1 and receipt["experiment"] == EXPERIMENT and
            receipt["status"] == "REPLAY_EXACT" and receipt["profile"] == case["profile"] and
            receipt["source_revision"] == source_revision and receipt["sample_format"] == "float32le" and
            receipt["frame_samples"] == HOP and receipt["offset_samples"] == HOP and
            receipt["input_frames"] == receipt["frames"] == receipt["agc_calls"] == case["frames"] and
            receipt["error_count"] == 0 and receipt["first_error"] == "" and receipt["first_mismatch"] is None,
            "D2 original AGC exact replay did not qualify")
    require(receipt["target_dbfs"] == {"call": -20, "assistant": -18}[case["profile"]] and
            receipt["limiter_dbfs"] == -2, "actual profile defaults changed")
    reader = csv.DictReader(io.StringIO((views / "gain.csv").read_text(encoding="ascii")))
    require(reader.fieldnames == TRACE_FIELDS, "D2 gain trace schema drift")
    rows = list(reader)
    require(len(rows) == case["frames"], "D2 gain trace frame count drift")
    values = {"pre_agc": d1.samples(parent_taps / "ns_output.f32le", "f", case["samples"])}
    raw = {"pre_agc": (parent_taps / "ns_output.f32le").read_bytes()}
    hashes = {}
    for name in LANES:
        path = views / (name + ".f32le")
        values[name] = d1.samples(path, "f", case["samples"])
        raw[name], hashes[name + ".f32le"] = path.read_bytes(), descriptor(path)
        lane = receipt["lanes"][name]
        require(lane == {"file": name + ".f32le", "frames": case["frames"], "samples": case["samples"],
                         "bytes": case["samples"] * 4, "offset_samples": HOP}, "D2 lane format drift")
    require(set(receipt["lanes"]) == set(LANES) and
            raw["replay_final"] == (parent_taps / "agc_output.f32le").read_bytes(), "D2 final/reference byte mismatch")
    counts = {"target_gate_frames": 0, "output_gate_frames": 0, "peak_limit_frames": 0, "clamped_samples": 0}
    reset_count = 0
    constants = None
    for frame, (row, record) in enumerate(zip(rows, struct.iter_unpack("<IIff", controls))):
        allow, reset, before, after = record
        ints = {name: int(row[name]) for name in INT_FIELDS}
        require(ints["frame"] == frame and ints["allow"] == allow and ints["reset"] == reset and
                all(ints[k] == 1 for k in MATCH_FIELDS) and all(ints[k] in (0, 1) for k in CAP_FIELDS) and
                0 <= ints["final_sample_clamp_count"] <= HOP, "D2 replay/trace control mismatch")
        floats = {name: f32(float(row[name])) for name in TRACE_FIELDS if name not in INT_FIELDS and row[name] != ""}
        require(all(math.isfinite(v) for v in floats.values()) and
                (row["peak_limit_gain"] == "") == (floats["input_peak"] <= f32(1e-6)), "invalid gain trace float")
        require(same_float(floats["state_gain_before"], before) and same_float(floats["reference_gain_before"], before) and
                all(same_float(floats[name], after) for name in
                    ("state_gain_after", "expected_state_gain_after", "reference_gain_after")), "D2 state trajectory mismatch")
        current_constants = (bits(floats["target_linear"]), bits(floats["limiter_linear"]))
        if constants is None:
            constants = current_constants
        require(current_constants == constants, "profile constants changed during continuous stream")
        first, last = frame * HOP, (frame + 1) * HOP
        signal = values["pre_agc"][first:last]
        gate, applied = audit_gain_observation(signal, before, after, allow, floats, ints)
        limit = floats["limiter_linear"]
        for lane, gain in (("state_only", after), ("gate_capped", gate), ("peak_capped", applied)):
            require(float_bytes(v * gain for v in signal) == raw[lane][first * 4:last * 4],
                    "D2 ordered view arithmetic mismatch: " + lane)
        peak_samples = values["peak_capped"][first:last]
        clamped = [max(-limit, min(limit, value)) for value in peak_samples]
        require(float_bytes(clamped) == raw["replay_final"][first * 4:last * 4], "final clamp formula mismatch")
        clamps = sum(not same_float(a, b) for a, b in zip(peak_samples, clamped))
        require(clamps == ints["final_sample_clamp_count"], "final clamp count mismatch")
        for lane in LANES:
            field = lane + "_peak"
            require(same_float(max(abs(v) for v in values[lane][first:last]), floats[field]), "view peak trace mismatch")
        for key, field in (("target_gate_frames", "target_gate_cap_active"), ("output_gate_frames", "output_gate_cap_active"),
                           ("peak_limit_frames", "peak_cap_active"), ("clamped_samples", "final_sample_clamp_count")):
            counts[key] += ints[field]
        reset_count += reset
    require(receipt["cap_counts"] == counts and receipt["reset_count"] == reset_count, "D2 cap/reset count mismatch")
    diff_counts, first_diffs = {}, {}
    for step, left, right in zip(STEPS, VIEWS, VIEWS[1:]):
        diff_counts[step], first_diffs[step] = differences(raw[left], raw[right])
    require(receipt["difference_sample_counts"] == diff_counts and receipt["first_differences"] == first_diffs,
            "D2 ordered difference ledger mismatch")
    for name in ("gain.csv", "gain.json"):
        hashes[name] = descriptor(views / name)
    return values, {"cap_counts": counts, "reset_count": reset_count, "first_differences": first_diffs,
                    "difference_sample_counts": diff_counts, "views": hashes,
                    "state_before_after_and_final_byte_exact": True, "ordered_view_arithmetic_byte_exact": True}


def execution_receipt(path):
    receipt = read_json(path)
    require(receipt["status"] == "COMPLETE" and receipt["returncode"] == 0 and
            0 <= receipt["elapsed_seconds"] <= receipt["timeout_seconds"] <= BUDGET and
            receipt["process_budget_seconds"] == BUDGET and
            set(receipt["environment"]["keys"]) <= {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"} and
            "LC_ALL" in receipt["environment"]["keys"] and receipt["environment"]["LC_ALL"] == "C",
            "D2 execution receipt/budget/environment drift")


def validate_execution(directory, case, build):
    command = read_json(directory / "execution/command.json")
    suffix = "/cases/" + case["key"]
    require(len(command) == 7 and command[0].endswith("/bin/dualmic_gain_d2") and
            command[3].endswith(suffix + "/taps/ns_output.f32le"), "D2 command path contract")
    run_root = Path(command[0][:-len("/bin/dualmic_gain_d2")])
    parent_root = Path(command[3][:-len(suffix + "/taps/ns_output.f32le")])
    expected = [str(run_root / build["program"]["path"]), "--profile", case["profile"],
                str(parent_root / "cases" / case["key"] / "taps/ns_output.f32le"),
                str(parent_root / "cases" / case["key"] / "taps/agc_output.f32le"),
                str(run_root / "cases" / case["key"] / "control.bin"), str(run_root / "cases" / case["key"] / "views")]
    require(command == expected, "D2 unfrozen command mutation")
    execution_receipt(directory / "execution/execution.json")


def analysis_payload(output, parent, started):
    lock = input_lock()
    binding, parent_report, parent_build = parent_binding(parent, lock, started)
    require(binding == read_json(output / "parent-binding.json"), "D2 bound parent drift")
    identity, build = verify_sources(output, lock)
    require(build["parent_plain"] == parent_build["builds"]["plain"] and
            build["parent_build_manifest"] == binding["build_manifest"] and
            identity["source_revision"] == identity["fresh_parent_source_revision"] == binding["fresh_parent_source_revision"] and
            identity["source_tree"] == binding["fresh_parent_source_tree"], "plain build/driver binding drift")
    index = read_json(output / "run-index.json")
    catalogs = [entry["catalog"] for entry in lock["cases"]]
    require(index["status"] == "RUN_COMPLETE_REPLAY_EXACT" and index["experiment"] == EXPERIMENT and
            index["cases"] == catalogs and index["completed_cases"] == [c["key"] for c in catalogs] and
            index["parent_binding"] == binding and index["source_revision"] == identity["source_revision"],
            "D2 incomplete run matrix/source")
    require(file_set(output / "cases") == {case["key"] + "/" + name for case in catalogs for name in
            ("control.bin", "execution/command.json", "execution/execution.json", "execution/stdout.txt",
             "execution/stderr.txt", "views/gain.csv", "views/gain.json", *("views/" + lane + ".f32le" for lane in LANES))},
            "D2 case/file closure drift")
    cases = []
    for entry, prior in zip(lock["cases"], parent_report["cases"]):
        remaining(started)
        case, reference = entry["catalog"], None
        directory = output / "cases" / case["key"]
        validate_execution(directory, case, build)
        taps = parent / "cases" / case["key"] / "taps"
        controls = control_bytes(taps / "control.csv", case)
        require((directory / "control.bin").read_bytes() == controls, "D2 control encoding drift")
        values, evidence = trace_evidence(directory, taps, case, controls, binding["fresh_parent_source_revision"])
        reason = "C_has_no_admitted_clean_near_reference" if case["group"] == "C" else "no_clean_near_reference"
        if case["group"] == "A" and case["inputs"]["clean_near"]:
            raw = d1.samples(safe(parent / "originals/A", case["inputs"]["clean_near"]), "h", case["samples"])
            reference = [float(value) / 32768.0 for value in raw]
        stages = {name: d1.measure_lane(values[name], HOP, case["samples"], reference, reason, True) for name in VIEWS}
        require(stages["pre_agc"] == prior["stages"]["ns_output"] and
                stages["replay_final"] == prior["stages"]["agc_output"], "D2 endpoint measurement differs from parent D1")
        changes = {step: d1.stage_delta(stages, left, right, "ordered_state_conditioned_" + step)
                   for step, left, right in zip(STEPS, VIEWS, VIEWS[1:])}
        cases.append({"key": case["key"], "group": case["group"], "case_id": case["case_id"],
                      "profile": case["profile"], "scenario": case["scenario"], "frames": case["frames"],
                      "samples": case["samples"], "capture_only": case["capture_only"],
                      "data_role": "disclosed-regression", "human_vad_labels": False,
                      "input_events": case["input_events"], "parent_events": prior["events"],
                      "parent_control_counts": prior["control_counts"], "parent_taps": entry["parent_taps"],
                      "control_binary": descriptor(directory / "control.bin"), **evidence,
                      "stages": stages, "ordered_conditional_changes": changes})
    aggregates = []
    for group in ("A", "C"):
        for profile in d1.PROFILES:
            for scenario in sorted({case["scenario"] for case in cases if case["group"] == group}):
                selected = [case for case in cases if (case["group"], case["profile"], case["scenario"]) ==
                            (group, profile, scenario)]
                changes = {}
                for step in STEPS:
                    scores = [case["ordered_conditional_changes"][step]["common"]["near_si_sdr_change_db"]
                              for case in selected if case["ordered_conditional_changes"][step]["common"]["near_si_sdr_change_db"] is not None]
                    changes[step] = {"count": len(scores), "min": min(scores) if scores else None,
                                     "median": statistics.median(scores) if scores else None, "max": max(scores) if scores else None}
                aggregates.append({"group": group, "profile": profile, "scenario": scenario, "cases": len(selected),
                                   "descriptive_ordered_conditional_si_sdr_changes_db": changes})
    remaining(started)
    return {"schema_version": 1, "experiment": EXPERIMENT, "status": "GAIN_DECOMPOSITION_VALID_NO_PROMOTION",
            "measurement_valid": True, "promotion_allowed": False, "candidate_selected": False,
            "models_executed": False, "canonical_reports_recomputed": False, "data_role": "disclosed-regression",
            "source_revision": identity["source_revision"], "source_tree": identity["source_tree"],
            "parent_binding": binding, "build_manifest": descriptor(output / "build-manifest.json"),
            "case_count": 60, "frames": lock["frames"], "samples": lock["samples"],
            "measurement_contract": {"sample_rate_hz": RATE, "frame_samples": HOP, "lane_offsets_samples": {name: HOP for name in VIEWS},
                "physical_common_span": "[0,N-160)", "windows": "all fixed one-second windows; final clipped at N-160",
                "methods": "unchanged D1 measure_lane/stage_delta; canonical si_sdr_span and D19 energy",
                "control_frame_shift": 0, "lag_search": False, "ordered_conditional_not_independent_contributions": True,
                "state_trajectory": "original state already includes original target gate; never written by views",
                "C_near_truth": "not scored", "phase_windows_are_human_vad": False,
                "intermediate_views_are_playable_outputs": False}, "aggregates": aggregates, "cases": cases}


def payload_inventory(output):
    return {name: descriptor(safe(output, name)) for name in sorted(file_set(output))
            if name != "artifact-manifest.json" and name not in VERIFY_FILES}


def worker_verify(args):
    started, output, parent = time.monotonic(), args.output.resolve(), args.parent_result.resolve()
    manifest = read_json(output / "artifact-manifest.json")
    require(manifest["experiment"] == EXPERIMENT and manifest["files"] == payload_inventory(output), "D2 payload seal drift")
    for phase in ("build", "run", "analysis"):
        receipt = read_json(output / (phase + "-phase.json"))
        require(receipt["status"] == "COMPLETE" and receipt["returncode"] == 0 and
                0 <= receipt["elapsed_seconds"] <= BUDGET and receipt["budget_seconds"] == BUDGET, "D2 phase/budget invalid")
    recomputed = analysis_payload(output, parent, started)
    require(recomputed == read_json(output / "report.json"), "D2 saved report differs from readback")
    write_json(output / "readback.json", {"schema_version": 1, "experiment": EXPERIMENT, "status": "PASS",
               "DSP_executed": False, "models_executed": False, "case_count": 60, "frames": 35916, "samples": 5746560,
               "report": descriptor(output / "report.json"), "manifest": descriptor(output / "artifact-manifest.json"),
               "parent_binding": read_json(output / "parent-binding.json")})
    remaining(started)


def supervise(args, phase):
    output, started = args.output.resolve(), time.monotonic()
    command = [sys.executable, str(Path(__file__).resolve()), "--worker-phase", phase,
               "--parent-result", str(args.parent_result.resolve()), "--output", str(output)]
    if phase == "build":
        command += ["--build-dir", str(args.build_dir.resolve())]
    status, code, error = "FAILED", None, None
    with (output / (phase + ".log")).open("wb") as log:
        child = subprocess.Popen(command, cwd=ROOT, env=d1.process_environment(), stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = child.wait(timeout=remaining(started, 2.0))
            status = "COMPLETE" if code == 0 else "FAILED"
        except subprocess.TimeoutExpired:
            status, error = "TIMEOUT", "frozen phase wall budget reached"
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait(timeout=1)
    receipt = {"schema_version": 1, "experiment": EXPERIMENT, "phase": phase, "status": status,
               "returncode": code, "command": command, "error": error, "terminal": True,
               "budget_seconds": BUDGET, "elapsed_seconds": time.monotonic() - started}
    path = output / (phase + "-phase.json")
    write_json(path, receipt)
    receipt["elapsed_seconds"] = time.monotonic() - started
    receipt["elapsed_scope"] = "through first phase receipt write; final write deadline checked"
    if receipt["elapsed_seconds"] > BUDGET:
        receipt["status"], receipt["error"] = "TIMEOUT", "phase finalization exceeded budget"
    write_json(path, receipt)
    if time.monotonic() - started > BUDGET:
        receipt.update(status="TIMEOUT", error="final phase write exceeded budget", elapsed_seconds=time.monotonic() - started)
        write_json(path, receipt)
    return receipt["status"] == "COMPLETE", started


def seal(output, started):
    manifest = {"schema_version": 1, "experiment": EXPERIMENT, "files": payload_inventory(output)}
    write_json(output / "artifact-manifest.json", manifest)
    receipt = read_json(output / "analysis-phase.json")
    receipt["elapsed_seconds"] = time.monotonic() - started
    receipt["elapsed_scope"] = "analysis through artifact hash/seal write; final writes deadline checked"
    if receipt["elapsed_seconds"] > BUDGET:
        receipt.update(status="TIMEOUT", error="artifact sealing exceeded analysis budget")
    write_json(output / "analysis-phase.json", receipt)
    manifest["files"]["analysis-phase.json"] = descriptor(output / "analysis-phase.json")
    write_json(output / "artifact-manifest.json", manifest)
    if time.monotonic() - started > BUDGET:
        receipt.update(status="TIMEOUT", error="final seal write exceeded analysis budget", elapsed_seconds=time.monotonic() - started)
        write_json(output / "analysis-phase.json", receipt)
        manifest["files"]["analysis-phase.json"] = descriptor(output / "analysis-phase.json")
        write_json(output / "artifact-manifest.json", manifest)
    return receipt["status"] == "COMPLETE"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("run", "verify"))
    parser.add_argument("--parent-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--worker-phase", choices=("build", "run", "analysis", "verify"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if args.worker_phase:
        try:
            if args.worker_phase == "build":
                worker_build(args)
            elif args.worker_phase == "run":
                worker_run(args)
            elif args.worker_phase == "analysis":
                started = time.monotonic()
                write_json(output / "report.json", analysis_payload(output, args.parent_result.resolve(), started))
                remaining(started)
            else:
                worker_verify(args)
            return 0
        except Exception as exc:
            write_json(output / (args.worker_phase + "-error.json"), {"experiment": EXPERIMENT,
                       "status": "MEASUREMENT_INVALID", "type": type(exc).__name__, "error": str(exc), "promotion_allowed": False})
            if args.worker_phase == "verify":
                write_json(output / "readback.json", {"experiment": EXPERIMENT, "status": "FAIL", "DSP_executed": False,
                           "models_executed": False, "error": str(exc)})
            print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
            return 1
    if args.command == "run":
        if args.build_dir is None:
            parser.error("run requires --build-dir from the same fresh D1 execution")
        require(not args.output.exists() and not args.output.is_symlink(), "new absent D2 output directory required")
        output.mkdir(parents=True, exist_ok=False)
        success = True
        for phase in ("build", "run", "analysis"):
            success, started = supervise(args, phase)
            if not success:
                break
        if success:
            success = seal(output, started)
        if not success:
            write_json(output / "measurement-invalid.json", {"experiment": EXPERIMENT, "status": "MEASUREMENT_INVALID",
                       "promotion_allowed": False, "reason": "Preserved phase errors are measurement failures; no quality conclusion."})
        print(d1.json.dumps({"experiment": EXPERIMENT, "status": "GAIN_DECOMPOSITION_VALID_NO_PROMOTION" if success else
                             "MEASUREMENT_INVALID", "output": str(output), "readback_required": success}, sort_keys=True))
        return 0 if success else 1
    if args.command == "verify":
        require(output.is_dir() and not args.output.is_symlink(), "existing D2 output required")
        success, _ = supervise(args, "verify")
        print(d1.json.dumps({"experiment": EXPERIMENT, "status": "PASS" if success else "FAIL", "DSP_executed": False}, sort_keys=True))
        return 0 if success else 1
    parser.error("choose run or verify")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(2)
