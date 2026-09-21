#!/usr/bin/env python3
"""Hierarchical dataset-driven algorithm-family and parameter optimizer.

Algorithm families are compared only on development data at one frozen baseline
tuning. Parameter search then runs only on the development-selected algorithm
family. Validation/shadow data see only the final joint winner and may reject it;
they never re-rank algorithms or parameters. Maximum authority is
FROZEN_RESEARCH_CANDIDATE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
from pathlib import Path
from typing import Any

import research_dataset_registry as dataset_registry
import research_optimizer as core
import research_optimizer_v3 as v3
import research_optimizer_v5 as v5
import tuning_iteration
import tuning_iteration_engine as engine

DEFAULT_ALGORITHM_SPACE = Path(
    ".github/research/continuous-optimization/algorithm-space-v1.json"
)
DEFAULT_REGISTRY = Path(
    ".github/research/continuous-optimization/dataset-registry.json"
)


def sha256_file(path: Path) -> str:
    return engine.sha256_file(path)


def _safe_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {raw}")
    return resolved


def _canonical_hash(payload: Any, length: int) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def algorithm_candidate_id(algorithm: dict[str, Any]) -> str:
    return _canonical_hash({"algorithm": algorithm}, 12)


def joint_candidate_id(algorithm: dict[str, Any], tuning: dict[str, float]) -> str:
    return _canonical_hash({"algorithm": algorithm, "tuning": tuning}, 12)


def joint_research_candidate_id(
    hypothesis_id: str,
    source_sha: str,
    algorithm: dict[str, Any],
    tuning: dict[str, float],
) -> str:
    return _canonical_hash(
        {
            "hypothesis_id": hypothesis_id,
            "source_sha": source_sha,
            "algorithm": algorithm,
            "tuning": tuning,
        },
        16,
    )


def validate_algorithm_space(payload: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "algorithm_space_id",
        "authority",
        "max_algorithm_variants",
        "baseline_algorithm_id",
        "parameter_search_space",
        "baseline_tuning",
        "common_build_contract",
        "variants",
        "hierarchy",
        "output_authority",
    }
    if set(payload) != required or payload["schema_version"] != 1:
        raise ValueError("algorithm space fields/schema invalid")
    if payload["authority"] != "RESEARCH_SELECTION_ONLY":
        raise ValueError("algorithm space authority drift")
    variants = payload["variants"]
    if not isinstance(variants, list) or not variants:
        raise ValueError("algorithm variants required")
    if len(variants) > int(payload["max_algorithm_variants"]):
        raise ValueError("algorithm variant budget exceeded")
    ids: list[str] = []
    allowed_aec = {"MDF", "NLMS"}
    allowed_ns = {"EMA", "MCRA"}
    for item in variants:
        if set(item) != {"algorithm_id", "aec_backend", "ns_estimator"}:
            raise ValueError("algorithm variant fields invalid")
        algorithm_id = str(item["algorithm_id"])
        if not algorithm_id or algorithm_id in ids:
            raise ValueError("algorithm ids must be unique non-empty strings")
        if item["aec_backend"] not in allowed_aec:
            raise ValueError("unsupported AEC backend in algorithm space")
        if item["ns_estimator"] not in allowed_ns:
            raise ValueError("unsupported NS estimator in algorithm space")
        ids.append(algorithm_id)
    if payload["baseline_algorithm_id"] not in ids:
        raise ValueError("baseline algorithm missing")
    if ids[0] != payload["baseline_algorithm_id"]:
        raise ValueError("baseline algorithm must be first")

    common = payload["common_build_contract"]
    if common != {
        "resampler_mode": "BANDLIMITED",
        "bf_direction_tracking": True,
        "fast_math": False,
        "simd_backend": "SCALAR",
    }:
        raise ValueError("common build contract drifted")

    baseline = payload["baseline_tuning"]
    if set(baseline) != {
        "aec_mu", "ns_floor", "agc_target_dbfs", "limiter_dbfs"
    }:
        raise ValueError("baseline tuning fields invalid")
    if not all(math.isfinite(float(value)) for value in baseline.values()):
        raise ValueError("baseline tuning must be finite")

    hierarchy = payload["hierarchy"]
    if hierarchy.get("holdout_feedback_to_selection") is not False:
        raise ValueError("holdout feedback to selection is forbidden")
    if hierarchy.get("maximum_algorithm_rounds") != 1:
        raise ValueError("v1 permits exactly one algorithm screen")
    authority = payload["output_authority"]
    if authority != {
        "maximum_status": "FROZEN_RESEARCH_CANDIDATE",
        "next_gate": "validation-grade-blind",
        "automatic_main_mutation": False,
        "automatic_shipping_promotion": False,
        "hil_authority": False,
        "product_certification_authority": False,
    }:
        raise ValueError("algorithm output authority drifted")


def load_algorithm_space(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_algorithm_space(payload)
    return payload


def load_processors(
    path: Path,
    algorithm_space: dict[str, Any],
    root: Path,
) -> dict[str, Path]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {item["algorithm_id"] for item in algorithm_space["variants"]}
    if set(payload) != expected:
        raise ValueError("processor map must exactly match algorithm variants")
    resolved: dict[str, Path] = {}
    for algorithm_id, raw in payload.items():
        processor = _safe_path(root, str(raw))
        if not processor.is_file():
            raise ValueError(f"processor missing for {algorithm_id}: {processor}")
        resolved[algorithm_id] = processor
    return resolved


def _report_binding(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "validation_result": report.get("validation_result"),
        "summary": report.get("summary", {}),
    }


def _evaluate(
    root: Path,
    processor: Path,
    unit: dict[str, Any],
    tuning: dict[str, float],
    report_path: Path,
) -> dict[str, Any]:
    report, _elapsed = engine.run_validation(
        root,
        processor,
        unit["corpus"],
        unit["policy"],
        unit["dataset_lock"],
        tuning,
        report_path,
    )
    return report


def _rank_algorithms(
    space: dict[str, Any],
    algorithms: list[dict[str, Any]],
    baseline_tuning: dict[str, float],
    dev_units: list[dict[str, Any]],
    matrix: dict[str, dict[str, dict[str, Any]]],
    source_sha: str,
    hypothesis_id: str,
    minimum_score: float,
    minimum_unit_score: float,
    maximum_pareto: int,
    *,
    semantics: engine.IterationSemantics | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    semantics = semantics or v5.case_scoped_semantics()
    metric_specs = engine.objective_metrics(space)
    metric_names = [str(metric["name"]) for metric in metric_specs]
    expected_units: dict[str, list[str]] = {}
    for metric in metric_specs:
        name = str(metric["name"])
        applicable = [
            unit["evaluation_id"]
            for unit in dev_units
            if v3.metric_applies(metric, unit)
        ]
        minimum = v3._minimum_units(metric)
        if len(applicable) < minimum:
            raise ValueError(
                f"algorithm objective {name} has {len(applicable)} units; "
                f"minimum_units={minimum}"
            )
        expected_units[name] = applicable

    baseline_algorithm = algorithms[0]
    baseline_id = str(baseline_algorithm["algorithm_id"])
    ranking: list[dict[str, Any]] = []
    for algorithm in algorithms:
        algorithm_id = str(algorithm["algorithm_id"])
        unit_scores: list[float] = []
        metric_values: dict[str, list[float]] = {
            name: [] for name in metric_names
        }
        violations: list[dict[str, Any]] = []
        for unit in dev_units:
            unit_id = unit["evaluation_id"]
            unit_space = v3.space_for_unit(space, unit)
            baseline_report = matrix[baseline_id][unit_id]
            candidate_report = matrix[algorithm_id][unit_id]
            score, deltas = semantics.score_against_baseline(
                unit_space, baseline_report, candidate_report
            )
            _case_summary, case_violations = semantics.case_delta_gate_violations(
                unit_space, baseline_report, candidate_report
            )
            regression = semantics.regression_violations(
                unit_space, baseline_report, candidate_report
            )
            unit_scores.append(float(score))
            for delta in deltas:
                value = delta.get("directed_delta")
                metric = str(delta["metric"])
                if value is None or not math.isfinite(float(value)):
                    violations.append({
                        "gate": "objective_metric_missing",
                        "unit": unit_id,
                        "metric": metric,
                    })
                else:
                    metric_values[metric].append(float(value))
            for violation in regression + case_violations:
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
        ranking.append({
            "candidate_id": algorithm_candidate_id(algorithm),
            "research_candidate_id": joint_research_candidate_id(
                hypothesis_id, source_sha, algorithm, baseline_tuning
            ),
            "algorithm_id": algorithm_id,
            "algorithm": algorithm,
            "tuning": baseline_tuning,
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
            f"algorithm Pareto frontier {len(frontier)} exceeds "
            f"maximum_pareto_candidates={maximum_pareto}"
        )
    baseline_row = next(
        row for row in ranking if row["algorithm_id"] == baseline_id
    )
    selectable = [
        row
        for row in frontier
        if row["algorithm_id"] != baseline_id
        and row["development_score"] >= minimum_score
        and row["worst_development_unit_score"] >= minimum_unit_score
    ]
    selectable.sort(
        key=lambda row: (
            -row["development_score"],
            -row["worst_development_unit_score"],
            row["research_candidate_id"],
        )
    )
    selected = selectable[0] if selectable else baseline_row
    return selected, ranking, frontier


def execute(
    run_spec: dict[str, Any],
    *,
    repo_root: Path,
    algorithm_space_path: Path,
    processors_path: Path,
    registry_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    semantics = v5.case_scoped_semantics()
    algorithm_space = load_algorithm_space(algorithm_space_path)
    processors = load_processors(processors_path, algorithm_space, repo_root)
    registry = dataset_registry.load_registry(registry_path, repo_root)
    units = core.validate_run_spec(run_spec, registry, repo_root)
    source_sha = str(run_spec["source_sha"])

    parameter_space_path = _safe_path(
        repo_root, str(algorithm_space["parameter_search_space"])
    )
    if str(run_spec["search_space"]) != str(
        algorithm_space["parameter_search_space"]
    ):
        raise ValueError("run spec search_space must equal algorithm parameter space")
    parameter_space = json.loads(
        parameter_space_path.read_text(encoding="utf-8")
    )
    semantics.validate_search_space(parameter_space)
    parameter_candidates = engine.generate_candidates(parameter_space)
    baseline_parameter = parameter_candidates[0]
    if baseline_parameter["tuning"] != algorithm_space["baseline_tuning"]:
        raise ValueError("parameter baseline and algorithm baseline tuning differ")

    algorithms = list(algorithm_space["variants"])
    if len(algorithms) != 4:
        raise ValueError("v1 requires exactly four algorithm variants")
    dev_units = [unit for unit in units if unit["role"] == "development"]
    output_dir.mkdir(parents=True, exist_ok=True)

    algorithm_matrix: dict[str, dict[str, dict[str, Any]]] = {
        str(item["algorithm_id"]): {} for item in algorithms
    }
    algorithm_report_paths: dict[tuple[str, str], Path] = {}
    for algorithm in algorithms:
        algorithm_id = str(algorithm["algorithm_id"])
        for unit in dev_units:
            path = (
                output_dir
                / "reports"
                / "algorithm-screen"
                / algorithm_id
                / f"{unit['evaluation_id']}.json"
            )
            report = _evaluate(
                repo_root,
                processors[algorithm_id],
                unit,
                algorithm_space["baseline_tuning"],
                path,
            )
            algorithm_matrix[algorithm_id][unit["evaluation_id"]] = report
            algorithm_report_paths[(algorithm_id, unit["evaluation_id"])] = path

    policy = run_spec["policy"]
    selected_algorithm, algorithm_ranking, algorithm_frontier = _rank_algorithms(
        parameter_space,
        algorithms,
        algorithm_space["baseline_tuning"],
        dev_units,
        algorithm_matrix,
        source_sha,
        str(run_spec["hypothesis_id"]) + ":algorithm-screen",
        float(policy["minimum_development_score"]),
        float(policy["minimum_development_unit_score"]),
        min(int(policy["maximum_pareto_candidates"]), len(algorithms)),
        semantics=semantics,
    )
    selected_algorithm_id = str(selected_algorithm["algorithm_id"])
    selected_algorithm_payload = next(
        item for item in algorithms
        if item["algorithm_id"] == selected_algorithm_id
    )

    parameter_matrix: dict[str, dict[str, dict[str, Any]]] = {
        candidate["candidate_id"]: {} for candidate in parameter_candidates
    }
    parameter_report_paths: dict[tuple[str, str], Path] = {}
    for candidate in parameter_candidates:
        for unit in dev_units:
            unit_id = unit["evaluation_id"]
            if candidate["candidate_id"] == baseline_parameter["candidate_id"]:
                report = algorithm_matrix[selected_algorithm_id][unit_id]
                path = algorithm_report_paths[(selected_algorithm_id, unit_id)]
            else:
                path = (
                    output_dir
                    / "reports"
                    / "parameter-search"
                    / selected_algorithm_id
                    / unit_id
                    / f"{candidate['candidate_id']}.json"
                )
                report = _evaluate(
                    repo_root,
                    processors[selected_algorithm_id],
                    unit,
                    candidate["tuning"],
                    path,
                )
            parameter_matrix[candidate["candidate_id"]][unit_id] = report
            parameter_report_paths[(candidate["candidate_id"], unit_id)] = path

    selected_parameter, parameter_ranking, parameter_frontier = v3.rank_development(
        parameter_space,
        parameter_candidates,
        units,
        parameter_matrix,
        source_sha,
        str(run_spec["hypothesis_id"]) + ":parameter-search:"
        + selected_algorithm_id,
        registry,
        float(policy["minimum_development_score"]),
        float(policy["minimum_development_unit_score"]),
        int(policy["maximum_pareto_candidates"]),
        semantics=semantics,
    )
    selected_parameter_candidate = next(
        candidate for candidate in parameter_candidates
        if candidate["candidate_id"] == selected_parameter["candidate_id"]
    )
    final_tuning = selected_parameter_candidate["tuning"]

    baseline_algorithm = algorithms[0]
    baseline_algorithm_id = str(baseline_algorithm["algorithm_id"])
    final_joint_id = joint_candidate_id(
        selected_algorithm_payload, final_tuning
    )
    final_research_id = joint_research_candidate_id(
        str(run_spec["hypothesis_id"]),
        source_sha,
        selected_algorithm_payload,
        final_tuning,
    )
    same_as_baseline = (
        selected_algorithm_id == baseline_algorithm_id
        and final_tuning == algorithm_space["baseline_tuning"]
    )

    gate_results: list[dict[str, Any]] = []
    gate_violations: list[dict[str, Any]] = []
    for unit in [
        item for item in units if item["role"] in {"validation", "shadow"}
    ]:
        role_dir = (
            output_dir / "reports" / unit["role"] / unit["evaluation_id"]
        )
        baseline_path = role_dir / "baseline.json"
        baseline_report = _evaluate(
            repo_root,
            processors[baseline_algorithm_id],
            unit,
            algorithm_space["baseline_tuning"],
            baseline_path,
        )
        if same_as_baseline:
            candidate_path = baseline_path
            candidate_report = baseline_report
        else:
            candidate_path = role_dir / "candidate.json"
            candidate_report = _evaluate(
                repo_root,
                processors[selected_algorithm_id],
                unit,
                final_tuning,
                candidate_path,
            )
        unit_space = v3.space_for_unit(parameter_space, unit)
        case_summary, case_violations = semantics.case_delta_gate_violations(
            unit_space, baseline_report, candidate_report
        )
        violations = semantics.regression_violations(
            unit_space, baseline_report, candidate_report
        ) + case_violations
        if baseline_report.get("validation_result") != "PASS":
            violations.append({
                "gate": "baseline_health",
                "actual": baseline_report.get("validation_result"),
            })
        if (
            not same_as_baseline
            and candidate_report.get("validation_result") != "PASS"
        ):
            violations.append({
                "gate": "candidate_validation_result",
                "actual": candidate_report.get("validation_result"),
            })
        gate_results.append({
            "evaluation_id": unit["evaluation_id"],
            "dataset_id": unit["dataset_id"],
            "role": unit["role"],
            "seed": unit["seed"],
            "baseline": _report_binding(baseline_path, baseline_report),
            "candidate": _report_binding(candidate_path, candidate_report),
            "case_delta_summary": case_summary,
            "regression_violations": violations,
        })
        gate_violations.extend(
            {"evaluation_id": unit["evaluation_id"], **item}
            for item in violations
        )

    if dataset_registry.is_terminal_candidate(
        registry, final_joint_id, source_sha
    ):
        gate_violations.append({
            "gate": "terminal_joint_candidate_reuse",
            "candidate_id": final_joint_id,
        })

    if same_as_baseline:
        decision = "KEEP_BASELINE"
        status = "NO_RESEARCH_CANDIDATE"
    elif gate_violations:
        decision = "REJECT_CANDIDATE"
        status = "RESEARCH_CANDIDATE_REJECTED"
    else:
        decision = "FREEZE_RESEARCH_CANDIDATE"
        status = registry["output_authority"]["candidate_status"]

    algorithm_bindings: list[dict[str, Any]] = []
    for row in algorithm_ranking:
        reports = []
        for unit in dev_units:
            path = algorithm_report_paths[
                (row["algorithm_id"], unit["evaluation_id"])
            ]
            report = algorithm_matrix[row["algorithm_id"]][
                unit["evaluation_id"]
            ]
            reports.append({
                "evaluation_id": unit["evaluation_id"],
                "dataset_id": unit["dataset_id"],
                "seed": unit["seed"],
                "report": _report_binding(path, report),
            })
        algorithm_bindings.append({**row, "reports": reports})

    parameter_bindings: list[dict[str, Any]] = []
    for row in parameter_ranking:
        reports = []
        for unit in dev_units:
            path = parameter_report_paths[
                (row["candidate_id"], unit["evaluation_id"])
            ]
            report = parameter_matrix[row["candidate_id"]][
                unit["evaluation_id"]
            ]
            reports.append({
                "evaluation_id": unit["evaluation_id"],
                "dataset_id": unit["dataset_id"],
                "seed": unit["seed"],
                "report": _report_binding(path, report),
            })
        parameter_bindings.append({**row, "reports": reports})

    result = {
        "schema_version": 1,
        "experiment_id": run_spec["experiment_id"],
        "hypothesis_id": run_spec["hypothesis_id"],
        "source_sha": source_sha,
        "authority":
            "research-only-hierarchical-algorithm-parameter-optimization",
        "decision": decision,
        "status": status,
        "shipping_baseline": registry["shipping_baseline"],
        "algorithm_space": {
            "path": str(algorithm_space_path),
            "sha256": sha256_file(algorithm_space_path),
            "variant_count": len(algorithms),
        },
        "parameter_search_space": {
            "path": str(parameter_space_path),
            "sha256": sha256_file(parameter_space_path),
            "candidate_count": len(parameter_candidates),
        },
        "development": {
            "units": [{
                "evaluation_id": unit["evaluation_id"],
                "dataset_id": unit["dataset_id"],
                "seed": unit["seed"],
                "tier": unit["tier"],
            } for unit in dev_units],
            "algorithm_screen": {
                "ranking": algorithm_bindings,
                "pareto_frontier": [
                    row["research_candidate_id"]
                    for row in algorithm_frontier
                ],
                "selected_algorithm_id": selected_algorithm_id,
            },
            "parameter_search": {
                "algorithm_id": selected_algorithm_id,
                "ranking": parameter_bindings,
                "pareto_frontier": [
                    row["research_candidate_id"]
                    for row in parameter_frontier
                ],
            },
        },
        "selected": {
            "candidate_id": final_joint_id,
            "research_candidate_id": final_research_id,
            "algorithm_id": selected_algorithm_id,
            "algorithm": selected_algorithm_payload,
            "tuning_candidate_id": selected_parameter["candidate_id"],
            "tuning": final_tuning,
            "algorithm_development_score":
                selected_algorithm["development_score"],
            "parameter_development_score":
                selected_parameter["development_score"],
            "parameter_worst_development_unit_score":
                selected_parameter["worst_development_unit_score"],
        },
        "generalization_gates": gate_results,
        "gate_violations": gate_violations,
        "output_authority": registry["output_authority"],
        "next_gate": (
            registry["output_authority"]["next_gate"]
            if status == "FROZEN_RESEARCH_CANDIDATE"
            else None
        ),
        "automatic_shipping_promotion": False,
        "automatic_main_mutation": False,
    }
    output_path = output_dir / "optimization-result.json"
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    semantics = v5.case_scoped_semantics()
    repo_root = Path(__file__).resolve().parents[3]
    algorithm_path = repo_root / DEFAULT_ALGORITHM_SPACE
    algorithm_space = load_algorithm_space(algorithm_path)
    parameter_path = repo_root / algorithm_space["parameter_search_space"]
    parameter_space = json.loads(parameter_path.read_text(encoding="utf-8"))
    semantics.validate_search_space(parameter_space)
    candidates = engine.generate_candidates(parameter_space)
    assert len(algorithm_space["variants"]) == 4
    assert len(candidates) == 8
    ids = {
        joint_candidate_id(algorithm, candidate["tuning"])
        for algorithm in algorithm_space["variants"]
        for candidate in candidates
    }
    assert len(ids) == 32
    baseline = algorithm_space["baseline_tuning"]
    same_tuning_ids = {
        joint_candidate_id(algorithm, baseline)
        for algorithm in algorithm_space["variants"]
    }
    assert len(same_tuning_ids) == 4

    fixture_space = {
        "schema_version": 1,
        "search_space_id": "algorithm-screen-self-test",
        "strategy": "one-at-a-time",
        "max_candidates": 1,
        "baseline": baseline,
        "parameters": {"aec_mu": [0.22]},
        "objective": {
            "metrics": [{
                "name": "pass_rate",
                "direction": "max",
                "weight": 1.0,
                "scale": 0.02,
                "max_regression": 0.0,
                "minimum_units": 2,
            }],
            "case_delta_gates": [],
        },
    }
    semantics.validate_search_space(fixture_space)
    algorithms = algorithm_space["variants"][:2]
    units = [
        {
            "evaluation_id": "d1",
            "dataset_id": "synthetic-regression",
            "role": "development",
            "seed": 1,
        },
        {
            "evaluation_id": "d2",
            "dataset_id": "synthetic-regression",
            "role": "development",
            "seed": 2,
        },
    ]
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for index, algorithm in enumerate(algorithms):
        value = 1.0 + 0.02 * index
        matrix[algorithm["algorithm_id"]] = {
            "d1": {"validation_result": "PASS", "summary": {"pass_rate": value}},
            "d2": {"validation_result": "PASS", "summary": {"pass_rate": value}},
        }
    selected, ranking, frontier = _rank_algorithms(
        fixture_space,
        algorithms,
        baseline,
        units,
        matrix,
        "a" * 40,
        "fixture",
        0.5,
        0.0,
        2,
        semantics=semantics,
    )
    assert selected["algorithm_id"] == algorithms[1]["algorithm_id"]
    assert len(ranking) == 2 and frontier
    print("hierarchical algorithm+parameter optimizer self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--algorithm-space", type=Path, default=DEFAULT_ALGORITHM_SPACE
    )
    parser.add_argument("--processors-json", type=Path)
    parser.add_argument("--run-spec", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if (
        args.processors_json is None
        or args.run_spec is None
        or args.output_dir is None
    ):
        parser.error("--processors-json, --run-spec and --output-dir are required")

    root = args.repo_root.resolve()
    algorithm_space_path = _safe_path(root, str(args.algorithm_space))
    processors_path = _safe_path(root, str(args.processors_json))
    run_spec_path = _safe_path(root, str(args.run_spec))
    registry_path = _safe_path(root, str(args.registry))
    for path in (
        algorithm_space_path,
        processors_path,
        run_spec_path,
        registry_path,
    ):
        if not path.is_file():
            raise SystemExit(f"required input missing: {path}")
    run_spec = json.loads(run_spec_path.read_text(encoding="utf-8"))
    if (
        os.environ.get("GITHUB_SHA")
        and run_spec.get("source_sha") != os.environ["GITHUB_SHA"]
    ):
        raise SystemExit("run spec source_sha must equal GITHUB_SHA")

    result = execute(
        run_spec,
        repo_root=root,
        algorithm_space_path=algorithm_space_path,
        processors_path=processors_path,
        registry_path=registry_path,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "decision": result["decision"],
        "status": result["status"],
        "algorithm": result["selected"]["algorithm_id"],
        "candidate": result["selected"]["research_candidate_id"],
        "next_gate": result["next_gate"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
