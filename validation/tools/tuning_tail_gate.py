#!/usr/bin/env python3
"""Fail-closed aligned case-tail comparison for acoustic tuning candidates.

The gate compares the same case IDs in baseline and candidate validation
reports. It complements aggregate/percentile objectives by preventing a
candidate from improving medians while sacrificing a small hard-case tail.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    frac = position - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("validation_result") not in {"PASS", "FAIL"}:
        raise ValueError(f"invalid validation report: {path}")
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"case-level report required: {path}")
    return report


def case_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for case in report["cases"]:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in result:
            raise ValueError("case IDs must be unique non-empty strings")
        result[case_id] = case
    return result


def metric_deltas(baseline: dict[str, Any], candidate: dict[str, Any], metric: str) -> list[float]:
    before = case_map(baseline)
    after = case_map(candidate)
    if set(before) != set(after):
        missing = sorted(set(before) - set(after))
        extra = sorted(set(after) - set(before))
        raise ValueError(f"case identity drift: missing={missing} extra={extra}")
    deltas: list[float] = []
    for case_id in sorted(before):
        base_value = before[case_id].get("metrics", {}).get(metric)
        cand_value = after[case_id].get("metrics", {}).get(metric)
        if base_value is None and cand_value is None:
            continue
        if base_value is None or cand_value is None:
            raise ValueError(f"metric availability drift: {case_id}/{metric}")
        base = float(base_value)
        cand = float(cand_value)
        if not math.isfinite(base) or not math.isfinite(cand):
            raise ValueError(f"non-finite metric: {case_id}/{metric}")
        deltas.append(cand - base)
    if not deltas:
        raise ValueError(f"metric unavailable for all cases: {metric}")
    return deltas


def evaluate(baseline: dict[str, Any], candidate: dict[str, Any],
             corr_worst_min: float, corr_p10_min: float,
             erle_worst_min: float) -> dict[str, Any]:
    corr = metric_deltas(baseline, candidate, "output_render_corr_reduction")
    erle = metric_deltas(baseline, candidate, "erle_db")
    summary = {
        "correlation": {
            "cases": len(corr),
            "worst_delta": min(corr),
            "p10_delta": percentile(corr, 0.10),
            "median_delta": percentile(corr, 0.50),
            "worsened_cases": sum(1 for value in corr if value < 0.0),
        },
        "erle": {
            "cases": len(erle),
            "worst_delta_db": min(erle),
            "p10_delta_db": percentile(erle, 0.10),
            "median_delta_db": percentile(erle, 0.50),
            "worsened_cases": sum(1 for value in erle if value < 0.0),
        },
    }
    violations = []
    if summary["correlation"]["worst_delta"] < corr_worst_min:
        violations.append({"gate": "corr_worst_delta", "actual": summary["correlation"]["worst_delta"], "expected_min": corr_worst_min})
    if summary["correlation"]["p10_delta"] < corr_p10_min:
        violations.append({"gate": "corr_p10_delta", "actual": summary["correlation"]["p10_delta"], "expected_min": corr_p10_min})
    if summary["erle"]["worst_delta_db"] < erle_worst_min:
        violations.append({"gate": "erle_worst_delta_db", "actual": summary["erle"]["worst_delta_db"], "expected_min": erle_worst_min})
    return {"decision": "PASS" if not violations else "REJECT_CANDIDATE", "summary": summary, "violations": violations}


def self_test() -> None:
    baseline = {"validation_result": "PASS", "cases": [
        {"case_id": "a", "metrics": {"output_render_corr_reduction": 0.10, "erle_db": 10.0}},
        {"case_id": "b", "metrics": {"output_render_corr_reduction": 0.20, "erle_db": 12.0}},
    ]}
    candidate = {"validation_result": "PASS", "cases": [
        {"case_id": "a", "metrics": {"output_render_corr_reduction": 0.095, "erle_db": 10.5}},
        {"case_id": "b", "metrics": {"output_render_corr_reduction": 0.23, "erle_db": 13.0}},
    ]}
    result = evaluate(baseline, candidate, -0.015, -0.010, -0.5)
    assert result["decision"] == "PASS"
    bad = json.loads(json.dumps(candidate))
    bad["cases"][0]["metrics"]["output_render_corr_reduction"] = 0.05
    assert evaluate(baseline, bad, -0.015, -0.010, -0.5)["decision"] == "REJECT_CANDIDATE"
    print("tuning tail gate self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--corr-worst-min", type=float, default=-0.015)
    parser.add_argument("--corr-p10-min", type=float, default=-0.005)
    parser.add_argument("--erle-worst-min", type=float, default=-0.5)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.baseline is None or args.candidate is None or args.output is None:
        parser.error("--baseline, --candidate and --output are required")
    result = evaluate(load_report(args.baseline), load_report(args.candidate),
                      args.corr_worst_min, args.corr_p10_min, args.erle_worst_min)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 2 if args.enforce and result["decision"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
