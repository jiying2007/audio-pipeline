#!/usr/bin/env python3
"""Candidate-zero pure-far Activity energy-ratio diagnostic.

Runs a read-only research probe against the unchanged pipeline and summarizes
only the upstream AECMOS far-end rating interval. Existing Activity thresholds
are observations, never search variables or tuning authority.
"""
from __future__ import annotations

import argparse
import array
import hashlib
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def verify_source_file(root: Path, metadata: dict) -> Path:
    path = root / metadata["path"]
    require(path.is_file(), f"missing source file: {path}")
    require(path.stat().st_size == int(metadata["size"]), f"size mismatch: {path}")
    require(sha256_file(path) == metadata["sha256"], f"sha256 mismatch: {path}")
    return path


def fraction(values: list[bool]) -> float | None:
    return None if not values else sum(values) / len(values)


def median(values) -> float | None:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.median(clean) if clean else None


def percentile(values, q: float) -> float | None:
    clean = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return clean[lo]
    return clean[lo] * (hi - position) + clean[hi] * (position - lo)


def active_runs(values: list[bool]) -> tuple[int, int]:
    runs = 0
    longest = 0
    current = 0
    for value in values:
        if value:
            if current == 0:
                runs += 1
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return runs, longest


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "pure-far-activity-ratio-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget must remain zero")
    require(manifest["source"]["revision"] == "6c633d0a9d2a143a0e364899b91b06f127315b18", "source revision")
    require(manifest["selection"]["optimized"] is False, "selection must be frozen")
    require([case["case_id"] for case in manifest["selection"]["cases"]] == [
        "49II-farend", "7GT-farend"
    ], "exact two pure-far cases required")
    method = manifest["observation_method"]
    require(method["internal_state_read_only"] is True, "internal state must be read-only")
    require(method["public_api_change"] is False, "public API change forbidden")
    require(method["existing_thresholds_are_observation_labels_only"] is True, "threshold semantics")
    require(method["selection_threshold"] is None, "selection threshold forbidden")
    require(method["candidate_selection"] is False and method["tuning_authority"] is False,
            "candidate/tuning authority forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority")
    require(all(authority[key] is False for key in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority forbidden")


def official_farend_bounds(common_samples: int) -> tuple[int, int]:
    rating_length = int(common_samples / 2)
    require(rating_length > 0, "non-empty far-end rating interval required")
    return common_samples - rating_length, common_samples


def summarize(rows: list[dict], start_frame: int, end_frame: int, constants: dict) -> dict:
    part = rows[max(0, start_frame):min(len(rows), end_frame)]
    require(part, "empty frame-aligned rating interval")

    expected_far_threshold = float(constants["far_end_threshold"])
    expected_dt_ratio = float(constants["double_talk_ratio"])
    expected_hangover = int(constants["hangover_frames"])
    for row in part:
        require(math.isclose(float(row["far_end_threshold"]), expected_far_threshold,
                             rel_tol=1e-6, abs_tol=1e-12), "far threshold drift")
        require(math.isclose(float(row["double_talk_ratio"]), expected_dt_ratio,
                             rel_tol=1e-6, abs_tol=1e-9), "DTD ratio drift")
        require(int(row["hangover_frames"]) == expected_hangover, "hangover drift")
        require(not bool(row["dt_on_evidence"]) or bool(row["double_talk_active"]),
                "dt_on evidence must imply public DTD")
        require(not bool(row["double_talk_active"]) or bool(row["far_end_active"]),
                "public DTD must remain far-gated")

    far = [bool(row["far_end_active"]) for row in part]
    dtd = [bool(row["double_talk_active"]) for row in part]
    on = [bool(row["dt_on_evidence"]) for row in part]
    hold = [bool(row["dt_hold_evidence"]) for row in part]
    far_rows = [row for row in part if row["far_end_active"]]
    dtd_rows = [row for row in part if row["double_talk_active"]]
    far_non_dtd_rows = [row for row in part if row["far_end_active"] and not row["double_talk_active"]]
    runs, longest = active_runs(dtd)

    dtd_given_far = None
    on_given_far = None
    hold_given_far = None
    if far_rows:
        dtd_given_far = sum(bool(row["double_talk_active"]) for row in far_rows) / len(far_rows)
        on_given_far = sum(bool(row["dt_on_evidence"]) for row in far_rows) / len(far_rows)
        hold_given_far = sum(bool(row["dt_hold_evidence"]) for row in far_rows) / len(far_rows)

    dtd_current_on = None
    dtd_current_hold = None
    dtd_hangover_only = None
    if dtd_rows:
        dtd_current_on = sum(bool(row["dt_on_evidence"]) for row in dtd_rows) / len(dtd_rows)
        dtd_current_hold = sum(bool(row["dt_hold_evidence"]) for row in dtd_rows) / len(dtd_rows)
        dtd_hangover_only = sum(
            not row["dt_on_evidence"] and not row["dt_hold_evidence"] for row in dtd_rows
        ) / len(dtd_rows)

    def ratios(group: list[dict]) -> dict:
        return {
            "smoothed_ratio_median": median([row["smoothed_ratio"] for row in group]),
            "smoothed_ratio_p95": percentile([row["smoothed_ratio"] for row in group], 0.95),
            "instant_ratio_median": median([row["instant_ratio"] for row in group]),
            "instant_ratio_p95": percentile([row["instant_ratio"] for row in group], 0.95),
        }

    return {
        "frames": len(part),
        "far_end_fraction": fraction(far),
        "double_talk_fraction": fraction(dtd),
        "double_talk_given_far_fraction": dtd_given_far,
        "dt_on_evidence_fraction": fraction(on),
        "dt_hold_evidence_fraction": fraction(hold),
        "dt_on_given_far_fraction": on_given_far,
        "dt_hold_given_far_fraction": hold_given_far,
        "double_talk_current_dt_on_fraction": dtd_current_on,
        "double_talk_current_dt_hold_fraction": dtd_current_hold,
        "double_talk_hangover_only_fraction": dtd_hangover_only,
        "double_talk_active_run_count": runs,
        "double_talk_longest_active_run_ms": longest * 10,
        "all_frames_ratio": ratios(part),
        "far_frames_ratio": ratios(far_rows),
        "double_talk_frames_ratio": ratios(dtd_rows),
        "far_non_double_talk_frames_ratio": ratios(far_non_dtd_rows),
        "mic_recovery_relative_error_max": max(float(row["mic_recovery_relative_error"]) for row in part),
        "reference_recovery_relative_error_max": max(
            float(row["reference_recovery_relative_error"]) for row in part
        ),
        "aec_converged_fraction": fraction([bool(row["aec_converged"]) for row in part]),
        "estimated_delay_ms_median": median([row["estimated_delay_ms"] for row in part]),
        "double_talk_hangover_max": max(int(row["double_talk_hangover"]) for row in part),
        "far_end_hangover_max": max(int(row["far_end_hangover"]) for row in part),
    }


def run_case(probe: Path, source_root: Path, case: dict, manifest: dict, output: Path) -> dict:
    mic_path = verify_source_file(source_root, case["mic"])
    lpb_path = verify_source_file(source_root, case["lpb"])
    mic_rate, mic = read_wav(mic_path)
    lpb_rate, lpb = read_wav(lpb_path)
    require(mic_rate == lpb_rate == 16000, f"16 kHz paired WAV required: {case['case_id']}")
    common = min(len(mic), len(lpb))
    mic = mic[:common]
    lpb = lpb[:common]

    case_dir = output / "cases" / case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=False)
    mic_raw = case_dir / "mic.pcm"
    lpb_raw = case_dir / "render.pcm"
    trace_path = case_dir / "activity-ratio.jsonl"
    write_pcm16(mic_raw, mic)
    write_pcm16(lpb_raw, lpb)
    subprocess.run([str(probe), str(mic_raw), str(lpb_raw), str(trace_path)], check=True)
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows and all(int(row["frame"]) == index for index, row in enumerate(rows)),
            f"contiguous trace required: {case['case_id']}")

    frame_samples = mic_rate // 100
    rating_start, rating_end = official_farend_bounds(common)
    start_frame = (rating_start + frame_samples - 1) // frame_samples
    end_frame = min(len(rows), rating_end // frame_samples)
    require(end_frame > start_frame, "empty official rating interval after frame alignment")

    metrics = summarize(
        rows, start_frame, end_frame,
        manifest["baseline_code_lock"]["activity_constants_observed_not_tuned"],
    )
    return {
        "case_id": case["case_id"],
        "guid": case["guid"],
        "scenario": case["scenario"],
        "sample_rate_hz": mic_rate,
        "common_samples": common,
        "clip_duration_seconds": common / mic_rate,
        "official_rating_start_seconds": rating_start / mic_rate,
        "official_rating_duration_seconds": (rating_end - rating_start) / mic_rate,
        "analysis_start_seconds": start_frame * frame_samples / mic_rate,
        "analysis_duration_seconds": (end_frame - start_frame) * 0.01,
        "metrics": metrics,
    }


def case_delta(left: dict, right: dict) -> dict:
    left_metrics = left["metrics"]
    right_metrics = right["metrics"]
    keys = [
        "far_end_fraction",
        "double_talk_fraction",
        "double_talk_given_far_fraction",
        "dt_on_given_far_fraction",
        "dt_hold_given_far_fraction",
        "aec_converged_fraction",
    ]
    result = {f"7GT_minus_49II_{key}": right_metrics[key] - left_metrics[key] for key in keys}
    for ratio_group in ("far_frames_ratio", "double_talk_frames_ratio", "far_non_double_talk_frames_ratio"):
        for key in ("smoothed_ratio_median", "instant_ratio_median"):
            a = left_metrics[ratio_group][key]
            b = right_metrics[ratio_group][key]
            result[f"7GT_minus_49II_{ratio_group}_{key}"] = None if a is None or b is None else b - a
    return result


def self_test() -> None:
    assert official_farend_bounds(100) == (50, 100)
    assert active_runs([False, True, True, False, True]) == (2, 2)
    assert percentile([0.0, 10.0], 0.5) == 5.0
    print(json.dumps({"result": "PASS", "candidate_budget": 0, "threshold_search": False}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    require(args.probe and args.manifest and args.source_root and args.output,
            "probe/manifest/source-root/output required")
    require(args.probe.is_file(), "research probe missing")
    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    require(not args.output.exists() or (args.output.is_dir() and not any(args.output.iterdir())),
            "output must be absent or empty")
    args.output.mkdir(parents=True, exist_ok=True)

    cases = [run_case(args.probe, args.source_root, case, manifest, args.output)
             for case in manifest["selection"]["cases"]]
    require(len(cases) == 2, "two pure-far cases required")
    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "selection_performed": False,
        "threshold_search_performed": False,
        "tuning_performed": False,
        "source_revision": manifest["source"]["revision"],
        "existing_thresholds_are_observation_labels_only": True,
        "cases": cases,
        "descriptive_delta": case_delta(cases[0], cases[1]),
        "interpretation_rule": manifest["interpretation_rule"],
    }
    write_json(args.output / "pure-far-activity-ratio-result.json", payload)
    print(json.dumps({
        "output": str(args.output / "pure-far-activity-ratio-result.json"),
        "candidate_budget": 0,
        "cases": len(cases),
        "threshold_search_performed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
