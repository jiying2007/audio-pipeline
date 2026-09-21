#!/usr/bin/env python3
"""Case-scoped research optimizer entrypoint for double-talk regression ratchets."""
from __future__ import annotations

import json
import sys
from typing import Any

import research_optimizer_v3 as v3
import tuning_iteration
import tuning_iteration_engine as engine

_ORIGINAL_CASE_DELTA = engine.case_delta_gate_violations


def _case_ids(gate: dict[str, Any]) -> list[str] | None:
    return engine.gate_case_ids(gate)


def validate_case_scopes(space: dict[str, Any]) -> None:
    v3.dataset_aware_validate_search_space(space, allow_case_scope=True)
    for gate in space.get("objective", {}).get("case_delta_gates", []):
        _case_ids(gate)


def _scoped_report(report: dict[str, Any], required: list[str]) -> tuple[dict[str, Any] | None, list[str]]:
    cases = report.get("cases")
    if not isinstance(cases, list):
        return None, list(required)
    by_id = {
        str(case.get("case_id")): case
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    present = [case_id for case_id in required if case_id in by_id]
    if not present:
        return None, []
    missing = [case_id for case_id in required if case_id not in by_id]
    if missing:
        return None, missing
    scoped = dict(report)
    scoped["cases"] = [by_id[case_id] for case_id in required]
    return scoped, []


def case_scoped_delta_gate_violations(
    space: dict[str, Any],
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gates = list(space.get("objective", {}).get("case_delta_gates", []))
    if not gates:
        return [], []
    summaries: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for gate in gates:
        required = _case_ids(gate)
        if required is None:
            scoped_space = {"objective": {"case_delta_gates": [gate]}}
            gate_summaries, gate_violations = _ORIGINAL_CASE_DELTA(
                scoped_space, baseline, candidate
            )
        else:
            base_scoped, base_missing = _scoped_report(baseline, required)
            cand_scoped, cand_missing = _scoped_report(candidate, required)
            if base_scoped is None and cand_scoped is None and not base_missing and not cand_missing:
                continue
            missing = sorted(set(base_missing + cand_missing))
            if base_scoped is None or cand_scoped is None or missing:
                violations.append({
                    "gate": "case_scope_incomplete",
                    "metric": str(gate["metric"]),
                    "case_ids": required,
                    "missing_cases": missing,
                    "missing_count": len(missing),
                })
                continue
            raw_gate = {
                "metric": gate["metric"],
                "stat": gate["stat"],
                "minimum_delta": gate["minimum_delta"],
            }
            scoped_space = {"objective": {"case_delta_gates": [raw_gate]}}
            gate_summaries, gate_violations = _ORIGINAL_CASE_DELTA(
                scoped_space, base_scoped, cand_scoped
            )
            for item in gate_summaries:
                item["case_ids"] = required
            for item in gate_violations:
                item["case_ids"] = required
        summaries.extend(gate_summaries)
        violations.extend(gate_violations)
    return summaries, violations


def install() -> None:
    v3.install()
    tuning_iteration.strict_validate_search_space = validate_case_scopes
    engine.validate_search_space = validate_case_scopes
    engine.case_delta_gate_violations = case_scoped_delta_gate_violations


def self_test() -> None:
    install()
    space = {
        "schema_version": 1,
        "search_space_id": "case-scope-self-test",
        "strategy": "one-at-a-time",
        "max_candidates": 2,
        "baseline": {
            "aec_mu": 0.22,
            "ns_floor": 0.12,
            "agc_target_dbfs": -20.0,
            "limiter_dbfs": -2.0,
        },
        "parameters": {"aec_mu": [0.22]},
        "objective": {
            "metrics": [{
                "name": "pass_rate",
                "direction": "max",
                "weight": 1.0,
                "scale": 0.02,
                "max_regression": 0.0,
                "minimum_units": 1,
            }],
            "case_delta_gates": [{
                "metric": "vad_recall",
                "stat": "min",
                "minimum_delta": -0.03,
                "case_ids": ["dt-a", "dt-b"],
            }],
        },
    }
    engine.validate_search_space(space)
    bad_case_ids = json.loads(json.dumps(space))
    bad_case_ids["objective"]["case_delta_gates"][0]["case_ids"] = [1]
    try:
        engine.validate_search_space(bad_case_ids)
    except ValueError:
        pass
    else:
        raise AssertionError("case-scoped validator must reject non-string case ids")
    baseline = {
        "validation_result": "PASS",
        "summary": {"pass_rate": 1.0},
        "cases": [
            {"case_id": "dt-a", "scenario": "aec-doubletalk", "metrics": {"vad_recall": 0.80}},
            {"case_id": "dt-b", "scenario": "aec-doubletalk-balance", "metrics": {"vad_recall": 0.75}},
            {"case_id": "far", "scenario": "aec-farend", "metrics": {"erle_db": 10.0}},
        ],
    }
    passing = json.loads(json.dumps(baseline))
    passing["cases"][0]["metrics"]["vad_recall"] = 0.78
    passing["cases"][1]["metrics"]["vad_recall"] = 0.73
    summary, violations = engine.case_delta_gate_violations(space, baseline, passing)
    assert not violations
    assert len(summary) == 1 and summary[0]["cases"] == 2
    assert summary[0]["case_ids"] == ["dt-a", "dt-b"]

    failing = json.loads(json.dumps(baseline))
    failing["cases"][1]["metrics"]["vad_recall"] = 0.70
    _summary, violations = engine.case_delta_gate_violations(space, baseline, failing)
    assert any(item["gate"] == "case_delta_regression" for item in violations)

    unrelated = {
        "validation_result": "PASS",
        "summary": {"pass_rate": 1.0},
        "cases": [{"case_id": "motion", "scenario": "aec-motion", "metrics": {"erle_db": 8.0}}],
    }
    assert engine.case_delta_gate_violations(space, unrelated, unrelated) == ([], [])

    partial = {
        "validation_result": "PASS",
        "summary": {"pass_rate": 1.0},
        "cases": [{"case_id": "dt-a", "scenario": "aec-doubletalk", "metrics": {"vad_recall": 0.80}}],
    }
    _summary, violations = engine.case_delta_gate_violations(space, partial, partial)
    assert any(item["gate"] == "case_scope_incomplete" for item in violations)
    print("case-scoped research optimizer self-test: OK")


def main() -> int:
    install()
    if "--self-test" in sys.argv:
        self_test()
        return 0
    return v3.core.main()


if __name__ == "__main__":
    raise SystemExit(main())
