#!/usr/bin/env python3
"""Multi-seed research optimizer with cross-dataset gates and Pareto selection.

Development data may rank candidates. Validation/shadow data can only accept or
reject the single development winner; they never rescue or re-rank candidates.
The maximum output authority is FROZEN_RESEARCH_CANDIDATE.
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

import authority
import research_dataset_registry as dataset_registry
import tuning_iteration
import tuning_iteration_engine as engine

SHA_RE = dataset_registry.SHA_RE
ROLES = ("development", "validation", "shadow")
DEFAULT_REGISTRY = Path(".github/research/continuous-optimization/dataset-registry.json")


def sha256_file(path: Path) -> str:
    return engine.sha256_file(path)


def research_candidate_id(hypothesis_id: str, source_sha: str, tuning: dict[str, float]) -> str:
    payload = json.dumps({
        "hypothesis_id": hypothesis_id,
        "source_sha": source_sha,
        "tuning": tuning,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _safe_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {raw}")
    return resolved


def validate_run_spec(spec: dict[str, Any], registry: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    required = {
        "schema_version", "experiment_id", "hypothesis_id", "source_sha", "search_space",
        "policy", "evaluations",
    }
    if set(spec) != required or spec["schema_version"] != 1:
        raise ValueError("optimization run spec fields/schema invalid")
    if not str(spec["experiment_id"]) or not str(spec["hypothesis_id"]):
        raise ValueError("experiment_id and hypothesis_id are required")
    if not SHA_RE.fullmatch(str(spec["source_sha"])):
        raise ValueError("source_sha must be an exact 40-char commit SHA")
    search_space = _safe_path(root, str(spec["search_space"]))
    if not search_space.is_file():
        raise ValueError("search_space missing")

    policy = spec["policy"]
    if set(policy) != {
        "minimum_development_score", "minimum_development_unit_score",
        "minimum_distinct_development_seeds", "maximum_pareto_candidates",
    }:
        raise ValueError("optimization policy fields invalid")
    for key in ("minimum_development_score", "minimum_development_unit_score"):
        if not math.isfinite(float(policy[key])):
            raise ValueError(f"{key} must be finite")
    min_seeds = int(policy["minimum_distinct_development_seeds"])
    if min_seeds < 2 or min_seeds > 16:
        raise ValueError("minimum_distinct_development_seeds must be 2..16")
    max_frontier = int(policy["maximum_pareto_candidates"])
    if max_frontier < 1 or max_frontier > 32:
        raise ValueError("maximum_pareto_candidates must be 1..32")

    evaluations = spec["evaluations"]
    if not isinstance(evaluations, list) or not evaluations:
        raise ValueError("evaluations must be non-empty")
    seen: set[str] = set()
    resolved: list[dict[str, Any]] = []
    role_counts = {role: 0 for role in ROLES}
    development_seeds: set[int] = set()
    auth = authority.load_authority()
    for item in evaluations:
        fields = {"evaluation_id", "dataset_id", "role", "seed", "corpus", "dataset_lock", "policy"}
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("evaluation entry fields invalid")
        evaluation_id = item["evaluation_id"]
        if not isinstance(evaluation_id, str) or not evaluation_id or evaluation_id in seen:
            raise ValueError("evaluation_id must be unique non-empty string")
        seen.add(evaluation_id)
        role = item["role"]
        if role not in ROLES:
            raise ValueError(f"invalid evaluation role: {role}")
        dataset_id = str(item["dataset_id"])
        selection = role == "development"
        if not dataset_registry.role_allowed(registry, dataset_id, role, selection=selection):
            raise ValueError(f"registry forbids dataset={dataset_id} role={role}")
        seed = item["seed"]
        if type(seed) is not int or seed < 0 or seed >= 2 ** 32:
            raise ValueError(f"invalid seed for {evaluation_id}")
        corpus = _safe_path(root, str(item["corpus"]))
        dataset_lock = _safe_path(root, str(item["dataset_lock"]))
        policy_path = _safe_path(root, str(item["policy"]))
        for path, label in ((corpus, "corpus"), (dataset_lock, "dataset_lock"), (policy_path, "policy")):
            if not path.is_file():
                raise ValueError(f"{evaluation_id} {label} missing: {path}")
        corpus_payload = json.loads(corpus.read_text(encoding="utf-8"))
        tier = corpus_payload.get("tier")
        if not authority.optimizer_role_allowed(auth, tier, role):
            raise ValueError(f"authority forbids corpus tier={tier!r} as optimizer role={role!r}")
        generator = corpus_payload.get("generator") or {}
        actual_seed = generator.get("seed") if isinstance(generator, dict) else None
        if actual_seed is not None and int(actual_seed) != seed:
            raise ValueError(f"declared seed mismatch for {evaluation_id}")
        role_counts[role] += 1
        if role == "development":
            development_seeds.add(seed)
        resolved.append({
            **item,
            "corpus": corpus,
            "dataset_lock": dataset_lock,
            "policy": policy_path,
            "tier": tier,
        })
    if len(development_seeds) < min_seeds:
        raise ValueError("insufficient independent development seeds")
    if role_counts["validation"] < 1 or role_counts["shadow"] < 1:
        raise ValueError("at least one validation and one shadow gate are required")
    return resolved


def _pareto_front(rows: list[dict[str, Any]], metric_names: list[str]) -> list[dict[str, Any]]:
    frontier: list[dict[str, Any]] = []
    for row in rows:
        vector = row["objective_vector"]
        dominated = False
        for other in rows:
            if other is row:
                continue
            ov = other["objective_vector"]
            if all(ov[name] >= vector[name] - 1.0e-12 for name in metric_names) and any(
                    ov[name] > vector[name] + 1.0e-12 for name in metric_names):
                dominated = True
                break
        if not dominated:
            frontier.append(row)
    return sorted(frontier, key=lambda item: item["candidate_id"])


def rank_development(space: dict[str, Any], candidates: list[dict[str, Any]],
                     units: list[dict[str, Any]], matrix: dict[str, dict[str, dict[str, Any]]],
                     source_sha: str, hypothesis_id: str, registry: dict[str, Any],
                     minimum_score: float, minimum_unit_score: float,
                     maximum_pareto: int) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    dev_units = [unit for unit in units if unit["role"] == "development"]
    if not dev_units:
        raise ValueError("development units required")
    baseline = candidates[0]
    metric_specs = engine.objective_metrics(space)
    metric_names = [str(metric["name"]) for metric in metric_specs]
    ranking: list[dict[str, Any]] = []
    for candidate in candidates:
        unit_scores: list[float] = []
        metric_values: dict[str, list[float]] = {name: [] for name in metric_names}
        violations: list[dict[str, Any]] = []
        for unit in dev_units:
            unit_id = unit["evaluation_id"]
            base_report = matrix[baseline["candidate_id"]][unit_id]
            candidate_report = matrix[candidate["candidate_id"]][unit_id]
            score, deltas = engine.score_against_baseline(space, base_report, candidate_report)
            _case_summary, case_violations = engine.case_delta_gate_violations(space, base_report, candidate_report)
            metric_violations = engine.regression_violations(space, base_report, candidate_report)
            unit_scores.append(float(score))
            for delta in deltas:
                value = delta.get("directed_delta")
                if value is None or not math.isfinite(float(value)):
                    violations.append({"gate": "objective_metric_missing", "unit": unit_id, "metric": delta["metric"]})
                else:
                    metric_values[str(delta["metric"])].append(float(value))
            for violation in metric_violations + case_violations:
                violations.append({"unit": unit_id, **violation})
            if candidate_report.get("validation_result") != "PASS":
                violations.append({
                    "gate": "development_validation_result", "unit": unit_id,
                    "actual": candidate_report.get("validation_result"),
                })
        objective_vector: dict[str, float] = {}
        for name in metric_names:
            values = metric_values[name]
            if len(values) != len(dev_units):
                objective_vector[name] = -1.0e12
                violations.append({"gate": "objective_metric_coverage", "metric": name})
            else:
                objective_vector[name] = statistics.fmean(values)
        mean_score = statistics.fmean(unit_scores)
        worst_score = min(unit_scores)
        tuning_id = candidate["candidate_id"]
        terminal = dataset_registry.is_terminal_candidate(registry, tuning_id, source_sha)
        if terminal:
            violations.append({"gate": "terminal_candidate_reuse", "candidate_id": tuning_id, "source_sha": source_sha})
        ranking.append({
            "candidate_id": tuning_id,
            "research_candidate_id": research_candidate_id(hypothesis_id, source_sha, candidate["tuning"]),
            "label": candidate["label"],
            "tuning": candidate["tuning"],
            "development_score": mean_score,
            "worst_development_unit_score": worst_score,
            "objective_vector": objective_vector,
            "eligible": not violations,
            "violations": violations,
        })

    eligible = [row for row in ranking if row["eligible"]]
    frontier = _pareto_front(eligible, metric_names) if eligible else []
    if len(frontier) > maximum_pareto:
        raise ValueError(f"Pareto frontier {len(frontier)} exceeds maximum_pareto_candidates={maximum_pareto}")
    baseline_id = baseline["candidate_id"]
    selectable = [
        row for row in frontier
        if row["candidate_id"] != baseline_id
        and row["development_score"] >= minimum_score
        and row["worst_development_unit_score"] >= minimum_unit_score
    ]
    selectable.sort(key=lambda row: (
        -row["development_score"], -row["worst_development_unit_score"], row["research_candidate_id"]
    ))
    selected = selectable[0] if selectable else next(row for row in ranking if row["candidate_id"] == baseline_id)
    return selected, ranking, frontier


def _evaluate(repo_root: Path, processor: Path, unit: dict[str, Any], tuning: dict[str, float],
              report_path: Path) -> dict[str, Any]:
    report, _elapsed = engine.run_validation(
        repo_root, processor, unit["corpus"], unit["policy"], unit["dataset_lock"], tuning, report_path
    )
    return report


def _report_binding(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path), "sha256": sha256_file(path),
        "validation_result": report.get("validation_result"), "summary": report.get("summary", {}),
    }


def execute(spec: dict[str, Any], *, repo_root: Path, processor: Path,
            registry_path: Path, output_dir: Path) -> dict[str, Any]:
    tuning_iteration.install_fail_closed_guards()
    registry = dataset_registry.load_registry(registry_path, repo_root)
    units = validate_run_spec(spec, registry, repo_root)
    source_sha = str(spec["source_sha"])
    search_space_path = _safe_path(repo_root, str(spec["search_space"]))
    space = json.loads(search_space_path.read_text(encoding="utf-8"))
    engine.validate_search_space(space)
    candidates = engine.generate_candidates(space)
    output_dir.mkdir(parents=True, exist_ok=True)

    matrix: dict[str, dict[str, dict[str, Any]]] = {candidate["candidate_id"]: {} for candidate in candidates}
    report_paths: dict[tuple[str, str], Path] = {}
    dev_units = [unit for unit in units if unit["role"] == "development"]
    for candidate in candidates:
        for unit in dev_units:
            path = output_dir / "reports" / "development" / unit["evaluation_id"] / f"{candidate['candidate_id']}.json"
            matrix[candidate["candidate_id"]][unit["evaluation_id"]] = _evaluate(
                repo_root, processor, unit, candidate["tuning"], path
            )
            report_paths[(candidate["candidate_id"], unit["evaluation_id"])] = path

    policy = spec["policy"]
    selected, ranking, frontier = rank_development(
        space, candidates, units, matrix, source_sha, str(spec["hypothesis_id"]), registry,
        float(policy["minimum_development_score"]),
        float(policy["minimum_development_unit_score"]),
        int(policy["maximum_pareto_candidates"]),
    )
    baseline = candidates[0]
    selected_candidate = next(item for item in candidates if item["candidate_id"] == selected["candidate_id"])
    same_as_baseline = selected_candidate["candidate_id"] == baseline["candidate_id"]

    gate_results: list[dict[str, Any]] = []
    gate_violations: list[dict[str, Any]] = []
    for unit in [item for item in units if item["role"] in {"validation", "shadow"}]:
        role_dir = output_dir / "reports" / unit["role"] / unit["evaluation_id"]
        baseline_path = role_dir / "baseline.json"
        baseline_report = _evaluate(repo_root, processor, unit, baseline["tuning"], baseline_path)
        if same_as_baseline:
            candidate_path = baseline_path
            candidate_report = baseline_report
        else:
            candidate_path = role_dir / "candidate.json"
            candidate_report = _evaluate(repo_root, processor, unit, selected_candidate["tuning"], candidate_path)
        case_summary, case_violations = engine.case_delta_gate_violations(space, baseline_report, candidate_report)
        violations = engine.regression_violations(space, baseline_report, candidate_report) + case_violations
        if baseline_report.get("validation_result") != "PASS":
            violations.append({"gate": "baseline_health", "actual": baseline_report.get("validation_result")})
        if not same_as_baseline and candidate_report.get("validation_result") != "PASS":
            violations.append({"gate": "candidate_validation_result", "actual": candidate_report.get("validation_result")})
        gate_results.append({
            "evaluation_id": unit["evaluation_id"], "dataset_id": unit["dataset_id"],
            "role": unit["role"], "seed": unit["seed"],
            "baseline": _report_binding(baseline_path, baseline_report),
            "candidate": _report_binding(candidate_path, candidate_report),
            "case_delta_summary": case_summary,
            "regression_violations": violations,
        })
        gate_violations.extend({"evaluation_id": unit["evaluation_id"], **item} for item in violations)

    if same_as_baseline:
        decision = "KEEP_BASELINE"
        status = "NO_RESEARCH_CANDIDATE"
    elif gate_violations:
        decision = "REJECT_CANDIDATE"
        status = "RESEARCH_CANDIDATE_REJECTED"
    else:
        decision = "FREEZE_RESEARCH_CANDIDATE"
        status = registry["output_authority"]["candidate_status"]

    development_bindings: list[dict[str, Any]] = []
    for row in ranking:
        reports = []
        for unit in dev_units:
            path = report_paths[(row["candidate_id"], unit["evaluation_id"])]
            reports.append({
                "evaluation_id": unit["evaluation_id"], "dataset_id": unit["dataset_id"],
                "seed": unit["seed"], "report": _report_binding(path, matrix[row["candidate_id"]][unit["evaluation_id"]]),
            })
        development_bindings.append({**row, "reports": reports})

    result = {
        "schema_version": 1,
        "experiment_id": spec["experiment_id"],
        "hypothesis_id": spec["hypothesis_id"],
        "source_sha": source_sha,
        "authority": "research-only-data-driven-optimization",
        "decision": decision,
        "status": status,
        "shipping_baseline": registry["shipping_baseline"],
        "search_space": {
            "path": str(spec["search_space"]), "sha256": sha256_file(search_space_path),
            "candidate_count": len(candidates),
        },
        "dataset_registry": {
            "id": registry["registry_id"], "path": str(registry_path), "sha256": sha256_file(registry_path),
        },
        "development": {
            "units": [{
                "evaluation_id": unit["evaluation_id"], "dataset_id": unit["dataset_id"],
                "seed": unit["seed"], "tier": unit["tier"],
            } for unit in dev_units],
            "ranking": development_bindings,
            "pareto_frontier": [row["research_candidate_id"] for row in frontier],
        },
        "selected": {
            "candidate_id": selected["candidate_id"],
            "research_candidate_id": selected["research_candidate_id"],
            "label": selected["label"], "tuning": selected["tuning"],
            "development_score": selected["development_score"],
            "worst_development_unit_score": selected["worst_development_unit_score"],
        },
        "generalization_gates": gate_results,
        "gate_violations": gate_violations,
        "output_authority": registry["output_authority"],
        "next_gate": registry["output_authority"]["next_gate"] if status == "FROZEN_RESEARCH_CANDIDATE" else None,
        "automatic_shipping_promotion": False,
        "automatic_main_mutation": False,
    }
    output_path = output_dir / "optimization-result.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    tuning_iteration.install_fail_closed_guards()
    repo_root = Path(__file__).resolve().parents[3]
    default_registry = _safe_path(repo_root, str(DEFAULT_REGISTRY))
    dataset_registry.load_registry(default_registry, repo_root)
    space = {
        "schema_version": 1, "search_space_id": "research-self-test", "strategy": "one-at-a-time",
        "max_candidates": 4,
        "baseline": {"aec_mu": 0.22, "ns_floor": 0.12, "agc_target_dbfs": -20.0, "limiter_dbfs": -2.0},
        "parameters": {"aec_mu": [0.20, 0.22, 0.23]},
        "objective": {
            "minimum_improvement_score": 0.0,
            "metrics": [
                {"name": "pass_rate", "direction": "max", "weight": 8.0, "scale": 0.02, "max_regression": 0.0},
                {"name": "median_erle_db", "direction": "max", "weight": 1.0, "scale": 1.0, "max_regression": 1.0},
            ],
        },
    }
    candidates = engine.generate_candidates(space)
    units = [
        {"evaluation_id": "d1", "dataset_id": "synthetic", "role": "development", "seed": 1},
        {"evaluation_id": "d2", "dataset_id": "synthetic", "role": "development", "seed": 2},
    ]
    fixture_registry = {"terminal_candidates": []}
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    baseline_id = candidates[0]["candidate_id"]
    for candidate in candidates:
        delta = 0.0 if candidate["candidate_id"] == baseline_id else (1.0 if candidate["tuning"]["aec_mu"] == 0.23 else -0.5)
        matrix[candidate["candidate_id"]] = {
            "d1": {"validation_result": "PASS", "summary": {"pass_rate": 1.0, "median_erle_db": 10.0 + delta}},
            "d2": {"validation_result": "PASS", "summary": {"pass_rate": 1.0, "median_erle_db": 10.2 + delta}},
        }
    selected, ranking, frontier = rank_development(
        space, candidates, units, matrix, "b" * 40, "hypothesis", fixture_registry,
        0.1, 0.0, 8,
    )
    assert selected["tuning"]["aec_mu"] == 0.23
    assert selected["candidate_id"] != baseline_id
    assert frontier
    terminal_registry = {"terminal_candidates": [{
        "candidate_id": selected["candidate_id"], "source_sha": "b" * 40, "decision": "REJECTED"
    }]}
    selected2, ranking2, _ = rank_development(
        space, candidates, units, matrix, "b" * 40, "hypothesis", terminal_registry,
        0.1, 0.0, 8,
    )
    assert selected2["candidate_id"] == baseline_id
    assert any(
        violation["gate"] == "terminal_candidate_reuse"
        for row in ranking2 for violation in row["violations"]
    )
    assert all("research_candidate_id" in row for row in ranking)
    print("research optimizer self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--run-spec", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--require-frozen-candidate", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.processor is None or args.run_spec is None or args.output_dir is None:
        parser.error("--processor, --run-spec and --output-dir are required")
    root = args.repo_root.resolve()
    processor = _safe_path(root, str(args.processor))
    run_spec = _safe_path(root, str(args.run_spec))
    registry_path = _safe_path(root, str(args.registry))
    if not processor.is_file() or not run_spec.is_file() or not registry_path.is_file():
        raise SystemExit("processor/run-spec/registry must exist")
    spec = json.loads(run_spec.read_text(encoding="utf-8"))
    if os.environ.get("GITHUB_SHA") and spec.get("source_sha") != os.environ["GITHUB_SHA"]:
        raise SystemExit("run spec source_sha must equal GITHUB_SHA in hosted execution")
    result = execute(spec, repo_root=root, processor=processor, registry_path=registry_path,
                     output_dir=args.output_dir)
    print(json.dumps({
        "decision": result["decision"], "status": result["status"],
        "selected": result["selected"]["research_candidate_id"],
        "next_gate": result["next_gate"],
    }, sort_keys=True))
    if args.require_frozen_candidate and result["status"] != "FROZEN_RESEARCH_CANDIDATE":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
