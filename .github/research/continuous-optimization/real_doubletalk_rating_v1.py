#!/usr/bin/env python3
"""Candidate-zero real double-talk rating-interval diagnostic.

Uses the exact upstream Interspeech2021 real double-talk recordings and the
upstream AECMOS rating-interval formula. The rating interval is descriptive
scenario evidence, not an exact near-end onset label.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import importlib.util
import json
import math
import statistics
import subprocess
import sys
import wave
from pathlib import Path


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def load_route_module():
    path = Path(__file__).with_name("doubletalk_temporal_route_v2.py")
    spec = importlib.util.spec_from_file_location("doubletalk_temporal_route_v2", path)
    require(spec is not None and spec.loader is not None, "cannot load temporal route helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROUTE = load_route_module()


def read_wav(path: Path) -> tuple[int, list[int]]:
    with wave.open(str(path), "rb") as wav:
        require(wav.getnchannels() == 1, f"mono WAV required: {path}")
        require(wav.getsampwidth() == 2, f"PCM16 WAV required: {path}")
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return rate, list(samples)


def write_pcm16(path: Path, samples: list[int]) -> None:
    values = array.array("h", samples)
    if sys.byteorder != "little":
        values.byteswap()
    path.write_bytes(values.tobytes())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def median(values) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(clean) if clean else None


def percentile(values: list[float], q: float) -> float | None:
    values = sorted(value for value in values if math.isfinite(value))
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def fraction(rows: list[dict], key: str) -> float | None:
    return None if not rows else sum(int(row[key]) != 0 for row in rows) / len(rows)


def active_runs(values: list[bool]) -> tuple[int, int]:
    runs = 0
    longest = 0
    current = 0
    for active in values:
        if active:
            if current == 0:
                runs += 1
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return runs, longest


def official_rating_bounds(common_samples: int, rate: int) -> tuple[int, int]:
    silence_samples = 15 * rate
    require(common_samples > silence_samples, "clip must exceed 15 seconds")
    rating_length = int((common_samples - silence_samples) / 2)
    require(rating_length > 0, "rating interval must be non-empty")
    return common_samples - rating_length, common_samples


def summarize_metrics(rows: list[dict], start_frame: int, end_frame: int) -> dict:
    part = rows[max(0, start_frame):min(len(rows), end_frame)]
    require(part, "empty rating metrics interval")
    dt = [int(row["double_talk_active"]) != 0 for row in part]
    runs, longest = active_runs(dt)
    first = next((index for index, value in enumerate(dt) if value), None)
    errors = [abs(float(row["delay_error_samples"])) for row in part
              if row.get("delay_error_samples") is not None]
    return {
        "frames": len(part),
        "double_talk_fraction": sum(dt) / len(dt),
        "double_talk_first_active_offset_ms": None if first is None else first * 10,
        "double_talk_active_run_count": runs,
        "double_talk_longest_active_run_ms": longest * 10,
        "far_end_fraction": fraction(part, "far_end_active"),
        "aec_converged_fraction": fraction(part, "aec_converged"),
        "estimated_delay_ms_median": median([row.get("estimated_delay_ms") for row in part]),
        "delay_error_abs_p95_samples": percentile(errors, 0.95),
    }


def route_series(mic: list[int], render: list[int], rate: int,
                 start_sample: int, end_sample: int, geometry: dict) -> dict:
    window = int(round(float(geometry["route_window_seconds"]) * rate))
    hop = int(round(float(geometry["route_hop_seconds"]) * rate))
    require(window > 0 and hop > 0, "invalid route window geometry")
    cfg = {
        "max_delay_ms": geometry["route_max_delay_ms"],
        "coarse_step_samples": geometry["route_coarse_step_samples"],
        "sample_stride": geometry["route_sample_stride"],
        "runner_guard_samples": geometry["route_runner_guard_samples"],
    }
    windows = []
    index = 0
    cursor = start_sample
    while cursor + window <= end_sample:
        snap = ROUTE.route_snapshot_samples(mic, render, rate, cursor, cursor + window, cfg)
        windows.append({
            "index": index,
            "start_offset_seconds": (cursor - start_sample) / rate,
            "end_offset_seconds": (cursor + window - start_sample) / rate,
            "best_delay_samples": snap["best_delay_samples"],
            "best_delay_ms": snap["best_delay_ms"],
            "best_score_squared": snap["best_score_squared"],
            "runner_up_score_squared": snap["runner_up_score_squared"],
            "peak_ratio": snap["peak_ratio"],
        })
        cursor += hop
        index += 1
    require(len(windows) >= 2, "rating interval must support at least two route windows")
    return {"windows": windows, "shape": ROUTE.trajectory_shape(windows)}


def verify_source_file(root: Path, metadata: dict) -> Path:
    path = root / metadata["path"]
    require(path.is_file(), f"missing source file: {path}")
    require(path.stat().st_size == int(metadata["size"]), f"size mismatch: {path}")
    require(sha256_file(path) == metadata["sha256"], f"sha256 mismatch: {path}")
    return path


def run_case(processor: Path, root: Path, case: dict, geometry: dict, output: Path) -> dict:
    lpb_path = verify_source_file(root, case["lpb"])
    mic_path = verify_source_file(root, case["mic"])
    lpb_rate, lpb = read_wav(lpb_path)
    mic_rate, mic = read_wav(mic_path)
    require(lpb_rate == mic_rate == 16000, f"16 kHz paired WAV required: {case['case_id']}")
    common = min(len(lpb), len(mic))
    lpb = lpb[:common]
    mic = mic[:common]
    rating_start, rating_end = official_rating_bounds(common, mic_rate)

    case_dir = output / "cases" / case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=False)
    mic_raw = case_dir / "mic.pcm"
    lpb_raw = case_dir / "render.pcm"
    out_raw = case_dir / "out.pcm"
    metrics_path = case_dir / "metrics.jsonl"
    write_pcm16(mic_raw, mic)
    write_pcm16(lpb_raw, lpb)
    subprocess.run([
        str(processor), "--sample-rate", str(mic_rate), "--mic-channels", "1",
        "--metrics-jsonl", str(metrics_path), str(mic_raw), str(lpb_raw), str(out_raw),
    ], check=True)
    rows = [json.loads(line) for line in metrics_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows and all(int(row["frame"]) == i for i, row in enumerate(rows)),
            f"contiguous metrics required: {case['case_id']}")

    frame_samples = mic_rate // 100
    start_frame = (rating_start + frame_samples - 1) // frame_samples
    end_frame = min(len(rows), rating_end // frame_samples)
    require(end_frame > start_frame, "empty frame-aligned rating interval")
    aligned_start = start_frame * frame_samples
    aligned_end = end_frame * frame_samples

    return {
        "case_id": case["case_id"],
        "guid": case["guid"],
        "scenario": case["scenario"],
        "movement": bool(case["movement"]),
        "sample_rate_hz": mic_rate,
        "common_samples": common,
        "clip_duration_seconds": common / mic_rate,
        "official_rating_start_seconds": rating_start / mic_rate,
        "official_rating_duration_seconds": (rating_end - rating_start) / mic_rate,
        "analysis_start_seconds": aligned_start / mic_rate,
        "analysis_duration_seconds": (aligned_end - aligned_start) / mic_rate,
        "official_interval_is_exact_onset_label": False,
        "metrics": summarize_metrics(rows, start_frame, end_frame),
        "route": route_series(mic, lpb, mic_rate, aligned_start, aligned_end, geometry),
    }


def aggregate(cases: list[dict]) -> dict:
    groups = {
        "no_movement": [case for case in cases if not case["movement"]],
        "movement": [case for case in cases if case["movement"]],
    }
    result = {}
    for name, group in groups.items():
        result[name] = {
            "cases": len(group),
            "double_talk_fraction_median": median([case["metrics"]["double_talk_fraction"] for case in group]),
            "double_talk_longest_active_run_ms_median": median([
                case["metrics"]["double_talk_longest_active_run_ms"] for case in group
            ]),
            "far_end_fraction_median": median([case["metrics"]["far_end_fraction"] for case in group]),
            "aec_converged_fraction_median": median([case["metrics"]["aec_converged_fraction"] for case in group]),
            "route_peak_score_median": median([case["route"]["shape"]["peak_score_median"] for case in group]),
            "route_lag_range_ms_median": median([case["route"]["shape"]["lag_range_ms"] for case in group]),
            "route_lag_total_variation_ms_median": median([
                case["route"]["shape"]["lag_total_variation_ms"] for case in group
            ]),
            "route_peak_score_total_variation_median": median([
                case["route"]["shape"]["peak_score_total_variation"] for case in group
            ]),
        }
    return result


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "real-doubletalk-rating-interval-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget must be zero")
    require(manifest["source"]["revision"] == "6c633d0a9d2a143a0e364899b91b06f127315b18", "source revision")
    require(manifest["selection"]["optimized"] is False, "selection must be non-optimized")
    require(manifest["selection"]["selected_guids"] == [
        "49IIo03GZ0CYQOmeA3A0BA", "7GTxyTksSUqCnP5y0ILG4A"
    ], "selected GUIDs")
    require(len(manifest["selection"]["cases"]) == 4, "four selected cases required")
    require(manifest["observation_geometry"]["selection_threshold"] is None, "threshold forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority")
    require(all(authority[key] is False for key in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority forbidden")


def self_test() -> None:
    start, end = official_rating_bounds(40 * 16000, 16000)
    assert start == int(27.5 * 16000)
    assert end == 40 * 16000
    runs, longest = active_runs([False, True, True, False, True, False])
    assert (runs, longest) == (2, 2)
    print(json.dumps({
        "result": "PASS", "candidate_budget": 0,
        "rating_interval_is_exact_onset_label": False,
    }, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.processor and args.manifest and args.source_root and args.output,
            "processor/manifest/source-root/output required")
    require(args.processor.is_file(), "processor missing")
    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    require(not args.output.exists() or (args.output.is_dir() and not any(args.output.iterdir())),
            "output must be absent or empty")
    args.output.mkdir(parents=True, exist_ok=True)

    cases = [run_case(args.processor, args.source_root, case, manifest["observation_geometry"], args.output)
             for case in manifest["selection"]["cases"]]
    require(sum(case["movement"] for case in cases) == 2, "two movement cases required")
    require(sum(not case["movement"] for case in cases) == 2, "two no-movement cases required")
    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "selection_performed": False,
        "tuning_performed": False,
        "rating_interval_is_exact_onset_label": False,
        "source_revision": manifest["source"]["revision"],
        "source_semantics": manifest["source"]["rating_interval_semantics"],
        "aggregate": aggregate(cases),
        "cases": cases,
        "interpretation_rule": manifest["interpretation_rule"],
    }
    write_json(args.output / "real-doubletalk-rating-result.json", payload)
    print(json.dumps({
        "output": str(args.output / "real-doubletalk-rating-result.json"),
        "candidate_budget": 0,
        "cases": len(cases),
        "rating_interval_is_exact_onset_label": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
