#!/usr/bin/env python3
"""Evaluate the frozen strong-origin bounded-hysteresis exact C candidate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/tools"))
sys.path.insert(0, str(ROOT / "tests/validation"))
sys.path.insert(0, str(ROOT / ".github/research/continuous-optimization"))

import stage_source_candidate_evaluate as source_eval
import vad_stage_lane_v2 as lane_v2


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def regressions(base: dict[str, Any], cand: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    checks = (
        ("min_vad_recall", "drop", float(spec["max_recall_regression"])),
        ("min_vad_f1", "drop", float(spec["max_f1_regression"])),
        ("max_vad_false_positive_rate", "rise", float(spec["max_fpr_regression"])),
    )
    for metric, kind, allowed in checks:
        b = float(base[metric])
        c = float(cand[metric])
        value = b - c if kind == "drop" else c - b
        if value > allowed + 1.0e-12:
            out.append({
                "metric": metric,
                "regression": value,
                "allowed": allowed,
                "baseline": b,
                "candidate": c,
            })
    return out


def evaluate(
    base_processor: Path,
    candidate_processor: Path,
    corpora: list[Path],
    contract_path: Path,
    base_state_size: int,
    candidate_state_size: int,
    output: Path,
) -> dict[str, Any]:
    contract = load(contract_path)
    if contract.get("authority") != "SOURCE_CANDIDATE_EVALUATION_ONLY":
        raise ValueError("unexpected source-candidate authority")
    if contract.get("candidate_id") != "vad-strong-origin-bounded-hysteresis-v1":
        raise ValueError("unexpected source candidate")
    spec = contract["fresh_candidate_evaluation"]
    expected_seeds = [int(x) for x in spec["seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("source-candidate corpus count mismatch")

    growth = int(candidate_state_size) - int(base_state_size)
    max_growth = int(contract["exact_source_change"]["state"]["max_state_size_growth_bytes"])
    violations: list[dict[str, Any]] = []
    if growth < 0 or growth > max_growth:
        violations.append({
            "gate": "vad_state_size_growth",
            "baseline_bytes": base_state_size,
            "candidate_bytes": candidate_state_size,
            "growth_bytes": growth,
            "allowed_max": max_growth,
        })

    lane_contract = {"fixed_policy": contract["fixed_policy"]}
    partitions = []
    observed_seeds: list[int] = []
    total_probability_mismatch = 0
    total_policy_mismatch = 0
    total_changed = 0
    total_contractions = 0

    for corpus in corpora:
        base = source_eval.collect_vad_partition(base_processor, corpus)
        cand = source_eval.collect_vad_partition(candidate_processor, corpus)
        seed = int(cand["seed"])
        observed_seeds.append(seed)
        if [x["case_id"] for x in base["cases"]] != [x["case_id"] for x in cand["cases"]]:
            raise ValueError("VAD source-candidate case identity drift")

        case_checks = []
        for b, c in zip(base["cases"], cand["cases"]):
            if b["profile"] != c["profile"] or b["labels"] != c["labels"]:
                raise ValueError("VAD source-candidate binding drift")
            if len(b["probabilities"]) != len(c["probabilities"]):
                raise ValueError("VAD source-candidate trace length drift")
            prob_mismatch = sum(
                abs(x - y) > 1.0e-7
                for x, y in zip(b["probabilities"], c["probabilities"])
            )
            expected = [
                int(row["vad_active"])
                for row in lane_v2.candidate_trace(
                    c["probabilities"],
                    c["profile"],
                    float(contract["fixed_policy"]["release_margin"]),
                    int(contract["fixed_policy"]["subthreshold_budget_frames"]),
                    lane_contract,
                )
            ]
            policy_mismatch = sum(x != y for x, y in zip(expected, c["active"]))
            changed = sum(x != y for x, y in zip(b["active"], c["active"]))
            contractions = sum(x == 1 and y == 0 for x, y in zip(b["active"], c["active"]))
            total_probability_mismatch += prob_mismatch
            total_policy_mismatch += policy_mismatch
            total_changed += changed
            total_contractions += contractions
            case_checks.append({
                "case_id": c["case_id"],
                "profile": c["profile"],
                "probability_mismatches": prob_mismatch,
                "policy_mismatches": policy_mismatch,
                "changed_active_frames_vs_base": changed,
                "active_contractions_vs_base": contractions,
            })

        base_summary = source_eval.vad_partition_summary(base)
        cand_summary = source_eval.vad_partition_summary(cand)
        local_regressions = regressions(base_summary["summary"], cand_summary["summary"], spec)
        local_violations = []
        if spec["require_all_case_gates_pass"] and cand_summary["validation_result"] != "PASS":
            local_violations.append({
                "gate": "candidate_case_gates",
                "actual": cand_summary["validation_result"],
            })
        if local_regressions:
            local_violations.append({
                "gate": "candidate_regression",
                "violations": local_regressions,
            })
        if local_violations:
            violations.append({"seed": seed, "violations": local_violations})

        partitions.append({
            "seed": seed,
            "baseline": base_summary["summary"],
            "candidate": cand_summary["summary"],
            "candidate_validation_result": cand_summary["validation_result"],
            "regression_violations": local_regressions,
            "case_checks": case_checks,
        })

    if observed_seeds != expected_seeds:
        raise ValueError(f"source-candidate seed drift: {observed_seeds} != {expected_seeds}")
    if spec["require_probability_trace_identity"] and total_probability_mismatch:
        violations.append({"gate": "probability_trace_identity", "count": total_probability_mismatch})
    if spec["required_exact_policy_conformance"] and total_policy_mismatch:
        violations.append({"gate": "candidate_policy_conformance", "count": total_policy_mismatch})
    if spec["require_no_active_contraction"] and total_contractions:
        violations.append({"gate": "active_contraction", "count": total_contractions})
    if spec["require_candidate_behavior_exercised"] and total_changed <= 0:
        violations.append({"gate": "candidate_behavior_not_exercised"})

    result = {
        "schema_version": 1,
        "authority": "source-candidate-evaluation-only",
        "candidate_id": contract["candidate_id"],
        "decision": "SOURCE_CANDIDATE_PASS" if not violations else "SOURCE_CANDIDATE_REJECT",
        "fresh_seeds": observed_seeds,
        "state_size": {
            "baseline_bytes": int(base_state_size),
            "candidate_bytes": int(candidate_state_size),
            "growth_bytes": growth,
            "allowed_max_growth_bytes": max_growth,
        },
        "total_changed_active_frames_vs_base": total_changed,
        "total_probability_mismatches": total_probability_mismatch,
        "total_policy_mismatches": total_policy_mismatch,
        "total_active_contractions_vs_base": total_contractions,
        "partitions": partitions,
        "violations": violations,
        "shipping_authority": False,
        "source_merge_authorized": False,
        "automatic_main_mutation": False,
        "independent_confirmation_required_after_pass": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    spec = {
        "max_recall_regression": 0.03,
        "max_f1_regression": 0.03,
        "max_fpr_regression": 0.03,
    }
    base = {"min_vad_recall": 0.8, "min_vad_f1": 0.8, "max_vad_false_positive_rate": 0.3}
    good = {"min_vad_recall": 0.82, "min_vad_f1": 0.81, "max_vad_false_positive_rate": 0.3}
    bad = {"min_vad_recall": 0.7, "min_vad_f1": 0.8, "max_vad_false_positive_rate": 0.3}
    assert regressions(base, good, spec) == []
    assert regressions(base, bad, spec)[0]["metric"] == "min_vad_recall"
    print("VAD bounded-hysteresis source evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--base-processor", type=Path)
    parser.add_argument("--candidate-processor", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--base-state-size", type=int)
    parser.add_argument("--candidate-state-size", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (
        args.base_processor,
        args.candidate_processor,
        args.contract,
        args.base_state_size,
        args.candidate_state_size,
        args.output,
    )
    if any(x is None for x in required):
        parser.error("base/candidate processors, contract, state sizes and output are required")
    result = evaluate(
        args.base_processor.resolve(),
        args.candidate_processor.resolve(),
        [x.resolve() for x in args.corpus],
        args.contract.resolve(),
        int(args.base_state_size),
        int(args.candidate_state_size),
        args.output.resolve(),
    )
    print(json.dumps({
        "candidate_id": result["candidate_id"],
        "decision": result["decision"],
        "changed_active_frames": result["total_changed_active_frames_vs_base"],
        "probability_mismatches": result["total_probability_mismatches"],
        "policy_mismatches": result["total_policy_mismatches"],
        "active_contractions": result["total_active_contractions_vs_base"],
        "violations": len(result["violations"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
