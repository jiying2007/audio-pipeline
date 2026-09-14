#!/usr/bin/env python3
"""Mine validation failures into a deterministic research curriculum."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

CATEGORIES = (
    "double_talk",
    "motion",
    "far_field",
    "low_snr",
    "nonstationary_noise",
    "mic_fault",
    "clipping",
    "reverberation",
    "residual_echo",
    "vad_false_positive",
    "speech_recall",
    "other",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tokens(case: dict[str, Any]) -> str:
    fields: list[str] = []
    for key in ("case_id", "scenario", "name", "description", "scene", "category"):
        value = case.get(key)
        if value is not None:
            fields.append(str(value))
    metadata = case.get("metadata")
    if isinstance(metadata, dict):
        fields.extend(f"{key}={value}" for key, value in sorted(metadata.items()))
    metrics = case.get("metrics")
    if isinstance(metrics, dict):
        fields.extend(f"{key}={value}" for key, value in sorted(metrics.items()))
    violations = case.get("violations") or case.get("failures")
    if isinstance(violations, list):
        for item in violations:
            if isinstance(item, dict):
                fields.extend(f"{key}={value}" for key, value in sorted(item.items()))
            else:
                fields.append(str(item))
    return " ".join(fields).lower().replace("-", "_")


def case_failed(case: dict[str, Any]) -> bool:
    if case.get("passed") is False:
        return True
    status = str(case.get("status", case.get("result", ""))).upper()
    if status in {"FAIL", "FAILED", "ERROR", "REJECTED"}:
        return True
    for key in ("violations", "failures"):
        value = case.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def classify_case(case: dict[str, Any]) -> list[str]:
    text = _tokens(case)
    categories: list[str] = []

    def add(category: str, *needles: str) -> None:
        if any(needle in text for needle in needles) and category not in categories:
            categories.append(category)

    add("double_talk", "doubletalk", "double_talk", "near_far", "nearend_farend")
    add("motion", "movement", "moving", "motion", "tracking", "robot_turn", "rotation")
    add("far_field", "farfield", "far_field", "distance", "5m", "4m", "rear")
    add("low_snr", "low_snr", "critical_snr", "snr=-", "snr_", "snr=")
    add("nonstationary_noise", "nonstationary", "non_stationary", "transient_noise", "domestic_noise", "machine_noise")
    add("mic_fault", "mic_fault", "microphone_fault", "missing_mic", "hard_mic", "channel_fault", "mic_mismatch")
    add("clipping", "clip", "clipping", "saturation")
    add("reverberation", "reverb", "reverberation", "rir", "room")
    add("residual_echo", "residual_echo", "echo", "erle", "farend")
    add("vad_false_positive", "vad_false_positive", "false_positive", "vad_fp", "speech_absent")
    add("speech_recall", "speech_recall", "false_reject", "vad_recall", "near_si_sdr", "speech_preservation")
    return categories or ["other"]


def _report_failed_cases(report: dict[str, Any]) -> list[dict[str, Any]]:
    cases = report.get("cases")
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict) and case_failed(case)]


def mine_reports(paths: list[Path], max_weight: float = 3.0) -> dict[str, Any]:
    if not paths:
        raise ValueError("at least one report is required")
    if not math.isfinite(max_weight) or max_weight < 1.0 or max_weight > 10.0:
        raise ValueError("max_weight must be finite and in [1,10]")
    counts = Counter({name: 0 for name in CATEGORIES})
    report_bindings: list[dict[str, Any]] = []
    failed_cases = 0
    total_cases = 0
    for path in sorted(paths, key=lambda item: str(item)):
        report = json.loads(path.read_text(encoding="utf-8"))
        cases = report.get("cases")
        if not isinstance(cases, list):
            raise ValueError(f"report cases must be a list: {path}")
        failures = _report_failed_cases(report)
        total_cases += len(cases)
        failed_cases += len(failures)
        local = Counter()
        for case in failures:
            for category in classify_case(case):
                counts[category] += 1
                local[category] += 1
        report_bindings.append({
            "path": str(path),
            "sha256": sha256_file(path),
            "tier": report.get("tier"),
            "validation_result": report.get("validation_result"),
            "cases": len(cases),
            "failed_cases": len(failures),
            "failure_categories": dict(sorted(local.items())),
        })
    denom = max(1, failed_cases)
    maximum = max(counts.values()) if counts else 0
    curriculum = []
    for category in CATEGORIES:
        count = counts[category]
        share = count / denom
        normalized = count / maximum if maximum else 0.0
        weight = min(max_weight, 1.0 + (max_weight - 1.0) * normalized)
        curriculum.append({
            "category": category,
            "failure_count": count,
            "failure_share": share,
            "recommended_weight": weight,
        })
    curriculum.sort(key=lambda item: (-item["failure_count"], item["category"]))
    return {
        "schema_version": 1,
        "authority": "research-curriculum-only",
        "shipping_authority": False,
        "automatic_training_mutation": False,
        "reports": report_bindings,
        "total_cases": total_cases,
        "failed_cases": failed_cases,
        "curriculum": curriculum,
        "next_action": "review curriculum before changing any search/training distribution",
    }


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ap-failure-mining-") as temporary:
        root = Path(temporary)
        report = {
            "tier": "regression",
            "validation_result": "FAIL",
            "cases": [
                {"case_id": "moving-rear-critical-snr", "passed": False,
                 "metadata": {"movement": True, "distance": "5m", "snr": "critical"}},
                {"case_id": "doubletalk-erle", "status": "FAIL", "metrics": {"erle_db": 2.0}},
                {"case_id": "mic-fault-1", "violations": [{"gate": "hard_mic_fault"}]},
                {"case_id": "healthy", "passed": True},
            ],
        }
        path = root / "report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        result = mine_reports([path])
        assert result["failed_cases"] == 3
        by_category = {item["category"]: item for item in result["curriculum"]}
        assert by_category["motion"]["failure_count"] == 1
        assert by_category["far_field"]["failure_count"] == 1
        assert by_category["double_talk"]["failure_count"] == 1
        assert by_category["mic_fault"]["failure_count"] == 1
        assert result["shipping_authority"] is False
        assert result["automatic_training_mutation"] is False
    print("failure mining self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="*", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-weight", type=float, default=3.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.reports:
        parser.error("at least one report is required")
    result = mine_reports(args.reports, args.max_weight)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
