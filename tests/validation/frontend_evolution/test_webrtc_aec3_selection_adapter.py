#!/usr/bin/env python3
"""Bounded real-binary selection engineering; synthetic inputs only."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import test_webrtc_aec3_adapter as original
import test_webrtc_aec3_linear_tap_adapter as linear
import webrtc_aec3_selection_source as selection
from contracts import require, sha256
from webrtc_aec3_ci import runtime_identity

VALID_SAMPLES = 64000
REQUESTED_SAMPLES = 321280
PROCESS_CALLS = 14
MAX_WALL_SECONDS = 120


def run(binary: Path, output: Path, build_receipt: Path, code_revision: str, env=None) -> dict:
    require(not output.exists(), "fresh selection engineering output required")
    output.mkdir(parents=True)
    started, deadline = time.monotonic(), time.monotonic() + MAX_WALL_SECONDS
    environment = dict(os.environ if env is None else env, LC_ALL="C")
    before = runtime_identity(binary, environment)
    report = {"schema_version": 1, "status": "FAIL", "experiment_id": selection.EXPERIMENT,
              "code_revision": code_revision, "binary_sha256": sha256(binary.read_bytes()),
              "build_receipt_sha256": sha256(build_receipt.read_bytes()),
              "fixture_source_sha256": sha256(Path(__file__).read_bytes()),
              "runtime_identity": before, "calls": [], "checks": [], "failures": [],
              "valid_processed_samples": 0, "requested_capture_samples": 0,
              "acoustic_acceptance": False, "promotion_allowed": False}

    def invoke(name, mic, render, mode, overrides=None, extra=None, valid=True, channels=1):
        directory = output / name
        directory.mkdir()
        (directory / "mic.pcm").write_bytes(mic)
        (directory / "render.pcm").write_bytes(render)
        paths, args = linear.invocation(binary, directory, "factory-on", overrides=overrides)
        if mode is not None:
            args += ["--aec3-synthesis-selection", mode]
        args += extra or []
        requested = len(mic) // (2 * channels)
        report["requested_capture_samples"] += requested
        require(len(report["calls"]) < PROCESS_CALLS and
                report["requested_capture_samples"] <= REQUESTED_SAMPLES, "selection engineering request budget")
        begin = time.monotonic()
        require(begin < deadline, "selection engineering wall budget")
        row = {"name": name, "mode": mode, "command": args, "requested_samples": requested,
               "exit_code": None, "elapsed_seconds": None, "processed_samples": 0,
               "process_started": False, "pid": None, "started_monotonic_ns": time.monotonic_ns()}
        report["calls"].append(row)
        original.write_json(directory / "invocation-start.json",
                            {"name": name, "mode": mode, "command": args, "environment": environment,
                             "requested_samples": requested, "started_monotonic_ns": row["started_monotonic_ns"]})
        try:
            with (directory / "stdout.log").open("xb") as out, (directory / "stderr.log").open("xb") as err:
                process = subprocess.Popen(args, stdout=out, stderr=err, env=environment, start_new_session=True)
                row["pid"], row["process_started"] = process.pid, True
                try:
                    row["exit_code"] = process.wait(timeout=deadline - time.monotonic())
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    row["exit_code"] = process.wait()
                    raise ValueError("selection engineering wall budget exhausted")
        finally:
            row["finished_monotonic_ns"] = time.monotonic_ns()
            row["elapsed_seconds"] = time.monotonic() - begin
        code = row["exit_code"]
        if not valid:
            require(code == 2, "invalid selection contract was not rejected before DSP: " + name)
            require(not any(paths[key].exists() for key in ("--output", "--metadata", "--frame-times", "--linear-output")),
                    "invalid selection contract created processing outputs: " + name)
            require(selection.TRACE_KIND not in (directory / "stderr.log").read_text(),
                    "invalid contract entered selection DSP: " + name)
            return None
        require(code == 0, "selection engineering native execution failed: " + name)
        linear.inspect_outputs(paths, "factory-on", mic, None)
        row["processed_samples"] = requested
        report["valid_processed_samples"] += requested
        require(report["valid_processed_samples"] <= VALID_SAMPLES, "selection engineering processed budget")
        stderr = (directory / "stderr.log").read_bytes()
        metadata = json.loads(paths["--metadata"].read_text())
        trace = None
        if mode is None:
            require(selection.TRACE_KIND not in stderr.decode() and "aec3_synthesis_selection" not in metadata,
                    "default path unexpectedly emitted selection observation")
        else:
            trace = selection.parse_trace(stderr, requested, mode)
            require(metadata["aec3_synthesis_selection"]["mode"] == mode and
                    metadata["aec3_synthesis_selection"]["promotion_allowed"] is False,
                    "selection metadata missing explicit mode or scope")
        row["files_sha256"] = {key: sha256(path.read_bytes()) for key, path in paths.items()}
        return {"final": paths["--output"].read_bytes(), "linear": paths["--linear-output"].read_bytes(),
                "trace": trace}

    try:
        mic, render = original.signal(1, frames=80, seed=37)
        off = invoke("off", mic, render, None)
        observed = invoke("observe", mic, render, "observe")
        forced = invoke("force-linear", mic, render, "force-linear")
        repeat = invoke("observe-repeat", mic, render, "observe")
        require(off["final"] == observed["final"] == repeat["final"] and
                off["linear"] == observed["linear"] == repeat["linear"] == forced["linear"],
                "observation neutrality, repeat determinism or force linear invariance failed")
        require(observed["trace"] == repeat["trace"] and
                [{k: r[k] for k in ("source_linear", "gain_bits", "high_bands_gain_bits", "dominant_nearend_after_gain")}
                 for r in observed["trace"]] ==
                [{k: r[k] for k in ("source_linear", "gain_bits", "high_bands_gain_bits", "dominant_nearend_after_gain")}
                 for r in forced["trace"]], "selection source state or suppression control changed")
        require(any(not r["source_linear"] for r in observed["trace"]) and
                any(r["forced"] for r in forced["trace"]) and
                forced["final"] != observed["final"],
                "synthetic intervention did not exercise a real Y to E output change")
        report["checks"].extend(("observer-final-and-tap-byte-neutrality", "repeat-byte-and-trace-determinism",
                                "force-only-synthesis-source-with-invariant-linear-and-selector-state",
                                "real-nontrivial-Y-to-E-intervention"))
        prefix_mic, prefix_render = original.signal(1, frames=40, seed=71)
        changed_mic, changed_render = original.signal(1, frames=20, seed=911)
        future_a = invoke("future-a", prefix_mic, prefix_render, "observe")
        future_b = invoke("future-b", prefix_mic[:6400] + changed_mic,
                          prefix_render[:6400] + changed_render, "observe")
        require(future_a["final"][:6400] == future_b["final"][:6400] and
                future_a["linear"][:12800] == future_b["linear"][:12800] and
                future_a["trace"][:50] == future_b["trace"][:50],
                "same-prefix outputs depend on future suffix")
        report["checks"].append("causal-same-prefix-different-future")
        short_mic, short_render = original.signal(1, frames=1, seed=13)
        invoke("reject-empty", short_mic, short_render, "", valid=False)
        invoke("reject-unknown", short_mic, short_render, "bad", valid=False)
        invoke("reject-duplicate", short_mic, short_render, "observe",
               extra=["--aec3-synthesis-selection", "observe"], valid=False)
        invoke("reject-apm", short_mic, short_render, "observe", overrides={"--mode": "apm"}, valid=False)
        two_mic, _ = original.signal(2, frames=1, seed=13)
        invoke("reject-two-channel", two_mic, short_render, "observe",
               overrides={"--mic-channels": "2", "--channel-map": "0,1"}, valid=False, channels=2)
        invoke("reject-factory-off", short_mic, short_render, "observe",
               overrides={"--aec3-export-mode": "factory-off", "--linear-output": None}, valid=False)
        invoke("reject-reset", short_mic, short_render, "observe",
               extra=["--reset-before-frame", "0"], valid=False)
        invoke("reject-overlength", bytes(1601 * 160 * 2), bytes(1601 * 160 * 2),
               "observe", valid=False)
        report["checks"].append("eight-contract-rejections-before-DSP")
        require(len(report["calls"]) == PROCESS_CALLS and
                report["valid_processed_samples"] == VALID_SAMPLES and
                report["requested_capture_samples"] == REQUESTED_SAMPLES, "exact engineering invocation budget")
        after = runtime_identity(binary, environment)
        require(after == before and sha256(binary.read_bytes()) == report["binary_sha256"],
                "binary or runtime identity changed during engineering")
        report["checks"].extend(("exact-fixed-process-and-input-budgets", "runtime-and-binary-stable"))
        report["status"] = "PASS_SELECTION_ENGINEERING_ONLY"
    except Exception as error:
        report["failures"].append(str(error))
        raise
    finally:
        report["wall_seconds"] = time.monotonic() - started
        if not (math.isfinite(report["wall_seconds"]) and 0 < report["wall_seconds"] <= MAX_WALL_SECONDS):
            report["status"] = "FAIL"
            report["failures"].append("wall time exceeded")
        original.write_json(output / "engineering.json", report)
    require(report["status"] == "PASS_SELECTION_ENGINEERING_ONLY", "selection engineering failed")
    return report


def verify_saved(output: Path, report: dict) -> None:
    """Regenerate tiny inputs and check all native evidence, without execution."""
    names = ("off", "observe", "force-linear", "observe-repeat", "future-a", "future-b",
             "reject-empty", "reject-unknown", "reject-duplicate", "reject-apm",
             "reject-two-channel", "reject-factory-off", "reject-reset", "reject-overlength")
    require([r["name"] for r in report["calls"]] == list(names), "engineering call identity/order changed")
    base = original.signal(1, frames=80, seed=37)
    future = original.signal(1, frames=40, seed=71)
    tail = original.signal(1, frames=20, seed=911)
    short = original.signal(1, frames=1, seed=13)
    pair = original.signal(2, frames=1, seed=13)
    inputs = [base] * 4 + [future, (future[0][:6400] + tail[0], future[1][:6400] + tail[1])]
    inputs += [short] * 4 + [(pair[0], short[1]), short, short, (bytes(1601 * 320), bytes(1601 * 320))]
    observed = {}
    processed, requested = 0, 0
    for index, (row, expected) in enumerate(zip(report["calls"], inputs)):
        folder = output / row["name"]
        mic, render = (folder / "mic.pcm").read_bytes(), (folder / "render.pcm").read_bytes()
        require((mic, render) == expected, "saved synthetic input differs from fixed generator")
        channels = 2 if row["name"] == "reject-two-channel" else 1
        count = len(mic) // (2 * channels)
        requested += count
        start = json.loads((folder / "invocation-start.json").read_text())
        require(start["name"] == row["name"] and start["mode"] == row["mode"] and
                start["command"] == row["command"] and start["requested_samples"] == count and
                start["started_monotonic_ns"] == row["started_monotonic_ns"] and
                type(row["started_monotonic_ns"]) is int and
                type(row["finished_monotonic_ns"]) is int and
                row["finished_monotonic_ns"] > row["started_monotonic_ns"] and
                row["process_started"] is True and type(row["pid"]) is int and row["pid"] > 0,
                "saved engineering invocation witness mismatch")
        require(row["requested_samples"] == count and
                type(row["elapsed_seconds"]) in (int, float) and math.isfinite(row["elapsed_seconds"]) and
                0 <= row["elapsed_seconds"] <= MAX_WALL_SECONDS, "saved invocation duration/count")
        paths = {key: folder / value for key, value in linear.OUTPUT_FILES.items()}
        if index >= 6:
            require(row["exit_code"] == 2 and row["processed_samples"] == 0 and
                    not any(paths[key].exists() for key in ("--output", "--metadata", "--frame-times", "--linear-output")),
                    "saved invalid invocation contains DSP processing outputs")
            stderr = (folder / "stderr.log").read_text()
            error = json.loads(stderr.strip())
            require(error["status"] == "ERROR" and error["exit_code"] == 2 and error["error"] and
                    selection.TRACE_KIND not in stderr, "saved invalid invocation error evidence")
            continue
        processed += count
        require(row["exit_code"] == 0 and row["processed_samples"] == count and
                row["files_sha256"] == {key: sha256(path.read_bytes()) for key, path in paths.items()},
                "saved valid invocation byte bindings")
        linear.inspect_outputs(paths, "factory-on", mic, None)
        mode = None if row["name"] == "off" else ("force-linear" if row["name"] == "force-linear" else "observe")
        require(row["mode"] == mode, "saved selection invocation mode")
        stderr = (folder / "stderr.log").read_bytes()
        meta = json.loads(paths["--metadata"].read_text())
        if mode is None:
            require(selection.TRACE_KIND not in stderr.decode() and "aec3_synthesis_selection" not in meta,
                    "off path emitted observation")
            trace = None
        else:
            trace = selection.parse_trace(stderr, count, mode)
            require(meta["aec3_synthesis_selection"]["mode"] == mode and
                    meta["aec3_synthesis_selection"]["promotion_allowed"] is False, "saved native explicit mode")
        observed[row["name"]] = {"final": paths["--output"].read_bytes(), "linear": paths["--linear-output"].read_bytes(),
                                 "trace": trace}
    require(processed == VALID_SAMPLES and requested == REQUESTED_SAMPLES, "saved engineering budget total")
    off, obs, forced, repeat = (observed[name] for name in names[:4])
    require(off["final"] == obs["final"] == repeat["final"] and
            off["linear"] == obs["linear"] == forced["linear"] == repeat["linear"] and
            obs["trace"] == repeat["trace"], "saved neutrality/determinism/linear invariant")
    stable = ("source_linear", "gain_bits", "high_bands_gain_bits", "dominant_nearend_after_gain")
    require([{k: r[k] for k in stable} for r in obs["trace"]] ==
            [{k: r[k] for k in stable} for r in forced["trace"]] and
            any(r["forced"] for r in forced["trace"]) and forced["final"] != obs["final"],
            "saved intervention did not preserve controls or exercise output")
    a, b = observed["future-a"], observed["future-b"]
    require(a["final"][:6400] == b["final"][:6400] and a["linear"][:12800] == b["linear"][:12800] and
            a["trace"][:50] == b["trace"][:50], "saved future-prefix causality")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-receipt", required=True, type=Path)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    run(args.binary, args.output, args.build_receipt, args.code_revision)


if __name__ == "__main__":
    main()
