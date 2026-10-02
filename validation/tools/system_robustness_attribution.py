#!/usr/bin/env python3
"""Create candidate-zero heatmap, attribution and durable replay index.

Release/policy PASS is intentionally distinct from a diagnostic degradation
signature. S001 diagnostic-watch rules may trigger replay creation but have no
release, promotion or shipping authority.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

STAGES = ["capture", "BF", "SYNC", "AEC", "RES", "NS", "AGC", "VAD", "final"]


def observable_stage(case: dict) -> str | None:
    profile = case.get("processor_profile", "default")
    if profile == "bf-isolated":
        return "BF"
    if profile == "ns-isolated":
        return "NS"
    if profile == "agc-isolated":
        return "AGC"
    if profile == "vad-isolated":
        return "VAD"

    scenario = case.get("scenario", "")
    family = case.get("dimensions", {}).get("family")
    if family in {"capture", "clock_drift_proxy", "frame_timing"}:
        return "capture"
    if family == "mic_mismatch":
        return "BF"
    if family == "aec" or "aec-" in scenario:
        return "AEC"
    if family in {"snr", "robot_motion_noise", "room_proxy"}:
        return None
    return None


def load_watch(path: Path | None) -> dict:
    if path is None:
        return {"authority": "none", "rules": []}
    contract = json.loads(path.read_text(encoding="utf-8"))
    watch = contract.get("diagnostic_watch")
    if not isinstance(watch, dict):
        raise ValueError("diagnostic_watch missing from contract")
    if watch.get("authority") != "replay-trigger-only-not-release-acceptance-gate":
        raise ValueError("diagnostic watch must be replay-only")
    rules = watch.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("diagnostic watch rules must be non-empty")
    for rule in rules:
        if (
            not isinstance(rule, dict)
            or not isinstance(rule.get("id"), str)
            or not isinstance(rule.get("metric"), str)
            or rule.get("operator") not in {"lt", "gt"}
            or not isinstance(rule.get("limit"), (int, float))
        ):
            raise ValueError(f"invalid diagnostic watch rule: {rule!r}")
    return watch


def diagnostic_signatures(result: dict, watch: dict) -> list[dict]:
    metrics = result.get("metrics", {})
    signatures: list[dict] = []
    for rule in watch.get("rules", []):
        value = metrics.get(rule["metric"])
        if value is None:
            continue
        actual = float(value)
        limit = float(rule["limit"])
        triggered = actual < limit if rule["operator"] == "lt" else actual > limit
        if triggered:
            signatures.append({
                "id": rule["id"],
                "metric": rule["metric"],
                "operator": rule["operator"],
                "limit": limit,
                "actual": actual,
            })
    return signatures


def build(corpus: dict, report: dict, watch: dict) -> tuple[dict, dict, dict, dict]:
    results = {item["case_id"]: item for item in report.get("cases", [])}
    rows: list[dict] = []
    by_family = defaultdict(
        lambda: Counter(total=0, policy_failed=0, diagnostic_degraded=0, replayed=0)
    )
    stage_counts: Counter = Counter()
    signature_counts: Counter = Counter()
    replay: list[dict] = []
    seed = int(corpus.get("generator", {}).get("seed", 0))

    for case in corpus["cases"]:
        result = results.get(case["case_id"], {})
        policy_passed = bool(result.get("passed", report.get("validation_result") == "PASS"))
        signatures = diagnostic_signatures(result, watch)
        diagnostic_degraded = bool(signatures)
        replay_required = (not policy_passed) or diagnostic_degraded
        stage = observable_stage(case) if replay_required else None
        dims = case.get("dimensions", {})
        family = str(dims.get("family", "unknown"))

        by_family[family]["total"] += 1
        if not policy_passed:
            by_family[family]["policy_failed"] += 1
        if diagnostic_degraded:
            by_family[family]["diagnostic_degraded"] += 1
        if replay_required:
            by_family[family]["replayed"] += 1
            stage_counts[stage or "unknown"] += 1
            signature_counts.update(item["id"] for item in signatures)
            replay.append({
                "schema_version": 1,
                "failure_id": f"{corpus['corpus_id']}::{case['case_id']}",
                "source_identity": {
                    "corpus_id": corpus["corpus_id"],
                    "case_id": case["case_id"],
                    "source_revision": report.get("source_revision"),
                },
                "seed": seed,
                "perturbation": dims,
                "telemetry": {
                    "report_case_id": case["case_id"],
                    "metrics": result.get("metrics", {}),
                },
                "expected_failure_signature": {
                    "policy_violations": result.get("violations", []),
                    "diagnostic_signatures": signatures,
                    "policy_passed": policy_passed,
                },
                "shipping_output": {"report_case_id": case["case_id"]},
                "first_observable_stage": stage,
                "regression_assertion": {
                    "must_remain_replayable": True,
                    "candidate_authority": False,
                    "release_acceptance_authority": False,
                },
            })

        rows.append({
            "case_id": case["case_id"],
            "policy_passed": policy_passed,
            "diagnostic_degraded": diagnostic_degraded,
            "diagnostic_signatures": signatures,
            "dimensions": dims,
            "first_observable_stage": stage,
        })

    heat = {
        "schema_version": 1,
        "corpus_id": corpus["corpus_id"],
        "release_validation_result": report.get("validation_result"),
        "families": {key: dict(value) for key, value in sorted(by_family.items())},
        "first_observable_stage_replays": dict(stage_counts),
        "diagnostic_signature_counts": dict(signature_counts),
    }
    attribution = {
        "schema_version": 1,
        "stage_order": STAGES,
        "cases": rows,
        "rule": "unknown/null is retained when earliest bad stage is not proven",
    }
    index = {"schema_version": 1, "failures": replay}
    watch_report = {
        "schema_version": 1,
        "authority": watch.get("authority", "none"),
        "rules": watch.get("rules", []),
        "replay_count": len(replay),
        "diagnostic_degradation_count": sum(
            1 for item in rows if item["diagnostic_degraded"]
        ),
        "policy_failure_count": sum(
            1 for item in rows if not item["policy_passed"]
        ),
    }
    return heat, attribution, index, watch_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--watch-contract", type=Path)
    args = parser.parse_args()

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    watch = load_watch(args.watch_contract)
    heat, attribution, index, watch_report = build(corpus, report, watch)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("failure-heatmap.json", heat),
        ("attribution.json", attribution),
        ("failure-replay-index.json", index),
        ("diagnostic-watch.json", watch_report),
    ]:
        (args.output_dir / name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(json.dumps({
        "replays": len(index["failures"]),
        "diagnostic_degradations": watch_report["diagnostic_degradation_count"],
        "policy_failures": watch_report["policy_failure_count"],
        "families": len(heat["families"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
