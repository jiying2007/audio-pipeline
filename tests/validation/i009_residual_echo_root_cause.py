#!/usr/bin/env python3
"""I009 candidate-zero residual/echo rescue differential.

This evaluator does not change shipping code. It replays already-exposed I009
Development seeds and simulates one causal structural extension: preserve the
shipping raw mic/render DTD path and OR it with previous-frame AEC
residual/echo evidence after AEC convergence, using exactly the same Activity
ratio, instant multipliers, EMA constants, and hangover.
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


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def run_checked(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def build_probe(root: Path, output: Path) -> Path:
    build = output / "build"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    run_checked([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON", f"-DAP_BUILD_SOURCE_REVISION={revision}",
    ])
    run_checked(["cmake", "--build", str(build), "--target", "audio_pipeline", "--parallel"])
    probe = build / "i009_residual_echo_probe"
    run_checked([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(root / "include"), "-I" + str(root / "src"), "-I" + str(build / "generated"),
        str(root / "tests/validation/i009_residual_echo_probe.c"),
        str(build / "libaudio_pipeline.a"), "-lm", "-o", str(probe),
    ])
    return probe


def validate_contract(contract: dict, baseline_contract: dict, root: Path) -> dict:
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "I009", "I009 identity")
    require(contract.get("phase") == "activity-double-talk-residual-echo-differential", "I009 phase")
    require(contract.get("root_cause_id") == "activity-double-talk-near-evidence-after-echo-cancellation", "I009 root cause")
    require(contract.get("base_sha") == "317756d9feb17de5f7065b619e08dd7a77b9f166", "I009 exact base")
    require(contract.get("candidate_limit") == 0 and contract.get("confirmation_limit") == 0,
            "I009 differential must remain candidate-zero")
    require(contract.get("promotion_allowed") is False and contract.get("shipping_source_change_allowed") is False,
            "I009 differential cannot promote/change shipping")
    require(contract.get("data_role") == "already-exposed-development-root-cause-only", "I009 data role")
    require(contract.get("seeds") == [17109, 27109, 37109], "I009 exposed seeds")
    require(contract.get("scenarios") == [
        "pure-far-end-residual-low", "near-far-doubletalk", "near-far-weak-near"
    ], "I009 scenarios")
    baseline = contract["baseline_execution"]
    require(baseline["workflow_run_id"] == 34031305098 and baseline["artifact_id"] == 9988691434 and
            baseline["artifact_digest"] == "sha256:ab6f36bc7252a988ff5228230137436bf75ea500c6d9a884c8f8ddf5f5299229" and
            baseline["internal_sha256s_verified"] == 284 and baseline["gate_failure_partitions"] == 5,
            "I009 baseline evidence drift")
    rejected = contract["rejected_echo_normalized_execution"]
    require(rejected["workflow_run_id"] == 34031731756 and rejected["artifact_id"] == 9988834254 and
            rejected["artifact_digest"] == "sha256:3111f6acc2e851cd94d59520dad58f07d5aaf4c4ac7070621e083fe58e766a2e" and
            rejected["internal_sha256s_verified"] == 301 and rejected["near_far_passed"] == 6 and
            rejected["pure_far_passed"] == 0,
            "I009 rejected echo-normalized evidence drift")
    cf = contract["counterfactual"]
    require(cf["name"] == "shipping-raw-or-previous-residual-over-echo-v1", "counterfactual identity")
    require(cf["double_talk_ratio"] == 1.5 and cf["instant_on_multiplier"] == 0.90 and
            cf["instant_hold_multiplier"] == 0.72 and cf["double_talk_hangover_frames"] == 3 and
            cf["energy_attack_alpha"] == 0.35 and cf["energy_release_alpha"] == 0.08,
            "I009 existing Activity constants must remain unchanged")
    require(cf["new_numeric_thresholds"] is False and cf["parameter_search"] is False and
            cf["source_candidate"] is False, "I009 cannot tune/select here")
    require(contract["diagnostic_gates"]["near_far"] == {
        "min_counterfactual_double_talk_fraction_on_near_active": 0.35,
        "required_partitions_pass": 6,
    }, "near/far gate drift")
    require(contract["diagnostic_gates"]["pure_far"] == {
        "max_counterfactual_double_talk_fraction_on_far_active": 0.0,
        "required_partitions_pass": 3,
    }, "pure-far gate drift")
    require(all(value is False for value in contract["authority"].values()), "I009 authority must remain false")
    require(contract.get("product_qualification") == "DEFERRED_BY_SCOPE", "product boundary")

    i006_base.validate_contract(baseline_contract)
    g = baseline_contract["generator"]
    require(g["far_echo_delays_samples"] == [640, 960] and g["far_echo_gains_low"] == [0.16, 0.06] and
            g["near_scale_balanced"] == 1.30 and g["near_scale_weak"] == 0.72,
            "I009 inherited generator drift")
    activity = (root / "src/activity/ap_activity.c").read_text(encoding="utf-8")
    pipeline = (root / "src/core/ap_pipeline.c").read_text(encoding="utf-8")
    require("smoothed_ratio > s->double_talk_ratio" in activity and
            "instant_ratio > 0.90f * s->double_talk_ratio" in activity and
            "instant_ratio > 0.72f * s->double_talk_ratio" in activity,
            "shipping Activity predicates drift")
    require(pipeline.index("ap_activity_process(&pipeline->activity") <
            pipeline.index("ap_aec_backend_process(&pipeline->aec"),
            "Activity/AEC source order drift")
    return {
        "activity_source_sha256": i006_base.sha256(root / "src/activity/ap_activity.c"),
        "pipeline_source_sha256": i006_base.sha256(root / "src/core/ap_pipeline.c"),
        "aec_source_order": "Activity-before-AEC",
    }


def simulate(rows: list[dict], ratio: float, on_mult: float, hold_mult: float,
             hangover_frames: int) -> tuple[list[int], list[int]]:
    hangover = 0
    flags: list[int] = []
    rescue_on_flags: list[int] = []
    for row in rows:
        far = bool(int(row["far_end_active"]))
        raw_on = (float(row["raw_smoothed_ratio"]) > ratio and
                  float(row["raw_instant_ratio"]) > on_mult * ratio)
        raw_hold = float(row["raw_instant_ratio"]) > hold_mult * ratio
        ready = bool(int(row["previous_aec_converged"]))
        rescue_on = ready and (float(row["residual_echo_smoothed_ratio"]) > ratio and
                               float(row["residual_echo_instant_ratio"]) > on_mult * ratio)
        rescue_hold = ready and float(row["residual_echo_instant_ratio"]) > hold_mult * ratio
        dt_on = far and (raw_on or rescue_on)
        dt_hold = far and (raw_hold or rescue_hold)
        if dt_on:
            hangover = hangover_frames
        elif not dt_hold and hangover > 0:
            hangover -= 1
        flags.append(1 if far and hangover > 0 else 0)
        rescue_on_flags.append(1 if far and rescue_on else 0)
    return flags, rescue_on_flags


def run_probe(probe: Path, case_dir: Path, mic: list[float], render: list[float]) -> list[dict]:
    mic_path = case_dir / "mic.pcm"
    render_path = case_dir / "render.pcm"
    synth.write_pcm(mic_path, mic)
    synth.write_pcm(render_path, render)
    completed = subprocess.run([str(probe), str(mic_path), str(render_path)],
                               check=True, text=True, capture_output=True)
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    require(rows, "I009 residual/echo probe produced no rows")
    return rows


def percentile(values: list[float], q: float) -> float | None:
    return i006_base.percentile(values, q)


def summarize_near(rows: list[dict], labels: list[int], flags: list[int], rescue: list[int],
                   warmup: int, minimum_frames: int, minimum_fraction: float) -> tuple[dict, list[str], list[str]]:
    indices = [i for i, row in enumerate(rows[warmup:], start=warmup)
               if int(row["frame"]) < len(labels) and labels[int(row["frame"])] != 0]
    inputs: list[str] = []
    failures: list[str] = []
    if len(indices) < minimum_frames:
        inputs.append("near_active_frames")
    far_fraction = sum(int(rows[i]["far_end_active"]) != 0 for i in indices) / max(1, len(indices))
    current = sum(int(rows[i]["double_talk_active"]) != 0 for i in indices) / max(1, len(indices))
    counterfactual = sum(flags[i] != 0 for i in indices) / max(1, len(indices))
    rescue_fraction = sum(rescue[i] != 0 for i in indices) / max(1, len(indices))
    ready_indices = [i for i in indices if int(rows[i]["previous_aec_converged"]) != 0]
    current_misses = [i for i in ready_indices if int(rows[i]["double_talk_active"]) == 0]
    if not inputs and counterfactual < minimum_fraction:
        failures.append("counterfactual_double_talk_activity")
    return ({
        "near_active_frames": len(indices),
        "far_active_fraction_on_near_active": far_fraction,
        "current_double_talk_fraction": current,
        "counterfactual_double_talk_fraction": counterfactual,
        "rescue_on_fraction_on_near_active": rescue_fraction,
        "previous_aec_ready_fraction_on_near_active": len(ready_indices) / max(1, len(indices)),
        "current_miss_residual_echo_instant_ratio_p50": percentile([
            float(rows[i]["residual_echo_instant_ratio"]) for i in current_misses
        ], 0.50),
        "current_miss_residual_echo_smoothed_ratio_p50": percentile([
            float(rows[i]["residual_echo_smoothed_ratio"]) for i in current_misses
        ], 0.50),
    }, inputs, failures)


def summarize_far(rows: list[dict], labels: list[int], flags: list[int], rescue: list[int],
                  warmup: int, minimum_frames: int, maximum_fraction: float) -> tuple[dict, list[str], list[str]]:
    indices = [i for i, row in enumerate(rows[warmup:], start=warmup)
               if int(row["frame"]) < len(labels) and labels[int(row["frame"])] != 0]
    inputs: list[str] = []
    failures: list[str] = []
    if len(indices) < minimum_frames:
        inputs.append("far_active_frames")
    current = sum(int(rows[i]["double_talk_active"]) != 0 for i in indices) / max(1, len(indices))
    counterfactual = sum(flags[i] != 0 for i in indices) / max(1, len(indices))
    rescue_fraction = sum(rescue[i] != 0 for i in indices) / max(1, len(indices))
    ready_indices = [i for i in indices if int(rows[i]["previous_aec_converged"]) != 0]
    if not inputs and counterfactual > maximum_fraction:
        failures.append("counterfactual_false_double_talk")
    return ({
        "far_active_frames": len(indices),
        "current_false_double_talk_fraction": current,
        "counterfactual_false_double_talk_fraction": counterfactual,
        "rescue_on_fraction_on_far_active": rescue_fraction,
        "previous_aec_ready_fraction_on_far_active": len(ready_indices) / max(1, len(indices)),
        "residual_echo_instant_ratio_p95_when_ready": percentile([
            float(rows[i]["residual_echo_instant_ratio"]) for i in ready_indices
        ], 0.95),
        "residual_echo_smoothed_ratio_p95_when_ready": percentile([
            float(rows[i]["residual_echo_smoothed_ratio"]) for i in ready_indices
        ], 0.95),
    }, inputs, failures)


def self_test() -> None:
    rows = []
    for frame in range(80):
        rows.append({
            "far_end_active": 1,
            "previous_aec_converged": 1 if frame >= 50 else 0,
            "raw_smoothed_ratio": 1.0,
            "raw_instant_ratio": 1.0,
            "residual_echo_smoothed_ratio": 2.0,
            "residual_echo_instant_ratio": 2.0,
        })
    flags, rescue = simulate(rows, 1.5, 0.9, 0.72, 3)
    assert sum(flags[:50]) == 0 and sum(flags[50:]) == 30
    assert sum(rescue) == 30
    print(json.dumps({"result": "PASS", "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--i006-contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return 0
    require(args.contract and args.i006_contract and args.output, "contract/i006-contract/output required")
    root = Path(__file__).resolve().parents[2]
    contract = load_json(args.contract)
    baseline_contract = load_json(args.i006_contract)
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"I009 exact base drift: {current}")
    source_contract = validate_contract(contract, baseline_contract, root)

    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    probe = build_probe(root, output)
    corpus = output / "corpus"
    corpus.mkdir()
    pre = contract["input_preconditions"]
    warmup = int(pre["warmup_frames"])
    min_trace = int(pre["min_trace_frames"])
    min_near = int(pre["min_near_active_frames"])
    min_far = int(pre["min_far_active_frames"])
    cf = contract["counterfactual"]
    near_min = float(contract["diagnostic_gates"]["near_far"]["min_counterfactual_double_talk_fraction_on_near_active"])
    far_max = float(contract["diagnostic_gates"]["pure_far"]["max_counterfactual_double_talk_fraction_on_far_active"])

    cases: list[dict] = []
    input_failures: list[dict] = []
    gate_failures: list[dict] = []
    for seed in contract["seeds"]:
        for scenario in contract["scenarios"]:
            case_dir = corpus / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True)
            mic, render, near, near_labels, far_labels, category = i006_base.generate_case(
                baseline_contract, scenario, int(seed))
            synth.write_pcm(case_dir / "near-clean.pcm", near)
            (case_dir / "near-labels.json").write_text(json.dumps(near_labels) + "\n", encoding="utf-8")
            (case_dir / "far-labels.json").write_text(json.dumps(far_labels) + "\n", encoding="utf-8")
            rows = run_probe(probe, case_dir, mic, render)
            if len(rows) < min_trace:
                input_failures.append({"seed": seed, "scenario": scenario, "reason": "trace_too_short"})
            flags, rescue = simulate(rows, float(cf["double_talk_ratio"]),
                                     float(cf["instant_on_multiplier"]),
                                     float(cf["instant_hold_multiplier"]),
                                     int(cf["double_talk_hangover_frames"]))
            for index, row in enumerate(rows):
                row["counterfactual_double_talk_active"] = flags[index]
                row["residual_echo_rescue_on"] = rescue[index]
            (case_dir / "trace.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
            if category == "near_far":
                metrics, inputs, failures = summarize_near(
                    rows, near_labels, flags, rescue, warmup, min_near, near_min)
            else:
                require(category == "pure_far_end", "I009 differential scenario category drift")
                metrics, inputs, failures = summarize_far(
                    rows, far_labels, flags, rescue, warmup, min_far, far_max)
            if inputs:
                input_failures.append({"seed": seed, "scenario": scenario, "failures": inputs})
            if failures:
                gate_failures.append({"seed": seed, "scenario": scenario, "failures": failures})
            cases.append({
                "seed": seed, "scenario": scenario, "category": category,
                "input_failures": inputs, "gate_failures": failures, "metrics": metrics,
            })

    near = [c for c in cases if c["category"] == "near_far"]
    far = [c for c in cases if c["category"] == "pure_far_end"]
    require(len(near) == 6 and len(far) == 3, "I009 partition drift")
    near_passed = sum(not c["input_failures"] and not c["gate_failures"] for c in near)
    far_passed = sum(not c["input_failures"] and not c["gate_failures"] for c in far)
    if input_failures:
        decision = "INPUT_INVALID_REVIEW_REQUIRED"
    elif near_passed == 6 and far_passed == 3:
        decision = "RESIDUAL_ECHO_RESCUE_SUPPORTED_REVIEW_REQUIRED"
    else:
        decision = "RESIDUAL_ECHO_RESCUE_NOT_SUPPORTED_REVIEW_REQUIRED"

    report = {
        "schema_version": 1,
        "iteration_id": "I009",
        "phase": contract["phase"],
        "root_cause_id": contract["root_cause_id"],
        "source_sha": current,
        "authority": "candidate-zero-exposed-development-residual-echo-only",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "candidate_search_performed": False,
        "parameter_tuning_performed": False,
        "shipping_source_changed": False,
        "promotion_allowed": False,
        "source_contract": source_contract,
        "probe_sha256": i006_base.sha256(probe),
        "cases": cases,
        "aggregate": {
            "partitions": len(cases),
            "near_far_partitions": 6,
            "near_far_passed": near_passed,
            "pure_far_partitions": 3,
            "pure_far_passed": far_passed,
            "input_failure_partitions": len(input_failures),
            "gate_failure_partitions": len(gate_failures),
        },
        "decision": decision,
        "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
        "next_step": (
            "review residual/echo structural evidence before any explicit bounded source-candidate contract"
            if decision == "RESIDUAL_ECHO_RESCUE_SUPPORTED_REVIEW_REQUIRED" else
            "do not implement this residual/echo rescue as a source candidate; continue mechanism review"
        ),
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "root-cause-result.json", report)
    manifest = {str(path.relative_to(output)): i006_base.sha256(path)
                for path in sorted(output.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1, "source_sha": current, "files": manifest})
    manifest["evidence-manifest.json"] = i006_base.sha256(output / "evidence-manifest.json")
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({
        "decision": decision,
        "partitions": len(cases),
        "near_far_passed": near_passed,
        "pure_far_passed": far_passed,
        "input_failures": len(input_failures),
        "candidate_limit": 0,
        "confirmation_limit": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
