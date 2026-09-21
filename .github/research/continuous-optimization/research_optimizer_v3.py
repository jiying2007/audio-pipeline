#!/usr/bin/env python3
"""Dataset-aware research optimizer entrypoint for heterogeneous development units."""
from __future__ import annotations

import json
import math
import statistics
import sys
from typing import Any

import research_optimizer as core
import tuning_iteration
import tuning_iteration_engine as engine

EXTRA_OBJECTIVE_METRICS = {
    "median_output_render_corr_reduction",
    "p10_output_render_corr_reduction",
}
def _metric_datasets(metric: dict[str, Any]) -> list[str] | None:
    return engine.metric_datasets(metric)


def _minimum_units(metric: dict[str, Any]) -> int:
    return engine.metric_minimum_units(metric)


def dataset_aware_validate_search_space(
    space: dict[str, Any], *, allow_case_scope: bool = False
) -> None:
    tuning_iteration.strict_validate_search_space(
        space,
        allow_dataset_scope=True,
        allow_case_scope=allow_case_scope,
        extra_objective_metrics=EXTRA_OBJECTIVE_METRICS,
    )
    for metric in engine.objective_metrics(space):
        datasets = _metric_datasets(metric)
        _minimum_units(metric)
        if datasets is not None and "synthetic-regression" not in datasets:
            raise ValueError(
                f"dataset-scoped metric {metric['name']} must include synthetic-regression "
                "for independent validation/shadow gating"
            )


def dataset_aware_semantics(
    *,
    allow_case_scope: bool = False,
    case_delta_gate_violations: Any = None,
) -> engine.IterationSemantics:
    def validate(space: dict[str, Any]) -> None:
        dataset_aware_validate_search_space(
            space, allow_case_scope=allow_case_scope
        )

    return engine.IterationSemantics(
        validate_search_space=validate,
        enforce_partition_independence=tuning_iteration.strict_partition_independence,
        score_against_baseline=tuning_iteration.strict_score,
        regression_violations=tuning_iteration.strict_regression,
        case_delta_gate_violations=(
            case_delta_gate_violations or engine.case_delta_gate_violations
        ),
    )


def metric_applies(metric: dict[str, Any], unit: dict[str, Any]) -> bool:
    datasets = _metric_datasets(metric)
    return datasets is None or str(unit["dataset_id"]) in datasets


