#!/usr/bin/env python3
"""Independent confirmation for the fixed VAD strong/weak refresh hypothesis.

No parameter search is performed. The hypothesis is frozen to strong=0.50,
weak=6 with the shipping local/NS decision thresholds unchanged and strong hold
fixed at 8. Confirmation authorities are new synthetic seeds 4307/5307/6307
plus the separately hash-pinned AMI ES2004a external-timing microset.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
from pathlib import Path
from typing import Any, Callable

import ami_vad_microset_eval as ami_eval
import run_validation_engine as engine
import vad_hangover_counterfactual as fixed
import vad_operating_point_selector as selector
import vad_strong_weak_refresh as policy

FIXED_STRONG_THRESHOLD = 0.50
FIXED_WEAK_HOLD = 6
CONFIRMATION_SEEDS = (4307, 5307, 6307)
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


def retry_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    for attempt in range(MAX_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_HTTP_STATUS or attempt + 1 >= MAX_ATTEMPTS:
                raise
            raw = error.headers.get("Retry-After") if error.headers is not None else None
            delay = None
            if raw:
                try:
                    delay = min(max(float(raw), 0.25), 8.0)
                except ValueError:
                    delay = None
            if delay is None:
                delay = min(float(1 << attempt), 8.0)
            time.sleep(delay)
    raise AssertionError("unreachable bounded retry loop")


def collect_ami_with_retries(processor: Path, lock_path: Path) -> dict[str, Any]:
    original_small = ami_eval.request_small
    original_range = ami_eval.request_exact_range

    def small(url: str, max_bytes: int = ami_eval.MAX_XML_BYTES) -> bytes:
        return retry_call(original_small, url, max_bytes)

    def exact_range(url: str, start: int, end: int) -> bytes:
        return retry_call(original_range, url, start, end)

    ami_eval.request_small = small
    ami_eval.request_exact_range = exact_range
    try:
        return fixed.collect_ami(processor, lock_path)
    finally:
        ami_eval.request_small = original_small
        ami_eval.request_exact_range = original_range


def synthetic_authority(processor: Path, corpus_path: Path) -> dict[str, Any]:
    partition = selector.collect_partition(processor, corpus_path)
    baseline = policy.evaluate_synthetic(partition, None, None)
    candidate = policy.evaluate_synthetic(
        partition, FIXED_STRONG_THRESHOLD, FIXED_WEAK_HOLD
    )
    regressions = policy.synthetic_regressions(baseline, candidate)
    score = policy.score_synthetic(baseline, candidate)
    return {
        "identity": policy.partition_identity(partition),
        "baseline": baseline,
        "candidate": candidate,
        "score": score,
        "regression_violations": regressions,
        "confirmed": (
            baseline["validation_result"] == "PASS"
            and candidate["validation_result"] == "PASS"
            and not regressions
            and score >= 0.0
        ),
    }


def metric(report: dict[str, Any], name: str) -> float:
    value = report["aggregate"].get(name)
    if value is None:
        raise ValueError(f"missing AMI metric: {name}")
    return float(value)


def confirmation_ami_regressions(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> list[dict[str, Any]]:
    """Apply the #82 AMI policy with a meeting-generic low-activity window."""
    violations: list[dict[str, Any]] = []
    fpr_improvement = (
        metric(baseline, "false_positive_rate")
        - metric(candidate, "false_positive_rate")
    )
    recall_drop = metric(baseline, "recall") - metric(candidate, "recall")
    f1_drop = metric(baseline, "f1") - metric(candidate, "f1")
    if fpr_improvement < fixed.AMI_MIN_FPR_IMPROVEMENT - 1.0e-12:
        violations.append({
            "gate": "ami_aggregate_fpr_improvement",
            "actual": fpr_improvement,
            "required": fixed.AMI_MIN_FPR_IMPROVEMENT,
        })
    if recall_drop > fixed.AMI_MAX_RECALL_DROP + 1.0e-12:
        violations.append({
            "gate": "ami_aggregate_recall_drop",
            "actual": recall_drop,
            "allowed": fixed.AMI_MAX_RECALL_DROP,
        })
    if f1_drop > fixed.AMI_MAX_F1_DROP + 1.0e-12:
        violations.append({
            "gate": "ami_aggregate_f1_drop",
            "actual": f1_drop,
            "allowed": fixed.AMI_MAX_F1_DROP,
        })

    baseline_by_id = {item["window_id"]: item for item in baseline["windows"]}
    low_activity_id = min(
        baseline["windows"], key=lambda item: float(item["activity_fraction"])
    )["window_id"]
    for item in candidate["windows"]:
        base = baseline_by_id[item["window_id"]]["metrics"]
        cand = item["metrics"]
        recall_drop_window = float(base["recall"]) - float(cand["recall"])
        f1_drop_window = float(base["f1"]) - float(cand["f1"])
        fpr_rise_window = (
            float(cand["false_positive_rate"])
            - float(base["false_positive_rate"])
        )
        if recall_drop_window > fixed.AMI_WINDOW_MAX_RECALL_DROP + 1.0e-12:
            violations.append({
                "gate": "ami_window_recall_drop",
                "window_id": item["window_id"],
                "actual": recall_drop_window,
                "allowed": fixed.AMI_WINDOW_MAX_RECALL_DROP,
            })
        if f1_drop_window > fixed.AMI_WINDOW_MAX_F1_DROP + 1.0e-12:
            violations.append({
                "gate": "ami_window_f1_drop",
                "window_id": item["window_id"],
                "actual": f1_drop_window,
                "allowed": fixed.AMI_WINDOW_MAX_F1_DROP,
            })
        if fpr_rise_window > fixed.AMI_WINDOW_MAX_FPR_RISE + 1.0e-12:
            violations.append({
                "gate": "ami_window_fpr_rise",
                "window_id": item["window_id"],
                "actual": fpr_rise_window,
                "allowed": fixed.AMI_WINDOW_MAX_FPR_RISE,
            })
        if item["window_id"] == low_activity_id:
            improvement = (
                float(base["false_positive_rate"])
                - float(cand["false_positive_rate"])
            )
            if improvement < fixed.AMI_W2_MIN_FPR_IMPROVEMENT - 1.0e-12:
                violations.append({
                    "gate": "ami_low_activity_fpr_improvement",
                    "window_id": low_activity_id,
                    "actual": improvement,
                    "required": fixed.AMI_W2_MIN_FPR_IMPROVEMENT,
                })
    return violations


