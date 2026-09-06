#!/usr/bin/env python3
"""Evaluate the frozen I009 Activity source candidate on explicit seed sets.

This measures the actual compiled pipeline, not a Python counterfactual. The
caller controls the seed role; this script never promotes a candidate or treats
an exposed seed set as confirmation.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import i004_ns_nonstationary_diagnostic as synth
import i006_agc_residual_floor_baseline as i006_base


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def build_probe(root: Path, output: Path) -> Path:
    build = output / "build"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    subprocess.run([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON", f"-DAP_BUILD_SOURCE_REVISION={revision}",
    ], check=True)
    subprocess.run(["cmake", "--build", str(build), "--target", "audio_pipeline", "--parallel"], check=True)
    probe = build / "i009_activity_candidate_probe"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(root / "include"), "-I" + str(root / "src"), "-I" + str(build / "generated"),
        str(root / "tests/validation/i006_agc_root_cause_probe.c"),
        str(build / "libaudio_pipeline.a"), "-lm", "-o", str(probe),
    ], check=True)
    return probe


def run_probe(probe: Path, case_dir: Path, mic: list[float], render: list[float]) -> list[dict]:
    mic_path = case_dir / "mic.pcm"
    render_path = case_dir / "render.pcm"
    synth.write_pcm(mic_path, mic)
    synth.write_pcm(render_path, render)
    completed = subprocess.run([str(probe), str(mic_path), str(render_path)], check=True,
                               text=True, capture_output=True)
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    require(rows, "I009 candidate probe produced no rows")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", required=True, help="comma-separated integers")
    parser.add_argument("--role", required=True,
                        choices=["fresh-development-candidate-gate", "regression-only"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    seeds = [int(v) for v in args.seeds.split(",")]
    require(len(seeds) == 3 and len(set(seeds)) == 3, "exactly three distinct seeds required")
    if args.role == "fresh-development-candidate-gate":
        require(seeds == [18109, 28109, 38109], "fresh Development candidate seeds drift")
    else:
        require(seeds == [17109, 27109, 37109], "regression seeds drift")

    contract = json.loads((root / "docs/program/iterations/I006-baseline.json").read_text())
    i006_base.validate_contract(contract)
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    probe = build_probe(root, output)
    warmup = int(contract["input_preconditions"]["warmup_frames"])
    min_near = int(contract["input_preconditions"]["min_near_active_frames"])
    min_far = int(contract["input_preconditions"]["min_pure_far_active_frames"])
    scenarios = ["pure-far-end-residual-low", "near-far-doubletalk", "near-far-weak-near"]
    cases: list[dict] = []
    input_failures: list[dict] = []
    gate_failures: list[dict] = []
    corpus = output / "corpus"
    corpus.mkdir()
    for seed in seeds:
        for scenario in scenarios:
            case_dir = corpus / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True)
            mic, render, _near, near_labels, far_labels, category = i006_base.generate_case(contract, scenario, seed)
            rows = run_probe(probe, case_dir, mic, render)
            (case_dir / "trace.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
            failures: list[str] = []
            inputs: list[str] = []
            if category == "near_far":
                active = [row for row in rows[warmup:]
                          if int(row["frame"]) < len(near_labels)
                          and near_labels[int(row["frame"])] != 0]
                if len(active) < min_near:
                    inputs.append("near_active_frames")
                far_fraction = sum(int(row["far_end_active"]) != 0 for row in active) / max(1, len(active))
                dt_fraction = sum(int(row["double_talk_active"]) != 0 for row in active) / max(1, len(active))
                if not inputs and far_fraction < 0.70:
                    failures.append("far_activity")
                if not inputs and dt_fraction < 0.35:
                    failures.append("double_talk_activity")
                metrics = {
                    "near_active_frames": len(active),
                    "far_active_fraction_on_near_active": far_fraction,
                    "double_talk_fraction_on_near_active": dt_fraction,
                }
            else:
                require(category == "pure_far_end", "candidate scenario category drift")
                active = [row for row in rows[warmup:]
                          if int(row["frame"]) < len(far_labels)
                          and far_labels[int(row["frame"])] != 0]
                if len(active) < min_far:
                    inputs.append("far_active_frames")
                far_fraction = sum(int(row["far_end_active"]) != 0 for row in active) / max(1, len(active))
                false_dt = sum(int(row["double_talk_active"]) != 0 for row in active) / max(1, len(active))
                if not inputs and far_fraction < 0.85:
                    failures.append("far_activity")
                if not inputs and false_dt > 0.0:
                    failures.append("false_double_talk")
                metrics = {
                    "far_active_frames": len(active),
                    "far_active_fraction": far_fraction,
                    "false_double_talk_fraction": false_dt,
                }
            if inputs:
                input_failures.append({"seed": seed, "scenario": scenario, "failures": inputs})
            if failures:
                gate_failures.append({"seed": seed, "scenario": scenario, "failures": failures})
            cases.append({"seed": seed, "scenario": scenario, "category": category,
                          "input_failures": inputs, "gate_failures": failures, "metrics": metrics})

    near = [case for case in cases if case["category"] == "near_far"]
    far = [case for case in cases if case["category"] == "pure_far_end"]
    near_passed = sum(not c["input_failures"] and not c["gate_failures"] for c in near)
    far_passed = sum(not c["input_failures"] and not c["gate_failures"] for c in far)
    report = {
        "schema_version": 1,
        "iteration_id": "I009",
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "role": args.role,
        "seeds": seeds,
        "candidate_search_performed": False,
        "threshold_tuning_performed": False,
        "cases": cases,
        "aggregate": {
            "partitions": 9,
            "near_far_partitions": 6,
            "near_far_passed": near_passed,
            "pure_far_partitions": 3,
            "pure_far_passed": far_passed,
            "input_failure_partitions": len(input_failures),
            "gate_failure_partitions": len(gate_failures),
        },
        "decision": "PASS" if not input_failures and near_passed == 6 and far_passed == 3 else "FAIL",
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "candidate-eval.json", report)
    manifest = {str(path.relative_to(output)): i006_base.sha256(path)
                for path in sorted(output.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1, "files": manifest})
    manifest["evidence-manifest.json"] = i006_base.sha256(output / "evidence-manifest.json")
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({"role": args.role, "decision": report["decision"],
                      "near_far_passed": near_passed, "pure_far_passed": far_passed,
                      "input_failures": len(input_failures)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
