#!/usr/bin/env python3
"""Candidate-zero coverage of pure-far Activity ratio behavior across all complete real pairs."""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import statistics
import subprocess
import sys
import tempfile
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


def verify_file(root: Path, meta: dict) -> Path:
    path = root / meta["path"]
    require(path.is_file(), f"missing materialized LFS object: {path}")
    require(path.stat().st_size == int(meta["size"]), f"size mismatch: {path}")
    require(sha256_file(path) == meta["sha256"], f"sha256 mismatch: {path}")
    return path


def read_wav(path: Path) -> tuple[int, list[int]]:
    with wave.open(str(path), "rb") as wav:
        require(wav.getnchannels() == 1, f"mono WAV required: {path}")
        require(wav.getsampwidth() == 2, f"PCM16 WAV required: {path}")
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    values = array.array("h")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    return rate, list(values)


def write_pcm16(path: Path, samples: list[int]) -> None:
    values = array.array("h", samples)
    if sys.byteorder != "little":
        values.byteswap()
    path.write_bytes(values.tobytes())


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
    pos = (len(clean) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return clean[lo]
    return clean[lo] * (hi - pos) + clean[hi] * (pos - lo)


def distribution(values) -> dict:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return {
        "count": len(clean),
        "min": min(clean) if clean else None,
        "median": statistics.median(clean) if clean else None,
        "p95": percentile(clean, 0.95),
        "max": max(clean) if clean else None,
    }


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "pure-far-activity-ratio-coverage-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget")
    require(manifest["selection"]["all_complete_pairs"] is True, "all-pair selection required")
    require(manifest["selection"]["optimized"] is False, "selection must not be optimized")
    require(manifest["selection"]["result_dependent_selection"] is False, "result-dependent selection forbidden")
    require(manifest["observation_method"]["selection_threshold"] is None, "selection threshold forbidden")
    require(manifest["observation_method"]["candidate_selection"] is False, "candidate selection forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority required")
    require(all(authority[k] is False for k in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority forbidden")


def validate_inventory(inventory: dict, manifest: dict) -> list[dict]:
    require(inventory.get("source_revision") == manifest["source"]["revision"], "inventory source revision")
    require(inventory.get("selection_rule") == manifest["selection"]["rule"], "inventory selection rule")
    cases = inventory.get("cases")
    require(isinstance(cases, list) and cases, "non-empty inventory required")
    require(len(cases) == int(inventory["complete_pair_count"]), "inventory count mismatch")
    require(len(cases) <= int(manifest["ci_resource_guard"]["max_complete_pairs"]), "pair resource ceiling")
    require(int(inventory["total_lfs_bytes"]) <= int(manifest["ci_resource_guard"]["max_total_lfs_bytes"]),
            "byte resource ceiling")
    guids = [case["guid"] for case in cases]
    require(guids == sorted(guids) and len(guids) == len(set(guids)), "sorted unique GUID inventory required")
    for case in cases:
        require(case["scenario"] == "farend_singletalk", "pure-far no-movement scenario required")
        for role in ("lpb", "mic"):
            meta = case[role]
            require("with_movement" not in meta["path"], "movement file forbidden")
            require(meta["path"].endswith(f"_farend_singletalk_{role}.wav"), "exact no-movement suffix required")
            require(len(meta["sha256"]) == 64 and int(meta["size"]) > 0, "LFS object binding required")
    canonical = json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    require(hashlib.sha256(canonical).hexdigest() == inventory["selection_fingerprint_sha256"],
            "inventory fingerprint mismatch")
    return cases


def summarize_rows(rows: list[dict], start_frame: int, end_frame: int, constants: dict) -> dict:
    part = rows[max(0, start_frame):min(len(rows), end_frame)]
    require(part, "empty official rating interval")
    far_threshold = float(constants["far_end_threshold"])
    dt_ratio = float(constants["double_talk_ratio"])
    instant_on = float(constants["instant_on_multiplier"]) * dt_ratio
    instant_hold = float(constants["instant_hold_multiplier"]) * dt_ratio

    mismatch_on = 0
    mismatch_hold = 0
    for row in part:
        require(math.isclose(float(row["far_end_threshold"]), far_threshold, rel_tol=1e-6, abs_tol=1e-12),
                "far threshold drift")
        require(math.isclose(float(row["double_talk_ratio"]), dt_ratio, rel_tol=1e-6, abs_tol=1e-9),
                "DTD ratio drift")
        require(int(row["hangover_frames"]) == int(constants["hangover_frames"]), "hangover drift")
        independent_instant = float(row["metric_mic_energy"]) / (float(row["direct_reference_energy"]) + 1.0e-12)
        independent_smoothed = float(row["smoothed_mic_energy"]) / (float(row["smoothed_reference_energy"]) + 1.0e-12)
        independent_on = bool(row["far_end_active"]) and independent_smoothed > dt_ratio and independent_instant > instant_on
        independent_hold = bool(row["far_end_active"]) and independent_instant > instant_hold
        mismatch_on += independent_on != bool(row["dt_on_evidence"])
        mismatch_hold += independent_hold != bool(row["dt_hold_evidence"])
    require(mismatch_on == 0 and mismatch_hold == 0, "independent Activity evidence mismatch")

    far_rows = [r for r in part if r["far_end_active"]]
    dtd_rows = [r for r in part if r["double_talk_active"]]
    high_ref_far_rows = [
        r for r in part
        if r["far_end_active"] and float(r["direct_reference_energy"]) >= far_threshold
    ]

    def ratio_summary(group: list[dict]) -> dict:
        return {
            "smoothed_ratio_median": median([r["smoothed_ratio"] for r in group]),
            "smoothed_ratio_p95": percentile([r["smoothed_ratio"] for r in group], 0.95),
            "instant_ratio_median": median([
                float(r["metric_mic_energy"]) / (float(r["direct_reference_energy"]) + 1.0e-12)
                for r in group
            ]),
            "instant_ratio_p95": percentile([
                float(r["metric_mic_energy"]) / (float(r["direct_reference_energy"]) + 1.0e-12)
                for r in group
            ], 0.95),
        }

    return {
        "frames": len(part),
        "far_end_fraction": fraction([bool(r["far_end_active"]) for r in part]),
        "double_talk_fraction": fraction([bool(r["double_talk_active"]) for r in part]),
        "double_talk_given_far_fraction": fraction([bool(r["double_talk_active"]) for r in far_rows]),
        "dt_on_given_far_fraction": fraction([bool(r["dt_on_evidence"]) for r in far_rows]),
        "dt_hold_given_far_fraction": fraction([bool(r["dt_hold_evidence"]) for r in far_rows]),
        "high_direct_reference_far_fraction_of_far": None if not far_rows else len(high_ref_far_rows) / len(far_rows),
        "double_talk_given_high_direct_reference_far_fraction": fraction([
            bool(r["double_talk_active"]) for r in high_ref_far_rows
        ]),
        "dt_on_given_high_direct_reference_far_fraction": fraction([
            bool(r["dt_on_evidence"]) for r in high_ref_far_rows
        ]),
        "dt_hold_given_high_direct_reference_far_fraction": fraction([
            bool(r["dt_hold_evidence"]) for r in high_ref_far_rows
        ]),
        "far_frames_ratio": ratio_summary(far_rows),
        "high_direct_reference_far_frames_ratio": ratio_summary(high_ref_far_rows),
        "double_talk_frames_ratio": ratio_summary(dtd_rows),
        "aec_converged_fraction": fraction([bool(r["aec_converged"]) for r in part]),
        "independent_dt_on_mismatch_count": mismatch_on,
        "independent_dt_hold_mismatch_count": mismatch_hold,
    }


def run_case(probe: Path, source_root: Path, case: dict, constants: dict) -> dict:
    mic_path = verify_file(source_root, case["mic"])
    lpb_path = verify_file(source_root, case["lpb"])
    mic_rate, mic = read_wav(mic_path)
    lpb_rate, lpb = read_wav(lpb_path)
    require(mic_rate == lpb_rate == 16000, f"16 kHz paired WAV required: {case['guid']}")
    common = min(len(mic), len(lpb))
    require(common >= 320, f"clip too short: {case['guid']}")
    mic = mic[:common]
    lpb = lpb[:common]
    with tempfile.TemporaryDirectory(prefix="pure-far-coverage-") as tmp:
        tmp_path = Path(tmp)
        mic_pcm = tmp_path / "mic.pcm"
        render_pcm = tmp_path / "render.pcm"
        trace = tmp_path / "trace.jsonl"
        write_pcm16(mic_pcm, mic)
        write_pcm16(render_pcm, lpb)
        subprocess.run([str(probe), str(mic_pcm), str(render_pcm), str(trace)], check=True)
        rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows and all(int(row["frame"]) == i for i, row in enumerate(rows)), "contiguous probe trace required")
    frame_samples = mic_rate // 100
    rating_length = common // 2
    rating_start = common - rating_length
    start_frame = (rating_start + frame_samples - 1) // frame_samples
    end_frame = min(len(rows), common // frame_samples)
    metrics = summarize_rows(rows, start_frame, end_frame, constants)
    return {
        "guid": case["guid"],
        "scenario": case["scenario"],
        "clip_duration_seconds": common / mic_rate,
        "official_rating_start_seconds": rating_start / mic_rate,
        "analysis_duration_seconds": (end_frame - start_frame) * 0.01,
        "metrics": metrics,
    }


def aggregate(cases: list[dict]) -> dict:
    def values(path: tuple[str, ...]):
        result = []
        for case in cases:
            value = case
            for key in path:
                value = value[key]
            result.append(value)
        return result

    fields = {
        "far_end_fraction": ("metrics", "far_end_fraction"),
        "double_talk_fraction": ("metrics", "double_talk_fraction"),
        "double_talk_given_far_fraction": ("metrics", "double_talk_given_far_fraction"),
        "dt_on_given_far_fraction": ("metrics", "dt_on_given_far_fraction"),
        "dt_hold_given_far_fraction": ("metrics", "dt_hold_given_far_fraction"),
        "high_direct_reference_far_fraction_of_far": ("metrics", "high_direct_reference_far_fraction_of_far"),
        "double_talk_given_high_direct_reference_far_fraction": (
            "metrics", "double_talk_given_high_direct_reference_far_fraction"
        ),
        "far_frames_smoothed_ratio_median": ("metrics", "far_frames_ratio", "smoothed_ratio_median"),
        "far_frames_instant_ratio_median": ("metrics", "far_frames_ratio", "instant_ratio_median"),
        "high_ref_far_instant_ratio_median": (
            "metrics", "high_direct_reference_far_frames_ratio", "instant_ratio_median"
        ),
        "aec_converged_fraction": ("metrics", "aec_converged_fraction"),
    }
    return {name: distribution(values(path)) for name, path in fields.items()}


def self_test() -> None:
    assert percentile([0.0, 10.0], 0.5) == 5.0
    assert distribution([1.0, 2.0, 3.0])["median"] == 2.0
    print(json.dumps({"result": "PASS", "candidate_budget": 0, "subsampling": False}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(all((args.probe, args.manifest, args.inventory, args.source_root, args.output)), "all paths required")
    require(args.probe.is_file(), "research probe missing")
    manifest = load_json(args.manifest)
    inventory = load_json(args.inventory)
    validate_manifest(manifest)
    inventory_cases = validate_inventory(inventory, manifest)
    require(not args.output.exists() or (args.output.is_dir() and not any(args.output.iterdir())),
            "output must be absent or empty")
    args.output.mkdir(parents=True, exist_ok=True)

    constants = manifest["baseline_code_lock"]["activity_constants_observed_not_tuned"]
    cases = [run_case(args.probe, args.source_root, case, constants) for case in inventory_cases]
    mismatch_total = sum(
        c["metrics"]["independent_dt_on_mismatch_count"] + c["metrics"]["independent_dt_hold_mismatch_count"]
        for c in cases
    )
    require(mismatch_total == 0, "coverage independent evidence mismatch")
    anchors = {}
    for guid in ("49IIo03GZ0CYQOmeA3A0BA", "7GTxyTksSUqCnP5y0ILG4A"):
        match = next((case for case in cases if case["guid"] == guid), None)
        if match is not None:
            anchors[guid] = match

    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "selection_rule": manifest["selection"]["rule"],
        "all_complete_pairs_executed": True,
        "subsampling_performed": False,
        "threshold_search_performed": False,
        "tuning_performed": False,
        "candidate_selection_performed": False,
        "source_revision": manifest["source"]["revision"],
        "inventory": {
            "complete_pair_count": inventory["complete_pair_count"],
            "total_lfs_bytes": inventory["total_lfs_bytes"],
            "selection_fingerprint_sha256": inventory["selection_fingerprint_sha256"],
        },
        "independent_evidence_mismatch_total": mismatch_total,
        "cases": cases,
        "aggregate": aggregate(cases),
        "named_predecessor_anchors": anchors,
        "interpretation_rule": manifest["interpretation_rule"],
    }
    write_json(args.output / "pure-far-activity-ratio-coverage-result.json", payload)
    print(json.dumps({
        "output": str(args.output / "pure-far-activity-ratio-coverage-result.json"),
        "cases": len(cases),
        "candidate_budget": 0,
        "subsampling": False,
        "independent_evidence_mismatch_total": mismatch_total,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
