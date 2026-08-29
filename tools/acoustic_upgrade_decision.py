#!/usr/bin/env python3
"""Decide whether advanced acoustic complexity is justified by real SKU evidence."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path


CHECKS = (
    ("far_end_erle_db", "min_far_end_erle_db", "min", "aec_residual"),
    ("aec_convergence_ms", "max_aec_convergence_ms", "max", "aec_sync"),
    ("double_talk_near_si_sdr_db", "min_double_talk_near_si_sdr_db", "min", "aec_double_talk"),
    ("noise_si_sdr_improvement_db", "min_noise_si_sdr_improvement_db", "min", "noise_frontend"),
    ("vad_f1", "min_vad_f1", "min", "vad_activity"),
)


def decide(policy: dict, report: dict) -> dict:
    if policy.get("shipping_approved") is not True:
        raise ValueError("algorithm escalation requires a shipping-approved SKU policy")
    acoustic = report.get("acoustic")
    if not isinstance(acoustic, dict):
        raise ValueError("acoustic report must contain an 'acoustic' object")
    if str(policy.get("sku", "")) == "":
        raise ValueError("policy.sku is required")

    failures = []
    for metric, threshold_key, direction, category in CHECKS:
        if metric not in acoustic or threshold_key not in policy:
            raise ValueError(f"missing {metric} or {threshold_key}")
        value = float(acoustic[metric])
        threshold = float(policy[threshold_key])
        passed = value >= threshold if direction == "min" else value <= threshold
        if not passed:
            failures.append({
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "direction": direction,
                "category": category,
            })

    total = int(acoustic.get("cases_total", 0))
    passed_cases = int(acoustic.get("cases_passed", 0))
    if total <= 0:
        raise ValueError("acoustic.cases_total must be positive real-corpus evidence")
    if passed_cases != total:
        failures.append({
            "metric": "cases_passed",
            "value": passed_cases,
            "threshold": total,
            "direction": "equal",
            "category": "corpus_case_failure",
        })

    categories = sorted({item["category"] for item in failures})
    decision = "KEEP_BASELINE" if not failures else "UPGRADE_ELIGIBLE"
    return {
        "schema_version": 1,
        "policy_id": policy.get("policy_id"),
        "sku": policy.get("sku"),
        "corpus_revision": acoustic.get("corpus_revision"),
        "decision": decision,
        "failed_categories": categories,
        "failures": failures,
        "rule": (
            "Advanced acoustic complexity is eligible only when real SKU evidence fails "
            "the approved shipping policy. KEEP_BASELINE means no complexity escalation is justified."
        ),
    }


def self_test() -> None:
    policy = {
        "policy_id": "shipping-v1",
        "sku": "sku-a",
        "shipping_approved": True,
        "min_far_end_erle_db": 15,
        "max_aec_convergence_ms": 1000,
        "min_double_talk_near_si_sdr_db": 5,
        "min_noise_si_sdr_improvement_db": 3,
        "min_vad_f1": 0.85,
    }
    report = {
        "acoustic": {
            "corpus_revision": "real-r1",
            "cases_total": 10,
            "cases_passed": 10,
            "far_end_erle_db": 20,
            "aec_convergence_ms": 500,
            "double_talk_near_si_sdr_db": 8,
            "noise_si_sdr_improvement_db": 4,
            "vad_f1": 0.9,
        }
    }
    assert decide(policy, report)["decision"] == "KEEP_BASELINE"
    report["acoustic"]["far_end_erle_db"] = 10
    failed = decide(policy, report)
    assert failed["decision"] == "UPGRADE_ELIGIBLE"
    assert "aec_residual" in failed["failed_categories"]
    with tempfile.TemporaryDirectory(prefix="ap-acoustic-upgrade-") as temporary:
        path = Path(temporary) / "decision.json"
        path.write_text(json.dumps(failed), encoding="utf-8")
        assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1
    print("acoustic upgrade decision self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--acoustic", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-upgrade-eligible",
        action="store_true",
        help="fail unless real evidence demonstrates at least one approved-policy acoustic failure",
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.policy or not args.acoustic or not args.output:
        parser.error("--policy, --acoustic and --output are required")
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    report = json.loads(args.acoustic.read_text(encoding="utf-8"))
    result = decide(policy, report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if args.require_upgrade_eligible and result["decision"] != "UPGRADE_ELIGIBLE":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
