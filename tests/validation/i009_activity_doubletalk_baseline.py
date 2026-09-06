#!/usr/bin/env python3
"""I009 fresh Development baseline for Activity double-talk admission.

This evaluator deliberately separates I006 inherited/exposed evidence from new
I009 Development data. It measures the current shipping Activity predicates on
fresh deterministic seeds, but cannot tune thresholds, select a candidate,
consume confirmation, promote a release, or claim Product Qualification.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import i004_ns_nonstationary_diagnostic as synth
import i006_agc_residual_floor_baseline as i006_base
import i006_agc_root_cause_differential as i006_root


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def validate_contract(contract: dict, inherited: dict, i006_contract: dict, root: Path) -> dict:
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "I009", "I009 identity")
    require(contract.get("phase") == "activity-double-talk-baseline", "I009 phase")
    require(contract.get("root_cause_id") == "activity-double-talk-ratio-admission", "I009 root cause")
    require(contract.get("base_sha") == "dd3e541c740640412c9b8b76c77cee269563e5b8", "I009 exact main")
    require(contract.get("candidate_limit") == 0 and contract.get("confirmation_limit") == 0,
            "I009 baseline must remain candidate-zero")
    require(contract.get("promotion_allowed") is False and contract.get("shipping_source_change_allowed") is False,
            "I009 baseline cannot promote or change shipping")
    require(contract.get("data_role") == "development", "I009 source role")
    require(contract.get("seeds") == [17109, 27109, 37109] and len(set(contract["seeds"])) == 3,
            "I009 fresh Development seeds")
    require(not set(contract["seeds"]) & {16107, 26107, 36107}, "I009 seeds overlap inherited I006 evidence")
    require(contract.get("scenarios") == ["near-far-doubletalk", "near-far-weak-near"],
            "I009 frozen scenarios")
    require(contract.get("seconds") == 8.0, "I009 duration")
    require(float(contract["frozen_gate"]["min_double_talk_fraction_on_near_active"]) == 0.35,
            "I009 gate must remain inherited frozen 0.35")
    require(all(value is False for value in contract["authority"].values()), "I009 baseline authority must remain false")
    require(contract.get("product_qualification") == "DEFERRED_BY_SCOPE", "I009 product boundary")

    require(inherited.get("schema_version") == 1 and inherited.get("iteration_id") == "I009", "I009 inherited identity")
    require(inherited.get("phase") == "inherited-root-cause-context", "I009 inherited phase")
    require(inherited.get("root_cause_id") == contract["root_cause_id"], "I009 inherited root cause mismatch")
    require(inherited.get("authority") == "already-observed-regression-root-cause-context-only",
            "I009 inherited authority")
    require(inherited.get("may_be_independent_confirmation") is False and
            inherited.get("may_be_candidate_selection_data") is False and
            inherited.get("may_authorize_threshold_search") is False and
            inherited.get("may_authorize_shipping_change") is False,
            "I009 inherited evidence cannot gain authority")
    differential = inherited["root_cause_differential"]
    require(differential["workflow_run_id"] == 34020771042 and differential["artifact_id"] == 9985408103,
            "I009 inherited root-cause identity")
    require(differential["internal_sha256s_verified"] == 283 and differential["cases"] == 6,
            "I009 inherited root-cause evidence")
    require(differential["classification_distribution"] == {
        "DT_SMOOTHED_RATIO_GATE_LIMIT": 3,
        "DT_BOTH_RATIO_GATES_LIMIT": 3,
        "DT_INSTANT_RATIO_GATE_LIMIT": 0,
        "DT_NOT_EXPLAINED_BY_CURRENT_RATIO_GATES": 0,
    }, "I009 inherited classification drift")

    i006_base.validate_contract(i006_contract)
    gen = contract["generator_contract"]
    frozen = i006_contract["generator"]
    require(gen["source"] == "tests/validation/i006_agc_residual_floor_baseline.py:generate_case" and
            gen["frozen_from"] == "docs/program/iterations/I006-baseline.json", "I009 generator source")
    require(float(gen["near_scale_balanced"]) == float(frozen["near_scale_balanced"]) == 1.30 and
            float(gen["near_scale_weak"]) == float(frozen["near_scale_weak"]) == 0.72,
            "I009 near/far generator drift")
    require(gen["far_echo_delays_samples"] == frozen["far_echo_delays_samples"] == [640, 960] and
            gen["far_echo_gains_low"] == frozen["far_echo_gains_low"] == [0.16, 0.06],
            "I009 echo generator drift")

    activity = (root / "src/activity/ap_activity.c").read_text(encoding="utf-8")
    require("const float alpha = value > old_value ? 0.35f : 0.08f" in activity,
            "shipping Activity smoothing drift")
    require("smoothed_ratio > s->double_talk_ratio" in activity and
            "instant_ratio > 0.90f * s->double_talk_ratio" in activity and
            "instant_ratio > 0.72f * s->double_talk_ratio" in activity,
            "shipping Activity ratio predicates drift")
    return {
        "activity_source_sha256": i006_base.sha256(root / "src/activity/ap_activity.c"),
        "double_talk_ratio": 1.5,
        "instant_on_ratio": 1.35,
        "instant_hold_ratio": 1.08,
        "rise_alpha": 0.35,
        "decay_alpha": 0.08,
    }


def summarize_case(rows: list[dict], near_labels: list[int], warmup: int,
                   min_near: int, min_far_fraction: float, min_dt_fraction: float,
                   allowed_classifications: list[str]) -> tuple[dict, list[str], list[str]]:
    usable = rows[warmup:]
    near_rows = [row for row in usable
                 if int(row["frame"]) < len(near_labels) and near_labels[int(row["frame"])] != 0]
    input_failures: list[str] = []
    gate_failures: list[str] = []
    if len(near_rows) < min_near:
        input_failures.append("near_active_frames")
    far_fraction = (sum(int(row["far_end_active"]) != 0 for row in near_rows) / len(near_rows)
                    if near_rows else 0.0)
    dt_fraction = (sum(int(row["double_talk_active"]) != 0 for row in near_rows) / len(near_rows)
                   if near_rows else 0.0)
    if far_fraction < min_far_fraction:
        input_failures.append("far_activity_on_near")
    if not input_failures and dt_fraction < min_dt_fraction:
        gate_failures.append("double_talk_activity")

    diagnosis = None
    far_near_count = sum(int(row["far_end_active"]) != 0 for row in near_rows)
    if len(near_rows) >= min_near and far_near_count >= 80:
        diagnosis = i006_root.double_talk_summary(rows, near_labels, warmup, allowed_classifications)

    return ({
        "near_active_frames": len(near_rows),
        "far_active_fraction_on_near_active": far_fraction,
        "double_talk_fraction_on_near_active": dt_fraction,
        "diagnosis": diagnosis,
    }, input_failures, gate_failures)


def self_test() -> None:
    rows = []
    labels = [0] * 100
    for frame in range(100):
        active = 10 <= frame < 90
        labels[frame] = 1 if active else 0
        rows.append({
            "frame": frame,
            "far_end_active": 1 if active else 0,
            "double_talk_active": 1 if 20 <= frame < 80 else 0,
            "smoothed_gate": 1 if 20 <= frame < 80 else 0,
            "instant_on_proxy_gate": 1 if active else 0,
            "instant_hold_proxy_gate": 1 if active else 0,
        })
    metrics, inputs, gates = summarize_case(
        rows, labels, 0, 60, 0.70, 0.35,
        ["DT_SMOOTHED_RATIO_GATE_LIMIT", "DT_INSTANT_RATIO_GATE_LIMIT",
         "DT_BOTH_RATIO_GATES_LIMIT", "DT_NOT_EXPLAINED_BY_CURRENT_RATIO_GATES"])
    assert not inputs and not gates
    assert metrics["near_active_frames"] == 80
    assert metrics["double_talk_fraction_on_near_active"] == 0.75
    print(json.dumps({"result": "PASS", "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--inherited", type=Path)
    parser.add_argument("--i006-contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.contract and args.inherited and args.i006_contract and args.output,
            "contract/inherited/i006-contract/output required")

    root = Path(__file__).resolve().parents[2]
    contract = load_json(args.contract)
    inherited = load_json(args.inherited)
    i006_contract = load_json(args.i006_contract)
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"I009 exact main drift: {current}")
    source_contract = validate_contract(contract, inherited, i006_contract, root)

    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    probe = i006_root.build_probe(root, output)
    corpus_root = output / "corpus"
    corpus_root.mkdir()

    pre = contract["input_preconditions"]
    warmup = int(pre["warmup_frames"])
    min_trace = int(pre["min_trace_frames"])
    min_near = int(pre["min_near_active_frames"])
    min_far_fraction = float(pre["min_far_active_fraction_on_near_active"])
    min_dt_fraction = float(contract["frozen_gate"]["min_double_talk_fraction_on_near_active"])
    allowed = list(contract["diagnostics"]["allowed_classifications"])

    cases: list[dict] = []
    all_input_failures: list[dict] = []
    all_gate_failures: list[dict] = []
    for seed in contract["seeds"]:
        for scenario in contract["scenarios"]:
            case_dir = corpus_root / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True)
            mic, render, near, near_labels, far_labels, category = i006_base.generate_case(
                i006_contract, scenario, int(seed))
            require(category == "near_far", "I009 permits only near/far cases")
            synth.write_pcm(case_dir / "near-clean.pcm", near)
            (case_dir / "near-labels.json").write_text(json.dumps(near_labels) + "\n", encoding="utf-8")
            (case_dir / "far-labels.json").write_text(json.dumps(far_labels) + "\n", encoding="utf-8")
            rows = i006_root.run_probe(probe, case_dir, mic, render)
            require(len(rows) >= min_trace, "I009 trace too short")
            trace = case_dir / "trace.jsonl"
            trace.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
            metrics, input_failures, gate_failures = summarize_case(
                rows, near_labels, warmup, min_near, min_far_fraction, min_dt_fraction, allowed)
            row = {
                "seed": seed,
                "scenario": scenario,
                "metrics": metrics,
                "input_failures": input_failures,
                "gate_failures": gate_failures,
            }
            cases.append(row)
            for failure in input_failures:
                all_input_failures.append({"seed": seed, "scenario": scenario, "gate": failure})
            for failure in gate_failures:
                all_gate_failures.append({"seed": seed, "scenario": scenario, "gate": failure})

    require(len(cases) == 6, "I009 partition count drift")
    classifications: dict[str, int] = {}
    for case in cases:
        diagnosis = case["metrics"]["diagnosis"]
        if diagnosis is not None:
            key = str(diagnosis["classification"])
            classifications[key] = classifications.get(key, 0) + 1

    if all_input_failures:
        decision = "INPUT_INVALID_REVIEW_REQUIRED"
    elif all_gate_failures:
        decision = "MEASURED_GAP_REVIEW_REQUIRED"
    else:
        decision = "BASELINE_ADEQUATE_NO_SEARCH"

    report = {
        "schema_version": 1,
        "iteration_id": "I009",
        "phase": "activity-double-talk-baseline",
        "root_cause_id": contract["root_cause_id"],
        "source_sha": current,
        "authority": "fresh-development-candidate-zero-measurement-only",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "candidate_search_performed": False,
        "threshold_tuning_performed": False,
        "shipping_source_changed": False,
        "promotion_allowed": False,
        "source_contract": source_contract,
        "probe_sha256": i006_base.sha256(probe),
        "fresh_development_seeds": contract["seeds"],
        "inherited_i006_seeds_reused": False,
        "cases": cases,
        "aggregate": {
            "partitions": len(cases),
            "input_failure_partitions": len({(x["seed"], x["scenario"]) for x in all_input_failures}),
            "gate_failure_partitions": len({(x["seed"], x["scenario"]) for x in all_gate_failures}),
            "double_talk_classification_distribution": classifications,
            "double_talk_fraction_range": [
                min(float(case["metrics"]["double_talk_fraction_on_near_active"]) for case in cases),
                max(float(case["metrics"]["double_talk_fraction_on_near_active"]) for case in cases),
            ],
            "far_active_fraction_range": [
                min(float(case["metrics"]["far_active_fraction_on_near_active"]) for case in cases),
                max(float(case["metrics"]["far_active_fraction_on_near_active"]) for case in cases),
            ],
        },
        "decision": decision,
        "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
        "next_step": ("review fresh Development mechanism evidence before any bounded Activity source candidate"
                      if decision == "MEASURED_GAP_REVIEW_REQUIRED" else
                      "no Activity source search authorized from this baseline"),
        "source_retirement": contract["source_retirement"],
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "baseline-result.json", report)
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
        "input_failures": report["aggregate"]["input_failure_partitions"],
        "gate_failures": report["aggregate"]["gate_failure_partitions"],
        "classifications": classifications,
        "candidate_limit": 0,
        "confirmation_limit": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
