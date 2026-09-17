#!/usr/bin/env python3
"""Candidate-zero pure-far Sync interpolation energy diagnostic."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import subprocess
import tempfile
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


def import_module(path: Path):
    spec = importlib.util.spec_from_file_location("frozen_pure_far_helper", path)
    require(spec is not None and spec.loader is not None, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def percentile(values: list[float], q: float) -> float | None:
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


def distribution(values: list[float]) -> dict:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return {
        "count": len(clean),
        "min": min(clean) if clean else None,
        "median": statistics.median(clean) if clean else None,
        "p05": percentile(clean, 0.05),
        "p95": percentile(clean, 0.95),
        "max": max(clean) if clean else None,
    }


def average_ranks(values: list[float]) -> list[float]:
    indexed = sorted((float(value), index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][0] == indexed[i][0]:
            j += 1
        rank = ((i + 1) + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][1]] = rank
        i = j
    return ranks


def spearman(xs: list[float], ys: list[float]) -> dict:
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys)
             if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))]
    if len(pairs) < 2:
        return {"count": len(pairs), "rho": None}
    xr = average_ranks([x for x, _ in pairs])
    yr = average_ranks([y for _, y in pairs])
    mx = statistics.mean(xr)
    my = statistics.mean(yr)
    num = sum((x - mx) * (y - my) for x, y in zip(xr, yr))
    dx = sum((x - mx) ** 2 for x in xr)
    dy = sum((y - my) ** 2 for y in yr)
    return {"count": len(pairs), "rho": None if dx <= 0.0 or dy <= 0.0 else num / math.sqrt(dx * dy)}


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "pure-far-sync-interpolation-energy-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget")
    require(manifest["selection"]["subsampling_allowed"] is False, "subsampling forbidden")
    require(manifest["selection"]["result_dependent_selection"] is False, "result selection forbidden")
    obs = manifest["observation_method"]
    require(obs["same_delay_position"] is True, "same-delay comparison required")
    require(obs["signal_correction_applied"] is False, "signal correction forbidden")
    require(obs["delay_search_performed"] is False, "delay search forbidden")
    require(obs["threshold_search_performed"] is False, "threshold search forbidden")
    require(obs["selection_threshold"] is None, "selection threshold forbidden")
    require(obs["candidate_selection"] is False, "candidate selection forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority required")
    require(all(authority[k] is False for k in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority forbidden")


def validate_inventory(inventory: dict, manifest: dict) -> list[dict]:
    selection = manifest["selection"]
    require(inventory["source_revision"] == manifest["source"]["revision"], "source revision drift")
    require(inventory["source_tree_sha"] == manifest["source"]["dataset_tree_sha"], "tree drift")
    require(inventory["complete_pair_count"] == selection["expected_complete_pair_count"], "pair-count drift")
    require(inventory["total_lfs_bytes"] == selection["expected_total_lfs_bytes"], "byte-count drift")
    require(inventory["selection_fingerprint_sha256"] == selection["expected_selection_fingerprint_sha256"],
            "selection fingerprint drift")
    cases = inventory.get("cases")
    require(isinstance(cases, list) and len(cases) == selection["expected_complete_pair_count"], "case list drift")
    guids = [c["guid"] for c in cases]
    require(guids == sorted(guids) and len(set(guids)) == len(guids), "sorted unique GUIDs required")
    return cases


def summarize_interpolation(rows: list[dict]) -> dict:
    valid = [r for r in rows if int(r["reference_start_valid"]) != 0]
    valid_far = [r for r in valid if int(r["far_end_active"]) != 0]
    require(valid_far, "valid far frames required")
    dtd_valid_far = sum(int(r["double_talk_active"]) != 0 for r in valid_far) / len(valid_far)
    return {
        "valid_reference_frame_fraction": len(valid) / len(rows),
        "valid_far_frame_count": len(valid_far),
        "public_dtd_given_valid_far_fraction": dtd_valid_far,
        "interpolation_energy_ratio": distribution([r["interpolation_energy_ratio"] for r in valid_far]),
        "interpolation_energy_delta_db": distribution([r["interpolation_energy_delta_db"] for r in valid_far]),
        "nearest_mic_reference_ratio": distribution([r["nearest_mic_reference_ratio"] for r in valid_far]),
        "synced_instant_ratio": distribution([r["instant_ratio"] for r in valid_far]),
        "abs_fractional_offset": distribution([abs(float(r["fractional_offset"])) for r in valid_far]),
        "sync_reconstruction_max_abs_error": distribution(
            [r["sync_reconstruction_max_abs_error"] for r in valid_far]
        ),
    }


def run_case(case: dict, source_root: Path, probe: Path, helper, manifest: dict) -> dict:
    mic_path = helper.verify_file(source_root, case["mic"])
    render_path = helper.verify_file(source_root, case["lpb"])
    mic_rate, mic = helper.read_wav(mic_path)
    render_rate, render = helper.read_wav(render_path)
    require(mic_rate == render_rate == int(manifest["source"]["source_rate_hz"]),
            f"source-rate drift: {case['guid']}")
    common = min(len(mic), len(render))
    require(common >= mic_rate, f"clip too short: {case['guid']}")
    mic = mic[:common]
    render = render[:common]
    with tempfile.TemporaryDirectory(prefix="pure-far-sync-interp-") as tmp:
        root = Path(tmp)
        mic_pcm = root / "mic.pcm"
        render_pcm = root / "render.pcm"
        trace = root / "trace.jsonl"
        helper.write_pcm16(mic_pcm, mic)
        helper.write_pcm16(render_pcm, render)
        subprocess.run([str(probe), str(mic_rate), str(mic_pcm), str(render_pcm), str(trace)], check=True)
        rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows and all(int(row["frame"]) == i for i, row in enumerate(rows)), "contiguous trace required")
    require(all(int(row["source_rate_hz"]) == mic_rate for row in rows), "source-rate trace drift")
    require(all(int(row["internal_rate_hz"]) == int(manifest["source"]["internal_rate_hz"]) for row in rows),
            "internal-rate trace drift")
    frame_samples = mic_rate // 100
    end_frame = min(len(rows), common // frame_samples)
    rows = rows[:end_frame]
    constants = manifest["baseline_code_lock"]["activity_constants_observed_not_tuned"]
    activity = helper.summarize_rows(rows, 0, len(rows), constants)
    return {
        "guid": case["guid"],
        "source_sample_rate_hz": mic_rate,
        "internal_sample_rate_hz": int(manifest["source"]["internal_rate_hz"]),
        "clip_duration_seconds": common / mic_rate,
        "analysis_interval": "full common-length clip",
        "activity": activity,
        "sync_interpolation": summarize_interpolation(rows),
    }


def aggregate(cases: list[dict]) -> dict:
    dtd = [c["activity"]["double_talk_fraction"] for c in cases]
    interp_db = [c["sync_interpolation"]["interpolation_energy_delta_db"]["median"] for c in cases]
    interp_ratio = [c["sync_interpolation"]["interpolation_energy_ratio"]["median"] for c in cases]
    nearest_ratio = [c["sync_interpolation"]["nearest_mic_reference_ratio"]["median"] for c in cases]
    synced_ratio = [c["sync_interpolation"]["synced_instant_ratio"]["median"] for c in cases]
    frac = [c["sync_interpolation"]["abs_fractional_offset"]["median"] for c in cases]
    recon = [c["sync_interpolation"]["sync_reconstruction_max_abs_error"]["max"] for c in cases]
    return {
        "case_count": len(cases),
        "cases_with_nonzero_public_dtd": sum(float(v) > 0.0 for v in dtd),
        "distributions": {
            "public_dtd_fraction": distribution(dtd),
            "median_interpolation_energy_delta_db": distribution(interp_db),
            "median_interpolation_energy_ratio": distribution(interp_ratio),
            "median_nearest_mic_reference_ratio": distribution(nearest_ratio),
            "median_synced_instant_ratio": distribution(synced_ratio),
            "median_abs_fractional_offset": distribution(frac),
            "per_case_max_sync_reconstruction_abs_error": distribution(recon),
        },
        "spearman_associations": {
            "dtd_vs_interpolation_energy_delta_db": spearman(dtd, interp_db),
            "dtd_vs_interpolation_energy_ratio": spearman(dtd, interp_ratio),
            "dtd_vs_nearest_mic_reference_ratio": spearman(dtd, nearest_ratio),
            "dtd_vs_synced_instant_ratio": spearman(dtd, synced_ratio),
            "dtd_vs_abs_fractional_offset": spearman(dtd, frac),
            "interpolation_delta_db_vs_abs_fractional_offset": spearman(interp_db, frac),
        },
    }


def self_test() -> None:
    require(average_ranks([1.0, 1.0, 3.0]) == [1.5, 1.5, 3.0], "rank self-test")
    assoc = spearman([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    require(assoc["rho"] is not None and abs(assoc["rho"] - 1.0) < 1.0e-12, "Spearman self-test")
    d = distribution([1.0, 2.0, 3.0])
    require(d["median"] == 2.0 and d["count"] == 3, "distribution self-test")
    print("pure-far sync interpolation energy analyzer self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--helper", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = [args.manifest, args.inventory, args.source_root, args.probe, args.helper, args.output]
    if any(v is None for v in required):
        parser.error("manifest/inventory/source-root/probe/helper/output are required")

    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    inventory = load_json(args.inventory)
    inventory_cases = validate_inventory(inventory, manifest)
    helper = import_module(args.helper)
    cases = [run_case(case, args.source_root, args.probe, helper, manifest) for case in inventory_cases]
    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "inventory": {
            "complete_pair_count": inventory["complete_pair_count"],
            "total_lfs_bytes": inventory["total_lfs_bytes"],
            "selection_fingerprint_sha256": inventory["selection_fingerprint_sha256"],
        },
        "same_delay_position": True,
        "signal_correction_applied": False,
        "delay_search_performed": False,
        "threshold_search_performed": False,
        "candidate_selection_performed": False,
        "cases": cases,
        "aggregate": aggregate(cases),
        "interpretation_rule": manifest["interpretation_rule"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "pure-far-sync-interpolation-energy-result.json", payload)
    with (args.output / "summary.md").open("w", encoding="utf-8") as fh:
        fh.write("## Pure-far Sync interpolation energy v1\n\n")
        fh.write("- Authority: `research-diagnostic-only`\n")
        fh.write("- Candidate budget: `0`\n")
        fh.write(f"- Frozen complete pairs: `{inventory['complete_pair_count']}`\n")
        fh.write("- Comparison: same Sync delay position, nearest integer sample vs unchanged fractional interpolation\n")
        fh.write("- Signal correction applied: `false`\n")
        fh.write("- Delay/threshold search: `false`\n\n")
        for key, value in sorted(payload["aggregate"]["distributions"].items()):
            fh.write(f"- {key}: `{json.dumps(value, sort_keys=True)}`\n")
        fh.write("\n### Descriptive Spearman associations\n")
        for key, value in sorted(payload["aggregate"]["spearman_associations"].items()):
            fh.write(f"- {key}: `{json.dumps(value, sort_keys=True)}`\n")
        fh.write("\nNo association authorizes Sync changes, DTD tuning, gain normalization, or source-candidate selection.\n")
    print(json.dumps(payload["aggregate"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