def run(
    processor: Path,
    corpus_paths: list[Path],
    ami_lock: Path,
    output: Path,
) -> dict[str, Any]:
    if len(corpus_paths) != 3:
        raise ValueError("exactly three confirmation corpora are required")
    synthetic = [synthetic_authority(processor, path) for path in corpus_paths]
    observed_seeds = tuple(
        int(item["identity"]["generator_seed"]) for item in synthetic
    )
    if observed_seeds != CONFIRMATION_SEEDS:
        raise ValueError(
            f"confirmation seed contract drifted: {observed_seeds} != {CONFIRMATION_SEEDS}"
        )
    if len({item["identity"]["corpus_sha256"] for item in synthetic}) != 3:
        raise ValueError("confirmation corpus hashes must remain distinct")

    lock = json.loads(ami_lock.read_text(encoding="utf-8"))
    ami_eval.validate_lock(lock)
    if lock.get("dataset", {}).get("meeting") != "ES2004a":
        raise ValueError("confirmation real authority must remain ES2004a")
    confirmation_policy = lock.get("confirmation_policy", {})
    expected_policy = {
        "candidate_search": False,
        "fixed_strong_threshold": FIXED_STRONG_THRESHOLD,
        "fixed_weak_hold_frames": FIXED_WEAK_HOLD,
        "strong_hold_frames": 8,
        "local_decision_threshold": 0.45,
        "ns_decision_threshold": 0.35,
        "synthetic_seeds": list(CONFIRMATION_SEEDS),
        "real_authority_meeting": "ES2004a",
    }
    if confirmation_policy != expected_policy:
        raise ValueError("confirmation policy metadata drifted")

    ami = collect_ami_with_retries(processor, ami_lock)
    ami_baseline = policy.ami_report(ami, None, None)
    ami_candidate = policy.ami_report(
        ami, FIXED_STRONG_THRESHOLD, FIXED_WEAK_HOLD
    )
    ami_regressions = confirmation_ami_regressions(
        ami_baseline, ami_candidate
    )
    ami_score = fixed.ami_score(ami_baseline, ami_candidate)
    low_activity = min(
        ami_baseline["windows"], key=lambda item: float(item["activity_fraction"])
    )
    ami_confirmed = not ami_regressions and ami_score >= 0.0

    confirmed = all(item["confirmed"] for item in synthetic) and ami_confirmed
    result = {
        "schema_version": 1,
        "authority": "independent-vad-strong-weak-confirmation",
        "decision": (
            "CONFIRMED_RESEARCH_CANDIDATE"
            if confirmed
            else "REJECT_CONFIRMATION"
        ),
        "fixed_candidate": {
            "strong_threshold": FIXED_STRONG_THRESHOLD,
            "weak_hold_frames": FIXED_WEAK_HOLD,
            "strong_hold_frames": 8,
            "local_threshold": 0.45,
            "ns_threshold": 0.35,
            "candidate_search": False,
        },
        "synthetic_authorities": synthetic,
        "ami_authority": {
            "identity": {
                "meeting": ami["meeting"],
                "license": ami["license"],
                "transport_revision": ami["transport_revision"],
                "lock_sha256": ami["lock_sha256"],
            },
            "baseline": ami_baseline,
            "candidate": ami_candidate,
            "score": ami_score,
            "regression_violations": ami_regressions,
            "low_activity_window_id": low_activity["window_id"],
            "confirmed": ami_confirmed,
        },
        "scope": {
            "new_confirmation_seeds_only": list(CONFIRMATION_SEEDS),
            "new_real_meeting_only": "ES2004a",
            "old_1307_2307_3307_es2003a_not_promotion_authority": True,
            "shipping_source_unchanged": True,
            "candidate_search": False,
        },
        "promotion_boundary": (
            "confirmation may justify a separate release-bearing exact-source "
            "product candidate, but cannot modify shipping policy directly"
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def self_test() -> None:
    assert FIXED_STRONG_THRESHOLD == 0.50
    assert FIXED_WEAK_HOLD == 6
    assert CONFIRMATION_SEEDS == (4307, 5307, 6307)
    probabilities = [0.1, 0.4] + [0.1] * 8
    trace = policy.policy_trace(probabilities, 0.35, 0.50, 6)
    assert sum(row["vad_active"] for row in trace) == 6
    strong = policy.policy_trace([0.1, 0.6] + [0.1] * 9, 0.35, 0.50, 6)
    assert sum(row["vad_active"] for row in strong) == 8
    print("VAD strong/weak independent confirmation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--ami-lock", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.processor is None or args.ami_lock is None or args.output is None:
        parser.error("processor, AMI lock and output are required")
    result = run(args.processor, args.corpus, args.ami_lock, args.output)
    print(json.dumps({
        "decision": result["decision"],
        "synthetic": [
            {
                "seed": item["identity"]["generator_seed"],
                "confirmed": item["confirmed"],
                "score": item["score"],
                "violations": len(item["regression_violations"]),
            }
            for item in result["synthetic_authorities"]
        ],
        "ami": {
            "meeting": result["ami_authority"]["identity"]["meeting"],
            "confirmed": result["ami_authority"]["confirmed"],
            "score": result["ami_authority"]["score"],
            "violations": len(result["ami_authority"]["regression_violations"]),
            "low_activity_window_id": result["ami_authority"]["low_activity_window_id"],
        },
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
