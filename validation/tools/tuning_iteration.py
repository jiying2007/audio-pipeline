#!/usr/bin/env python3
"""Authority-guarded acoustic tuning CLI.

The search implementation lives in tuning_iteration_engine.py. This entrypoint
owns optimizer data-role admission and fail-closed objective semantics so
blind/product evidence cannot enter feedback and candidates cannot improve by
making an objective metric disappear.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from authority import load_authority, optimizer_role_allowed
import tuning_iteration_engine as engine

KNOWN_OBJECTIVE_METRICS = {
    "pass_rate",
    "p10_near_si_sdr_improvement_db",
    "p10_noise_only_attenuation_db",
    "median_erle_db",
    "min_vad_f1",
    "min_vad_recall",
    "max_vad_false_positive_rate",
    "max_output_clip_fraction",
}
_MISSING_METRIC_PENALTY = -1.0e12
_original_validate_search_space = engine.validate_search_space
_original_score = engine.score_against_baseline
_original_regression = engine.regression_violations


def corpus_tier(path: Path) -> str:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    tier = corpus.get("tier")
    if not isinstance(tier, str) or not tier:
        raise ValueError(f"corpus tier is required: {path}")
    return tier


def enforce_optimizer_authority(development: Path, validation: Path, shadow: Path) -> None:
    authority = load_authority()
    for role, path in (
        ("development", development),
        ("validation", validation),
        ("shadow", shadow),
    ):
        tier = corpus_tier(path)
        if not optimizer_role_allowed(authority, tier, role):
            raise ValueError(f"authority rejects {tier!r} corpus for optimizer role {role!r}")


def strict_partition_independence(development: Path, validation: Path,
                                  shadow: Path) -> dict[str, Any]:
    identities = {
        "development": engine.load_corpus_identity(development),
        "validation": engine.load_corpus_identity(validation),
        "shadow": engine.load_corpus_identity(shadow),
    }
    hashes = [item["sha256"] for item in identities.values()]
    ids = [item["corpus_id"] for item in identities.values()]
    seeds = [item["generator_seed"] for item in identities.values()]
    if len(set(hashes)) != 3 or len(set(ids)) != 3:
        raise ValueError("development/validation/shadow corpora must be distinct")
    if all(seed is not None for seed in seeds) and len(set(seeds)) != 3:
        raise ValueError("generated partitions must use distinct seeds")
    authority = load_authority()
    for role, identity in identities.items():
        tier = identity["tier"]
        if not optimizer_role_allowed(authority, tier, role):
            raise ValueError(f"authority rejects {tier!r} corpus for optimizer role {role!r}")
    return identities


def strict_validate_search_space(space: dict[str, Any]) -> None:
    _original_validate_search_space(space)
    metrics = engine.objective_metrics(space)
    names = [str(metric.get("name", "")) for metric in metrics]
    if len(names) != len(set(names)):
        raise ValueError("objective metric names must be unique")
    unknown = set(names) - KNOWN_OBJECTIVE_METRICS
    if unknown:
        raise ValueError(f"unknown objective metrics: {sorted(unknown)}")


def strict_score(space: dict[str, Any], baseline: dict[str, Any],
                 candidate: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    score, deltas = _original_score(space, baseline, candidate)
    for metric in engine.objective_metrics(space):
        name = str(metric["name"])
        base = engine.summary_value(baseline, name)
        cand = engine.summary_value(candidate, name)
        if base is not None and cand is None:
            deltas.append({
                "metric": name,
                "baseline": base,
                "candidate": None,
                "directed_delta": None,
                "weighted_score": _MISSING_METRIC_PENALTY,
                "reason": "candidate_objective_metric_missing",
            })
            score = min(score, _MISSING_METRIC_PENALTY)
    return score, deltas


def strict_regression(space: dict[str, Any], baseline: dict[str, Any],
                      candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations = _original_regression(space, baseline, candidate)
    for metric in engine.objective_metrics(space):
        name = str(metric["name"])
        base = engine.summary_value(baseline, name)
        cand = engine.summary_value(candidate, name)
        if base is not None and cand is None:
            violations.append({
                "gate": "objective_metric_missing",
                "metric": name,
                "baseline": base,
                "candidate": None,
            })
    return violations


def install_fail_closed_guards() -> None:
    engine.enforce_partition_independence = strict_partition_independence
    engine.validate_search_space = strict_validate_search_space
    engine.score_against_baseline = strict_score
    engine.regression_violations = strict_regression


def self_test() -> None:
    authority = load_authority()
    assert optimizer_role_allowed(authority, "regression", "development")
    assert optimizer_role_allowed(authority, "research-validation", "development")
    assert not optimizer_role_allowed(authority, "validation-grade", "development")
    assert optimizer_role_allowed(authority, "validation-grade", "validation")
    assert not optimizer_role_allowed(authority, "validation-grade-blind", "validation")
    assert not optimizer_role_allowed(authority, "validation-grade-blind", "shadow")
    install_fail_closed_guards()
    engine.self_test()
    space = {
        "schema_version": 1,
        "search_space_id": "missing-metric-test",
        "strategy": "one-at-a-time",
        "max_candidates": 2,
        "baseline": {
            "aec_mu": 0.22, "ns_floor": 0.12,
            "agc_target_dbfs": -20.0, "limiter_dbfs": -2.0,
        },
        "parameters": {"aec_mu": [0.22]},
        "objective": {
            "metrics": [{
                "name": "median_erle_db", "direction": "max", "weight": 1.0,
                "scale": 1.0, "max_regression": 1.0,
            }],
        },
    }
    strict_validate_search_space(space)
    baseline = {"validation_result": "PASS", "summary": {"median_erle_db": 8.0}}
    missing = {"validation_result": "PASS", "summary": {"median_erle_db": None}}
    score, _ = strict_score(space, baseline, missing)
    assert score == _MISSING_METRIC_PENALTY
    assert any(item["gate"] == "objective_metric_missing"
               for item in strict_regression(space, baseline, missing))
    bad = json.loads(json.dumps(space))
    bad["objective"]["metrics"][0]["name"] = "not-a-real-metric"
    try:
        strict_validate_search_space(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown objective metric must fail closed")
    print("authority-guarded tuning self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    args, _ = parser.parse_known_args()
    install_fail_closed_guards()
    if args.self_test:
        self_test()
        return 0
    for name in ("development_corpus", "validation_corpus", "shadow_corpus"):
        if getattr(args, name) is None:
            raise SystemExit(f"--{name.replace('_', '-')} is required")
    enforce_optimizer_authority(
        args.development_corpus.resolve(),
        args.validation_corpus.resolve(),
        args.shadow_corpus.resolve(),
    )
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
