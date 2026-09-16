#!/usr/bin/env python3
"""Candidate-zero same-GUID far-end vs double-talk paired diagnostic.

The comparison uses scenario-specific official AECMOS rating intervals and the
unchanged baseline. A shared upstream GUID is a pairing key only; it is not
proof of identical physical recording conditions and no detector boundary is
selected.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import subprocess
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


def load_base_module():
    path = Path(__file__).with_name("real_doubletalk_rating_v1.py")
    spec = importlib.util.spec_from_file_location("real_doubletalk_rating_v1", path)
    require(spec is not None and spec.loader is not None, "cannot load predecessor helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_base_module()


def median(values) -> float | None:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.median(clean) if clean else None


def rating_bounds(scenario: str, common_samples: int, rate: int) -> tuple[int, int]:
    require(common_samples > 0, "non-empty clip required")
    if scenario == "farend_singletalk":
        start = common_samples - int(common_samples / 2)
        return start, common_samples
    if scenario == "doubletalk":
        return BASE.official_rating_bounds(common_samples, rate)
    raise ValueError(f"unsupported scenario: {scenario}")


def run_case(processor: Path, root: Path, case: dict, geometry: dict, output: Path) -> dict:
    lpb_path = BASE.verify_source_file(root, case["lpb"])
    mic_path = BASE.verify_source_file(root, case["mic"])
    lpb_rate, lpb = BASE.read_wav(lpb_path)
    mic_rate, mic = BASE.read_wav(mic_path)
    require(lpb_rate == mic_rate == 16000, f"16 kHz paired WAV required: {case['case_id']}")
    common = min(len(lpb), len(mic))
    lpb = lpb[:common]
    mic = mic[:common]
    rating_start, rating_end = rating_bounds(case["scenario"], common, mic_rate)

    case_dir = output / "cases" / case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=False)
    mic_raw = case_dir / "mic.pcm"
    lpb_raw = case_dir / "render.pcm"
    out_raw = case_dir / "out.pcm"
    metrics_path = case_dir / "metrics.jsonl"
    BASE.write_pcm16(mic_raw, mic)
    BASE.write_pcm16(lpb_raw, lpb)
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
        "sample_rate_hz": mic_rate,
        "clip_duration_seconds": common / mic_rate,
        "official_rating_start_seconds": rating_start / mic_rate,
        "official_rating_duration_seconds": (rating_end - rating_start) / mic_rate,
        "analysis_start_seconds": aligned_start / mic_rate,
        "analysis_duration_seconds": (aligned_end - aligned_start) / mic_rate,
        "time_aligned_with_paired_scenario": False,
        "metrics": BASE.summarize_metrics(rows, start_frame, end_frame),
        "route": BASE.route_series(mic, lpb, mic_rate, aligned_start, aligned_end, geometry),
    }


def numeric_delta(doubletalk: dict, farend: dict, key: str) -> float | None:
    left = doubletalk.get(key)
    right = farend.get(key)
    if left is None or right is None:
        return None
    return float(left) - float(right)


def build_pairs(cases: list[dict], selected_guids: list[str]) -> list[dict]:
    pairs = []
    for guid in selected_guids:
        group = [case for case in cases if case["guid"] == guid]
        require(len(group) == 2, f"two scenarios required for {guid}")
        by_scenario = {case["scenario"]: case for case in group}
        require(set(by_scenario) == {"farend_singletalk", "doubletalk"}, f"scenario pair required: {guid}")
        farend = by_scenario["farend_singletalk"]
        dt = by_scenario["doubletalk"]
        metric_keys = [
            "double_talk_fraction", "far_end_fraction", "aec_converged_fraction",
            "estimated_delay_ms_median", "delay_error_abs_p95_samples",
        ]
        shape_keys = [
            "lag_range_ms", "lag_total_variation_ms", "lag_step_abs_median_ms",
            "lag_step_abs_p95_ms", "peak_score_median", "peak_score_total_variation",
            "peak_ratio_median",
        ]
        pairs.append({
            "guid": guid,
            "pairing_semantics": "same upstream GUID identifier; not a physical-control guarantee",
            "time_aligned_pair": False,
            "farend_case_id": farend["case_id"],
            "doubletalk_case_id": dt["case_id"],
            "doubletalk_minus_farend_metrics": {
                key: numeric_delta(dt["metrics"], farend["metrics"], key) for key in metric_keys
            },
            "doubletalk_minus_farend_route_shape": {
                key: numeric_delta(dt["route"]["shape"], farend["route"]["shape"], key) for key in shape_keys
            },
        })
    return pairs


def aggregate_pairs(pairs: list[dict]) -> dict:
    metric_keys = sorted(pairs[0]["doubletalk_minus_farend_metrics"])
    shape_keys = sorted(pairs[0]["doubletalk_minus_farend_route_shape"])
    return {
        "pairs": len(pairs),
        "metric_delta_medians": {
            key: median([row["doubletalk_minus_farend_metrics"][key] for row in pairs]) for key in metric_keys
        },
        "route_shape_delta_medians": {
            key: median([row["doubletalk_minus_farend_route_shape"][key] for row in pairs]) for key in shape_keys
        },
    }


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "same-guid-farend-doubletalk-paired-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget")
    require(manifest["source"]["revision"] == "6c633d0a9d2a143a0e364899b91b06f127315b18", "source revision")
    require(manifest["selection"]["optimized"] is False, "selection must not be optimized")
    require(manifest["selection"]["selected_guids"] == [
        "49IIo03GZ0CYQOmeA3A0BA", "7GTxyTksSUqCnP5y0ILG4A"
    ], "selected GUIDs")
    require(len(manifest["selection"]["cases"]) == 4, "four paired cases required")
    require(manifest["observation_geometry"]["selection_threshold"] is None, "threshold forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority")
    require(all(authority[key] is False for key in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority forbidden")


def self_test() -> None:
    far_start, far_end = rating_bounds("farend_singletalk", 40 * 16000, 16000)
    dt_start, dt_end = rating_bounds("doubletalk", 40 * 16000, 16000)
    assert (far_start, far_end) == (20 * 16000, 40 * 16000)
    assert (dt_start, dt_end) == (int(27.5 * 16000), 40 * 16000)
    print(json.dumps({
        "result": "PASS", "candidate_budget": 0,
        "same_guid_is_physical_control_guarantee": False,
        "time_aligned_pair": False,
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
    pairs = build_pairs(cases, manifest["selection"]["selected_guids"])
    require(len(pairs) == 2, "two GUID pairs required")
    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "selection_performed": False,
        "tuning_performed": False,
        "same_guid_is_physical_control_guarantee": False,
        "time_aligned_pairs": False,
        "source_revision": manifest["source"]["revision"],
        "cases": cases,
        "pairs": pairs,
        "paired_summary": aggregate_pairs(pairs),
        "interpretation_rule": manifest["interpretation_rule"],
    }
    write_json(args.output / "same-guid-paired-result.json", payload)
    print(json.dumps({
        "output": str(args.output / "same-guid-paired-result.json"),
        "candidate_budget": 0, "cases": len(cases), "pairs": len(pairs),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
