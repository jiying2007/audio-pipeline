#!/usr/bin/env python3
"""Bounded native engineering of the joint gain path, synthetic input only."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time

from contracts import ROOT, require, sha256
import test_webrtc_aec3_adapter as original
import test_webrtc_aec3_linear_tap_adapter as linear
import webrtc_aec3_gain_control_source as source
import webrtc_aec3_gain_control_trace as trace
import webrtc_aec3_selection_source as selection
from webrtc_aec3_ci import runtime_identity

PLAN = ROOT / ".github/research/frontend-evolution-v1/aec3-joint-gain-controlled-synthesis-v1.json"
FRAMES = 800
VALID_SAMPLES = 3 * FRAMES * 160
REQUESTED_SAMPLES = VALID_SAMPLES + 5 * 160
PROCESS_CALLS = 8
MAX_WALL_SECONDS = 120
STATUS = "PASS_GAIN_CONTROL_ENGINEERING_ONLY"
MODES = ("observe", "gain-observe", "gain-unity")
NAMES = ("baseline", "neutral", "unity", "reject-empty", "reject-force-linear",
         "reject-unknown", "reject-short", "reject-reset")
NEGATIVE = ("", "force-linear", "bad", "gain-unity", "gain-observe")


def fixed_inputs():
    _, small_render = original.signal(1, frames=FRAMES, seed=37)
    render = [8 * x for x in original.samples(small_render)]
    mic = [(render[i - 16] // 2 if i >= 16 else 0) +
           (((i * 19 + 629) % 4001) - 2000 if i < 48000 else 0)
           for i in range(len(render))]
    return original.pcm(mic), original.pcm(render)


def check_plan():
    plan = json.loads(PLAN.read_text())
    expected = {"frames_per_valid_call": FRAMES, "valid_calls": 3, "invalid_calls": 5,
                "valid_processed_samples": VALID_SAMPLES, "requested_capture_samples": REQUESTED_SAMPLES,
                "wall_seconds_max": MAX_WALL_SECONDS, "speech_calls": 0, "retries": 0,
                "signal": "seed37-render-times8-delay16-half-echo-near-buzz-first48000"}
    require(plan["engineering"] == expected and plan["speech_execution_authorized"] is False and
            plan["promotion_allowed"] is False, "engineering contract drift or speech authority")
    return expected


def raw_observation(folder, mode, mic):
    paths = {key: folder / value for key, value in linear.OUTPUT_FILES.items()}
    linear.inspect_outputs(paths, "factory-on", mic, None)
    meta = json.loads(paths["--metadata"].read_text())
    raw = (folder / "stderr.log").read_bytes()
    require(meta["aec3_synthesis_selection"]["mode"] == mode, "native mode receipt drift")
    if mode == "observe":
        require("aec3_joint_gain_control" not in meta and source.TRACE_KIND.encode() not in raw,
                "baseline unexpectedly emitted gain trace")
        parsed = {"selector": selection.parse_trace(raw, len(mic) // 2, "observe")}
    else:
        require(meta["aec3_joint_gain_control"] ==
                {"mode": mode, "support_blocks": [1525, 1976], "block_samples": 64,
                 "cng_imaginary_endpoint_policy": source.CNG_ENDPOINT_POLICY,
                 "gain_controlled_cng_and_ola_may_change": True, "promotion_allowed": False},
                "native gain control metadata drift")
        parsed = trace.parse_trace(raw, len(mic) // 2, mode)
    return {"final": paths["--output"].read_bytes(), "linear": paths["--linear-output"].read_bytes(),
            "parsed": parsed}


def verify_saved(output: Path, report: dict) -> dict:
    check_plan()
    require(len(report["calls"]) == PROCESS_CALLS and
            [row["name"] for row in report["calls"]] == list(NAMES), "gain engineering call order/count")
    mic, render = fixed_inputs()
    seen = []
    requested = processed = 0
    for index, row in enumerate(report["calls"]):
        folder = output / row["name"]
        mode = MODES[index] if index < 3 else NEGATIVE[index - 3]
        pair = (mic, render) if index < 3 else (mic[:320], render[:320])
        require((folder / "mic.pcm").read_bytes() == pair[0] and
                (folder / "render.pcm").read_bytes() == pair[1], "saved synthetic input drift")
        count = len(pair[0]) // 2
        requested += count
        start = json.loads((folder / "invocation-start.json").read_text())
        require(row["mode"] == start["mode"] == mode and
                row["command"] == start["command"] and
                row["requested_samples"] == start["requested_samples"] == count and
                row["started_monotonic_ns"] == start["started_monotonic_ns"] and
                row["finished_monotonic_ns"] > row["started_monotonic_ns"] and
                type(row["pid"]) is int and row["pid"] > 0, "saved invocation witness drift")
        paths = {key: folder / value for key, value in linear.OUTPUT_FILES.items()}
        if index < 3:
            require(row["exit_code"] == 0 and row["processed_samples"] == count, "valid engineering exit")
            require(row["files_sha256"] == {key: sha256(path.read_bytes()) for key, path in paths.items()},
                    "native output hashes drift")
            seen.append(raw_observation(folder, mode, pair[0]))
            processed += count
        else:
            raw = (folder / "stderr.log").read_bytes()
            require(row["exit_code"] == 2 and row["processed_samples"] == 0 and
                    all(not path.exists() for key, path in paths.items()
                        if key in ("--output", "--metadata", "--frame-times", "--linear-output")) and
                    source.TRACE_KIND.encode() not in raw and selection.TRACE_KIND.encode() not in raw,
                    "negative request entered DSP or created output")
    require(requested == REQUESTED_SAMPLES and processed == VALID_SAMPLES and
            report["requested_capture_samples"] == requested and report["valid_processed_samples"] == processed,
            "engineering budget drift")
    base, neutral, unity = seen
    require(base["final"] == neutral["final"] and
            base["linear"] == neutral["linear"] == unity["linear"] and
            base["parsed"]["selector"] == neutral["parsed"]["selector"],
            "neutral instrumentation or upstream linear output changed")
    comparison = trace.compare_arms(neutral["parsed"], unity["parsed"])
    require(comparison["nonunity_support_blocks"] > 0 and neutral["final"] != unity["final"],
            "synthetic support did not exercise a nontrivial gain intervention")
    # Block 1525 contributes first at sample (1525 + 1) * 64; retain causal prefix.
    require(neutral["final"][:1526 * 64 * 2] == unity["final"][:1526 * 64 * 2],
            "gain substitution affected samples before its first synthesis output")
    return comparison


def run(binary: Path, output: Path, build_receipt: Path, code_revision: str, env=None) -> dict:
    check_plan()
    require(not output.exists(), "fresh gain-control engineering output required")
    output.mkdir(parents=True)
    started = time.monotonic()
    deadline = started + MAX_WALL_SECONDS
    environment = dict(os.environ if env is None else env, LC_ALL="C")
    before = runtime_identity(binary, environment)
    report = {"schema_version": 1, "status": "FAIL", "experiment_id": source.EXPERIMENT,
              "code_revision": code_revision, "binary_sha256": sha256(binary.read_bytes()),
              "build_receipt_sha256": sha256(build_receipt.read_bytes()),
              "fixture_source_sha256": sha256(Path(__file__).read_bytes()),
              "runtime_identity": before, "calls": [], "failures": [],
              "valid_processed_samples": 0, "requested_capture_samples": 0,
              "acoustic_acceptance": False, "promotion_allowed": False,
              "speech_calls": 0}
    mic, render = fixed_inputs()
    try:
        for index, name in enumerate(NAMES):
            folder = output / name
            folder.mkdir()
            mode = MODES[index] if index < 3 else NEGATIVE[index - 3]
            pair = (mic, render) if index < 3 else (mic[:320], render[:320])
            (folder / "mic.pcm").write_bytes(pair[0])
            (folder / "render.pcm").write_bytes(pair[1])
            paths, args = linear.invocation(binary, folder, "factory-on")
            args += ["--aec3-synthesis-selection", mode]
            if name == "reject-reset":
                args += ["--reset-before-frame", "0"]
            count = len(pair[0]) // 2
            report["requested_capture_samples"] += count
            require(len(report["calls"]) < PROCESS_CALLS and
                    report["requested_capture_samples"] <= REQUESTED_SAMPLES and time.monotonic() < deadline,
                    "gain engineering invocation budget")
            row = {"name": name, "mode": mode, "command": args, "requested_samples": count,
                   "processed_samples": 0, "exit_code": None, "pid": None,
                   "started_monotonic_ns": time.monotonic_ns()}
            report["calls"].append(row)
            original.write_json(folder / "invocation-start.json", row)
            try:
                with (folder / "stdout.log").open("xb") as out, (folder / "stderr.log").open("xb") as err:
                    proc = subprocess.Popen(args, stdout=out, stderr=err, env=environment, start_new_session=True)
                    row["pid"] = proc.pid
                    try:
                        row["exit_code"] = proc.wait(timeout=deadline - time.monotonic())
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        row["exit_code"] = proc.wait()
                        raise ValueError("gain engineering timeout")
            finally:
                row["finished_monotonic_ns"] = time.monotonic_ns()
            require(row["exit_code"] == (0 if index < 3 else 2), "unexpected gain fixture exit: " + name)
            if index < 3:
                row["processed_samples"] = count
                report["valid_processed_samples"] += count
                row["files_sha256"] = {key: sha256(path.read_bytes()) for key, path in paths.items()}
        report["comparison"] = verify_saved(output, report)
        require(runtime_identity(binary, environment) == before and
                sha256(binary.read_bytes()) == report["binary_sha256"], "runtime/binary changed")
        report["status"] = STATUS
    except Exception as error:
        report["failures"].append(str(error))
        raise
    finally:
        report["wall_seconds"] = time.monotonic() - started
        if not (math.isfinite(report["wall_seconds"]) and 0 < report["wall_seconds"] <= MAX_WALL_SECONDS):
            report["status"] = "FAIL"
            report["failures"].append("wall time exceeded")
        original.write_json(output / "engineering.json", report)
    require(report["status"] == STATUS, "gain-control engineering failed")
    return report
