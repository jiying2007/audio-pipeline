#!/usr/bin/env python3
"""Exact-source conformance gate for the shipping VAD strong/weak refresh policy.

The product processor is the authority for probability generation. This gate replays
only the confirmed final hangover policy from the emitted probability trace and
requires the product's emitted vad_active bit to match it frame-for-frame. Existing
per-case VAD gates are then evaluated on the product trace itself.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import run_validation_engine as engine
import stage_profile_support
import vad_operating_point_selector as selector

stage_profile_support.install(engine)

LOCAL_THRESHOLD = 0.45
NS_THRESHOLD = 0.35
STRONG_THRESHOLD = 0.50
STRONG_HOLD = 8
WEAK_HOLD = 6


def _probability(raw: float) -> float:
    value = float(raw)
    return value if math.isfinite(value) else 0.0


def threshold_for(profile: str) -> float:
    if profile == "ns-isolated":
        return NS_THRESHOLD
    if profile == "vad-isolated":
        return LOCAL_THRESHOLD
    raise ValueError(f"unsupported VAD profile: {profile}")


def expected_trace(probabilities: list[float], decision_threshold: float) -> list[int]:
    if not 0.0 < decision_threshold < STRONG_THRESHOLD < 1.0:
        raise ValueError("invalid shipping VAD threshold ordering")
    hangover = 0
    active: list[int] = []
    for raw in probabilities:
        probability = _probability(raw)
        if probability >= STRONG_THRESHOLD:
            hangover = STRONG_HOLD
        elif probability > decision_threshold:
            if hangover < WEAK_HOLD:
                hangover = WEAK_HOLD
        elif hangover:
            hangover -= 1
        active.append(1 if hangover > 0 else 0)
    return active


def _metrics(labels: list[int], active: list[int]) -> dict[str, float | None]:
    stats = engine.vad_stats(labels, [{"vad_active": value} for value in active])
    return {
        "vad_f1": stats["f1"],
        "vad_precision": stats["precision"],
        "vad_recall": stats["recall"],
        "vad_false_positive_rate": stats["false_positive_rate"],
        "vad_false_negative_rate": stats["false_negative_rate"],
    }


def evaluate_case(processor: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    profile = str(case.get("processor_profile", ""))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if labels_path is None:
        raise ValueError(f"missing VAD labels: {case['case_id']}")
    labels = engine.load_labels(labels_path)
    with tempfile.TemporaryDirectory(prefix="ap-vad-shipping-conformance-") as temporary:
        _, trace, _ = engine.invoke(processor, case, corpus_path, Path(temporary))
    probabilities = [float(row.get("vad_probability", 0.0)) for row in trace]
    actual = [int(row.get("vad_active", 0)) for row in trace]
    count = min(len(labels), len(probabilities), len(actual))
    if count == 0:
        raise ValueError(f"empty VAD trace: {case['case_id']}")
    labels = labels[:count]
    probabilities = probabilities[:count]
    actual = actual[:count]
    expected = expected_trace(probabilities, threshold_for(profile))
    mismatch_indices = [index for index, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1]]
    metrics = _metrics(labels, actual)
    violations = engine.threshold_violations(metrics, selector.vad_expected(case))
    return {
        "case_id": case["case_id"],
        "scenario": case.get("scenario"),
        "processor_profile": profile,
        "frames": count,
        "active_mismatches": len(mismatch_indices),
        "first_mismatch_frame": mismatch_indices[0] if mismatch_indices else None,
        "metrics": metrics,
        "violations": violations,
        "passed": not mismatch_indices and not violations,
    }


def evaluate_corpus(processor: Path, corpus_path: Path) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = []
    for case in corpus.get("cases", []):
        if case.get("processor_profile") in {"vad-isolated", "ns-isolated"} and case.get("vad_labels"):
            cases.append(evaluate_case(processor, corpus_path, case))
    if not cases:
        raise ValueError(f"no labeled VAD cases: {corpus_path}")
    profiles = {item["processor_profile"] for item in cases}
    if profiles != {"vad-isolated", "ns-isolated"}:
        raise ValueError(f"both VAD profiles required: {sorted(profiles)}")
    return {
        "corpus_id": corpus.get("corpus_id"),
        "generator_seed": corpus.get("generator", {}).get("seed"),
        "corpus_sha256": engine.sha256_file(corpus_path),
        "cases": cases,
        "total_active_mismatches": sum(item["active_mismatches"] for item in cases),
        "validation_result": "PASS" if all(item["passed"] for item in cases) else "FAIL",
    }


def self_test() -> None:
    probabilities = [0.0, 0.46, 0.0, 0.0, 0.51, 0.0, 0.0]
    trace = expected_trace(probabilities, LOCAL_THRESHOLD)
    assert trace == [0, 1, 1, 1, 1, 1, 1]
    weak = expected_trace([0.46] + [0.0] * 7, LOCAL_THRESHOLD)
    assert weak == [1, 1, 1, 1, 1, 1, 0, 0]
    strong = expected_trace([0.50] + [0.0] * 9, LOCAL_THRESHOLD)
    assert strong == [1, 1, 1, 1, 1, 1, 1, 1, 0, 0]
    print("VAD shipping policy conformance self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--corpus", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.processor is None or not args.corpus or args.output is None:
        parser.error("--processor, at least one --corpus, and --output are required")
    partitions = [evaluate_corpus(args.processor, path) for path in args.corpus]
    result = {
        "schema_version": 1,
        "authority": "shipping-vad-policy-conformance",
        "policy": {
            "local_threshold": LOCAL_THRESHOLD,
            "ns_threshold": NS_THRESHOLD,
            "strong_threshold": STRONG_THRESHOLD,
            "strong_hold_frames": STRONG_HOLD,
            "weak_hold_frames": WEAK_HOLD,
            "weak_refresh_never_truncates_strong_hold": True,
        },
        "partitions": partitions,
        "total_active_mismatches": sum(item["total_active_mismatches"] for item in partitions),
        "validation_result": "PASS" if all(item["validation_result"] == "PASS" for item in partitions) else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "validation_result": result["validation_result"],
        "total_active_mismatches": result["total_active_mismatches"],
        "seeds": [item["generator_seed"] for item in partitions],
    }, sort_keys=True))
    return 0 if result["validation_result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
