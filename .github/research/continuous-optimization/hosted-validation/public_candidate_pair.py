#!/usr/bin/env python3
"""Classify one frozen acoustic candidate against the canonical baseline.

This is a non-shipping promotion authority. Absolute public-policy results remain
diagnostic because the current Full160 baseline is not calibrated to those
aggregate thresholds. Candidate-specific authority comes only from regression
bounds that were frozen in the source revision's call-v1 search contract before
the public candidate evidence was produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

AUTHORITY = "non-shipping-paired-public-relative-acoustic-qualification"
QUALIFIED = "PUBLIC_RELATIVE_QUALIFIED_NON_SHIPPING"
REJECTED = "PUBLIC_RELATIVE_REJECTED_NON_SHIPPING"
INCOMPLETE = "PUBLIC_RELATIVE_INCOMPLETE_NON_SHIPPING"
EXPECTED_SEARCH_SPACE_ID = "call-runtime-safe-v1"
IGNORED_BINDING_KEYS = {"processor_sha256"}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_engine(source_root: Path):
    tools = source_root / "validation" / "tools"
    value = str(tools.resolve())
    if value not in sys.path:
        sys.path.insert(0, value)
    import tuning_iteration_engine as engine  # type: ignore
    return engine


def compare_report_identity(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for key in ("corpus_id", "policy_id", "source_revision", "tier"):
        if baseline.get(key) != candidate.get(key):
            violations.append({
                "gate": "report_identity_mismatch",
                "field": key,
                "baseline": baseline.get(key),
                "candidate": candidate.get(key),
            })
    base_bindings = baseline.get("bindings")
    cand_bindings = candidate.get("bindings")
    if not isinstance(base_bindings, dict) or not isinstance(cand_bindings, dict):
        violations.append({"gate": "report_bindings_missing"})
        return violations
    base_keys = set(base_bindings) - IGNORED_BINDING_KEYS
    cand_keys = set(cand_bindings) - IGNORED_BINDING_KEYS
    if base_keys != cand_keys:
        violations.append({
            "gate": "report_binding_keys_mismatch",
            "baseline_only": sorted(base_keys - cand_keys),
            "candidate_only": sorted(cand_keys - base_keys),
        })
        return violations
    for key in sorted(base_keys):
        if base_bindings.get(key) != cand_bindings.get(key):
            violations.append({
                "gate": "report_binding_mismatch",
                "field": key,
                "baseline": base_bindings.get(key),
                "candidate": cand_bindings.get(key),
            })
    return violations


def relative_summary(engine, space: dict[str, Any], baseline: dict[str, Any],
                     candidate: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], float]:
    comparisons: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    score = 0.0
    for metric in engine.objective_metrics(space):
        name = str(metric["name"])
        base = engine.summary_value(baseline, name)
        cand = engine.summary_value(candidate, name)
        if base is None and cand is None:
            comparisons.append({"metric": name, "status": "not_applicable_symmetric"})
            continue
        if base is None or cand is None:
            incomplete.append({
                "gate": "summary_metric_coverage_mismatch",
                "metric": name,
                "baseline": base,
                "candidate": cand,
            })
            continue
        direction = str(metric["direction"])
        directed = (cand - base) if direction == "max" else (base - cand)
        regression = -directed
        allowed = float(metric.get("max_regression", 0.0))
        scale = float(metric.get("scale", 1.0))
        weighted = float(metric.get("weight", 1.0)) * directed / scale
        score += weighted
        row = {
            "metric": name,
            "direction": direction,
            "baseline": base,
            "candidate": cand,
            "directed_delta": directed,
            "regression": regression,
            "allowed_regression": allowed,
            "weighted_score": weighted,
            "passed": regression <= allowed + 1.0e-12,
        }
        comparisons.append(row)
        if not row["passed"]:
            regressions.append({"gate": "metric_regression", **row})
    return comparisons, regressions, incomplete, score


def classify(source_root: Path, search_space_path: Path, baseline_path: Path,
             candidate_path: Path, output_path: Path) -> tuple[dict[str, Any], int]:
    engine = load_engine(source_root)
    space = load_json(search_space_path)
    engine.validate_search_space(space)
    if space.get("search_space_id") != EXPECTED_SEARCH_SPACE_ID:
        raise ValueError(
            f"public relative authority requires {EXPECTED_SEARCH_SPACE_ID}, "
            f"got {space.get('search_space_id')}"
        )
    baseline = load_json(baseline_path)
    candidate = load_json(candidate_path)

    structural = compare_report_identity(baseline, candidate)
    comparisons, summary_regressions, summary_incomplete, score = relative_summary(
        engine, space, baseline, candidate
    )
    case_summary, case_violations = engine.case_delta_gate_violations(
        space, baseline, candidate
    )
    incomplete_case_gates = {
        "case_set_invalid", "case_identity_invalid", "case_identity_duplicate",
        "case_set_mismatch", "case_metric_coverage_mismatch",
        "case_gate_not_applicable", "case_gate_insufficient_cases",
    }
    case_incomplete = [
        item for item in case_violations
        if item.get("gate") in incomplete_case_gates
    ]
    case_regressions = [
        item for item in case_violations
        if item.get("gate") not in incomplete_case_gates
    ]
    incomplete = structural + summary_incomplete + case_incomplete
    regressions = summary_regressions + case_regressions

    if incomplete:
        decision = INCOMPLETE
        next_gate = "validation-grade"
        terminal = False
        rc = 2
    elif regressions:
        decision = REJECTED
        next_gate = None
        terminal = True
        rc = 1
    else:
        decision = QUALIFIED
        next_gate = "validation-grade-blind"
        terminal = False
        rc = 0

    result = {
        "schema_version": 1,
        "authority": AUTHORITY,
        "decision": decision,
        "source_revision": baseline.get("source_revision"),
        "corpus_id": baseline.get("corpus_id"),
        "policy_id": baseline.get("policy_id"),
        "search_space": {
            "path": str(search_space_path),
            "id": space.get("search_space_id"),
            "sha256": sha256_file(search_space_path),
        },
        "baseline_absolute_result": baseline.get("validation_result"),
        "candidate_absolute_result": candidate.get("validation_result"),
        "absolute_policy_is_promotion_authority": False,
        "relative_score": score,
        "summary_comparisons": comparisons,
        "case_delta_summary": case_summary,
        "regressions": regressions,
        "incomplete_evidence": incomplete,
        "next_gate": next_gate,
        "terminal_candidate": terminal,
        "rule": (
            "Candidate-specific public authority uses only pre-frozen call-v1 "
            "baseline-relative regression bounds and case-delta gates. The "
            "baseline-incompatible absolute Full policy remains diagnostic."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result, rc


def self_test(source_root: Path) -> None:
    engine = load_engine(source_root)
    space = {
        "schema_version": 1,
        "search_space_id": EXPECTED_SEARCH_SPACE_ID,
        "strategy": "one-at-a-time",
        "max_candidates": 1,
        "baseline": {
            "aec_mu": 0.22, "ns_floor": 0.12,
            "agc_target_dbfs": -20.0, "limiter_dbfs": -2.0,
        },
        "parameters": {"ns_floor": [0.12]},
        "objective": {
            "minimum_improvement_score": 0.0,
            "metrics": [
                {"name": "pass_rate", "direction": "max", "weight": 1.0,
                 "scale": 0.1, "max_regression": 0.0},
                {"name": "median_erle_db", "direction": "max", "weight": 1.0,
                 "scale": 1.0, "max_regression": 1.0},
            ],
            "case_delta_gates": [
                {"metric": "vad_f1", "stat": "min",
                 "minimum_delta": -0.05, "min_cases": 1}
            ],
        },
    }
    engine.validate_search_space(space)
    base = {
        "validation_result": "FAIL",
        "corpus_id": "c", "policy_id": "p", "source_revision": "a" * 40,
        "tier": "validation-grade",
        "bindings": {"corpus_sha256": "x", "processor_sha256": "base"},
        "summary": {"pass_rate": 1.0, "median_erle_db": None},
        "cases": [{"case_id": "a", "metrics": {"vad_f1": 0.5}}],
    }
    good = json.loads(json.dumps(base))
    good["bindings"]["processor_sha256"] = "candidate"
    good["cases"][0]["metrics"]["vad_f1"] = 0.47
    comparisons, regressions, incomplete, _ = relative_summary(
        engine, space, base, good
    )
    assert not regressions and not incomplete
    assert any(item.get("status") == "not_applicable_symmetric"
               for item in comparisons)
    _, case_violations = engine.case_delta_gate_violations(space, base, good)
    assert not case_violations
    bad = json.loads(json.dumps(good))
    bad["cases"][0]["metrics"]["vad_f1"] = 0.40
    _, bad_case = engine.case_delta_gate_violations(space, base, bad)
    assert any(item.get("gate") == "case_delta_regression" for item in bad_case)
    mismatch = json.loads(json.dumps(good))
    mismatch["corpus_id"] = "other"
    assert compare_report_identity(base, mismatch)
    print("public candidate paired regression self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("."))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--search-space", type=Path)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--candidate-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test(args.source_root)
        return 0
    for name in ("search_space", "baseline_report", "candidate_report", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    result, rc = classify(
        args.source_root, args.search_space, args.baseline_report,
        args.candidate_report, args.output
    )
    print(json.dumps(result, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
