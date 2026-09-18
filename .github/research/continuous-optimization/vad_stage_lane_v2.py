#!/usr/bin/env python3
"""Development-only VAD lane for strong-origin bounded hysteresis.

Selection consumes only preregistered fresh development seeds. Validation and
shadow are reject-only. Previously consumed public/synthetic confirmation
authorities are not inputs to this lane.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/tools"))
sys.path.insert(0, str(ROOT / "tests/validation"))

import run_validation_engine as engine
import vad_operating_point_selector as selector


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def threshold(profile: str, contract: dict[str, Any]) -> float:
    fixed = contract["fixed_policy"]
    return float(fixed["ns_threshold"] if profile == "ns-isolated" else fixed["local_threshold"])


def shipping_trace(probabilities: list[float], profile: str, contract: dict[str, Any]) -> list[dict[str, int]]:
    fixed = contract["fixed_policy"]
    th = threshold(profile, contract)
    strong = float(fixed["strong_threshold"])
    strong_hold = int(fixed["strong_hold_frames"])
    weak_hold = int(fixed["weak_hold_frames"])
    hold = 0
    out: list[dict[str, int]] = []
    for raw in probabilities:
        p = float(raw)
        if not math.isfinite(p):
            p = 0.0
        if p >= strong:
            hold = strong_hold
        elif p > th:
            hold = max(hold, weak_hold)
        elif hold:
            hold -= 1
        out.append({"vad_active": 1 if hold > 0 else 0})
    return out


def candidate_trace(
    probabilities: list[float],
    profile: str,
    release_margin: float,
    budget_frames: int,
    contract: dict[str, Any],
) -> list[dict[str, int]]:
    fixed = contract["fixed_policy"]
    th = threshold(profile, contract)
    release = max(0.01, th - float(release_margin))
    strong = float(fixed["strong_threshold"])
    strong_hold = int(fixed["strong_hold_frames"])
    weak_hold = int(fixed["weak_hold_frames"])

    hold = 0
    strong_origin = False
    budget = 0
    out: list[dict[str, int]] = []
    for raw in probabilities:
        p = float(raw)
        if not math.isfinite(p):
            p = 0.0

        if p >= strong:
            hold = strong_hold
            strong_origin = True
            budget = int(budget_frames)
        elif p > th:
            hold = max(hold, weak_hold)
        elif hold:
            if strong_origin and budget > 0 and p > release:
                # Freeze rather than decrement the existing hold for a bounded
                # number of frames. This extends only strong-origin tails.
                hold = max(hold, 2)
                budget -= 1
            else:
                hold -= 1

        if hold <= 0:
            hold = 0
            strong_origin = False
            budget = 0

        out.append({"vad_active": 1 if hold > 0 else 0})
    return out


def evaluate(
    partition: dict[str, Any],
    contract: dict[str, Any],
    variant: dict[str, Any] | None,
) -> dict[str, Any]:
    rows = []
    positive: set[str] = set()
    for case in partition["cases"]:
        if any(case["labels"]):
            positive.add(case["case_id"])
        if variant is None:
            trace = shipping_trace(case["probabilities"], case["processor_profile"], contract)
        else:
            trace = candidate_trace(
                case["probabilities"],
                case["processor_profile"],
                float(variant["release_margin"]),
                int(variant["subthreshold_budget_frames"]),
                contract,
            )
        stats = engine.vad_stats(case["labels"], trace)
        metrics = {
            "vad_f1": stats["f1"],
            "vad_precision": stats["precision"],
            "vad_recall": stats["recall"],
            "vad_false_positive_rate": stats["false_positive_rate"],
            "vad_false_negative_rate": stats["false_negative_rate"],
        }
        violations = engine.threshold_violations(metrics, case["expected"])
        rows.append({
            "case_id": case["case_id"],
            "processor_profile": case["processor_profile"],
            "metrics": metrics,
            "violations": violations,
            "passed": not violations,
        })
    recalls = [float(x["metrics"]["vad_recall"]) for x in rows if x["case_id"] in positive]
    f1s = [float(x["metrics"]["vad_f1"]) for x in rows if x["case_id"] in positive]
    fprs = [float(x["metrics"]["vad_false_positive_rate"]) for x in rows]
    return {
        "validation_result": "PASS" if all(x["passed"] for x in rows) else "FAIL",
        "summary": {
            "pass_rate": sum(x["passed"] for x in rows) / max(1, len(rows)),
            "min_vad_recall": min(recalls),
            "min_vad_f1": min(f1s),
            "max_vad_false_positive_rate": max(fprs),
        },
        "cases": rows,
    }


def metric(report: dict[str, Any], name: str) -> float:
    return float(report["summary"][name])


def regressions(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    recall_drop: float,
    f1_drop: float,
    fpr_rise: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if candidate["validation_result"] != "PASS":
        out.append({"gate": "candidate_case_gates", "actual": candidate["validation_result"]})
    checks = (
        ("min_vad_recall", "drop", recall_drop),
        ("min_vad_f1", "drop", f1_drop),
        ("max_vad_false_positive_rate", "rise", fpr_rise),
    )
    for name, kind, allowed in checks:
        b = metric(baseline, name)
        c = metric(candidate, name)
        reg = b - c if kind == "drop" else c - b
        if reg > allowed + 1.0e-12:
            out.append({
                "gate": "aggregate_regression",
                "metric": name,
                "baseline": b,
                "candidate": c,
                "regression": reg,
                "allowed": allowed,
            })
    return out


def score(baseline: dict[str, Any], candidate: dict[str, Any]) -> float:
    return (
        2.0 * (metric(candidate, "min_vad_recall") - metric(baseline, "min_vad_recall")) / 0.02
        + 1.0 * (metric(candidate, "min_vad_f1") - metric(baseline, "min_vad_f1")) / 0.02
        + 1.5 * (metric(baseline, "max_vad_false_positive_rate") - metric(candidate, "max_vad_false_positive_rate")) / 0.02
    )


def partition_seed(partition: dict[str, Any]) -> int:
    value = partition.get("generator", {}).get("seed") if "generator" in partition else partition.get("seed")
    if value is None:
        raise ValueError("partition seed missing")
    return int(value)


def collect(path: Path) -> dict[str, Any]:
    return selector.collect_partition(path.parent / "__processor_placeholder__", path)


def collect_with_processor(processor: Path, path: Path) -> dict[str, Any]:
    return selector.collect_partition(processor, path)


def run(
    processor: Path,
    development_paths: list[Path],
    validation_path: Path,
    shadow_path: Path,
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load(contract_path)
    if contract.get("authority") != "DEVELOPMENT_SELECTION_ONLY":
        raise ValueError("unexpected VAD v2 authority")
    if contract.get("hypothesis_id") != "vad-strong-origin-bounded-hysteresis-v1":
        raise ValueError("unexpected hypothesis identity")
    if len(development_paths) != 2:
        raise ValueError("exactly two development corpora required")

    dev = [collect_with_processor(processor, p) for p in development_paths]
    validation = collect_with_processor(processor, validation_path)
    shadow = collect_with_processor(processor, shadow_path)

    observed_dev = [int(x["seed"]) for x in dev]
    observed_validation = int(validation["seed"])
    observed_shadow = int(shadow["seed"])
    authority = contract["fresh_authority"]
    if observed_dev != [int(x) for x in authority["development_seeds"]]:
        raise ValueError(f"development seed drift: {observed_dev}")
    if observed_validation != int(authority["validation_seed"]):
        raise ValueError(f"validation seed drift: {observed_validation}")
    if observed_shadow != int(authority["shadow_seed"]):
        raise ValueError(f"shadow seed drift: {observed_shadow}")

    gates = contract["gates"]
    baseline_dev = [evaluate(p, contract, None) for p in dev]
    ranking = []
    for variant in contract["variants"]:
        reports = [evaluate(p, contract, variant) for p in dev]
        scores = [score(b, c) for b, c in zip(baseline_dev, reports)]
        local_violations = []
        for index, (b, c) in enumerate(zip(baseline_dev, reports)):
            violations = regressions(
                b,
                c,
                float(gates["max_development_recall_drop"]),
                float(gates["max_development_f1_drop"]),
                float(gates["max_development_fpr_rise"]),
            )
            if violations:
                local_violations.append({
                    "development_seed": observed_dev[index],
                    "violations": violations,
                })
        ranking.append({
            **variant,
            "mean_development_score": mean(scores),
            "eligible": not local_violations,
            "violations": local_violations,
            "summaries": [r["summary"] for r in reports],
        })

    eligible = [
        x for x in ranking
        if x["eligible"] and x["mean_development_score"] >= float(gates["min_mean_development_score"])
    ]
    eligible.sort(key=lambda x: (
        -float(x["mean_development_score"]),
        float(x["release_margin"]),
        int(x["subthreshold_budget_frames"]),
    ))
    selected = eligible[0] if eligible else None

    validation_base = evaluate(validation, contract, None)
    shadow_base = evaluate(shadow, contract, None)
    if selected is None:
        validation_candidate = validation_base
        shadow_candidate = shadow_base
        validation_violations: list[dict[str, Any]] = []
        shadow_violations: list[dict[str, Any]] = []
        decision = contract["outcomes"]["no_eligible_development_candidate"]
    else:
        validation_candidate = evaluate(validation, contract, selected)
        shadow_candidate = evaluate(shadow, contract, selected)
        validation_violations = regressions(
            validation_base,
            validation_candidate,
            float(gates["max_validation_recall_drop"]),
            float(gates["max_validation_f1_drop"]),
            float(gates["max_validation_fpr_rise"]),
        )
        shadow_violations = regressions(
            shadow_base,
            shadow_candidate,
            float(gates["max_shadow_recall_drop"]),
            float(gates["max_shadow_f1_drop"]),
            float(gates["max_shadow_fpr_rise"]),
        )
        decision = (
            contract["outcomes"]["winner"]
            if not validation_violations and not shadow_violations
            else contract["outcomes"]["holdout_reject"]
        )

    result = {
        "schema_version": 1,
        "authority": "development-selection-only",
        "hypothesis_id": contract["hypothesis_id"],
        "decision": decision,
        "source_base_sha": contract["source_base_sha"],
        "fresh_authority": {
            "development_seeds": observed_dev,
            "validation_seed": observed_validation,
            "shadow_seed": observed_shadow,
        },
        "baseline": {
            "algorithm": "shipping-strong-weak",
            "strong_threshold": contract["fixed_policy"]["strong_threshold"],
            "strong_hold_frames": contract["fixed_policy"]["strong_hold_frames"],
            "weak_hold_frames": contract["fixed_policy"]["weak_hold_frames"],
        },
        "development": {
            "ranking": sorted(
                ranking,
                key=lambda x: (
                    -float(x["mean_development_score"]),
                    float(x["release_margin"]),
                    int(x["subthreshold_budget_frames"]),
                ),
            )
        },
        "selected": (
            {
                "variant_id": selected["variant_id"],
                "release_margin": selected["release_margin"],
                "subthreshold_budget_frames": selected["subthreshold_budget_frames"],
                "mean_development_score": selected["mean_development_score"],
            }
            if selected else None
        ),
        "validation": {
            "baseline": validation_base["summary"],
            "candidate": validation_candidate["summary"],
            "regression_violations": validation_violations,
        },
        "shadow": {
            "baseline": shadow_base["summary"],
            "candidate": shadow_candidate["summary"],
            "regression_violations": shadow_violations,
        },
        "feedback_boundary": {
            "development_selected": True,
            "validation_and_shadow_reject_only": True,
            "consumed_public_authority_used": False,
            "old_confirmation_seeds_used": False,
        },
        "automatic_main_mutation": False,
        "source_merge_authorized": False,
        "shipping_authority": False,
        "hil_authority": False,
        "product_certification_authority": False,
        "next_gate": (
            "separate exact-source candidate implementation and review"
            if decision == contract["outcomes"]["winner"] else None
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    contract = {
        "fixed_policy": {
            "local_threshold": 0.45,
            "ns_threshold": 0.35,
            "strong_threshold": 0.50,
            "strong_hold_frames": 8,
            "weak_hold_frames": 6,
        }
    }
    weak_only = [0.1, 0.46, 0.42] + [0.1] * 8
    base_weak = shipping_trace(weak_only, "vad-isolated", contract)
    cand_weak = candidate_trace(weak_only, "vad-isolated", 0.05, 3, contract)
    assert base_weak == cand_weak, "weak-only path must not gain hysteresis extension"

    strong = [0.1, 0.60, 0.42, 0.42, 0.42] + [0.1] * 12
    base_strong = shipping_trace(strong, "vad-isolated", contract)
    cand_strong = candidate_trace(strong, "vad-isolated", 0.05, 2, contract)
    assert len(base_strong) == len(cand_strong)
    assert sum(row["vad_active"] for row in cand_strong) > sum(row["vad_active"] for row in base_strong)

    bounded = candidate_trace([0.1, 0.60] + [0.42] * 20 + [0.1] * 20, "vad-isolated", 0.05, 2, contract)
    assert sum(row["vad_active"] for row in bounded) < len(bounded), "bounded tail must eventually release"
    print("VAD strong-origin bounded-hysteresis self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--development-corpus", action="append", type=Path, default=[])
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (args.processor, args.validation_corpus, args.shadow_corpus, args.contract, args.output)
    if any(x is None for x in required):
        parser.error("processor, validation, shadow, contract and output are required")
    result = run(
        args.processor.resolve(),
        [x.resolve() for x in args.development_corpus],
        args.validation_corpus.resolve(),
        args.shadow_corpus.resolve(),
        args.contract.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "hypothesis_id": result["hypothesis_id"],
        "decision": result["decision"],
        "selected": result["selected"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
