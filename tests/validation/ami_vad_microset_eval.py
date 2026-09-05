#!/usr/bin/env python3
"""Evaluate shipping vs research NS-assisted VAD thresholds on pinned AMI windows.

Research-only: labels come from external manual transcription segment timing,
not from this VAD, energy thresholding, or a dedicated audited SAD campaign.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

import run_validation_engine as engine
import stage_profile_support
import discover_ami_vad_microset as discovery

stage_profile_support.install(engine)

USER_AGENT = "audio-pipeline-ami-vad-eval/1"
MAX_XML_BYTES = 2 * 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_exact_range(url: str, start: int, end: int) -> bytes:
    expected = end - start + 1
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        status = int(getattr(response, "status", response.getcode()))
        content_range = response.headers.get("Content-Range", "")
        data = response.read(expected + 1)
    if status != 206:
        raise ValueError(f"AMI range request must return 206, got {status}")
    if content_range != f"bytes {start}-{end}/{start + (0 if False else 1)}" and not content_range.startswith(
        f"bytes {start}-{end}/"
    ):
        raise ValueError(f"unexpected Content-Range: {content_range}")
    if len(data) != expected:
        raise ValueError(f"AMI range length mismatch: {len(data)} != {expected}")
    return data


def request_small(url: str, max_bytes: int = MAX_XML_BYTES) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(max_bytes + 1)
    if not data or len(data) > max_bytes:
        raise ValueError(f"unexpected bounded download size: {url}")
    return data


def validate_lock(lock: dict[str, Any]) -> None:
    if lock.get("schema_version") != 1 or lock.get("authority") != "research-external-timing-only":
        raise ValueError("invalid AMI VAD research lock authority/schema")
    transport = lock.get("transport_mirror", {})
    if transport.get("repository") != discovery.HF_REPOSITORY or transport.get("revision") != discovery.HF_REVISION:
        raise ValueError("AMI transport mirror identity drifted")
    audio = lock.get("audio", {})
    wav = audio.get("wav", {})
    if wav.get("sample_rate_hz") != 16000 or wav.get("channels") != 1 or wav.get("bits_per_sample") != 16:
        raise ValueError("AMI locked WAV geometry drifted")
    if wav.get("byte_rate") != 32000 or wav.get("block_align") != 2 or wav.get("data_offset") != 44:
        raise ValueError("AMI locked PCM byte geometry drifted")
    windows = lock.get("windows", [])
    if len(windows) != 3:
        raise ValueError("AMI research lock must contain three windows")
    for window in windows:
        if int(window["length_bytes"]) != int(window["end_byte"]) - int(window["start_byte"]) + 1:
            raise ValueError(f"locked byte geometry mismatch: {window['window_id']}")
        if int(window["length_bytes"]) != 20 * int(wav["byte_rate"]):
            raise ValueError(f"window must remain exactly 20 seconds: {window['window_id']}")


def load_annotations(lock: dict[str, Any]) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    merged: list[tuple[float, float]] = []
    evidence = []
    for item in lock["annotations"]:
        url = discovery.hf_resolve_url(str(item["path"]))
        data = request_small(url)
        digest = sha256_bytes(data)
        if digest != item["sha256"] or len(data) != int(item["size_bytes"]):
            raise ValueError(f"annotation identity drifted: {item['speaker']}")
        intervals = discovery.parse_segments(data, str(item["speaker"]))
        if len(intervals) != int(item["segments"]):
            raise ValueError(f"annotation segment count drifted: {item['speaker']}")
        merged.extend(intervals)
        evidence.append({
            "speaker": item["speaker"],
            "sha256": digest,
            "segments": len(intervals),
            "size_bytes": len(data),
        })
    return discovery.merge_intervals(merged), evidence


def labels_for_window(intervals: list[tuple[float, float]], start_s: float, end_s: float) -> list[int]:
    frame_s = 0.010
    count = int(round((end_s - start_s) / frame_s))
    labels = []
    cursor = 0
    for index in range(count):
        center = start_s + (index + 0.5) * frame_s
        while cursor < len(intervals) and intervals[cursor][1] <= center:
            cursor += 1
        active = cursor < len(intervals) and intervals[cursor][0] <= center < intervals[cursor][1]
        labels.append(1 if active else 0)
    return labels


def decision_trace(probabilities: list[float], threshold: float, hangover_frames: int) -> list[dict[str, int]]:
    hangover = 0
    trace = []
    for raw in probabilities:
        probability = float(raw)
        if not math.isfinite(probability):
            probability = 0.0
        if probability > threshold:
            hangover = hangover_frames
        elif hangover:
            hangover -= 1
        trace.append({"vad_active": 1 if hangover > 0 else 0})
    return trace


def stats(labels: list[int], probabilities: list[float], threshold: float, hangover: int) -> dict[str, float | None]:
    return engine.vad_stats(labels, decision_trace(probabilities, threshold, hangover))


def delta(candidate: dict[str, float | None], baseline: dict[str, float | None], key: str) -> float:
    a = candidate.get(key)
    b = baseline.get(key)
    if a is None or b is None:
        raise ValueError(f"missing VAD metric: {key}")
    return float(a) - float(b)


def classify(aggregate_baseline: dict[str, float | None], aggregate_candidate: dict[str, float | None], windows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    recall_delta = delta(aggregate_candidate, aggregate_baseline, "recall")
    f1_delta = delta(aggregate_candidate, aggregate_baseline, "f1")
    fpr_delta = delta(aggregate_candidate, aggregate_baseline, "false_positive_rate")
    score = 2.0 * recall_delta + f1_delta - 1.5 * fpr_delta
    severe = []
    for item in windows:
        b = item["baseline"]
        c = item["candidate"]
        rd = delta(c, b, "recall")
        fd = delta(c, b, "f1")
        pd = delta(c, b, "false_positive_rate")
        if rd < -0.02 or fd < -0.03 or pd > 0.05:
            severe.append({"window_id": item["window_id"], "recall_delta": rd, "f1_delta": fd, "fpr_delta": pd})
    if severe or score < -0.01:
        decision = "CONTRADICTED"
    elif recall_delta > 0.0 and f1_delta >= -0.01 and fpr_delta <= 0.02 and score > 0.005:
        decision = "SUPPORT"
    else:
        decision = "MIXED"
    return decision, {
        "score": score,
        "recall_delta": recall_delta,
        "f1_delta": f1_delta,
        "fpr_delta": fpr_delta,
        "severe_window_regressions": severe,
    }


def evaluate(processor: Path, lock_path: Path, output_path: Path) -> dict[str, Any]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    validate_lock(lock)
    intervals, annotation_evidence = load_annotations(lock)
    audio_url = discovery.hf_resolve_url(str(lock["audio"]["path"]))
    shipping = float(lock["operating_points"]["shipping_ns_threshold"])
    research = float(lock["operating_points"]["research_ns_threshold"])
    hangover = int(lock["operating_points"]["hangover_frames"])

    window_reports = []
    aggregate_labels: list[int] = []
    aggregate_baseline_trace: list[dict[str, int]] = []
    aggregate_candidate_trace: list[dict[str, int]] = []

    with tempfile.TemporaryDirectory(prefix="ap-ami-vad-") as temporary:
        root = Path(temporary)
        corpus_path = root / "corpus.json"
        corpus_path.write_text('{"schema_version":1,"cases":[]}\n', encoding="utf-8")
        for window in lock["windows"]:
            start = int(window["start_byte"])
            end = int(window["end_byte"])
            pcm = request_exact_range(audio_url, start, end)
            digest = sha256_bytes(pcm)
            if digest != window["sha256"] or len(pcm) != int(window["length_bytes"]):
                raise ValueError(f"audio window identity drifted: {window['window_id']}")
            pcm_path = root / f"{window['window_id']}.pcm"
            pcm_path.write_bytes(pcm)
            labels = labels_for_window(intervals, float(window["start_s"]), float(window["end_s"]))
            measured_activity = sum(labels) / len(labels)
            if abs(measured_activity - float(window["activity_fraction"])) > 0.005:
                raise ValueError(f"annotation-derived activity drifted: {window['window_id']}")
            case = {
                "case_id": window["window_id"],
                "scenario": "ami-external-timing-real-speech",
                "sample_rate_hz": 16000,
                "mic_channels": 1,
                "mic_audio": pcm_path.name,
                "render_audio": None,
                "processor_profile": "ns-isolated",
                "control": {},
            }
            with tempfile.TemporaryDirectory(prefix="ap-ami-vad-run-") as work:
                _, trace, _ = engine.invoke(processor, case, corpus_path, Path(work))
            probabilities = [float(row.get("vad_probability", 0.0)) for row in trace]
            count = min(len(labels), len(probabilities))
            if count < 1900:
                raise ValueError(f"insufficient VAD trace frames: {window['window_id']} count={count}")
            labels = labels[:count]
            probabilities = probabilities[:count]
            baseline_trace = decision_trace(probabilities, shipping, hangover)
            candidate_trace = decision_trace(probabilities, research, hangover)
            baseline = engine.vad_stats(labels, baseline_trace)
            candidate = engine.vad_stats(labels, candidate_trace)
            aggregate_labels.extend(labels)
            aggregate_baseline_trace.extend(baseline_trace)
            aggregate_candidate_trace.extend(candidate_trace)
            window_reports.append({
                "window_id": window["window_id"],
                "start_s": window["start_s"],
                "activity_fraction": measured_activity,
                "audio_sha256": digest,
                "frames": count,
                "baseline": baseline,
                "candidate": candidate,
                "deltas": {
                    "recall": delta(candidate, baseline, "recall"),
                    "f1": delta(candidate, baseline, "f1"),
                    "false_positive_rate": delta(candidate, baseline, "false_positive_rate"),
                },
            })

    aggregate_baseline = engine.vad_stats(aggregate_labels, aggregate_baseline_trace)
    aggregate_candidate = engine.vad_stats(aggregate_labels, aggregate_candidate_trace)
    decision, evidence = classify(aggregate_baseline, aggregate_candidate, window_reports)
    result = {
        "schema_version": 1,
        "authority": "research-external-timing-vad-qualification",
        "decision": decision,
        "source": {
            "meeting": lock["dataset"]["meeting"],
            "license": lock["dataset"]["license"],
            "transport_revision": lock["transport_mirror"]["revision"],
            "lock_sha256": engine.sha256_file(lock_path),
            "processor_sha256": engine.sha256_file(processor),
            "annotation_semantics": lock["dataset"]["annotation_semantics"],
            "label_rule": lock["labeling"]["rule"],
        },
        "operating_points": {
            "shipping_ns_threshold": shipping,
            "research_ns_threshold": research,
            "hangover_frames": hangover,
        },
        "annotations": annotation_evidence,
        "aggregate": {
            "frames": len(aggregate_labels),
            "activity_fraction": sum(aggregate_labels) / len(aggregate_labels),
            "baseline": aggregate_baseline,
            "candidate": aggregate_candidate,
            "deltas": evidence,
        },
        "windows": window_reports,
        "promotion_boundary": (
            "research evidence only; manual transcription segment timing is not a dedicated audited SAD gold-label campaign, "
            "so this result cannot directly change shipping thresholds"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    intervals = [(1.0, 1.03), (1.05, 1.08)]
    labels = labels_for_window(intervals, 1.0, 1.10)
    assert len(labels) == 10
    assert sum(labels) == 6
    probs = [0.1, 0.4, 0.1] + [0.1] * 8
    active = [row["vad_active"] for row in decision_trace(probs, 0.35, 8)]
    assert active[1] == 1 and sum(active[1:9]) == 8 and active[9] == 0
    baseline = {"recall": 0.70, "f1": 0.70, "false_positive_rate": 0.10}
    candidate = {"recall": 0.73, "f1": 0.71, "false_positive_rate": 0.11}
    decision, evidence = classify(baseline, candidate, [])
    assert decision == "SUPPORT" and evidence["score"] > 0.0
    print("AMI VAD microset evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--lock", type=Path, default=Path("tests/validation/data/ami_vad_microset.lock.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.processor is None or args.output is None:
        parser.error("--processor and --output are required")
    result = evaluate(args.processor.resolve(), args.lock.resolve(), args.output.resolve())
    print(json.dumps({
        "decision": result["decision"],
        "aggregate": result["aggregate"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