def space_for_unit(space: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    scoped = json.loads(json.dumps(space))
    scoped["objective"]["metrics"] = [
        metric for metric in engine.objective_metrics(space) if metric_applies(metric, unit)
    ]
    if not scoped["objective"]["metrics"]:
        raise ValueError(f"no objective metrics apply to development unit {unit['evaluation_id']}")
    return scoped


def rank_development(
    space: dict[str, Any],
    candidates: list[dict[str, Any]],
    units: list[dict[str, Any]],
    matrix: dict[str, dict[str, dict[str, Any]]],
    source_sha: str,
    hypothesis_id: str,
    registry: dict[str, Any],
    minimum_score: float,
    minimum_unit_score: float,
    maximum_pareto: int,
    *,
    semantics: engine.IterationSemantics | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    semantics = semantics or dataset_aware_semantics()
    dev_units = [unit for unit in units if unit["role"] == "development"]
    if not dev_units:
        raise ValueError("development units required")
    baseline = candidates[0]
    metric_specs = engine.objective_metrics(space)
    metric_names = [str(metric["name"]) for metric in metric_specs]
    expected_units: dict[str, list[str]] = {}
    for metric in metric_specs:
        name = str(metric["name"])
        applicable = [unit["evaluation_id"] for unit in dev_units if metric_applies(metric, unit)]
        minimum = _minimum_units(metric)
        if len(applicable) < minimum:
            raise ValueError(
                f"objective metric {name} has only {len(applicable)} applicable development "
                f"units; minimum_units={minimum}"
            )
        expected_units[name] = applicable

    ranking: list[dict[str, Any]] = []
    for candidate in candidates:
        unit_scores: list[float] = []
        metric_values: dict[str, list[float]] = {name: [] for name in metric_names}
        violations: list[dict[str, Any]] = []
        for unit in dev_units:
            unit_id = unit["evaluation_id"]
            base_report = matrix[baseline["candidate_id"]][unit_id]
            candidate_report = matrix[candidate["candidate_id"]][unit_id]
            unit_space = space_for_unit(space, unit)
            score, deltas = semantics.score_against_baseline(
                unit_space, base_report, candidate_report
            )
            _case_summary, case_violations = semantics.case_delta_gate_violations(
                unit_space, base_report, candidate_report
            )
            metric_violations = semantics.regression_violations(
                unit_space, base_report, candidate_report
            )
            unit_scores.append(float(score))
            for delta in deltas:
                value = delta.get("directed_delta")
                if value is None or not math.isfinite(float(value)):
                    violations.append({
                        "gate": "objective_metric_missing",
                        "unit": unit_id,
                        "metric": delta["metric"],
                    })
                else:
                    metric_values[str(delta["metric"])].append(float(value))
            for violation in metric_violations + case_violations:
                violations.append({"unit": unit_id, **violation})
            if candidate_report.get("validation_result") != "PASS":
                violations.append({
                    "gate": "development_validation_result",
                    "unit": unit_id,
                    "actual": candidate_report.get("validation_result"),
                })

        objective_vector: dict[str, float] = {}
        objective_coverage: dict[str, dict[str, int]] = {}
        for metric in metric_specs:
            name = str(metric["name"])
            values = metric_values[name]
            expected = len(expected_units[name])
            objective_coverage[name] = {
                "expected_units": expected,
                "actual_units": len(values),
            }
            if len(values) != expected:
                objective_vector[name] = -1.0e12
                violations.append({
                    "gate": "objective_metric_coverage",
                    "metric": name,
                    "expected_units": expected,
                    "actual_units": len(values),
                })
            else:
                objective_vector[name] = statistics.fmean(values)

        mean_score = statistics.fmean(unit_scores)
        worst_score = min(unit_scores)
        tuning_id = candidate["candidate_id"]
        if core.dataset_registry.is_terminal_candidate(registry, tuning_id, source_sha):
            violations.append({
                "gate": "terminal_candidate_reuse",
                "candidate_id": tuning_id,
                "source_sha": source_sha,
            })
        ranking.append({
            "candidate_id": tuning_id,
            "research_candidate_id": core.research_candidate_id(
                hypothesis_id, source_sha, candidate["tuning"]
            ),
            "label": candidate["label"],
            "tuning": candidate["tuning"],
            "development_score": mean_score,
            "worst_development_unit_score": worst_score,
            "objective_vector": objective_vector,
            "objective_coverage": objective_coverage,
            "eligible": not violations,
            "violations": violations,
        })

    eligible = [row for row in ranking if row["eligible"]]
    frontier = core._pareto_front(eligible, metric_names) if eligible else []
    if len(frontier) > maximum_pareto:
        raise ValueError(
            f"Pareto frontier {len(frontier)} exceeds maximum_pareto_candidates={maximum_pareto}"
        )
    baseline_id = baseline["candidate_id"]
    selectable = [
        row for row in frontier
        if row["candidate_id"] != baseline_id
        and row["development_score"] >= minimum_score
        and row["worst_development_unit_score"] >= minimum_unit_score
    ]
    selectable.sort(key=lambda row: (
        -row["development_score"],
        -row["worst_development_unit_score"],
        row["research_candidate_id"],
    ))
    selected = selectable[0] if selectable else next(
        row for row in ranking if row["candidate_id"] == baseline_id
    )
    return selected, ranking, frontier


def self_test() -> None:
    engine_validate = engine.validate_search_space
    engine_case_gate = engine.case_delta_gate_violations
    core_rank = core.rank_development
    semantics = dataset_aware_semantics()
    assert engine.validate_search_space is engine_validate
    assert engine.case_delta_gate_violations is engine_case_gate
    assert core.rank_development is core_rank
    core.self_test()
    assert engine.validate_search_space is engine_validate
    assert engine.case_delta_gate_violations is engine_case_gate
    assert core.rank_development is core_rank
    space = {
        "schema_version": 1,
        "search_space_id": "dataset-aware-self-test",
        "strategy": "one-at-a-time",
        "max_candidates": 3,
        "baseline": {
            "aec_mu": 0.22,
            "ns_floor": 0.12,
            "agc_target_dbfs": -20.0,
            "limiter_dbfs": -2.0,
        },
        "parameters": {"aec_mu": [0.22, 0.23]},
        "objective": {"metrics": [
            {
                "name": "pass_rate", "direction": "max", "weight": 8.0,
                "scale": 0.02, "max_regression": 0.0, "minimum_units": 3,
            },
            {
                "name": "median_output_render_corr_reduction", "direction": "max",
                "weight": 2.0, "scale": 0.05, "max_regression": 0.01,
                "datasets": ["synthetic-regression", "aec-motion-regression"],
                "minimum_units": 2,
            },
        ]},
    }
    semantics.validate_search_space(space)
    candidates = engine.generate_candidates(space)
    bad_dataset = json.loads(json.dumps(space))
    bad_dataset["objective"]["metrics"][1]["datasets"] = [1]
    try:
        semantics.validate_search_space(bad_dataset)
    except ValueError:
        pass
    else:
        raise AssertionError("dataset-aware validator must reject non-string dataset ids")
    baseline_id = candidates[0]["candidate_id"]
    better = next(item for item in candidates if item["candidate_id"] != baseline_id)
    units = [
        {"evaluation_id": "synthetic", "dataset_id": "synthetic-regression", "role": "development", "seed": 1},
        {"evaluation_id": "motion", "dataset_id": "aec-motion-regression", "role": "development", "seed": 2},
        {"evaluation_id": "public", "dataset_id": "public-development-diverse", "role": "development", "seed": 3},
    ]
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for candidate in candidates:
        gain = 0.02 if candidate["candidate_id"] == better["candidate_id"] else 0.0
        matrix[candidate["candidate_id"]] = {
            "synthetic": {
                "validation_result": "PASS",
                "summary": {"pass_rate": 1.0, "median_output_render_corr_reduction": 0.50 + gain},
            },
            "motion": {
                "validation_result": "PASS",
                "summary": {"pass_rate": 1.0, "median_output_render_corr_reduction": 0.40 + gain},
            },
            "public": {"validation_result": "PASS", "summary": {"pass_rate": 1.0}},
        }
    selected, ranking, _ = rank_development(
        space, candidates, units, matrix, "c" * 40, "dataset-aware-hypothesis",
        {"terminal_candidates": []}, 0.1, 0.0, 8,
        semantics=semantics,
    )
    assert selected["candidate_id"] == better["candidate_id"]
    chosen = next(row for row in ranking if row["candidate_id"] == better["candidate_id"])
    assert chosen["eligible"] is True
    assert chosen["objective_coverage"]["median_output_render_corr_reduction"] == {
        "expected_units": 2, "actual_units": 2,
    }
    print("dataset-aware research optimizer self-test: OK")


def main() -> int:
    if "--self-test" in sys.argv:
        self_test()
        return 0
    return core.main(
        semantics=dataset_aware_semantics(),
        ranker=rank_development,
    )


if __name__ == "__main__":
    raise SystemExit(main())
