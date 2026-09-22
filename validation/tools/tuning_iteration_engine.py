#!/usr/bin/env python3
"""Deterministic acoustic tuning iteration with strict anti-overfit boundaries.

This tool searches only a designated development corpus, then independently
replays the selected tuning on validation and shadow corpora. It never promotes
shipping defaults. The output is an ACOUSTIC_CANDIDATE at most; blind, target
resource/HIL and product certification remain separate authorities.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import itertools
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

TUNING_KEYS = ("aec_mu", "ns_floor", "agc_target_dbfs", "limiter_dbfs")
# The top-level contract of a search space, matching
# validation/tuning/search-space.schema.json. Enforced rather than defaulted: see
# validate_search_space.
SEARCH_SPACE_KEYS = ("schema_version", "search_space_id", "strategy",
                     "max_candidates", "baseline", "parameters", "objective")
OBJECTIVE_KEYS = {"minimum_improvement_score", "metrics", "case_delta_gates"}
OBJECTIVE_METRIC_REQUIRED_KEYS = {"name", "direction", "weight", "scale", "max_regression"}
OBJECTIVE_METRIC_KEYS = {
    "name", "direction", "weight", "scale", "max_regression",
    "datasets", "minimum_units",
}
CASE_DELTA_GATE_KEYS = {
    "metric", "stat", "minimum_delta", "maximum_delta", "min_cases", "case_ids",
}
TUNING_FLAGS = {
    "aec_mu": "--aec-mu",
    "ns_floor": "--ns-floor",
    "agc_target_dbfs": "--agc-target-dbfs",
    "limiter_dbfs": "--limiter-dbfs",
}

DEFAULT_METRICS = [
    {"name": "pass_rate", "direction": "max", "weight": 8.0, "scale": 0.02, "max_regression": 0.0},
    {"name": "p10_near_si_sdr_improvement_db", "direction": "max", "weight": 1.4, "scale": 1.0, "max_regression": 0.75},
    {"name": "p10_noise_only_attenuation_db", "direction": "max", "weight": 0.8, "scale": 1.0, "max_regression": 0.75},
    {"name": "median_erle_db", "direction": "max", "weight": 1.0, "scale": 1.0, "max_regression": 1.0},
    {"name": "min_vad_f1", "direction": "max", "weight": 1.0, "scale": 0.05, "max_regression": 0.05},
    {"name": "max_vad_false_positive_rate", "direction": "min", "weight": 0.6, "scale": 0.05, "max_regression": 0.05},
    {"name": "max_output_clip_fraction", "direction": "min", "weight": 2.0, "scale": 0.002, "max_regression": 0.002},
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_tuning(raw: dict[str, Any]) -> dict[str, float]:
    unknown = set(raw) - set(TUNING_KEYS)
    if unknown:
        raise ValueError(f"unknown tuning keys: {sorted(unknown)}")
    tuning = {key: float(raw[key]) for key in TUNING_KEYS if key in raw}
    for key, value in tuning.items():
        if not math.isfinite(value):
            raise ValueError(f"{key} must be finite")
    if "aec_mu" in tuning and not 0.0 < tuning["aec_mu"] <= 1.0:
        raise ValueError("aec_mu must be in (0, 1]")
    if "ns_floor" in tuning and not 0.02 <= tuning["ns_floor"] <= 1.0:
        raise ValueError("ns_floor must be in [0.02, 1]")
    if "agc_target_dbfs" in tuning and not -60.0 <= tuning["agc_target_dbfs"] <= -1.0:
        raise ValueError("agc_target_dbfs must be in [-60, -1]")
    if "limiter_dbfs" in tuning and not -20.0 <= tuning["limiter_dbfs"] <= -0.1:
        raise ValueError("limiter_dbfs must be in [-20, -0.1]")
    if ("agc_target_dbfs" in tuning and "limiter_dbfs" in tuning and
            tuning["agc_target_dbfs"] >= tuning["limiter_dbfs"]):
        raise ValueError("agc_target_dbfs must be below limiter_dbfs")
    return tuning


def metric_datasets(metric: dict[str, Any]) -> list[str] | None:
    raw = metric.get("datasets")
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError("objective metric datasets must be a non-empty list")
    if any(not isinstance(item, str) or not item for item in raw):
        raise ValueError("objective metric datasets must contain non-empty string ids")
    if len(raw) != len(set(raw)):
        raise ValueError("objective metric datasets must contain unique ids")
    return list(raw)


def metric_minimum_units(metric: dict[str, Any]) -> int:
    raw = metric.get("minimum_units", 1)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1 or raw > 32:
        raise ValueError("objective metric minimum_units must be an integer in 1..32")
    return raw


def gate_case_ids(gate: dict[str, Any]) -> list[str] | None:
    raw = gate.get("case_ids")
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError("case delta gate case_ids must be a non-empty list")
    if any(not isinstance(item, str) or not item for item in raw):
        raise ValueError("case delta gate case_ids must contain non-empty string ids")
    if len(raw) != len(set(raw)):
        raise ValueError("case delta gate case_ids must contain unique ids")
    return list(raw)


def validate_search_space(space: dict[str, Any]) -> None:
    # Every optional key used to be read with a default and no unknown key was
    # rejected, so `strategies` in place of `strategy` silently ran the space as
    # one-at-a-time instead of cartesian, and a misspelled `max_candidates` was
    # silently replaced by the cap default. Both change the search that is
    # reported without changing anything the report says, so both fail closed.
    if not isinstance(space, dict):
        raise ValueError("search space must be an object")
    unknown = sorted(set(space) - set(SEARCH_SPACE_KEYS))
    if unknown:
        raise ValueError(f"unknown search space keys: {unknown}")
    missing = [key for key in SEARCH_SPACE_KEYS if key not in space]
    if missing:
        raise ValueError(f"search space is missing required keys: {missing}")
    if space["schema_version"] != 1:
        raise ValueError("search space schema_version must be 1")
    if not str(space["search_space_id"]):
        raise ValueError("search_space_id is required")
    baseline = canonical_tuning(space["baseline"])
    if set(baseline) != set(TUNING_KEYS):
        raise ValueError("baseline must define all supported tuning keys")
    params = space.get("parameters")
    if not isinstance(params, dict) or not params:
        raise ValueError("parameters must be a non-empty object")
    strategy = space["strategy"]
    if strategy not in {"one-at-a-time", "cartesian", "paired"}:
        raise ValueError("strategy must be one-at-a-time, cartesian or paired")
    for key, values in params.items():
        if key not in TUNING_KEYS or not isinstance(values, list) or not values:
            raise ValueError(f"invalid parameter grid for {key}")
        for value in values:
            if strategy == "paired":
                # Paired axes are validated as a complete tuple below. Checking
                # one axis against the baseline would reject legal coupled points
                # whose limiter is intentionally below the baseline AGC target.
                canonical_tuning({key: value})
            else:
                probe = dict(baseline)
                probe[key] = value
                canonical_tuning(probe)
    if strategy == "paired":
        lengths = {len(values) for values in params.values()}
        if len(lengths) != 1:
            raise ValueError("paired strategy requires equal-length parameter grids")
        keys = [key for key in TUNING_KEYS if key in params]
        grids = [params[key] for key in keys]
        for values in zip(*grids):
            candidate = dict(baseline)
            candidate.update(dict(zip(keys, values)))
            canonical_tuning(candidate)
    maximum = int(space["max_candidates"])
    if maximum < 1 or maximum > 256:
        raise ValueError("max_candidates must be 1..256")
    objective = space["objective"]
    if not isinstance(objective, dict):
        raise ValueError("objective must be an object")
    unknown_objective = sorted(set(objective) - OBJECTIVE_KEYS)
    if unknown_objective:
        raise ValueError(f"unknown objective keys: {unknown_objective}")
    if "minimum_improvement_score" in objective:
        minimum_score = float(objective["minimum_improvement_score"])
        if not math.isfinite(minimum_score) or minimum_score < 0.0:
            raise ValueError("minimum_improvement_score must be finite and >= 0")
    metrics = objective.get("metrics", DEFAULT_METRICS)
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("objective.metrics must be non-empty")
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValueError("objective metric must be an object")
        unknown_metric = sorted(set(metric) - OBJECTIVE_METRIC_KEYS)
        if unknown_metric:
            raise ValueError(f"unknown objective metric keys: {unknown_metric}")
        missing_metric = sorted(OBJECTIVE_METRIC_REQUIRED_KEYS - set(metric))
        if missing_metric:
            raise ValueError(f"objective metric is missing required keys: {missing_metric}")
        if not isinstance(metric["name"], str) or not metric["name"]:
            raise ValueError("objective metric name must be a non-empty string")
        if metric.get("direction") not in {"min", "max"}:
            raise ValueError("metric direction must be min or max")
        if float(metric.get("weight", 0.0)) < 0.0 or float(metric.get("scale", 0.0)) <= 0.0:
            raise ValueError("metric weight/scale invalid")
        if float(metric.get("max_regression", 0.0)) < 0.0:
            raise ValueError("max_regression must be >= 0")
        metric_datasets(metric)
        metric_minimum_units(metric)
    case_gates = objective.get("case_delta_gates", [])
    if not isinstance(case_gates, list):
        raise ValueError("objective.case_delta_gates must be a list")
    for gate in case_gates:
        if not isinstance(gate, dict) or not str(gate.get("metric", "")):
            raise ValueError("case delta gate metric is required")
        unknown_gate = sorted(set(gate) - CASE_DELTA_GATE_KEYS)
        if unknown_gate:
            raise ValueError(f"unknown case delta gate keys: {unknown_gate}")
        if gate.get("stat") not in {"min", "p10", "median", "max"}:
            raise ValueError("case delta gate stat must be min, p10, median or max")
        minimum_raw = gate.get("minimum_delta")
        maximum_raw = gate.get("maximum_delta")
        if minimum_raw is None and maximum_raw is None:
            raise ValueError(
                "case delta gate requires minimum_delta or maximum_delta")
        if minimum_raw is not None and not math.isfinite(float(minimum_raw)):
            raise ValueError("case delta gate minimum_delta must be finite")
        if maximum_raw is not None and not math.isfinite(float(maximum_raw)):
            raise ValueError("case delta gate maximum_delta must be finite")
        if (minimum_raw is not None and maximum_raw is not None and
                float(minimum_raw) > float(maximum_raw)):
            raise ValueError(
                "case delta gate minimum_delta must not exceed maximum_delta")
        min_cases = gate.get("min_cases", 1)
        if isinstance(min_cases, bool) or not isinstance(min_cases, int) or \
                min_cases < 1:
            raise ValueError("case delta gate min_cases must be a positive integer")
        gate_case_ids(gate)


def tuning_id(tuning: dict[str, float]) -> str:
    payload = json.dumps(tuning, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def generate_candidates(space: dict[str, Any]) -> list[dict[str, Any]]:
    validate_search_space(space)
    baseline = canonical_tuning(space["baseline"])
    strategy = space["strategy"]
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(tuning: dict[str, Any], label: str) -> None:
        canonical = canonical_tuning(tuning)
        ident = tuning_id(canonical)
        if ident in seen:
            return
        seen.add(ident)
        candidates.append({"candidate_id": ident, "label": label, "tuning": canonical})

    add(baseline, "baseline")
    if strategy == "one-at-a-time":
        for key in TUNING_KEYS:
            for value in space["parameters"].get(key, []):
                candidate = dict(baseline)
                candidate[key] = float(value)
                add(candidate, f"{key}={value}")
    elif strategy == "cartesian":
        keys = [key for key in TUNING_KEYS if key in space["parameters"]]
        grids = [space["parameters"][key] for key in keys]
        for values in itertools.product(*grids):
            candidate = dict(baseline)
            candidate.update(dict(zip(keys, values)))
            add(candidate, "cartesian")
    else:
        keys = [key for key in TUNING_KEYS if key in space["parameters"]]
        grids = [space["parameters"][key] for key in keys]
        for index, values in enumerate(zip(*grids), start=1):
            candidate = dict(baseline)
            candidate.update(dict(zip(keys, values)))
            label = "paired[" + str(index) + "]:" + ",".join(
                f"{key}={value}" for key, value in zip(keys, values)
            )
            add(candidate, label)

    maximum = int(space["max_candidates"])
    if len(candidates) > maximum:
        raise ValueError(f"generated {len(candidates)} candidates > max_candidates={maximum}")
    return candidates


def adjacent_development_sensitivity(space: dict[str, Any], selected: dict[str, Any],
                                     dev_results: list[dict[str, Any]]) -> dict[str, Any]:
    selected_tuning = canonical_tuning(selected["tuning"])
    by_id = {str(item["candidate_id"]): item for item in dev_results}
    neighbors: list[dict[str, Any]] = []
    unobserved_neighbors: list[dict[str, Any]] = []
    if space["strategy"] == "paired":
        keys = [key for key in TUNING_KEYS if key in space["parameters"]]
        grids = [space["parameters"][key] for key in keys]
        path: list[dict[str, float]] = [canonical_tuning(space["baseline"])]
        path_ids = {tuning_id(path[0])}
        for values in zip(*grids):
            candidate = dict(path[0])
            candidate.update(dict(zip(keys, values)))
            canonical = canonical_tuning(candidate)
            ident = tuning_id(canonical)
            if ident not in path_ids:
                path_ids.add(ident)
                path.append(canonical)
        selected_id = tuning_id(selected_tuning)
        selected_index = next(
            (index for index, tuning in enumerate(path)
             if tuning_id(tuning) == selected_id),
            None,
        )
        if selected_index is None:
            raise ValueError("selected tuning is outside the paired search path")
        for neighbor_index in (selected_index - 1, selected_index + 1):
            if neighbor_index < 0 or neighbor_index >= len(path):
                continue
            neighbor_tuning = path[neighbor_index]
            neighbor_id = tuning_id(neighbor_tuning)
            direction = "previous" if neighbor_index < selected_index else "next"
            item = by_id.get(neighbor_id)
            if item is None:
                unobserved_neighbors.append({
                    "tuning_id": neighbor_id,
                    "parameter": "paired",
                    "value": neighbor_index,
                    "paired_index": neighbor_index,
                    "direction": direction,
                    "tuning": neighbor_tuning,
                    "reason": "not_evaluated_in_development_search",
                })
                continue
            compliant = (
                item.get("validation_result") == "PASS"
                and not item.get("case_delta_violations", [])
            )
            neighbors.append({
                "candidate_id": item["candidate_id"],
                "label": item["label"],
                "parameter": "paired",
                "value": neighbor_index,
                "paired_index": neighbor_index,
                "direction": direction,
                "tuning": neighbor_tuning,
                "score": item["score"],
                "validation_result": item["validation_result"],
                "compliant": compliant,
                "case_delta_summary": item["case_delta_summary"],
                "case_delta_violations": item["case_delta_violations"],
            })
        neighbor_slot_count = len(neighbors) + len(unobserved_neighbors)
        return {
            "neighbor_count": len(neighbors),
            "neighbor_slot_count": neighbor_slot_count,
            "evaluated_neighbor_count": len(neighbors),
            "unobserved_neighbor_count": len(unobserved_neighbors),
            "complete_neighbor_coverage": not unobserved_neighbors,
            "compliant_neighbor_count": sum(bool(item["compliant"]) for item in neighbors),
            "violating_neighbor_count": sum(not bool(item["compliant"]) for item in neighbors),
            "neighbors": neighbors,
            "unobserved_neighbors": unobserved_neighbors,
        }
    for key in TUNING_KEYS:
        if key not in space.get("parameters", {}):
            continue
        values = sorted({
            float(space["baseline"][key]),
            *(float(value) for value in space["parameters"][key]),
        })
        current = selected_tuning[key]
        current_index = next(
            (index for index, value in enumerate(values)
             if abs(value - current) <= 1.0e-12),
            None,
        )
        if current_index is None:
            raise ValueError(f"selected {key}={current} is outside the search axis")
        for neighbor_index in (current_index - 1, current_index + 1):
            if neighbor_index < 0 or neighbor_index >= len(values):
                continue
            neighbor_tuning = dict(selected_tuning)
            neighbor_tuning[key] = values[neighbor_index]
            neighbor_id = tuning_id(neighbor_tuning)
            direction = "lower" if values[neighbor_index] < current else "higher"
            item = by_id.get(neighbor_id)
            if item is None:
                unobserved_neighbors.append({
                    "tuning_id": neighbor_id,
                    "parameter": key,
                    "value": values[neighbor_index],
                    "direction": direction,
                    "reason": "not_evaluated_in_development_search",
                })
                continue
            compliant = (
                item.get("validation_result") == "PASS"
                and not item.get("case_delta_violations", [])
            )
            neighbors.append({
                "candidate_id": item["candidate_id"],
                "label": item["label"],
                "parameter": key,
                "value": values[neighbor_index],
                "direction": direction,
                "score": item["score"],
                "validation_result": item["validation_result"],
                "compliant": compliant,
                "case_delta_summary": item["case_delta_summary"],
                "case_delta_violations": item["case_delta_violations"],
            })
    neighbors.sort(
        key=lambda item: (TUNING_KEYS.index(str(item["parameter"])), float(item["value"]))
    )
    unobserved_neighbors.sort(
        key=lambda item: (TUNING_KEYS.index(str(item["parameter"])), float(item["value"]))
    )
    neighbor_slot_count = len(neighbors) + len(unobserved_neighbors)
    return {
        # neighbor_count remains the evaluated-neighbor count for compatibility.
        "neighbor_count": len(neighbors),
        "neighbor_slot_count": neighbor_slot_count,
        "evaluated_neighbor_count": len(neighbors),
        "unobserved_neighbor_count": len(unobserved_neighbors),
        "complete_neighbor_coverage": not unobserved_neighbors,
        "compliant_neighbor_count": sum(bool(item["compliant"]) for item in neighbors),
        "violating_neighbor_count": sum(not bool(item["compliant"]) for item in neighbors),
        "neighbors": neighbors,
        "unobserved_neighbors": unobserved_neighbors,
    }


def summary_value(report: dict[str, Any], name: str) -> float | None:
    value = report.get("summary", {}).get(name)
    return None if value is None else float(value)


def objective_metrics(space: dict[str, Any]) -> list[dict[str, Any]]:
    return list(space.get("objective", {}).get("metrics", DEFAULT_METRICS))


def score_against_baseline(space: dict[str, Any], baseline: dict[str, Any],
                           candidate: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    score = 0.0
    deltas = []
    for metric in objective_metrics(space):
        name = str(metric["name"])
        base = summary_value(baseline, name)
        cand = summary_value(candidate, name)
        if base is None:
            raise ValueError(
                f"objective metric {name} is absent from the baseline summary")
        if cand is None:
            continue
        direction = str(metric["direction"])
        directed = (cand - base) if direction == "max" else (base - cand)
        scale = float(metric.get("scale", 1.0))
        weighted = float(metric.get("weight", 1.0)) * directed / scale
        score += weighted
        deltas.append({
            "metric": name, "baseline": base, "candidate": cand,
            "directed_delta": directed, "weighted_score": weighted,
        })
    return score, deltas


def regression_violations(space: dict[str, Any], baseline: dict[str, Any],
                          candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if candidate.get("validation_result") != "PASS":
        violations.append({"gate": "candidate_validation_result", "actual": candidate.get("validation_result")})
    for metric in objective_metrics(space):
        name = str(metric["name"])
        base = summary_value(baseline, name)
        cand = summary_value(candidate, name)
        if base is None:
            raise ValueError(
                f"objective metric {name} is absent from the baseline summary")
        if cand is None:
            continue
        direction = str(metric["direction"])
        regression = (base - cand) if direction == "max" else (cand - base)
        allowed = float(metric.get("max_regression", 0.0))
        if regression > allowed + 1.0e-12:
            violations.append({
                "gate": "metric_regression", "metric": name, "baseline": base,
                "candidate": cand, "regression": regression, "allowed": allowed,
            })
    return violations


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def strict_report_case_map(report: dict[str, Any], role: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        return {}, [{"gate": "case_set_invalid", "role": role, "reason": "non_empty_list_required"}]
    result: dict[str, dict[str, Any]] = {}
    violations: list[dict[str, Any]] = []
    for index, case in enumerate(raw_cases):
        if not isinstance(case, dict):
            violations.append({"gate": "case_identity_invalid", "role": role, "index": index})
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            violations.append({"gate": "case_identity_invalid", "role": role, "index": index})
            continue
        if case_id in result:
            violations.append({"gate": "case_identity_duplicate", "role": role, "case_id": case_id})
            continue
        result[case_id] = case
    return result, violations


def case_delta_gate_violations(space: dict[str, Any], baseline: dict[str, Any],
                               candidate: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gates = list(space.get("objective", {}).get("case_delta_gates", []))
    if not gates:
        return [], []
    baseline_cases, baseline_identity = strict_report_case_map(baseline, "baseline")
    candidate_cases, candidate_identity = strict_report_case_map(candidate, "candidate")
    identity_violations = baseline_identity + candidate_identity
    if identity_violations:
        return [], identity_violations
    if set(baseline_cases) != set(candidate_cases):
        missing = sorted(set(baseline_cases) - set(candidate_cases))
        extra = sorted(set(candidate_cases) - set(baseline_cases))
        return [], [{
            "gate": "case_set_mismatch",
            "baseline_cases": len(baseline_cases),
            "candidate_cases": len(candidate_cases),
            "missing_cases": missing[:8],
            "missing_count": len(missing),
            "extra_cases": extra[:8],
            "extra_count": len(extra),
        }]
    summaries: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for gate in gates:
        metric = str(gate["metric"])
        stat = str(gate["stat"])
        minimum_raw = gate.get("minimum_delta")
        maximum_raw = gate.get("maximum_delta")
        minimum = float(minimum_raw) if minimum_raw is not None else None
        maximum = float(maximum_raw) if maximum_raw is not None else None
        min_cases = int(gate.get("min_cases", 1))
        deltas: list[float] = []
        asymmetric: list[str] = []
        for case_id in sorted(baseline_cases):
            base_value = baseline_cases[case_id].get("metrics", {}).get(metric)
            cand_value = candidate_cases[case_id].get("metrics", {}).get(metric)
            base_ok = isinstance(base_value, (int, float)) and \
                math.isfinite(float(base_value))
            cand_ok = isinstance(cand_value, (int, float)) and \
                math.isfinite(float(cand_value))
            if base_ok != cand_ok:
                asymmetric.append(case_id)
                continue
            if not base_ok:
                continue
            deltas.append(float(cand_value) - float(base_value))
        if asymmetric:
            violations.append({
                "gate": "case_metric_coverage_mismatch", "metric": metric,
                "cases": asymmetric[:8], "count": len(asymmetric),
            })
            continue
        if not deltas:
            violations.append({
                "gate": "case_gate_not_applicable", "metric": metric,
                "cases": 0, "min_cases": min_cases,
            })
            continue
        if len(deltas) < min_cases:
            violations.append({
                "gate": "case_gate_insufficient_cases", "metric": metric,
                "cases": len(deltas), "min_cases": min_cases,
            })
            continue
        if stat == "min":
            actual = min(deltas)
        elif stat == "max":
            actual = max(deltas)
        elif stat == "p10":
            actual = percentile(deltas, 0.10)
        else:
            actual = percentile(deltas, 0.50)
        minimum_margin = actual - minimum if minimum is not None else None
        maximum_margin = maximum - actual if maximum is not None else None
        margins = [
            ("minimum_delta", minimum_margin),
            ("maximum_delta", maximum_margin),
        ]
        finite_margins = [
            (bound, margin) for bound, margin in margins if margin is not None
        ]
        binding_bound, binding_margin = min(
            finite_margins, key=lambda item: item[1]
        )
        summary = {
            "metric": metric, "stat": stat, "actual_delta": actual,
            "minimum_delta": minimum, "maximum_delta": maximum,
            "minimum_margin": minimum_margin, "maximum_margin": maximum_margin,
            "binding_bound": binding_bound, "binding_margin": binding_margin,
            "cases": len(deltas),
            "worsened_cases": sum(delta < 0.0 for delta in deltas),
        }
        summaries.append(summary)
        if minimum is not None and actual < minimum - 1.0e-12:
            violations.append({"gate": "case_delta_regression", **summary})
        if maximum is not None and actual > maximum + 1.0e-12:
            violations.append({"gate": "case_delta_excursion", **summary})
    return summaries, violations


def load_corpus_identity(path: Path) -> dict[str, Any]:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    return {
        "corpus_id": corpus.get("corpus_id"),
        "tier": corpus.get("tier"),
        "sha256": sha256_file(path),
        "generator_seed": corpus.get("generator", {}).get("seed"),
    }


def enforce_partition_independence(dev: Path, validation: Path, shadow: Path) -> dict[str, Any]:
    identities = {
        "development": load_corpus_identity(dev),
        "validation": load_corpus_identity(validation),
        "shadow": load_corpus_identity(shadow),
    }
    hashes = [item["sha256"] for item in identities.values()]
    ids = [item["corpus_id"] for item in identities.values()]
    seeds = [item["generator_seed"] for item in identities.values()]
    if len(set(hashes)) != 3 or len(set(ids)) != 3:
        raise ValueError("development/validation/shadow corpora must be distinct")
    if all(seed is not None for seed in seeds) and len(set(seeds)) != 3:
        raise ValueError("generated partitions must use distinct seeds")
    if identities["development"]["tier"] not in {"regression", "research-validation"}:
        raise ValueError(
            "development corpus must be regression or research-validation; "
            "validation-grade/blind/product evidence is never legal tuning input"
        )
    return identities


def write_wrapper(path: Path, processor: Path, tuning: dict[str, float]) -> None:
    flags = []
    for key in TUNING_KEYS:
        if key in tuning:
            flags += [TUNING_FLAGS[key], repr(float(tuning[key]))]
    script = [
        "#!/usr/bin/env python3",
        "import os, sys",
        f"processor = {str(processor.resolve())!r}",
        f"prefix = {flags!r}",
        "os.execv(processor, [processor] + prefix + sys.argv[1:])",
        "",
    ]
    path.write_text("\n".join(script), encoding="utf-8")
    path.chmod(0o700)


def run_validation(repo_root: Path, processor: Path, corpus: Path, policy: Path,
                   dataset_lock: Path, tuning: dict[str, float], output: Path) -> tuple[dict[str, Any], float]:
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output.with_suffix(".evidence.json")
    with tempfile.TemporaryDirectory(prefix="ap-tuning-wrapper-") as temporary:
        wrapper = Path(temporary) / "processor"
        write_wrapper(wrapper, processor, tuning)
        command = [
            sys.executable, str(repo_root / "validation/tools/run_validation.py"),
            "--corpus", str(corpus), "--policy", str(policy),
            "--dataset-lock", str(dataset_lock), "--processor", str(wrapper),
            "--output", str(output), "--evidence-manifest", str(evidence),
            "--source-revision", os.environ.get("GITHUB_SHA", "local-tuning-iteration"),
            "--enforce",
        ]
        started = time.monotonic()
        completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True)
        elapsed = time.monotonic() - started
        if completed.returncode != 0:
            if not output.exists():
                raise RuntimeError(
                    f"validation execution failed rc={completed.returncode}: "
                    f"{completed.stderr[-2000:] or completed.stdout[-2000:]}"
                )
        report = json.loads(output.read_text(encoding="utf-8"))
        report["_iteration_elapsed_s"] = elapsed
        report["_iteration_returncode"] = completed.returncode
        return report, elapsed


def bind_report(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "validation_result": report.get("validation_result"),
        "summary": report.get("summary", {}),
    }


@dataclass(frozen=True)
class IterationSemantics:
    validate_search_space: Callable[[dict[str, Any]], None]
    enforce_partition_independence: Callable[[Path, Path, Path], dict[str, Any]]
    score_against_baseline: Callable[
        [dict[str, Any], dict[str, Any], dict[str, Any]],
        tuple[float, list[dict[str, Any]]],
    ]
    regression_violations: Callable[
        [dict[str, Any], dict[str, Any], dict[str, Any]],
        list[dict[str, Any]],
    ]
    case_delta_gate_violations: Callable[
        [dict[str, Any], dict[str, Any], dict[str, Any]],
        tuple[list[dict[str, Any]], list[dict[str, Any]]],
    ]


def default_iteration_semantics() -> IterationSemantics:
    return IterationSemantics(
        validate_search_space=validate_search_space,
        enforce_partition_independence=enforce_partition_independence,
        score_against_baseline=score_against_baseline,
        regression_violations=regression_violations,
        case_delta_gate_violations=case_delta_gate_violations,
    )


def validate_parallelism(candidate_jobs: int, holdout_jobs: int) -> None:
    if candidate_jobs < 1 or candidate_jobs > 8:
        raise ValueError("candidate_jobs must be 1..8")
    if holdout_jobs < 1 or holdout_jobs > 4:
        raise ValueError("holdout_jobs must be 1..4")


def iterate(repo_root: Path, processor: Path, dev: Path, validation: Path, shadow: Path,
            policy: Path, dataset_lock: Path, search_space_path: Path, output_dir: Path,
            candidate_jobs: int = 1,
            semantics: IterationSemantics | None = None,
            holdout_jobs: int = 1) -> dict[str, Any]:
    semantics = semantics or default_iteration_semantics()
    space = json.loads(search_space_path.read_text(encoding="utf-8"))
    semantics.validate_search_space(space)
    identities = semantics.enforce_partition_independence(dev, validation, shadow)
    candidates = generate_candidates(space)
    output_dir.mkdir(parents=True, exist_ok=True)

    validate_parallelism(candidate_jobs, holdout_jobs)
    baseline_candidate = candidates[0]

    def evaluate_development(candidate: dict[str, Any]) -> dict[str, Any]:
        report_path = output_dir / "development" / f"{candidate['candidate_id']}.json"
        report, elapsed = run_validation(repo_root, processor, dev, policy, dataset_lock,
                                         candidate["tuning"], report_path)
        return {
            **candidate,
            "report_path": str(report_path),
            "report_sha256": sha256_file(report_path),
            "validation_result": report.get("validation_result"),
            "elapsed_s": elapsed,
            "report": report,
        }

    if candidate_jobs == 1:
        dev_results = [evaluate_development(candidate) for candidate in candidates]
    else:
        with ThreadPoolExecutor(max_workers=candidate_jobs) as executor:
            dev_results = list(executor.map(evaluate_development, candidates))
    baseline_dev_report = next(
        item["report"] for item in dev_results if item["label"] == "baseline"
    )

    for result in dev_results:
        score, deltas = semantics.score_against_baseline(
            space, baseline_dev_report, result["report"]
        )
        case_summary, case_violations = semantics.case_delta_gate_violations(
            space, baseline_dev_report, result["report"]
        )
        result["score"] = score
        result["objective_deltas"] = deltas
        result["case_delta_summary"] = case_summary
        result["case_delta_violations"] = case_violations

    eligible_dev = [
        result for result in dev_results
        if result["validation_result"] == "PASS" and not result["case_delta_violations"]
    ]
    eligible_dev.sort(key=lambda item: (-float(item["score"]), item["candidate_id"]))
    selected = eligible_dev[0] if eligible_dev else dev_results[0]
    min_score = float(space.get("objective", {}).get("minimum_improvement_score", 0.05))
    if selected["candidate_id"] == baseline_candidate["candidate_id"] or selected["score"] < min_score:
        selected = dev_results[0]
    development_sensitivity = adjacent_development_sensitivity(
        space, selected, dev_results
    )

    def evaluate_holdout(task: tuple[str, str, Path, dict[str, Any]]) -> tuple[
        str, str, Path, dict[str, Any], float
    ]:
        partition, role, corpus, candidate = task
        report_path = output_dir / partition / f"{role}.json"
        report, elapsed = run_validation(
            repo_root, processor, corpus, policy, dataset_lock,
            candidate["tuning"], report_path
        )
        return partition, role, report_path, report, elapsed

    holdout_tasks = [
        ("validation", "baseline", validation, dev_results[0]),
        ("validation", "candidate", validation, selected),
        ("shadow", "baseline", shadow, dev_results[0]),
        ("shadow", "candidate", shadow, selected),
    ]
    if holdout_jobs == 1:
        holdout_results = [evaluate_holdout(task) for task in holdout_tasks]
    else:
        with ThreadPoolExecutor(max_workers=holdout_jobs) as executor:
            holdout_results = list(executor.map(evaluate_holdout, holdout_tasks))

    validation_reports = {}
    shadow_reports = {}
    for partition, role, report_path, report, elapsed in holdout_results:
        target = validation_reports if partition == "validation" else shadow_reports
        target[role] = (report_path, report, elapsed)

    validation_case_summary, validation_case_violations = (
        semantics.case_delta_gate_violations(
            space, validation_reports["baseline"][1], validation_reports["candidate"][1]
        )
    )
    shadow_case_summary, shadow_case_violations = semantics.case_delta_gate_violations(
        space, shadow_reports["baseline"][1], shadow_reports["candidate"][1]
    )
    validation_violations = semantics.regression_violations(
        space, validation_reports["baseline"][1], validation_reports["candidate"][1]
    ) + validation_case_violations
    shadow_violations = semantics.regression_violations(
        space, shadow_reports["baseline"][1], shadow_reports["candidate"][1]
    ) + shadow_case_violations
    same_as_baseline = selected["candidate_id"] == baseline_candidate["candidate_id"]
    decision = "KEEP_BASELINE" if same_as_baseline else (
        "ACOUSTIC_CANDIDATE" if not validation_violations and not shadow_violations else "REJECT_CANDIDATE"
    )

    result = {
        "schema_version": 1,
        "iteration_id": f"{space['search_space_id']}:{selected['candidate_id']}",
        "decision": decision,
        "authority": "non-shipping-acoustic-iteration",
        "search_space": {
            "id": space["search_space_id"],
            "sha256": sha256_file(search_space_path),
            "strategy": space.get("strategy", "one-at-a-time"),
            "selection_policy": "highest-score-among-case-gate-compliant-development-candidates",
            "candidate_count": len(candidates),
            "candidate_jobs": candidate_jobs,
            "holdout_jobs": holdout_jobs,
        },
        "bindings": {
            "processor_sha256": sha256_file(processor),
            "policy_sha256": sha256_file(policy),
            "dataset_lock_sha256": sha256_file(dataset_lock),
            "partitions": identities,
        },
        "baseline": dev_results[0]["tuning"],
        "selected": {
            "candidate_id": selected["candidate_id"],
            "label": selected["label"],
            "tuning": selected["tuning"],
            "development_score": selected["score"],
            "development_case_delta_summary": selected["case_delta_summary"],
            "development_case_delta_violations": selected["case_delta_violations"],
            "development_adjacent_sensitivity": development_sensitivity,
        },
        "development_ranking": [
            {
                "candidate_id": item["candidate_id"], "label": item["label"],
                "tuning": item["tuning"], "score": item["score"],
                "validation_result": item["validation_result"],
                "report_sha256": item["report_sha256"],
                "elapsed_s": item["elapsed_s"],
                "case_delta_summary": item["case_delta_summary"],
                "case_delta_violations": item["case_delta_violations"],
            }
            for item in sorted(dev_results, key=lambda item: (-float(item["score"]), item["candidate_id"]))
        ],
        "validation": {
            "baseline": bind_report(validation_reports["baseline"][0], validation_reports["baseline"][1]),
            "candidate": bind_report(validation_reports["candidate"][0], validation_reports["candidate"][1]),
            "case_delta_summary": validation_case_summary,
            "regression_violations": validation_violations,
        },
        "shadow": {
            "baseline": bind_report(shadow_reports["baseline"][0], shadow_reports["baseline"][1]),
            "candidate": bind_report(shadow_reports["candidate"][0], shadow_reports["candidate"][1]),
            "case_delta_summary": shadow_case_summary,
            "regression_violations": shadow_violations,
        },
        "promotion_required": [
            "validation-grade-blind acoustic gate with a repository-external holdout key",
            "same-candidate target CPU/RSS/latency evidence",
            "SSC305/target HIL and soak evidence",
            "product certification record on shipping hardware/corpus",
            "reviewed source change or runtime product configuration; never automatic main mutation",
        ],
    }
    output_path = output_dir / "iteration-result.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    # Execution fan-out is intentionally bounded independently: candidate search
    # may use up to 8 workers, while the holdout plan has exactly four reports.
    validate_parallelism(1, 1)
    validate_parallelism(8, 4)
    for candidate_jobs, holdout_jobs in ((0, 1), (9, 1), (1, 0), (1, 5)):
        try:
            validate_parallelism(candidate_jobs, holdout_jobs)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"invalid parallelism accepted: candidate={candidate_jobs} holdout={holdout_jobs}"
            )

    space = {
        "schema_version": 1,
        "search_space_id": "self-test",
        "strategy": "one-at-a-time",
        "max_candidates": 8,
        "baseline": {
            "aec_mu": 0.22, "ns_floor": 0.12,
            "agc_target_dbfs": -20.0, "limiter_dbfs": -2.0,
        },
        "parameters": {"aec_mu": [0.18, 0.22, 0.26], "ns_floor": [0.10, 0.12]},
        "objective": {
            "minimum_improvement_score": 0.05,
            "metrics": [
                {"name": "pass_rate", "direction": "max", "weight": 8.0, "scale": 0.02, "max_regression": 0.0},
                {"name": "median_erle_db", "direction": "max", "weight": 1.0, "scale": 1.0, "max_regression": 1.0},
            ],
        },
    }
    validate_search_space(space)
    bad_objective_key = json.loads(json.dumps(space))
    bad_objective_key["objective"]["minimum_improvements_score"] = 0.1
    try:
        validate_search_space(bad_objective_key)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown objective key must fail closed")
    missing_metric_key = json.loads(json.dumps(space))
    del missing_metric_key["objective"]["metrics"][0]["weight"]
    try:
        validate_search_space(missing_metric_key)
    except ValueError:
        pass
    else:
        raise AssertionError("missing required objective metric key must fail closed")
    bad_metric_key = json.loads(json.dumps(space))
    bad_metric_key["objective"]["metrics"][0]["dataset"] = ["synthetic-regression"]
    try:
        validate_search_space(bad_metric_key)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown nested objective metric key must fail closed")
    bad_gate_key = json.loads(json.dumps(space))
    bad_gate_key["objective"]["case_delta_gates"] = [{
        "metric": "corr", "stat": "min", "minimum_delta": -0.1,
        "case_id": ["case-a"],
    }]
    try:
        validate_search_space(bad_gate_key)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown nested case gate key must fail closed")
    bad_dataset_type = json.loads(json.dumps(space))
    bad_dataset_type["objective"]["metrics"][0]["datasets"] = [1]
    try:
        validate_search_space(bad_dataset_type)
    except ValueError:
        pass
    else:
        raise AssertionError("non-string dataset id must fail closed")
    candidates = generate_candidates(space)
    assert candidates[0]["label"] == "baseline"
    assert len(candidates) == 4
    grid_space = json.loads(json.dumps(space))
    grid_space["strategy"] = "cartesian"
    grid_space["parameters"] = {"aec_mu": [0.22, 0.24], "ns_floor": [0.06, 0.07, 0.12]}
    grid_candidates = generate_candidates(grid_space)
    grid_results = []
    for candidate in grid_candidates:
        item = {
            **candidate,
            "score": 1.0,
            "validation_result": "PASS",
            "case_delta_summary": [],
            "case_delta_violations": [],
        }
        if (abs(candidate["tuning"]["aec_mu"] - 0.24) < 1.0e-12 and
                abs(candidate["tuning"]["ns_floor"] - 0.06) < 1.0e-12):
            item["case_delta_violations"] = [{"gate": "case_delta_regression"}]
        grid_results.append(item)
    grid_selected = next(
        item for item in grid_results
        if abs(item["tuning"]["aec_mu"] - 0.24) < 1.0e-12
        and abs(item["tuning"]["ns_floor"] - 0.07) < 1.0e-12
    )
    grid_sensitivity = adjacent_development_sensitivity(
        grid_space, grid_selected, grid_results
    )
    assert grid_sensitivity["neighbor_count"] == 3
    assert grid_sensitivity["neighbor_slot_count"] == 3
    assert grid_sensitivity["evaluated_neighbor_count"] == 3
    assert grid_sensitivity["unobserved_neighbor_count"] == 0
    assert grid_sensitivity["complete_neighbor_coverage"] is True
    assert grid_sensitivity["unobserved_neighbors"] == []
    assert grid_sensitivity["compliant_neighbor_count"] == 2
    assert grid_sensitivity["violating_neighbor_count"] == 1
    ns_neighbor = next(
        item for item in grid_sensitivity["neighbors"]
        if item["parameter"] == "ns_floor"
    )
    assert abs(ns_neighbor["value"] - 0.06) < 1.0e-12
    assert ns_neighbor["direction"] == "lower"
    assert ns_neighbor["compliant"] is False
    assert ns_neighbor["case_delta_violations"][0]["gate"] == "case_delta_regression"
    paired_space = json.loads(json.dumps(space))
    paired_space["strategy"] = "paired"
    paired_space["max_candidates"] = 4
    paired_space["baseline"] = {
        "aec_mu": 0.24, "ns_floor": 0.07,
        "agc_target_dbfs": -16.0, "limiter_dbfs": -14.0,
    }
    paired_space["parameters"] = {
        "agc_target_dbfs": [-17.0, -18.0, -19.0],
        "limiter_dbfs": [-15.0, -16.0, -17.0],
    }
    paired_candidates = generate_candidates(paired_space)
    assert len(paired_candidates) == 4
    assert paired_candidates[1]["tuning"]["agc_target_dbfs"] == -17.0
    assert paired_candidates[1]["tuning"]["limiter_dbfs"] == -15.0
    assert paired_candidates[3]["tuning"]["agc_target_dbfs"] == -19.0
    assert paired_candidates[3]["tuning"]["limiter_dbfs"] == -17.0
    paired_results = [{
        **candidate,
        "score": 1.0,
        "validation_result": "PASS",
        "case_delta_summary": [],
        "case_delta_violations": [],
    } for candidate in paired_candidates]
    paired_results[3]["case_delta_violations"] = [{"gate": "case_delta_regression"}]
    paired_sensitivity = adjacent_development_sensitivity(
        paired_space, paired_results[2], paired_results
    )
    assert paired_sensitivity["neighbor_slot_count"] == 2
    assert paired_sensitivity["evaluated_neighbor_count"] == 2
    assert paired_sensitivity["unobserved_neighbor_count"] == 0
    assert paired_sensitivity["complete_neighbor_coverage"] is True
    assert paired_sensitivity["compliant_neighbor_count"] == 1
    assert paired_sensitivity["violating_neighbor_count"] == 1
    assert {item["direction"] for item in paired_sensitivity["neighbors"]} == {
        "previous", "next"
    }
    assert all(item["parameter"] == "paired" for item in paired_sensitivity["neighbors"])
    unequal_pairs = json.loads(json.dumps(paired_space))
    unequal_pairs["parameters"]["limiter_dbfs"].pop()
    try:
        validate_search_space(unequal_pairs)
    except ValueError:
        pass
    else:
        raise AssertionError("paired strategy must reject unequal parameter lengths")
    illegal_pair = json.loads(json.dumps(paired_space))
    illegal_pair["parameters"] = {
        "agc_target_dbfs": [-15.0],
        "limiter_dbfs": [-15.0],
    }
    try:
        validate_search_space(illegal_pair)
    except ValueError:
        pass
    else:
        raise AssertionError("paired strategy must validate complete coupled tunings")
    ota_results = [{
        **candidate,
        "score": 1.0,
        "validation_result": "PASS",
        "case_delta_summary": [],
        "case_delta_violations": [],
    } for candidate in candidates]
    ota_selected = next(
        item for item in ota_results
        if abs(item["tuning"]["aec_mu"] - 0.18) < 1.0e-12
    )
    ota_sensitivity = adjacent_development_sensitivity(
        space, ota_selected, ota_results
    )
    assert ota_sensitivity["neighbor_slot_count"] == 2
    assert ota_sensitivity["evaluated_neighbor_count"] == 1
    assert ota_sensitivity["neighbor_count"] == 1
    assert ota_sensitivity["unobserved_neighbor_count"] == 1
    assert ota_sensitivity["complete_neighbor_coverage"] is False
    missing_neighbor = ota_sensitivity["unobserved_neighbors"][0]
    assert missing_neighbor["parameter"] == "ns_floor"
    assert abs(missing_neighbor["value"] - 0.10) < 1.0e-12
    assert missing_neighbor["direction"] == "lower"
    assert missing_neighbor["reason"] == "not_evaluated_in_development_search"
    assert isinstance(missing_neighbor["tuning_id"], str) and len(missing_neighbor["tuning_id"]) == 12
    baseline = {"validation_result": "PASS", "summary": {"pass_rate": 1.0, "median_erle_db": 10.0}}
    better = {"validation_result": "PASS", "summary": {"pass_rate": 1.0, "median_erle_db": 11.5}}
    score, _ = score_against_baseline(space, baseline, better)
    assert score > 1.0
    assert not regression_violations(space, baseline, better)
    worse = {"validation_result": "PASS", "summary": {"pass_rate": 0.98, "median_erle_db": 12.0}}
    assert regression_violations(space, baseline, worse)
    tail_space = json.loads(json.dumps(space))
    tail_space["objective"]["case_delta_gates"] = [
        {"metric": "corr", "stat": "min", "minimum_delta": -0.015},
        {"metric": "corr", "stat": "p10", "minimum_delta": -0.005},
        {"metric": "erle", "stat": "min", "minimum_delta": -0.5},
    ]
    validate_search_space(tail_space)
    tail_base = {"cases": [
        {"case_id": "a", "metrics": {"corr": 0.10, "erle": 10.0}},
        {"case_id": "b", "metrics": {"corr": 0.20, "erle": 11.0}},
    ]}
    tail_good = {"cases": [
        {"case_id": "a", "metrics": {"corr": 0.096, "erle": 11.0}},
        {"case_id": "b", "metrics": {"corr": 0.22, "erle": 12.0}},
    ]}
    summaries, violations = case_delta_gate_violations(tail_space, tail_base, tail_good)
    assert len(summaries) == 3 and not violations
    tail_min = next(
        item for item in summaries
        if item["metric"] == "corr" and item["stat"] == "min"
    )
    assert abs(tail_min["minimum_margin"] - 0.011) < 1.0e-9
    assert tail_min["maximum_margin"] is None
    assert tail_min["binding_bound"] == "minimum_delta"
    assert abs(tail_min["binding_margin"] - 0.011) < 1.0e-9
    tail_bad = {"cases": [
        {"case_id": "a", "metrics": {"corr": 0.07, "erle": 11.0}},
        {"case_id": "b", "metrics": {"corr": 0.22, "erle": 12.0}},
    ]}
    _, violations = case_delta_gate_violations(tail_space, tail_base, tail_bad)
    assert any(item["gate"] == "case_delta_regression" for item in violations)
    duplicate = json.loads(json.dumps(tail_good))
    duplicate["cases"].append(json.loads(json.dumps(duplicate["cases"][0])))
    _, violations = case_delta_gate_violations(tail_space, tail_base, duplicate)
    assert any(item["gate"] == "case_identity_duplicate" for item in violations)
    missing_case = json.loads(json.dumps(tail_good))
    missing_case["cases"].pop()
    _, violations = case_delta_gate_violations(tail_space, tail_base, missing_case)
    mismatch = next(item for item in violations if item["gate"] == "case_set_mismatch")
    assert mismatch["missing_count"] == 1 and mismatch["extra_count"] == 0
    # Metrics are intrinsically per-scenario, so a gate must apply to the subset
    # of cases that define the metric instead of failing the whole candidate.
    partial_space = json.loads(json.dumps(space))
    partial_space["objective"]["case_delta_gates"] = [
        {"metric": "speech", "stat": "min", "minimum_delta": -0.75, "min_cases": 1},
    ]
    validate_search_space(partial_space)
    partial_base = {"cases": [
        {"case_id": "echo", "metrics": {"speech": 4.0}},
        {"case_id": "clean", "metrics": {"erle": 12.0}},
    ]}
    partial_good = {"cases": [
        {"case_id": "echo", "metrics": {"speech": 3.8}},
        {"case_id": "clean", "metrics": {"erle": 12.0}},
    ]}
    partial_summary, partial_violations = case_delta_gate_violations(
        partial_space, partial_base, partial_good)
    assert len(partial_summary) == 1 and not partial_violations
    assert partial_summary[0]["cases"] == 1
    assert abs(partial_summary[0]["actual_delta"] + 0.20) < 1.0e-9
    partial_bad = {"cases": [
        {"case_id": "echo", "metrics": {"speech": 3.0}},
        {"case_id": "clean", "metrics": {"erle": 12.0}},
    ]}
    _, partial_violations = case_delta_gate_violations(
        partial_space, partial_base, partial_bad)
    assert any(item["gate"] == "case_delta_regression" for item in partial_violations)
    asymmetric = {"cases": [
        {"case_id": "echo", "metrics": {"speech": 3.8}},
        {"case_id": "clean", "metrics": {"erle": 12.0, "speech": 1.0}},
    ]}
    _, partial_violations = case_delta_gate_violations(
        partial_space, partial_base, asymmetric)
    assert any(item["gate"] == "case_metric_coverage_mismatch"
               for item in partial_violations)
    absent_base = {"cases": [
        {"case_id": "a", "metrics": {"erle": 10.0}},
        {"case_id": "b", "metrics": {"erle": 11.0}},
    ]}
    absent_cand = {"cases": [
        {"case_id": "a", "metrics": {"erle": 10.5}},
        {"case_id": "b", "metrics": {"erle": 11.5}},
    ]}
    _, partial_violations = case_delta_gate_violations(
        partial_space, absent_base, absent_cand)
    assert any(item["gate"] == "case_gate_not_applicable"
               for item in partial_violations)
    min_cases_space = json.loads(json.dumps(space))
    min_cases_space["objective"]["case_delta_gates"] = [
        {"metric": "speech", "stat": "min", "minimum_delta": -0.75, "min_cases": 3},
    ]
    validate_search_space(min_cases_space)
    _, partial_violations = case_delta_gate_violations(
        min_cases_space, partial_base, partial_good)
    assert any(item["gate"] == "case_gate_insufficient_cases"
               for item in partial_violations)
    upper_space = json.loads(json.dumps(space))
    upper_space["objective"]["case_delta_gates"] = [
        {"metric": "fpr", "stat": "max", "maximum_delta": 0.05},
    ]
    validate_search_space(upper_space)
    upper_base = {"cases": [
        {"case_id": "a", "metrics": {"fpr": 0.10}},
        {"case_id": "b", "metrics": {"fpr": 0.20}},
    ]}
    upper_ok = {"cases": [
        {"case_id": "a", "metrics": {"fpr": 0.12}},
        {"case_id": "b", "metrics": {"fpr": 0.20}},
    ]}
    upper_summary, upper_violations = case_delta_gate_violations(
        upper_space, upper_base, upper_ok)
    assert not upper_violations
    assert abs(upper_summary[0]["actual_delta"] - 0.02) < 1.0e-9
    assert upper_summary[0]["minimum_margin"] is None
    assert abs(upper_summary[0]["maximum_margin"] - 0.03) < 1.0e-9
    assert upper_summary[0]["binding_bound"] == "maximum_delta"
    assert abs(upper_summary[0]["binding_margin"] - 0.03) < 1.0e-9
    upper_bad = {"cases": [
        {"case_id": "a", "metrics": {"fpr": 0.12}},
        {"case_id": "b", "metrics": {"fpr": 0.28}},
    ]}
    _, upper_violations = case_delta_gate_violations(
        upper_space, upper_base, upper_bad)
    upper_violation = next(
        item for item in upper_violations
        if item["gate"] == "case_delta_excursion"
    )
    assert abs(upper_violation["maximum_margin"] + 0.03) < 1.0e-9
    assert abs(upper_violation["binding_margin"] + 0.03) < 1.0e-9
    unbounded = json.loads(json.dumps(space))
    unbounded["objective"]["case_delta_gates"] = [
        {"metric": "corr", "stat": "min"},
    ]
    try:
        validate_search_space(unbounded)
    except ValueError:
        pass
    else:
        raise AssertionError("case delta gate without a bound must fail closed")
    inverted = json.loads(json.dumps(space))
    inverted["objective"]["case_delta_gates"] = [
        {"metric": "corr", "stat": "min", "minimum_delta": 0.0, "maximum_delta": -1.0},
    ]
    try:
        validate_search_space(inverted)
    except ValueError:
        pass
    else:
        raise AssertionError("inverted case delta gate bounds must fail closed")
    # An unknown or misspelled top-level key used to be ignored and every optional
    # key had a silent default, so `strategies` in place of `strategy` ran the space
    # as one-at-a-time while the report still said cartesian. Both fail closed now.
    misspelled = json.loads(json.dumps(space))
    misspelled["strategies"] = misspelled.pop("strategy")
    misspelled["maxcandidates"] = misspelled.pop("max_candidates")
    try:
        validate_search_space(misspelled)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown search space keys must fail closed")
    undeclared = json.loads(json.dumps(space))
    undeclared.pop("strategy")
    try:
        validate_search_space(undeclared)
    except ValueError:
        pass
    else:
        raise AssertionError("a search space without strategy must fail closed")
    # A declared objective metric that the baseline summary does not produce used
    # to be skipped silently, which dropped its weight with no report entry and no
    # error. The baseline side must fail closed. The candidate side stays a skip
    # because tuning_iteration.py turns it into an explicit reported penalty, so it
    # is deliberately not asserted here: the strict wrapper changes that result.
    absent_metric = json.loads(json.dumps(space))
    absent_metric["objective"]["metrics"] = [
        {"name": "min_vad_recall", "direction": "max", "weight": 1.0,
         "scale": 1.0, "max_regression": 0.0},
    ]
    validate_search_space(absent_metric)
    produced = {"summary": {"erle": 1.0}}
    try:
        score_against_baseline(absent_metric, produced, produced)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "a baseline summary missing a declared metric must fail closed")
    try:
        regression_violations(absent_metric, produced, produced)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "a baseline summary missing a gated metric must fail closed")
    with tempfile.TemporaryDirectory(prefix="ap-tuning-selftest-") as temporary:
        root = Path(temporary)
        for index, seed in enumerate((1, 2, 3)):
            corpus = {
                "schema_version": 1, "corpus_id": f"c{index}", "tier": "regression",
                "generator": {"seed": seed}, "cases": [{"case_id": "same"}],
            }
            (root / f"{index}.json").write_text(json.dumps(corpus), encoding="utf-8")
        identities = enforce_partition_independence(root / "0.json", root / "1.json", root / "2.json")
        assert identities["development"]["generator_seed"] == 1
        validation_grade = json.loads((root / "0.json").read_text())
        validation_grade["tier"] = "validation-grade"
        (root / "0.json").write_text(json.dumps(validation_grade), encoding="utf-8")
        try:
            enforce_partition_independence(root / "0.json", root / "1.json", root / "2.json")
        except ValueError:
            pass
        else:
            raise AssertionError("validation-grade corpus must be rejected for selection")
    print("tuning iteration self-test: OK")


def main(semantics: IterationSemantics | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--policy", type=Path, default=Path("validation/policies/validation-smoke.json"))
    parser.add_argument("--dataset-lock", type=Path, default=Path("validation/datasets.lock.json"))
    parser.add_argument("--search-space", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--candidate-jobs", type=int, default=1,
                        help="parallel development candidates; deterministic output order is preserved")
    parser.add_argument("--holdout-jobs", type=int, default=1,
                        help="parallel validation/shadow reports; deterministic output order is preserved")
    parser.add_argument("--require-candidate", action="store_true",
                        help="return non-zero unless an independent-gate ACOUSTIC_CANDIDATE is produced")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = ("processor", "development_corpus", "validation_corpus",
                "shadow_corpus", "search_space", "output_dir")
    for name in required:
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    result = iterate(
        args.repo_root.resolve(), args.processor.resolve(),
        args.development_corpus.resolve(), args.validation_corpus.resolve(),
        args.shadow_corpus.resolve(), args.policy.resolve(), args.dataset_lock.resolve(),
        args.search_space.resolve(), args.output_dir.resolve(), args.candidate_jobs,
        semantics=semantics, holdout_jobs=args.holdout_jobs,
    )
    print(json.dumps({
        "decision": result["decision"], "iteration_id": result["iteration_id"],
        "selected": result["selected"],
    }, sort_keys=True))
    if args.require_candidate and result["decision"] != "ACOUSTIC_CANDIDATE":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
