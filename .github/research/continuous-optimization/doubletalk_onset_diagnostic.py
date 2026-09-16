#!/usr/bin/env python3
"""Development-only double-talk onset/control-chain diagnostic.

This tool consumes deterministic regression corpora plus the existing offline
processor metrics JSONL. It does not tune thresholds or select a candidate.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def load_labels(path: Path) -> list[int]:
    labels: list[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = int(line)
        if value not in (0, 1):
            raise ValueError(f"{path}: labels must be 0/1")
        labels.append(value)
    return labels


def active_segments(labels: list[int]) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(labels + [0]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            segments.append((start, index))
            start = None
    return segments


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def analyze_metrics(labels: list[int], metrics: list[dict[str, Any]], window_frames: int = 10) -> list[dict[str, Any]]:
    if len(metrics) < len(labels):
        raise ValueError(f"metrics shorter than labels: {len(metrics)} < {len(labels)}")
    out: list[dict[str, Any]] = []
    for start, end in active_segments(labels):
        active_metrics = metrics[start:end]
        first_dt: int | None = None
        for offset, row in enumerate(active_metrics):
            if int(row.get("double_talk_active", 0)) != 0:
                first_dt = start + offset
                break
        first = active_metrics[:window_frames]
        out.append({
            "near_onset_frame": start,
            "near_end_frame_exclusive": end,
            "first_double_talk_frame": first_dt,
            "double_talk_onset_delay_frames": None if first_dt is None else first_dt - start,
            "double_talk_detected_during_segment": first_dt is not None,
            "double_talk_active_fraction_first_window": (
                sum(1 for row in first if int(row.get("double_talk_active", 0)) != 0) / len(first)
                if first else None
            ),
            "far_end_active_fraction_first_window": (
                sum(1 for row in first if int(row.get("far_end_active", 0)) != 0) / len(first)
                if first else None
            ),
            "aec_converged_fraction_first_window": (
                sum(1 for row in first if int(row.get("aec_converged", 0)) != 0) / len(first)
                if first else None
            ),
            "vad_probability_mean_first_window": mean(
                [float(row["vad_probability"]) for row in first if row.get("vad_probability") is not None]
            ),
            "vad_active_fraction_first_window": (
                sum(1 for row in first if int(row.get("vad_active", 0)) != 0) / len(first)
                if first else None
            ),
        })
    return out


def run_profile(
    processor: Path,
    corpus_root: Path,
    case: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[int]]:
    mic = corpus_root / str(case["mic_audio"])
    render_value = case.get("render_audio")
    labels_value = case.get("vad_labels")
    if not render_value or not labels_value:
        raise ValueError(f"{case.get('case_id')}: render_audio and vad_labels are required")
    render = corpus_root / str(render_value)
    labels_path = corpus_root / str(labels_value)
    labels = load_labels(labels_path)

    with tempfile.TemporaryDirectory(prefix="ap-dt-onset-") as tmp:
        tmpdir = Path(tmp)
        output = tmpdir / "out.pcm"
        metrics_path = tmpdir / "metrics.jsonl"
        cmd = [
            str(processor),
            "--sample-rate", str(int(case["sample_rate_hz"])),
            "--mic-channels", str(int(case["mic_channels"])),
            "--metrics-jsonl", str(metrics_path),
            "--aec-mu", str(float(profile["aec_mu"])),
            "--ns-floor", str(float(profile["ns_floor"])),
            "--agc-target-dbfs", str(float(profile["agc_target_dbfs"])),
            "--limiter-dbfs", str(float(profile["limiter_dbfs"])),
            str(mic), str(render), str(output),
        ]
        subprocess.run(cmd, check=True)
        metrics = [
            json.loads(line)
            for line in metrics_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return metrics, labels


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("status") != "DIAGNOSTIC_ONLY":
        raise ValueError("manifest status must be DIAGNOSTIC_ONLY")
    if manifest.get("candidate_budget") != 0:
        raise ValueError("diagnostic candidate_budget must be zero")
    authority = manifest.get("output_authority", {})
    if authority.get("research_diagnostic_only") is not True:
        raise ValueError("research_diagnostic_only authority missing")
    for forbidden in ("shipping", "hil", "product_certification", "candidate_selection"):
        if authority.get(forbidden) is not False:
            raise ValueError(f"{forbidden} authority must remain false")
    profiles = manifest.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != {"baseline", "high_mu_probe"}:
        raise ValueError("manifest must define exactly baseline and high_mu_probe")
    base = profiles["baseline"]
    probe = profiles["high_mu_probe"]
    for key in ("ns_floor", "agc_target_dbfs", "limiter_dbfs"):
        if float(base[key]) != float(probe[key]):
            raise ValueError(f"profiles may differ only in aec_mu; {key} differs")
    if float(probe["aec_mu"]) <= float(base["aec_mu"]):
        raise ValueError("high_mu_probe must have larger aec_mu")
    case_ids = manifest.get("case_ids")
    if not isinstance(case_ids, list) or len(case_ids) != 4 or len(case_ids) != len(set(case_ids)):
        raise ValueError("manifest must define four unique double-talk case ids")


def self_test() -> None:
    labels = [0, 0, 1, 1, 1, 1, 0]
    metrics = [
        {"double_talk_active": 0, "far_end_active": 1, "aec_converged": 1, "vad_probability": 0.0, "vad_active": 0},
        {"double_talk_active": 0, "far_end_active": 1, "aec_converged": 1, "vad_probability": 0.0, "vad_active": 0},
        {"double_talk_active": 0, "far_end_active": 1, "aec_converged": 1, "vad_probability": 0.2, "vad_active": 0},
        {"double_talk_active": 1, "far_end_active": 1, "aec_converged": 1, "vad_probability": 0.8, "vad_active": 1},
        {"double_talk_active": 1, "far_end_active": 1, "aec_converged": 1, "vad_probability": 0.9, "vad_active": 1},
        {"double_talk_active": 1, "far_end_active": 1, "aec_converged": 1, "vad_probability": 0.9, "vad_active": 1},
        {"double_talk_active": 0, "far_end_active": 1, "aec_converged": 1, "vad_probability": 0.0, "vad_active": 0},
    ]
    result = analyze_metrics(labels, metrics, window_frames=3)
    assert len(result) == 1
    assert result[0]["near_onset_frame"] == 2
    assert result[0]["double_talk_onset_delay_frames"] == 1
    assert math.isclose(result[0]["double_talk_active_fraction_first_window"], 2.0 / 3.0)
    print("double-talk onset diagnostic self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--corpus", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.processor or not args.manifest or not args.corpus or not args.output:
        parser.error("--processor, --manifest, at least one --corpus, and --output are required")

    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    case_ids = set(str(item) for item in manifest["case_ids"])
    profiles = manifest["profiles"]
    evidence: list[dict[str, Any]] = []

    for corpus_path in args.corpus:
        corpus_path = corpus_path.resolve()
        corpus = load_json(corpus_path)
        corpus_root = corpus_path.parent
        cases = {
            str(case.get("case_id")): case
            for case in corpus.get("cases", [])
            if isinstance(case, dict) and case.get("case_id") in case_ids
        }
        missing = sorted(case_ids - set(cases))
        if missing:
            raise ValueError(f"{corpus_path}: missing diagnostic cases: {missing}")
        for case_id in sorted(case_ids):
            case = cases[case_id]
            for profile_name, profile in profiles.items():
                metrics, labels = run_profile(args.processor.resolve(), corpus_root, case, profile)
                evidence.append({
                    "corpus": str(corpus_path),
                    "case_id": case_id,
                    "scenario": case.get("scenario"),
                    "profile": profile_name,
                    "tuning": profile,
                    "segments": analyze_metrics(labels, metrics),
                })

    result = {
        "schema_version": 1,
        "authority": "research-diagnostic-only",
        "investigation_id": manifest["investigation_id"],
        "candidate_budget": 0,
        "source_evidence": manifest["source_evidence"],
        "records": evidence,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "investigation_id": result["investigation_id"],
        "records": len(evidence),
        "candidate_budget": 0,
        "authority": result["authority"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
