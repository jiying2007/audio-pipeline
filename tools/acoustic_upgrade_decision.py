#!/usr/bin/env python3
"""Compare acoustic research evidence against declared study thresholds."""

from __future__ import annotations

import argparse
import json
import math
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
    if policy.get("scope") != "technical-research":
        raise ValueError("explicit technical-research policy scope is required")
    if "shipping_approved" in policy or "sku" in policy:
        raise ValueError("obsolete product-policy fields are not research evidence")
    acoustic = report.get("acoustic")
    if not isinstance(acoustic, dict):
        raise ValueError("acoustic report must contain an 'acoustic' object")
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"].strip():
        raise ValueError("nonempty policy_id is required")
    if not isinstance(policy.get("study_id"), str) or not policy["study_id"].strip():
        raise ValueError("nonempty study_id is required")
    if not isinstance(acoustic.get("corpus_revision"), str) or not acoustic["corpus_revision"].strip():
        raise ValueError("acoustic.corpus_revision is required")

    failures = []
    for metric, threshold_key, direction, category in CHECKS:
        if metric not in acoustic or threshold_key not in policy:
            raise ValueError(f"missing {metric} or {threshold_key}")
        value = float(acoustic[metric])
        threshold = float(policy[threshold_key])
        if not math.isfinite(value) or not math.isfinite(threshold):
            raise ValueError(f"non-finite acoustic metric or threshold: {metric}")
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
        raise ValueError("acoustic.cases_total must be positive recorded research evidence")
    if passed_cases < 0 or passed_cases > total:
        raise ValueError("acoustic.cases_passed must be between zero and cases_total")
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
        "schema_version": 2,
        "policy_id": policy["policy_id"],
        "study_id": policy["study_id"],
        "scope": "technical-research",
        "corpus_revision": acoustic.get("corpus_revision"),
        "decision": decision,
        "failed_categories": categories,
        "failures": failures,
        "rule": (
            "A research upgrade is eligible for further controlled evaluation when "
            "recorded acoustic evidence misses a declared study threshold. "
            "KEEP_BASELINE means no threshold-based escalation is justified. "
            "Neither result certifies a product, a model or physical hardware."
        ),
    }


def self_test() -> None:
    policy = {
        "policy_id": "research-threshold-v1",
        "study_id": "aec-research-control",
        "scope": "technical-research",
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
    assert failed["scope"] == "technical-research" and failed["schema_version"] == 2
    for obsolete in ({"shipping_approved": True}, {"sku": "sku-a"}):
        try:
            decide({**policy, **obsolete}, report)
        except ValueError:
            pass
        else:
            raise AssertionError("obsolete commercial-policy input accepted")
    for invalid_scope in ("product", None):
        try:
            decide({**policy, "scope": invalid_scope}, report)
        except ValueError:
            pass
        else:
            raise AssertionError("non-research study scope accepted")
    bad_report = {"acoustic": {**report["acoustic"], "vad_f1": float("nan")}}
    try:
        decide(policy, bad_report)
    except ValueError:
        pass
    else:
        raise AssertionError("non-finite metric was accepted")
    with tempfile.TemporaryDirectory(prefix="ap-acoustic-upgrade-") as temporary:
        path = Path(temporary) / "decision.json"
        path.write_text(json.dumps(failed), encoding="utf-8")
        assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 2
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
        help="fail unless recorded evidence misses at least one study threshold",
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
