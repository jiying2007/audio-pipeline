#!/usr/bin/env python3
"""Evaluate the single reviewed I006 AGC maximum-gain candidate.

The candidate value is not searched.  The evaluator builds the immutable
shipping base and the candidate independently, replays only exposed Development
cases, preserves the frozen I006 protection gates, and treats the inherited
Activity double-talk metric as context rather than AGC candidate authority.
Passing this evaluator authorizes only a later fresh confirmation contract.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import i006_agc_paired_baseline as paired
import i006_agc_residual_floor_baseline as v1


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def validate_contract(contract: dict, baseline: dict) -> None:
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "I006", "I006 identity")
    require(contract.get("phase") == "bounded-source-candidate-search", "I006 candidate phase")
    require(contract.get("root_cause_id") == "noise-floor-max-gain-cap", "I006 candidate root cause")
    require(contract.get("base_sha") == "945344a29a826bbf5330baf3382cb3e34c8f4160", "I006 candidate base")
    require(contract.get("data_role") == "development-exposed-regression-only", "I006 candidate data role")
    require(contract.get("candidate_limit") == 1 and contract.get("confirmation_limit") == 0,
            "I006 candidate/confirmation budget")
    require(contract.get("promotion_allowed") is False, "I006 candidate cannot promote")
    variants = contract.get("candidate_variants")
    require(isinstance(variants, list) and len(variants) == 1, "exactly one I006 candidate required")
    variant = variants[0]
    require(variant.get("name") == "max-gain-cap-15db", "I006 candidate name")
    require(float(variant.get("candidate_max_gain_db")) == 15.0, "I006 candidate dB")
    require(abs(float(variant.get("candidate_max_gain_linear")) - 5.623413251903491) < 1.0e-12,
            "I006 candidate linear gain")
    authority = contract.get("authority", {})
    require(authority.get("may_apply_exact_pre_registered_candidate") is True, "exact candidate authority missing")
    for key in (
        "may_edit_checked_out_source", "may_add_candidate", "may_change_candidate_value",
        "may_tune_agc_target", "may_tune_limiter", "may_tune_attack_release",
        "may_tune_activity_thresholds", "may_consume_confirmation", "may_promote_release",
    ):
        require(authority.get(key) is False, f"I006 forbidden authority enabled: {key}")
    constraints = contract.get("constraints", {})
    require(constraints.get("same_exposed_development_data_is_not_confirmation") is True, "confirmation boundary")
    require(constraints.get("double_talk_gap_is_handed_to_I009") is True, "Activity handoff boundary")
    require(constraints.get("candidate_value_is_not_searchable") is True, "candidate value search boundary")
    require(constraints.get("candidate_pass_requires_later_fresh_independent_confirmation") is True,
            "fresh confirmation boundary")
    v1.validate_contract(baseline)
    require(baseline.get("measurement_revision") == 3, "I006 revision-3 baseline required")
    require(contract.get("development_seeds") == baseline.get("seeds"), "I006 seed lineage drift")
    require(contract.get("scenarios") == baseline.get("scenarios"), "I006 scenario lineage drift")
    require(contract.get("product_qualification", constraints.get("product_qualification")) == "DEFERRED_BY_SCOPE"
            or constraints.get("product_qualification") == "DEFERRED_BY_SCOPE", "product boundary")


def validate_source_delta(candidate_root: Path, base_root: Path, contract: dict) -> dict:
    base_sha = contract["base_sha"]
    require(git(base_root, "rev-parse", "HEAD") == base_sha, "exact shipping base worktree required")
    base_agc_path = base_root / "src/enhance/ap_agc.c"
    candidate_agc_path = candidate_root / "src/enhance/ap_agc.c"
    base_text = base_agc_path.read_text(encoding="utf-8")
    candidate_text = candidate_agc_path.read_text(encoding="utf-8")
    old = "0.25f, 8.0f"
    new = "0.25f, 5.623413f"
    require(base_text.count(old) == 1, "shipping 8x clamp source drift")
    expected = base_text.replace(old, new, 1)
    require(candidate_text == expected, "candidate AGC source must be the exact single clamp replacement")

    changed = [line for line in git(candidate_root, "diff", "--name-only", f"{base_sha}...HEAD").splitlines() if line]
    shipping_paths = [path for path in changed if path.startswith(("src/", "include/", "cmake/", "ci/")) or path == "CMakeLists.txt"]
    require(shipping_paths == ["src/enhance/ap_agc.c"], f"unexpected shipping candidate paths: {shipping_paths}")
    require((base_root / "src/activity/ap_activity.c").read_bytes() ==
            (candidate_root / "src/activity/ap_activity.c").read_bytes(), "Activity source changed in I006 candidate")
    require((base_root / "src/core/ap_pipeline.c").read_bytes() ==
            (candidate_root / "src/core/ap_pipeline.c").read_bytes(), "pipeline control source changed in I006 candidate")
    return {
        "base_agc_sha256": v1.sha256(base_agc_path),
        "candidate_agc_sha256": v1.sha256(candidate_agc_path),
        "changed_shipping_paths": shipping_paths,
        "exact_replacement": "0.25f, 8.0f -> 0.25f, 5.623413f",
        "activity_source_unchanged": True,
        "pipeline_control_source_unchanged": True,
    }


def gate_case(category: str, metrics: dict, contract: dict) -> list[str]:
    failures: list[str] = []
    gates = contract["gates"]
    if category == "pure_far_end":
        gate = gates["pure_far_end"]
        if metrics["far_only_fraction_on_far_active"] < float(gate["min_far_only_fraction_on_far_active"]):
            failures.append("far_only_fraction")
        if metrics["output_vs_input_rms_gain_db"] > float(gate["max_output_vs_input_rms_gain_db"]):
            failures.append("pure_far_gain_up")
        if metrics["clip_fraction"] > float(gate["max_clip_fraction"]):
            failures.append("clip_fraction")
    elif category == "noise_floor":
        gate = gates["noise_floor"]
        if metrics["tail_output_rms_dbfs"] > float(gate["max_tail_output_rms_dbfs"]):
            failures.append("noise_floor_output_level")
        if metrics["p95_frame_gain_db"] is None or metrics["p95_frame_gain_db"] > float(gate["max_p95_frame_gain_db"]):
            failures.append("noise_floor_gain")
        if metrics["clip_fraction"] > float(gate["max_clip_fraction"]):
            failures.append("clip_fraction")
    else:
        gate = gates["near_far"]
        if metrics["far_active_fraction_on_near_active"] < float(gate["min_far_active_fraction_on_near_active"]):
            failures.append("far_activity")
        if metrics["speech_si_sdr_improvement_db"] < float(gate["min_speech_si_sdr_improvement_db"]):
            failures.append("speech_preservation")
        if metrics["clip_fraction"] > float(gate["max_clip_fraction"]):
            failures.append("clip_fraction")
    return failures


def activity_equal(base: dict, candidate: dict, category: str) -> bool:
    if category == "pure_far_end":
        return base["far_only_fraction_on_far_active"] == candidate["far_only_fraction_on_far_active"]
    if category == "near_far":
        return (base["far_active_fraction_on_near_active"] == candidate["far_active_fraction_on_near_active"] and
                base["double_talk_fraction_on_near_active"] == candidate["double_talk_fraction_on_near_active"])
    return True


def evaluate_root(root: Path, baseline: dict, output: Path) -> tuple[Path, list[dict]]:
    probe, _raw = paired.build_tools(root, output)
    cases: list[dict] = []
    corpus = output / "corpus"
    corpus.mkdir()
    for seed in baseline["seeds"]:
        for scenario in baseline["scenarios"]:
            case_dir = corpus / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True)
            mic, render, near, near_labels, far_labels, category = v1.generate_case(baseline, scenario, int(seed))
            metrics = paired.run_paired(probe, case_dir, mic, render, near, near_labels, far_labels, baseline, category)
            cases.append({"seed": seed, "scenario": scenario, "category": category, "metrics": metrics})
    require(len(cases) == 18, "I006 candidate case count drift")
    return probe, cases


def self_test() -> None:
    contract = {
        "gates": {
            "pure_far_end": {"min_far_only_fraction_on_far_active": 0.85, "max_output_vs_input_rms_gain_db": 0.75, "max_clip_fraction": 0.001},
            "noise_floor": {"max_tail_output_rms_dbfs": -28.0, "max_p95_frame_gain_db": 15.0, "max_clip_fraction": 0.001},
            "near_far": {"min_far_active_fraction_on_near_active": 0.70, "min_speech_si_sdr_improvement_db": -0.50, "max_clip_fraction": 0.002},
        }
    }
    assert gate_case("noise_floor", {"tail_output_rms_dbfs": -30.0, "p95_frame_gain_db": 14.99, "clip_fraction": 0.0}, contract) == []
    assert gate_case("noise_floor", {"tail_output_rms_dbfs": -30.0, "p95_frame_gain_db": 18.0, "clip_fraction": 0.0}, contract) == ["noise_floor_gain"]
    print(json.dumps({"result": "PASS", "candidate_limit": 1, "confirmation_limit": 0}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--baseline-contract", type=Path)
    parser.add_argument("--base-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return 0
    require(all(value is not None for value in (args.contract, args.baseline_contract, args.base_root, args.output)),
            "contract/baseline-contract/base-root/output required")

    candidate_root = Path(__file__).resolve().parents[2]
    base_root = args.base_root.resolve()
    contract = load_json(args.contract)
    baseline = load_json(args.baseline_contract)
    validate_contract(contract, baseline)
    source_contract = validate_source_delta(candidate_root, base_root, contract)

    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    base_output = output / "base"
    candidate_output = output / "candidate"
    base_output.mkdir()
    candidate_output.mkdir()

    base_probe, base_cases = evaluate_root(base_root, baseline, base_output)
    candidate_probe, candidate_cases = evaluate_root(candidate_root, baseline, candidate_output)
    require([(row["seed"], row["scenario"], row["category"]) for row in base_cases] ==
            [(row["seed"], row["scenario"], row["category"]) for row in candidate_cases], "base/candidate case identity drift")

    cases: list[dict] = []
    candidate_failures: list[dict] = []
    activity_drift: list[dict] = []
    base_noise_gain_failures = 0
    candidate_noise_gain_passes = 0
    for base_row, candidate_row in zip(base_cases, candidate_cases):
        category = candidate_row["category"]
        base_metrics = base_row["metrics"]
        candidate_metrics = candidate_row["metrics"]
        base_failures = gate_case(category, base_metrics, contract)
        candidate_case_failures = gate_case(category, candidate_metrics, contract)
        if category == "noise_floor" and "noise_floor_gain" in base_failures:
            base_noise_gain_failures += 1
        if category == "noise_floor" and "noise_floor_gain" not in candidate_case_failures:
            candidate_noise_gain_passes += 1
        if not activity_equal(base_metrics, candidate_metrics, category):
            activity_drift.append({"seed": base_row["seed"], "scenario": base_row["scenario"]})
        if candidate_case_failures:
            candidate_failures.append({
                "seed": candidate_row["seed"], "scenario": candidate_row["scenario"],
                "failures": candidate_case_failures,
            })
        cases.append({
            "seed": candidate_row["seed"], "scenario": candidate_row["scenario"], "category": category,
            "base": base_metrics, "candidate": candidate_metrics,
            "base_failures_under_candidate_contract": base_failures,
            "candidate_failures": candidate_case_failures,
        })

    require(base_noise_gain_failures == 6, "immutable shipping base must reproduce six noise-floor gain failures")
    eligible = not candidate_failures and not activity_drift and candidate_noise_gain_passes == 6
    decision = "ELIGIBLE_FOR_FRESH_CONFIRMATION" if eligible else "KEEP_BASELINE_CANDIDATE_REJECTED"
    result = {
        "schema_version": 1,
        "iteration_id": "I006",
        "phase": "bounded-source-candidate-search",
        "root_cause_id": contract["root_cause_id"],
        "base_sha": contract["base_sha"],
        "candidate_head_sha": git(candidate_root, "rev-parse", "HEAD"),
        "data_role": contract["data_role"],
        "candidate_limit": 1,
        "candidate_limit_consumed": 1,
        "confirmation_limit": 0,
        "confirmation_limit_consumed": 0,
        "promotion_allowed": False,
        "source_contract": source_contract,
        "base_probe_sha256": v1.sha256(base_probe),
        "candidate_probe_sha256": v1.sha256(candidate_probe),
        "cases": cases,
        "candidate_failures": candidate_failures,
        "activity_drift": activity_drift,
        "aggregate": {
            "cases": len(cases),
            "shipping_base_noise_floor_gain_failures": base_noise_gain_failures,
            "candidate_noise_floor_gain_passes": candidate_noise_gain_passes,
            "candidate_gate_failures": len(candidate_failures),
            "activity_drift_cases": len(activity_drift),
        },
        "decision": decision,
        "candidate": "max-gain-cap-15db",
        "next_step": (
            "review and freeze this exact source candidate before registering one fresh independent confirmation source"
            if eligible else
            "keep v2.3.12 shipping baseline; do not consume confirmation"
        ),
        "software_release": "v2.3.12",
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "candidate-result.json", result)
    manifest = {str(path.relative_to(output)): v1.sha256(path)
                for path in sorted(output.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1, "files": manifest})
    manifest["evidence-manifest.json"] = v1.sha256(output / "evidence-manifest.json")
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({
        "decision": decision,
        "candidate_limit_consumed": 1,
        "confirmation_limit_consumed": 0,
        "base_noise_floor_gain_failures": base_noise_gain_failures,
        "candidate_noise_floor_gain_passes": candidate_noise_gain_passes,
        "candidate_gate_failures": len(candidate_failures),
        "activity_drift_cases": len(activity_drift),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"I006 max-gain candidate error: {exc}")
