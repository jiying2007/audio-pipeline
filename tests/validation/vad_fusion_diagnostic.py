#!/usr/bin/env python3
"""Causal-style VAD fusion diagnostics on the pinned AMI research windows.

The diagnostic first proves that the internal probe's fused trace matches the
shipping ns-isolated processor trace. It then compares independent raw-local,
NS-local and NS+upstream VAD states and attributes false-positive active frames
to counterfactual layers. Research-only; it never mutates product tuning.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import run_validation_engine as engine
import discover_ami_vad_microset as discovery
import ami_vad_microset_eval as ami_eval

SHIPPING_THRESHOLD = 0.35
PROBABILITY_MATCH_TOLERANCE = 2.0e-6


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def percentile(values: Iterable[float], q: float) -> float | None:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def distribution(values: list[float]) -> dict[str, float | None]:
    return {
        "p10": percentile(values, 0.10),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "mean": (sum(values) / len(values)) if values else None,
        "above_shipping_threshold_fraction": (
            sum(1 for value in values if value > SHIPPING_THRESHOLD) / len(values)
            if values else None
        ),
    }


def run_pipeline(processor: Path, pcm_path: Path, directory: Path) -> list[dict[str, Any]]:
    metrics = directory / "pipeline.jsonl"
    output = directory / "pipeline-out.pcm"
    subprocess.run([
        str(processor),
        "--sample-rate", "16000",
        "--mic-channels", "1",
        "--metrics-jsonl", str(metrics),
        "--capture-profile", "ns-isolated",
        "--capture-only",
        str(pcm_path),
        str(output),
    ], check=True)
    return read_jsonl(metrics)


def run_probe(probe: Path, pcm_path: Path, directory: Path) -> list[dict[str, Any]]:
    trace = directory / "probe.jsonl"
    subprocess.run([str(probe), str(pcm_path), str(trace)], check=True)
    return read_jsonl(trace)


def verify_probe(pipeline: list[dict[str, Any]], probe: list[dict[str, Any]]) -> dict[str, Any]:
    count = min(len(pipeline), len(probe))
    if count == 0 or len(pipeline) != len(probe):
        raise ValueError(f"pipeline/probe frame count mismatch: {len(pipeline)} != {len(probe)}")
    max_probability_error = 0.0
    active_mismatches = 0
    for index in range(count):
        expected = float(pipeline[index].get("vad_probability", 0.0))
        actual = float(probe[index]["fused_probability"])
        max_probability_error = max(max_probability_error, abs(expected - actual))
        if int(pipeline[index].get("vad_active", 0)) != int(probe[index]["fused_active"]):
            active_mismatches += 1
    if max_probability_error > PROBABILITY_MATCH_TOLERANCE or active_mismatches:
        raise ValueError(
            f"probe does not reproduce product fused VAD: max_probability_error={max_probability_error} "
            f"active_mismatches={active_mismatches}"
        )
    return {
        "frames": count,
        "max_probability_error": max_probability_error,
        "active_mismatches": active_mismatches,
        "tolerance": PROBABILITY_MATCH_TOLERANCE,
    }


def classify_false_positive(row: dict[str, Any]) -> str:
    raw_inst = float(row["raw_probability"]) > SHIPPING_THRESHOLD
    ns_local_inst = float(row["ns_local_probability"]) > SHIPPING_THRESHOLD
    fused_inst = float(row["fused_probability"]) > SHIPPING_THRESHOLD
    fused_active = bool(int(row["fused_active"]))
    if not fused_active:
        return "not_active"
    if not fused_inst:
        return "hangover_only"
    if not ns_local_inst:
        return "upstream_fusion_added"
    if not raw_inst:
        return "ns_processing_added"
    return "raw_local_already_high"


def analyze_window(labels: list[int], probe: list[dict[str, Any]]) -> dict[str, Any]:
    count = min(len(labels), len(probe))
    labels = labels[:count]
    probe = probe[:count]
    speech_indices = [index for index, label in enumerate(labels) if label]
    noise_indices = [index for index, label in enumerate(labels) if not label]
    fields = (
        "ns_speech_probability",
        "raw_probability",
        "ns_local_probability",
        "fused_probability",
    )
    distributions = {}
    for field in fields:
        distributions[field] = {
            "speech": distribution([float(probe[index][field]) for index in speech_indices]),
            "noise": distribution([float(probe[index][field]) for index in noise_indices]),
        }

    counter = Counter()
    for index in noise_indices:
        category = classify_false_positive(probe[index])
        if category != "not_active":
            counter[category] += 1
    active_noise = sum(counter.values())
    noise_frames = len(noise_indices)
    attribution = {
        name: {
            "frames": counter.get(name, 0),
            "fraction_of_noise_frames": counter.get(name, 0) / noise_frames if noise_frames else 0.0,
            "fraction_of_false_positive_active_frames": counter.get(name, 0) / active_noise if active_noise else 0.0,
        }
        for name in (
            "raw_local_already_high",
            "ns_processing_added",
            "upstream_fusion_added",
            "hangover_only",
        )
    }

    instantaneous = {}
    for field in ("raw_probability", "ns_local_probability", "fused_probability"):
        instantaneous[field] = {
            "speech_admission_fraction": (
                sum(1 for index in speech_indices if float(probe[index][field]) > SHIPPING_THRESHOLD) / len(speech_indices)
                if speech_indices else 0.0
            ),
            "noise_admission_fraction": (
                sum(1 for index in noise_indices if float(probe[index][field]) > SHIPPING_THRESHOLD) / len(noise_indices)
                if noise_indices else 0.0
            ),
        }
    fused_active_noise_fraction = (
        sum(1 for index in noise_indices if int(probe[index]["fused_active"])) / noise_frames
        if noise_frames else 0.0
    )
    fused_active_speech_fraction = (
        sum(1 for index in speech_indices if int(probe[index]["fused_active"])) / len(speech_indices)
        if speech_indices else 0.0
    )
    return {
        "frames": count,
        "speech_frames": len(speech_indices),
        "noise_frames": noise_frames,
        "distributions": distributions,
        "instantaneous_admission": instantaneous,
        "fused_active": {
            "speech_fraction": fused_active_speech_fraction,
            "noise_fraction": fused_active_noise_fraction,
        },
        "false_positive_attribution": attribution,
    }


def merge_counts(windows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = (
        "raw_local_already_high",
        "ns_processing_added",
        "upstream_fusion_added",
        "hangover_only",
    )
    total_noise = sum(int(item["analysis"]["noise_frames"]) for item in windows)
    counts = {
        category: sum(
            int(item["analysis"]["false_positive_attribution"][category]["frames"])
            for item in windows
        )
        for category in categories
    }
    total_fp = sum(counts.values())
    return {
        "noise_frames": total_noise,
        "false_positive_active_frames": total_fp,
        "categories": {
            category: {
                "frames": counts[category],
                "fraction_of_noise_frames": counts[category] / total_noise if total_noise else 0.0,
                "fraction_of_false_positive_active_frames": counts[category] / total_fp if total_fp else 0.0,
            }
            for category in categories
        },
    }


def diagnose(processor: Path, probe: Path, lock_path: Path, output_path: Path) -> dict[str, Any]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    ami_eval.validate_lock(lock)
    intervals, _ = ami_eval.load_annotations(lock)
    audio_url = discovery.hf_resolve_url(str(lock["audio"]["path"]))
    windows = []

    with tempfile.TemporaryDirectory(prefix="ap-ami-fusion-") as temporary:
        root = Path(temporary)
        for window in lock["windows"]:
            pcm = ami_eval.request_exact_range(audio_url, int(window["start_byte"]), int(window["end_byte"]))
            digest = ami_eval.sha256_bytes(pcm)
            if digest != window["sha256"]:
                raise ValueError(f"window hash drifted: {window['window_id']}")
            pcm_path = root / f"{window['window_id']}.pcm"
            pcm_path.write_bytes(pcm)
            labels = ami_eval.labels_for_window(intervals, float(window["start_s"]), float(window["end_s"]))
            work = root / f"work-{window['window_id']}"
            work.mkdir()
            pipeline_trace = run_pipeline(processor, pcm_path, work)
            probe_trace = run_probe(probe, pcm_path, work)
            fidelity = verify_probe(pipeline_trace, probe_trace)
            windows.append({
                "window_id": window["window_id"],
                "start_s": window["start_s"],
                "activity_fraction": sum(labels) / len(labels),
                "audio_sha256": digest,
                "probe_fidelity": fidelity,
                "analysis": analyze_window(labels, probe_trace),
            })

    aggregate = merge_counts(windows)
    w2 = next(item for item in windows if item["window_id"] == "ES2003a-w2")
    w2_categories = w2["analysis"]["false_positive_attribution"]
    dominant = max(
        w2_categories,
        key=lambda name: float(w2_categories[name]["fraction_of_false_positive_active_frames"]),
    )
    result = {
        "schema_version": 1,
        "authority": "research-vad-fusion-causal-diagnostic",
        "source": {
            "meeting": lock["dataset"]["meeting"],
            "lock_sha256": engine.sha256_file(lock_path),
            "processor_sha256": engine.sha256_file(processor),
            "probe_sha256": engine.sha256_file(probe),
        },
        "shipping_contract": {
            "sample_rate_hz": 16000,
            "frame_samples": 160,
            "quality": "FULL",
            "ns_floor": 0.12,
            "decision_threshold": SHIPPING_THRESHOLD,
            "hangover_frames": 8,
        },
        "windows": windows,
        "aggregate_false_positive_attribution": aggregate,
        "low_activity_window": {
            "window_id": "ES2003a-w2",
            "dominant_false_positive_category": dominant,
            "dominant_fraction": w2_categories[dominant]["fraction_of_false_positive_active_frames"],
        },
        "interpretation_boundary": (
            "counterfactual decomposition across independent VAD states; categories isolate software-path increments "
            "but do not claim dedicated perceptual SAD ground-truth causality"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    values = [0.1, 0.2, 0.3, 0.4]
    assert abs(float(percentile(values, 0.5)) - 0.25) < 1.0e-9
    row = {
        "raw_probability": 0.2,
        "ns_local_probability": 0.25,
        "fused_probability": 0.4,
        "fused_active": 1,
    }
    assert classify_false_positive(row) == "upstream_fusion_added"
    row["fused_probability"] = 0.2
    assert classify_false_positive(row) == "hangover_only"
    print("VAD fusion diagnostic self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--lock", type=Path, default=Path("tests/validation/data/ami_vad_microset.lock.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.processor is None or args.probe is None or args.output is None:
        parser.error("--processor, --probe and --output are required")
    result = diagnose(
        args.processor.resolve(),
        args.probe.resolve(),
        args.lock.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "low_activity_window": result["low_activity_window"],
        "aggregate_false_positive_attribution": result["aggregate_false_positive_attribution"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
