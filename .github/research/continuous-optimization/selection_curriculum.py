#!/usr/bin/env python3
"""Mine optimizer selection/regression violations into an advisory curriculum.

This complements failure_mining.py. Absolute validation case failures remain in
failure-curriculum.json; this tool explains why development-ranked algorithm or
parameter candidates were ineligible relative to the baseline. Only development
ranking data is consumed. Validation/shadow results never feed the curriculum.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("selection score must be finite")
    return number


def _violation_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("gate", "unknown")),
        str(item.get("metric", "none")),
        str(item.get("unit", "none")),
    )


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gates: Counter[str] = Counter()
    metrics: Counter[str] = Counter()
    units: Counter[str] = Counter()
    triples: Counter[tuple[str, str, str]] = Counter()
    total = 0
    for row in rows:
        violations = row.get("violations")
        if not isinstance(violations, list):
            raise ValueError("ranking violations must be a list")
        for item in violations:
            if not isinstance(item, dict):
                raise ValueError("ranking violation must be an object")
            gate, metric, unit = _violation_key(item)
            gates[gate] += 1
            metrics[metric] += 1
            units[unit] += 1
            triples[(gate, metric, unit)] += 1
            total += 1
    return {
        "total_violations": total,
        "by_gate": [
            {"gate": key, "count": count}
            for key, count in sorted(gates.items(), key=lambda item: (-item[1], item[0]))
        ],
        "by_metric": [
            {"metric": key, "count": count}
            for key, count in sorted(metrics.items(), key=lambda item: (-item[1], item[0]))
        ],
        "by_unit": [
            {"unit": key, "count": count}
            for key, count in sorted(units.items(), key=lambda item: (-item[1], item[0]))
        ],
        "top_combinations": [
            {"gate": gate, "metric": metric, "unit": unit, "count": count}
            for (gate, metric, unit), count in sorted(
                triples.items(), key=lambda item: (-item[1], item[0])
            )[:16]
        ],
    }


def _is_terminal_only(row: dict[str, Any]) -> bool:
    violations = row.get("violations") or []
    return bool(violations) and all(
        isinstance(item, dict) and item.get("gate") == "terminal_candidate_reuse"
        for item in violations
    )


def _nonterminal_violation_count(row: dict[str, Any]) -> int:
    return sum(
        1 for item in row.get("violations", [])
        if isinstance(item, dict) and item.get("gate") != "terminal_candidate_reuse"
    )


def _stage_summary(
    rows: list[dict[str, Any]],
    *,
    identity_key: str,
    baseline_identity: str,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("ranking rows required")
    identities = [str(row.get(identity_key, "")) for row in rows]
    if baseline_identity not in identities:
        raise ValueError("baseline identity missing from ranking")
    for row in rows:
        _finite(row.get("development_score", 0.0))
        _finite(row.get("worst_development_unit_score", 0.0))
        if not isinstance(row.get("eligible"), bool):
            raise ValueError("ranking eligible flag must be boolean")

    baseline = next(row for row in rows if str(row[identity_key]) == baseline_identity)
    nonbaseline = [row for row in rows if str(row[identity_key]) != baseline_identity]
    eligible_nonbaseline = [row for row in nonbaseline if row["eligible"]]
    ineligible = [row for row in nonbaseline if not row["eligible"]]

    highest_score_ineligible = None
    if ineligible:
        chosen = sorted(
            ineligible,
            key=lambda row: (
                -_finite(row["development_score"]),
                -_finite(row["worst_development_unit_score"]),
                str(row.get("research_candidate_id", row.get(identity_key, ""))),
            ),
        )[0]
        highest_score_ineligible = {
            identity_key: chosen[identity_key],
            "research_candidate_id": chosen.get("research_candidate_id"),
            "development_score": chosen["development_score"],
            "worst_development_unit_score": chosen["worst_development_unit_score"],
            "violations": chosen["violations"],
            "objective_vector": chosen.get("objective_vector", {}),
        }
        if "algorithm" in chosen:
            highest_score_ineligible["algorithm"] = chosen["algorithm"]
        if "tuning" in chosen:
            highest_score_ineligible["tuning"] = chosen["tuning"]

    repairable = [
        row for row in ineligible
        if not _is_terminal_only(row)
        and _nonterminal_violation_count(row) > 0
    ]
    closest_repairable = None
    if repairable:
        chosen = sorted(
            repairable,
            key=lambda row: (
                _nonterminal_violation_count(row),
                -_finite(row["development_score"]),
                -_finite(row["worst_development_unit_score"]),
                str(row.get("research_candidate_id", row.get(identity_key, ""))),
            ),
        )[0]
        closest_repairable = {
            identity_key: chosen[identity_key],
            "research_candidate_id": chosen.get("research_candidate_id"),
            "development_score": chosen["development_score"],
            "worst_development_unit_score": chosen["worst_development_unit_score"],
            "nonterminal_violation_count": _nonterminal_violation_count(chosen),
            "violations": [
                item for item in chosen["violations"]
                if item.get("gate") != "terminal_candidate_reuse"
            ],
            "objective_vector": chosen.get("objective_vector", {}),
        }
        if "algorithm" in chosen:
            closest_repairable["algorithm"] = chosen["algorithm"]
        if "tuning" in chosen:
            closest_repairable["tuning"] = chosen["tuning"]

    return {
        "baseline": {
            identity_key: baseline[identity_key],
            "development_score": baseline["development_score"],
            "eligible": baseline["eligible"],
        },
        "candidate_count": len(rows),
        "eligible_nonbaseline_count": len(eligible_nonbaseline),
        "terminal_only_ineligible_count": sum(_is_terminal_only(row) for row in ineligible),
        "highest_score_ineligible": highest_score_ineligible,
        "closest_repairable": closest_repairable,
        "violations": _aggregate(nonbaseline),
    }


def mine_selection(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("authority") != "research-only-hierarchical-algorithm-parameter-optimization":
        raise ValueError("unexpected optimization authority")
    if result.get("automatic_shipping_promotion") is not False:
        raise ValueError("shipping promotion authority drift")
    if result.get("automatic_main_mutation") is not False:
        raise ValueError("main mutation authority drift")

    development = result.get("development")
    if not isinstance(development, dict):
        raise ValueError("development result missing")
    algorithm_screen = development.get("algorithm_screen")
    parameter_search = development.get("parameter_search")
    if not isinstance(algorithm_screen, dict) or not isinstance(parameter_search, dict):
        raise ValueError("hierarchical rankings missing")

    algorithm_rows = algorithm_screen.get("ranking")
    parameter_rows = parameter_search.get("ranking")
    if not isinstance(algorithm_rows, list) or not isinstance(parameter_rows, list):
        raise ValueError("ranking arrays missing")

    algorithm_baseline = str(algorithm_rows[0].get("algorithm_id", ""))
    parameter_baseline = str(parameter_rows[0].get("candidate_id", ""))
    algorithm = _stage_summary(
        algorithm_rows,
        identity_key="algorithm_id",
        baseline_identity=algorithm_baseline,
    )
    parameter = _stage_summary(
        parameter_rows,
        identity_key="candidate_id",
        baseline_identity=parameter_baseline,
    )

    selected = result.get("selected") or {}
    selected_algorithm = str(selected.get("algorithm_id", ""))
    selected_tuning_id = str(selected.get("tuning_candidate_id", ""))
    if selected_algorithm != algorithm_screen.get("selected_algorithm_id"):
        raise ValueError("selected algorithm identity drift")
    if not selected_tuning_id:
        raise ValueError("selected tuning identity missing")

    algorithm_signal = (
        "EXPLORE_ELIGIBLE_NONBASELINE"
        if algorithm["eligible_nonbaseline_count"] > 0
        else "RETAIN_BASELINE_AND_DIAGNOSE_INELIGIBLE"
    )
    parameter_signal = (
        "EXPLORE_ELIGIBLE_NONBASELINE"
        if parameter["eligible_nonbaseline_count"] > 0
        else "RETAIN_BASELINE_AND_DIAGNOSE_BOUNDARY"
    )

    return {
        "schema_version": 1,
        "authority": "research-selection-curriculum-only",
        "source_sha": result.get("source_sha"),
        "experiment_id": result.get("experiment_id"),
        "optimization_decision": result.get("decision"),
        "optimization_status": result.get("status"),
        "selection_inputs": {
            "roles": ["development"],
            "validation_used_for_selection_curriculum": False,
            "shadow_used_for_selection_curriculum": False,
            "blind_used_for_selection_curriculum": False,
            "product_external_used_for_selection_curriculum": False,
        },
        "algorithm": {
            **algorithm,
            "selected_algorithm_id": selected_algorithm,
            "next_round_signal": algorithm_signal,
        },
        "parameter": {
            **parameter,
            "selected_tuning_candidate_id": selected_tuning_id,
            "selected_tuning": selected.get("tuning"),
            "next_round_signal": parameter_signal,
        },
        "automatic_search_space_mutation": False,
        "automatic_algorithm_source_mutation": False,
        "automatic_training_mutation": False,
        "automatic_main_mutation": False,
        "shipping_authority": False,
        "next_action":
            "consume development-only selection curriculum before defining a new bounded hypothesis; "
            "do not relax gates, reuse terminal candidates, or feed validation/shadow results back into selection",
    }


def self_test() -> None:
    fixture = {
        "authority": "research-only-hierarchical-algorithm-parameter-optimization",
        "automatic_shipping_promotion": False,
        "automatic_main_mutation": False,
        "source_sha": "a" * 40,
        "experiment_id": "fixture",
        "decision": "KEEP_BASELINE",
        "status": "NO_RESEARCH_CANDIDATE",
        "development": {
            "algorithm_screen": {
                "selected_algorithm_id": "mdf-ema",
                "ranking": [
                    {
                        "algorithm_id": "mdf-ema", "research_candidate_id": "base-a",
                        "development_score": 0.0, "worst_development_unit_score": 0.0,
                        "eligible": True, "violations": [], "objective_vector": {},
                        "algorithm": {"algorithm_id": "mdf-ema"},
                    },
                    {
                        "algorithm_id": "nlms-ema", "research_candidate_id": "nlms-a",
                        "development_score": 8.0, "worst_development_unit_score": 0.0,
                        "eligible": False,
                        "violations": [
                            {"gate": "case_delta_regression", "metric": "vad_recall", "unit": "d1"},
                            {"gate": "case_delta_regression", "metric": "near_si_sdr_improvement_db", "unit": "d1"},
                        ],
                        "objective_vector": {"median_erle_db": 10.0},
                        "algorithm": {"algorithm_id": "nlms-ema"},
                    },
                ],
            },
            "parameter_search": {
                "ranking": [
                    {
                        "candidate_id": "base-t", "research_candidate_id": "base-r",
                        "development_score": 0.0, "worst_development_unit_score": 0.0,
                        "eligible": True, "violations": [], "objective_vector": {},
                        "tuning": {"aec_mu": 0.22},
                    },
                    {
                        "candidate_id": "terminal-t", "research_candidate_id": "terminal-r",
                        "development_score": 2.0, "worst_development_unit_score": 0.0,
                        "eligible": False,
                        "violations": [{"gate": "terminal_candidate_reuse"}],
                        "objective_vector": {},
                        "tuning": {"aec_mu": 0.24},
                    },
                    {
                        "candidate_id": "near-t", "research_candidate_id": "near-r",
                        "development_score": 1.0, "worst_development_unit_score": 0.0,
                        "eligible": False,
                        "violations": [
                            {"gate": "case_delta_regression", "metric": "vad_recall", "unit": "d2"}
                        ],
                        "objective_vector": {"median_erle_db": 0.6},
                        "tuning": {"aec_mu": 0.26},
                    },
                ],
                "algorithm_id": "mdf-ema",
                "pareto_frontier": [],
            },
        },
        "selected": {
            "algorithm_id": "mdf-ema",
            "tuning_candidate_id": "base-t",
            "tuning": {"aec_mu": 0.22},
        },
    }
    mined = mine_selection(fixture)
    assert mined["algorithm"]["next_round_signal"] == "RETAIN_BASELINE_AND_DIAGNOSE_INELIGIBLE"
    assert mined["algorithm"]["highest_score_ineligible"]["algorithm_id"] == "nlms-ema"
    assert mined["parameter"]["terminal_only_ineligible_count"] == 1
    assert mined["parameter"]["closest_repairable"]["candidate_id"] == "near-t"
    assert mined["parameter"]["closest_repairable"]["nonterminal_violation_count"] == 1
    assert mined["selection_inputs"]["validation_used_for_selection_curriculum"] is False
    assert mined["automatic_search_space_mutation"] is False
    print("selection curriculum self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimization-result", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.optimization_result is None or args.output is None:
        parser.error("--optimization-result and --output are required")
    result = json.loads(args.optimization_result.read_text(encoding="utf-8"))
    mined = mine_selection(result)
    rendered = json.dumps(mined, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
