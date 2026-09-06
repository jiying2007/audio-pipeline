#!/usr/bin/env python3
"""Candidate-zero I005 VAD baseline measurement.

Measure the current shipping NS->VAD path and a local-VAD diagnostic path on
one pinned public Development source plus deterministic exact-timing far-field
cases. This tool never compares alternate thresholds/hangover values, never
ranks a source candidate, and cannot consume confirmation or promotion data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

import discover_ami_vad_microset as discovery
import i004_ns_nonstationary_diagnostic as synth
import run_validation_engine as engine
import stage_profile_support

stage_profile_support.install(engine)

RATE = 16000
FRAME = 160
FRAME_MS = 10.0
USER_AGENT = "audio-pipeline-i005-vad-baseline/1"
MAX_XML_BYTES = 2 * 1024 * 1024


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_small(url: str, max_bytes: int = MAX_XML_BYTES) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as response:
        data = response.read(max_bytes + 1)
    require(bool(data) and len(data) <= max_bytes, f"unexpected bounded download size: {url}")
    return data


def request_exact_range(url: str, start: int, end: int) -> bytes:
    expected = end - start + 1
    require(start >= 0 and end >= start and expected <= 2 * 1024 * 1024, "unsafe range request")
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end}"}
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        status = int(getattr(response, "status", response.getcode()))
        content_range = response.headers.get("Content-Range", "")
        data = response.read(expected + 1)
    require(status == 206, f"AMI range request must return 206, got {status}")
    require(content_range.startswith(f"bytes {start}-{end}/"), f"unexpected Content-Range: {content_range}")
    require(len(data) == expected, f"AMI range length mismatch: {len(data)} != {expected}")
    return data


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    f = position - lo
    return ordered[lo] * (1.0 - f) + ordered[hi] * f


def events_from_labels(labels: list[int], bridge_frames: int, min_event_frames: int) -> list[tuple[int, int]]:
    require(bridge_frames >= 0 and min_event_frames >= 1, "invalid event morphology")
    raw: list[tuple[int, int]] = []
    start: int | None = None
    for i, value in enumerate(labels + [0]):
        if value and start is None:
            start = i
        elif not value and start is not None:
            raw.append((start, i))
            start = None
    merged: list[tuple[int, int]] = []
    for start, end in raw:
        if merged and start - merged[-1][1] <= bridge_frames:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return [(start, end) for start, end in merged if end - start >= min_event_frames]


def frame_stats(labels: list[int], predicted: list[int]) -> dict[str, float | None]:
    count = min(len(labels), len(predicted))
    trace = [{"vad_active": int(predicted[i])} for i in range(count)]
    return engine.vad_stats(labels[:count], trace)


def event_stats(labels: list[int], predicted: list[int], bridge_frames: int,
                min_event_frames: int) -> dict[str, Any]:
    count = min(len(labels), len(predicted))
    labels = labels[:count]
    predicted = predicted[:count]
    events = events_from_labels(labels, bridge_frames, min_event_frames)
    hits = 0
    onset: list[float] = []
    release: list[float] = []
    details: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(events):
        next_start = events[index + 1][0] if index + 1 < len(events) else count
        first = next((i for i in range(start, end) if predicted[i]), None)
        hit = first is not None
        if hit:
            hits += 1
            onset_ms = (int(first) - start) * FRAME_MS
            onset.append(onset_ms)
        else:
            onset_ms = None
        cursor = end
        while cursor < next_start and predicted[cursor]:
            cursor += 1
        release_ms = (cursor - end) * FRAME_MS
        release.append(release_ms)
        details.append({
            "start_frame": start,
            "end_frame": end,
            "duration_ms": (end - start) * FRAME_MS,
            "hit": hit,
            "onset_delay_ms": onset_ms,
            "release_tail_ms": release_ms,
        })
    silence_frames = sum(1 for value in labels if not value)
    false_active_frames = sum(1 for i, value in enumerate(labels) if not value and predicted[i])
    return {
        "event_count": len(events),
        "events_hit": hits,
        "event_recall": hits / len(events) if events else None,
        "onset_delay_p50_ms": percentile(onset, 0.50),
        "onset_delay_p95_ms": percentile(onset, 0.95),
        "onset_delay_max_ms": max(onset) if onset else None,
        "release_tail_p50_ms": percentile(release, 0.50),
        "release_tail_p95_ms": percentile(release, 0.95),
        "release_tail_max_ms": max(release) if release else None,
        "false_active_ms": false_active_frames * FRAME_MS,
        "false_active_fraction": false_active_frames / silence_frames if silence_frames else 0.0,
        "details": details,
    }


def aggregate_reports(reports: list[dict], bridge_frames: int, min_event_frames: int) -> dict:
    labels: list[int] = []
    predicted: list[int] = []
    all_details: list[dict] = []
    total_events = total_hits = 0
    onset: list[float] = []
    release: list[float] = []
    false_active_frames = silence_frames = 0
    for report in reports:
        case_labels = report["labels"]
        case_pred = report["predicted"]
        labels.extend(case_labels)
        predicted.extend(case_pred)
        e = event_stats(case_labels, case_pred, bridge_frames, min_event_frames)
        total_events += int(e["event_count"])
        total_hits += int(e["events_hit"])
        all_details.extend(e["details"])
        onset.extend(float(x["onset_delay_ms"]) for x in e["details"] if x["onset_delay_ms"] is not None)
        release.extend(float(x["release_tail_ms"]) for x in e["details"])
        false_active_frames += sum(1 for i, v in enumerate(case_labels) if not v and case_pred[i])
        silence_frames += sum(1 for v in case_labels if not v)
    return {
        "frame": frame_stats(labels, predicted),
        "event": {
            "event_count": total_events,
            "events_hit": total_hits,
            "event_recall": total_hits / total_events if total_events else None,
            "onset_delay_p50_ms": percentile(onset, 0.50),
            "onset_delay_p95_ms": percentile(onset, 0.95),
            "onset_delay_max_ms": max(onset) if onset else None,
            "release_tail_p50_ms": percentile(release, 0.50),
            "release_tail_p95_ms": percentile(release, 0.95),
            "release_tail_max_ms": max(release) if release else None,
            "false_active_ms": false_active_frames * FRAME_MS,
            "false_active_fraction": false_active_frames / silence_frames if silence_frames else 0.0,
        },
    }


def load_annotations(lock: dict) -> tuple[list[tuple[float, float]], list[dict]]:
    merged: list[tuple[float, float]] = []
    evidence: list[dict] = []
    for item in lock["annotations"]:
        data = request_small(discovery.hf_resolve_url(str(item["path"])))
        digest = sha256_bytes(data)
        require(digest == item["sha256"] and len(data) == int(item["size_bytes"]),
                f"annotation identity drifted: {item['speaker']}")
        intervals = discovery.parse_segments(data, str(item["speaker"]))
        require(len(intervals) == int(item["segments"]), f"annotation count drifted: {item['speaker']}")
        merged.extend(intervals)
        evidence.append({"speaker": item["speaker"], "sha256": digest,
                         "size_bytes": len(data), "segments": len(intervals)})
    return discovery.merge_intervals(merged), evidence


def labels_for_window(intervals: list[tuple[float, float]], start_s: float, end_s: float) -> list[int]:
    frames = int(round((end_s - start_s) * 100.0))
    labels: list[int] = []
    cursor = 0
    for index in range(frames):
        center = start_s + (index + 0.5) * 0.010
        while cursor < len(intervals) and intervals[cursor][1] <= center:
            cursor += 1
        labels.append(1 if cursor < len(intervals) and intervals[cursor][0] <= center < intervals[cursor][1] else 0)
    return labels


def validate_lock(lock: dict, contract: dict) -> None:
    require(lock.get("schema_version") == 1 and lock.get("authority") == "i005-exposed-development-source",
            "invalid I005 source lock")
    require(lock["dataset"]["meeting"] == contract["public_source"]["meeting"] == "ES2005b", "meeting drift")
    require(lock["future_roles"] == {
        "development": True, "regression": True,
        "independent_confirmation": False, "promotion": False,
    }, "I005 source role drift")
    require(lock["audio"]["wav"]["sample_rate_hz"] == RATE and
            lock["audio"]["wav"]["channels"] == 1 and
            lock["audio"]["wav"]["bits_per_sample"] == 16, "WAV geometry")
    require(len(lock["annotations"]) == 4 and len(lock["windows"]) == 3, "locked source shape")
    require(lock["admission"]["decision"] == "ADMIT_DEVELOPMENT_SOURCE", "source not admitted")


def run_processor(processor: Path, pcm_path: Path, labels: list[int], profile: str,
                  case_id: str, minimum_frames: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="ap-i005-case-") as temporary:
        root = Path(temporary)
        local_pcm = root / "mic.pcm"
        local_pcm.write_bytes(pcm_path.read_bytes())
        corpus_path = root / "corpus.json"
        corpus_path.write_text('{"schema_version":1,"cases":[]}\n', encoding="utf-8")
        case = {
            "case_id": case_id,
            "split": "development",
            "scenario": "i005-vad-baseline",
            "sample_rate_hz": RATE,
            "mic_channels": 1,
            "mic_audio": "mic.pcm",
            "render_audio": None,
            "processor_profile": profile,
            "control": {},
        }
        with tempfile.TemporaryDirectory(prefix="ap-i005-run-") as work:
            _, trace, _ = engine.invoke(processor, case, corpus_path, Path(work))
    count = min(len(labels), len(trace))
    require(count >= minimum_frames, f"insufficient VAD trace: {case_id} {count}")
    labels = labels[:count]
    predicted = [1 if int(trace[i].get("vad_active", 0)) else 0 for i in range(count)]
    return {"labels": labels, "predicted": predicted, "trace_frames": count,
            "frame": frame_stats(labels, predicted)}


def public_reports(processor: Path, root: Path, contract: dict, output: Path) -> dict:
    lock_path = root / contract["public_source"]["lock"]
    lock = load_json(lock_path)
    validate_lock(lock, contract)
    intervals, annotation_evidence = load_annotations(lock)
    audio_url = discovery.hf_resolve_url(str(lock["audio"]["path"]))
    profiles = [contract["shipping_profile"], contract["diagnostic_profile"]]
    by_profile: dict[str, list[dict]] = {profile: [] for profile in profiles}
    materialized: list[dict] = []
    source_dir = output / "public-source"
    source_dir.mkdir(parents=True, exist_ok=True)
    for window in lock["windows"]:
        byte_range = window["audio_range"]
        pcm = request_exact_range(audio_url, int(byte_range["start_byte"]), int(byte_range["end_byte"]))
        digest = sha256_bytes(pcm)
        require(digest == byte_range["sha256"] and len(pcm) == int(byte_range["length_bytes"]),
                f"public audio drift: {window['window_id']}")
        pcm_path = source_dir / f"{window['window_id']}.pcm"
        pcm_path.write_bytes(pcm)
        labels = labels_for_window(intervals, float(window["start_s"]), float(window["end_s"]))
        activity = sum(labels) / len(labels)
        require(abs(activity - float(window["activity_fraction"])) <= 0.005,
                f"public timing activity drift: {window['window_id']}")
        require(0.05 < activity < 0.95, f"degenerate public activity: {window['window_id']}")
        materialized.append({"window_id": window["window_id"], "sha256": digest,
                             "frames": len(labels), "activity_fraction": activity})
        for profile in profiles:
            report = run_processor(
                processor, pcm_path, labels, profile, f"{window['window_id']}-{profile}",
                int(contract["input_preconditions"]["min_real_trace_frames_per_window"]),
            )
            report.update({"window_id": window["window_id"], "activity_fraction": activity,
                           "audio_sha256": digest})
            by_profile[profile].append(report)
    bridge = int(contract["public_source"]["event_bridge_gap_ms"] // 10)
    minimum = max(1, int(contract["public_source"]["min_event_ms"] // 10))
    aggregate = {profile: aggregate_reports(rows, bridge, minimum) for profile, rows in by_profile.items()}
    return {"source_lock_sha256": engine.sha256_file(lock_path),
            "annotation_evidence": annotation_evidence, "materialized_windows": materialized,
            "aggregate": aggregate,
            "windows": {
                profile: [{k: v for k, v in row.items() if k not in {"labels", "predicted"}}
                          for row in rows]
                for profile, rows in by_profile.items()
            }}


def room_path(clean: list[float], taps: list[list[float]]) -> list[float]:
    out = [0.0] * len(clean)
    for delay_raw, gain_raw in taps:
        delay, gain = int(delay_raw), float(gain_raw)
        require(delay >= 0 and 0.0 <= gain <= 1.0, "invalid far-field tap")
        for n in range(delay, len(clean)):
            out[n] += gain * clean[n - delay]
    return out


def rms_active(values: list[float], labels: list[int]) -> float:
    energy = count = 0
    for frame_index, active in enumerate(labels):
        if not active:
            continue
        start = frame_index * FRAME
        for value in values[start:start + FRAME]:
            energy += value * value
            count += 1
    return math.sqrt(energy / max(1, count))


def mix_at_snr(speech: list[float], noise: list[float], labels: list[int], snr_db: float) -> list[float]:
    speech_rms = rms_active(speech, labels)
    noise_rms = math.sqrt(sum(x * x for x in noise) / max(1, len(noise)))
    require(speech_rms > 1.0e-8 and noise_rms > 1.0e-8, "invalid SNR input")
    target_noise = speech_rms / (10.0 ** (snr_db / 20.0))
    scale = target_noise / noise_rms
    return [max(-0.98, min(0.98, s + scale * n)) for s, n in zip(speech, noise)]


def synthetic_reports(processor: Path, contract: dict, output: Path) -> dict:
    spec = contract["synthetic_farfield"]
    samples = int(round(float(spec["seconds"]) * RATE))
    profiles = [contract["shipping_profile"], contract["diagnostic_profile"]]
    by_profile: dict[str, list[dict]] = {profile: [] for profile in profiles}
    cases: list[dict] = []
    corpus_dir = output / "synthetic-farfield"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for seed in spec["seeds"]:
        clean, labels = synth.speech_like(samples, int(seed))
        far = room_path(clean, spec["room_taps_samples_and_gains"])
        require(len(labels) == samples // FRAME, "synthetic label geometry")
        exact_events = events_from_labels(labels, 0, 1)
        require(len(exact_events) == int(contract["input_preconditions"]["expected_synthetic_events_per_case"]),
                f"unexpected synthetic events: {seed}")
        noise = synth.mixed_noise(samples, int(seed) + 607)
        for scenario in spec["scenarios"]:
            if scenario == "reverb-only":
                mic = list(far)
            else:
                mic = mix_at_snr(far, noise, labels, float(spec["snr_db"][scenario]))
            case_id = f"seed-{seed}-{scenario}"
            pcm_path = corpus_dir / f"{case_id}.pcm"
            synth.write_pcm(pcm_path, mic)
            cases.append({"case_id": case_id, "seed": seed, "scenario": scenario,
                          "pcm_sha256": engine.sha256_file(pcm_path), "events": len(exact_events)})
            for profile in profiles:
                report = run_processor(
                    processor, pcm_path, labels, profile, f"{case_id}-{profile}",
                    int(contract["input_preconditions"]["min_synthetic_trace_frames_per_case"]),
                )
                report.update({"case_id": case_id, "seed": seed, "scenario": scenario,
                               "pcm_sha256": engine.sha256_file(pcm_path)})
                by_profile[profile].append(report)
    bridge = int(spec["event_bridge_gap_ms"] // 10)
    minimum = max(1, int(spec["min_event_ms"] // 10))
    aggregate = {profile: aggregate_reports(rows, bridge, minimum) for profile, rows in by_profile.items()}
    return {"generator": {"name": "i005_vad_baseline_measurement.py", "version": 1,
                           "seeds": spec["seeds"], "room_taps_samples_and_gains": spec["room_taps_samples_and_gains"]},
            "cases": cases, "aggregate": aggregate,
            "case_metrics": {
                profile: [{k: v for k, v in row.items() if k not in {"labels", "predicted"}}
                          for row in rows]
                for profile, rows in by_profile.items()
            }}


def gate_result(public: dict, synthetic: dict, contract: dict) -> tuple[str, list[dict]]:
    failures: list[dict] = []
    shipping = contract["shipping_profile"]
    real = public["aggregate"][shipping]
    exact = synthetic["aggregate"][shipping]
    pre = contract["input_preconditions"]
    if int(real["event"]["event_count"]) < int(pre["min_real_events_aggregate"]):
        return "INPUT_OR_LABEL_INVALID_REVIEW_REQUIRED", [{"gate": "min_real_events_aggregate",
                                                             "actual": real["event"]["event_count"]}]
    rg = contract["diagnostic_gates"]["real_proxy"]
    checks = [
        ("real.min_ns_frame_f1", real["frame"]["f1"], float(rg["min_ns_frame_f1"]), "min"),
        ("real.min_ns_event_recall", real["event"]["event_recall"], float(rg["min_ns_event_recall"]), "min"),
        ("real.max_ns_false_positive_rate", real["frame"]["false_positive_rate"], float(rg["max_ns_false_positive_rate"]), "max"),
    ]
    sg = contract["diagnostic_gates"]["synthetic_exact"]
    checks += [
        ("synthetic.min_ns_frame_f1", exact["frame"]["f1"], float(sg["min_ns_frame_f1"]), "min"),
        ("synthetic.min_ns_event_recall", exact["event"]["event_recall"], float(sg["min_ns_event_recall"]), "min"),
        ("synthetic.max_ns_onset_delay_p95_ms", exact["event"]["onset_delay_p95_ms"], float(sg["max_ns_onset_delay_p95_ms"]), "max"),
        ("synthetic.max_ns_release_tail_p95_ms", exact["event"]["release_tail_p95_ms"], float(sg["max_ns_release_tail_p95_ms"]), "max"),
        ("synthetic.max_ns_false_active_fraction", exact["event"]["false_active_fraction"], float(sg["max_ns_false_active_fraction"]), "max"),
    ]
    for name, actual, limit, direction in checks:
        if actual is None or (direction == "min" and float(actual) < limit) or (direction == "max" and float(actual) > limit):
            failures.append({"gate": name, "actual": actual,
                             "expected_min" if direction == "min" else "expected_max": limit})
    return ("MEASURED_GAP_REVIEW_REQUIRED" if failures else "BASELINE_ADEQUATE_NO_SEARCH"), failures


def validate_contract(c: dict) -> None:
    require(c.get("schema_version") == 1 and c.get("iteration_id") == "I005", "contract identity")
    require(c.get("phase") == "baseline-measurement" and
            c.get("root_cause_id") == "vad-event-onset-release-baseline", "contract phase/root cause")
    require(c.get("candidate_limit") == 0 and c.get("confirmation_limit") == 0 and
            c.get("promotion_allowed") is False, "candidate-zero authority")
    require(c.get("shipping_profile") == "ns-isolated" and c.get("diagnostic_profile") == "vad-isolated",
            "profile authority")
    require(c["public_source"]["meeting"] == "ES2005b" and
            c["public_source"]["role"] == "development-exposed", "public source")
    require(c["synthetic_farfield"]["seeds"] == [15107, 25107, 35107], "synthetic seeds")
    require(all(value is False for value in c["authority"].values()), "authority must remain false")
    require(c.get("product_qualification") == "DEFERRED_BY_SCOPE", "product boundary")


def self_test() -> None:
    labels = [0, 1, 1, 0, 0, 1, 1, 1, 0]
    assert events_from_labels(labels, 0, 1) == [(1, 3), (5, 8)]
    assert events_from_labels(labels, 2, 1) == [(1, 8)]
    predicted = [0, 0, 1, 1, 0, 1, 1, 0, 1]
    e = event_stats(labels, predicted, 0, 1)
    assert e["event_count"] == 2 and e["events_hit"] == 2
    assert e["onset_delay_p50_ms"] == 5.0
    assert e["release_tail_max_ms"] == 10.0
    assert percentile([0.0, 10.0], 0.95) == 9.5
    print(json.dumps({"result": "PASS", "event_metrics": True, "threshold_search": False}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.contract is not None and args.processor is not None and args.output is not None,
            "contract/processor/output required")
    root = Path(__file__).resolve().parents[2]
    contract = load_json(args.contract)
    validate_contract(contract)
    current = __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"exact base drift: {current}")
    require(args.processor.is_file(), "processor missing")
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)

    public = public_reports(args.processor.resolve(), root, contract, output)
    synthetic = synthetic_reports(args.processor.resolve(), contract, output)
    decision, failures = gate_result(public, synthetic, contract)
    shipping = contract["shipping_profile"]
    diagnostic = contract["diagnostic_profile"]
    report = {
        "schema_version": 1,
        "iteration_id": "I005",
        "phase": "baseline-measurement",
        "root_cause_id": contract["root_cause_id"],
        "source_sha": current,
        "processor_sha256": engine.sha256_file(args.processor),
        "authority": "candidate-zero-development-baseline-only",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "threshold_tuning_performed": False,
        "hangover_tuning_performed": False,
        "candidate_search_performed": False,
        "promotion_allowed": False,
        "decision": decision,
        "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
        "gate_failures": failures,
        "public_source": public,
        "synthetic_farfield": synthetic,
        "evidence_path_diagnostic": {
            "real_ns_minus_local_frame_recall": (
                float(public["aggregate"][shipping]["frame"]["recall"]) -
                float(public["aggregate"][diagnostic]["frame"]["recall"])
            ),
            "real_ns_minus_local_event_recall": (
                float(public["aggregate"][shipping]["event"]["event_recall"]) -
                float(public["aggregate"][diagnostic]["event"]["event_recall"])
            ),
            "synthetic_ns_minus_local_event_recall": (
                float(synthetic["aggregate"][shipping]["event"]["event_recall"]) -
                float(synthetic["aggregate"][diagnostic]["event"]["event_recall"])
            ),
            "interpretation": "diagnostic only; cannot weaken NS upstream evidence or authorize a VAD candidate"
        },
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "baseline-result.json", report)
    print(json.dumps({"decision": decision, "failures": len(failures),
                      "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"I005 VAD baseline error: {exc}")
