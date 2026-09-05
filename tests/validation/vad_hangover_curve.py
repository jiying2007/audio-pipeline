#!/usr/bin/env python3
"""Emit non-authoritative fixed-hangover response curves across all holdouts.

This diagnostic never selects a candidate. It reuses the same probability traces
and frozen AMI microset as vad_hangover_counterfactual.py so follow-up policy work
can see why fixed 2/4/6-frame holds fail or succeed on each partition.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import vad_hangover_counterfactual as hangover
import vad_operating_point_selector as selector


def synthetic_point(partition: dict[str, Any], baseline: dict[str, Any], frames: int) -> dict[str, Any]:
    report = hangover.evaluate_synthetic(partition, frames)
    failed = [
        {
            "case_id": item["case_id"],
            "scenario": item["scenario"],
            "processor_profile": item["processor_profile"],
            "violations": item["violations"],
        }
        for item in report["cases"]
        if not item["passed"]
    ]
    return {
        "hangover_frames": frames,
        "validation_result": report["validation_result"],
        "summary": report["summary"],
        "score_vs_8": hangover.synthetic_score(baseline, report),
        "regression_violations_vs_8": hangover.synthetic_regressions(baseline, report),
        "failed_cases": failed,
    }


def ami_point(ami: dict[str, Any], baseline: dict[str, Any], frames: int) -> dict[str, Any]:
    report = hangover.ami_report(ami, frames)
    w2 = next(item for item in report["windows"] if item["window_id"] == "ES2003a-w2")
    return {
        "hangover_frames": frames,
        "aggregate": report["aggregate"],
        "low_activity_w2": w2,
        "score_vs_8": hangover.ami_score(baseline, report),
        "regression_violations_vs_8": (
            [] if frames == hangover.BASELINE_HANGOVER
            else hangover.ami_regressions(baseline, report)
        ),
    }


def run(processor: Path, development_path: Path, validation_path: Path,
        shadow_path: Path, ami_lock: Path, output: Path) -> dict[str, Any]:
    partitions = {
        "development": selector.collect_partition(processor, development_path),
        "validation": selector.collect_partition(processor, validation_path),
        "shadow": selector.collect_partition(processor, shadow_path),
    }
    synthetic: dict[str, Any] = {}
    for role, partition in partitions.items():
        baseline = hangover.evaluate_synthetic(partition, hangover.BASELINE_HANGOVER)
        synthetic[role] = {
            "identity": hangover.partition_identity(partition),
            "points": [
                synthetic_point(partition, baseline, frames)
                for frames in hangover.HANGOVER_CANDIDATES
            ],
        }

    ami = hangover.collect_ami(processor, ami_lock)
    ami_baseline = hangover.ami_report(ami, hangover.BASELINE_HANGOVER)
    result = {
        "schema_version": 1,
        "authority": "diagnostic-only-vad-hangover-response-curve",
        "scope": {
            "candidate_selection": False,
            "local_threshold": hangover.LOCAL_THRESHOLD,
            "ns_threshold": hangover.NS_THRESHOLD,
            "hangover_candidates": list(hangover.HANGOVER_CANDIDATES),
            "baseline_hangover": hangover.BASELINE_HANGOVER,
        },
        "synthetic": synthetic,
        "ami": {
            "identity": {
                "meeting": ami["meeting"],
                "license": ami["license"],
                "transport_revision": ami["transport_revision"],
                "lock_sha256": ami["lock_sha256"],
            },
            "points": [
                ami_point(ami, ami_baseline, frames)
                for frames in hangover.HANGOVER_CANDIDATES
            ],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    assert tuple(hangover.HANGOVER_CANDIDATES) == (2, 4, 6, 8)
    assert hangover.BASELINE_HANGOVER == 8
    assert hangover.LOCAL_THRESHOLD == 0.45
    assert hangover.NS_THRESHOLD == 0.35
    print("VAD hangover response-curve self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--ami-lock", type=Path, default=Path("tests/validation/data/ami_vad_microset.lock.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("processor", "development_corpus", "validation_corpus", "shadow_corpus", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    result = run(
        args.processor.resolve(),
        args.development_corpus.resolve(),
        args.validation_corpus.resolve(),
        args.shadow_corpus.resolve(),
        args.ami_lock.resolve(),
        args.output.resolve(),
    )
    compact = {
        "synthetic": {
            role: [
                {
                    "hangover_frames": point["hangover_frames"],
                    "score_vs_8": point["score_vs_8"],
                    "validation_result": point["validation_result"],
                    "failed_cases": [item["case_id"] for item in point["failed_cases"]],
                }
                for point in payload["points"]
            ]
            for role, payload in result["synthetic"].items()
        },
        "ami": [
            {
                "hangover_frames": point["hangover_frames"],
                "score_vs_8": point["score_vs_8"],
                "recall": point["aggregate"]["recall"],
                "f1": point["aggregate"]["f1"],
                "fpr": point["aggregate"]["false_positive_rate"],
                "w2_fpr": point["low_activity_w2"]["metrics"]["false_positive_rate"],
            }
            for point in result["ami"]["points"]
        ],
    }
    print(json.dumps(compact, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
