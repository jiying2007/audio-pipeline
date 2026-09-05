#!/usr/bin/env python3
"""Fail-closed qualification for non-shipping VAD operating-point selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MIN_HOLDOUT_SCORE = 0.50
MAX_CASE_RECALL_DROP = 0.02
MAX_CASE_F1_DROP = 0.02
MAX_CASE_FPR_RISE = 0.02


def summary_metric(report: dict[str, Any], name: str) -> float:
    value = report.get("summary", {}).get(name)
    if value is None:
        raise ValueError(f"missing summary metric: {name}")
    return float(value)


def partition_score(baseline: dict[str, Any], candidate: dict[str, Any]) -> float:
    recall_delta = summary_metric(candidate, "min_vad_recall") - summary_metric(baseline, "min_vad_recall")
    f1_delta = summary_metric(candidate, "min_vad_f1") - summary_metric(baseline, "min_vad_f1")
    fpr_improvement = (
        summary_metric(baseline, "max_vad_false_positive_rate")
        - summary_metric(candidate, "max_vad_false_positive_rate")
    )
    return (
        2.0 * recall_delta / 0.02
        + 1.0 * f1_delta / 0.02
        + 1.5 * fpr_improvement / 0.02
    )


def case_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("non-empty report cases required")
    result: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in result:
            raise ValueError("case ids must be non-empty and unique")
        result[case_id] = case
    return result


def case_regression_violations(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    base_cases = case_map(baseline)
    cand_cases = case_map(candidate)
    if set(base_cases) != set(cand_cases):
        return [{
            "gate": "case_set_mismatch",
            "missing": sorted(set(base_cases) - set(cand_cases)),
            "extra": sorted(set(cand_cases) - set(base_cases)),
        }]
    violations: list[dict[str, Any]] = []
    for case_id in sorted(base_cases):
        base = base_cases[case_id].get("metrics", {})
        cand = cand_cases[case_id].get("metrics", {})
        checks = (
            ("vad_recall", "drop", MAX_CASE_RECALL_DROP),
            ("vad_f1", "drop", MAX_CASE_F1_DROP),
            ("vad_false_positive_rate", "rise", MAX_CASE_FPR_RISE),
        )
        for metric, direction, allowed in checks:
            base_value = base.get(metric)
            cand_value = cand.get(metric)
            if base_value is None or cand_value is None:
                violations.append({
                    "gate": "case_metric_missing",
                    "case_id": case_id,
                    "metric": metric,
                })
                continue
            base_float = float(base_value)
            cand_float = float(cand_value)
            regression = (
                base_float - cand_float if direction == "drop"
                else cand_float - base_float
            )
            if regression > allowed + 1.0e-12:
                violations.append({
                    "gate": "case_metric_regression",
                    "case_id": case_id,
                    "metric": metric,
                    "baseline": base_float,
                    "candidate": cand_float,
                    "regression": regression,
                    "allowed": allowed,
                })
    return violations


def qualify(selection: dict[str, Any]) -> dict[str, Any]:
    if selection.get("authority") != "non-shipping-vad-operating-point-selection":
        raise ValueError("unexpected selector authority")
    original = selection.get("decision")
    if original not in {"KEEP_BASELINE", "RESEARCH_CANDIDATE", "REJECT_CANDIDATE"}:
        raise ValueError("unexpected selector decision")

    partitions = {}
    all_holdout_pass = True
    for role in ("validation", "shadow"):
        block = selection.get(role, {})
        baseline = block.get("baseline", {})
        candidate = block.get("candidate", {})
        if baseline.get("validation_result") != "PASS":
            raise ValueError(f"{role} baseline must pass")
        violations = case_regression_violations(baseline, candidate)
        score = partition_score(baseline, candidate)
        passed = (
            candidate.get("validation_result") == "PASS"
            and not block.get("regression_violations")
            and not violations
            and score >= MIN_HOLDOUT_SCORE
        )
        all_holdout_pass = all_holdout_pass and passed
        partitions[role] = {
            "score": score,
            "passed": passed,
            "case_regression_violations": violations,
            "selector_regression_violations": block.get("regression_violations", []),
        }

    if original == "KEEP_BASELINE":
        decision = "KEEP_BASELINE"
    elif original == "RESEARCH_CANDIDATE" and all_holdout_pass:
        decision = "RESEARCH_CANDIDATE"
    else:
        decision = "REJECT_CANDIDATE"

    return {
        "schema_version": 1,
        "authority": "non-shipping-vad-operating-point-qualification",
        "original_decision": original,
        "decision": decision,
        "selected": selection.get("selected"),
        "minimum_holdout_score": MIN_HOLDOUT_SCORE,
        "case_limits": {
            "max_recall_drop": MAX_CASE_RECALL_DROP,
            "max_f1_drop": MAX_CASE_F1_DROP,
            "max_fpr_rise": MAX_CASE_FPR_RISE,
        },
        "partitions": partitions,
    }


def self_test() -> None:
    def report(recall: float, f1: float, fpr: float) -> dict[str, Any]:
        return {
            "validation_result": "PASS",
            "summary": {
                "min_vad_recall": recall,
                "min_vad_f1": f1,
                "max_vad_false_positive_rate": fpr,
            },
            "cases": [{
                "case_id": "x",
                "metrics": {
                    "vad_recall": recall,
                    "vad_f1": f1,
                    "vad_false_positive_rate": fpr,
                },
            }],
        }

    selection = {
        "authority": "non-shipping-vad-operating-point-selection",
        "decision": "RESEARCH_CANDIDATE",
        "selected": {"candidate_id": "local=0.45,ns=0.30"},
        "validation": {
            "baseline": report(0.80, 0.80, 0.40),
            "candidate": report(0.82, 0.81, 0.40),
            "regression_violations": [],
        },
        "shadow": {
            "baseline": report(0.75, 0.76, 0.39),
            "candidate": report(0.78, 0.78, 0.40),
            "regression_violations": [],
        },
    }
    result = qualify(selection)
    assert result["decision"] == "RESEARCH_CANDIDATE"
    bad = json.loads(json.dumps(selection))
    bad["shadow"]["candidate"]["cases"][0]["metrics"]["vad_false_positive_rate"] = 0.43
    assert qualify(bad)["decision"] == "REJECT_CANDIDATE"
    print("VAD operating-point qualification self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.selection is None or args.output is None:
        parser.error("--selection and --output are required")
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    result = qualify(selection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": result["decision"],
        "original_decision": result["original_decision"],
        "validation_score": result["partitions"]["validation"]["score"],
        "shadow_score": result["partitions"]["shadow"]["score"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
