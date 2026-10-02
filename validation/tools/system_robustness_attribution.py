#!/usr/bin/env python3
"""Create S001/S003 candidate-zero failure heatmap, attribution and replay index."""

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


def build(corpus: dict, report: dict) -> tuple[dict, dict, dict]:
    results = {item["case_id"]: item for item in report.get("cases", [])}
    rows: list[dict] = []
    by_family = defaultdict(lambda: Counter(total=0, failed=0))
    stage_counts: Counter = Counter()
    replay: list[dict] = []
    seed = int(corpus.get("generator", {}).get("seed", 0))

    for case in corpus["cases"]:
        result = results.get(case["case_id"], {})
        passed = bool(result.get("passed", report.get("validation_result") == "PASS"))
        stage = None if passed else observable_stage(case)
        dims = case.get("dimensions", {})
        family = str(dims.get("family", "unknown"))
        by_family[family]["total"] += 1
        if not passed:
            by_family[family]["failed"] += 1
            stage_counts[stage or "unknown"] += 1
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
                "telemetry": {"report_case_id": case["case_id"]},
                "expected_failure_signature": {
                    "violations": result.get("violations", []),
                },
                "shipping_output": {"report_case_id": case["case_id"]},
                "first_observable_stage": stage,
                "regression_assertion": {
                    "must_remain_replayable": True,
                    "candidate_authority": False,
                },
            })
        rows.append({
            "case_id": case["case_id"],
            "passed": passed,
            "dimensions": dims,
            "first_observable_stage": stage,
        })

    heat = {
        "schema_version": 1,
        "corpus_id": corpus["corpus_id"],
        "families": {key: dict(value) for key, value in sorted(by_family.items())},
        "first_observable_stage_failures": dict(stage_counts),
    }
    attribution = {
        "schema_version": 1,
        "stage_order": STAGES,
        "cases": rows,
        "rule": "unknown/null is retained when earliest bad stage is not proven",
    }
    index = {"schema_version": 1, "failures": replay}
    return heat, attribution, index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    heat, attribution, index = build(corpus, report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("failure-heatmap.json", heat),
        ("attribution.json", attribution),
        ("failure-replay-index.json", index),
    ]:
        (args.output_dir / name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps({
        "failures": len(index["failures"]),
        "families": len(heat["families"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
