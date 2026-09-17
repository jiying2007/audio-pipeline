#!/usr/bin/env python3
"""Candidate-zero source-level shape diagnostic over frozen pure-far corpus."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
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
    spec = importlib.util.spec_from_file_location("frozen_helper", path)
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


def pcm_stats(samples: list[int]) -> dict:
    require(samples, "non-empty PCM required")
    n = len(samples)
    energy = sum((float(s) / 32768.0) ** 2 for s in samples) / n
    rms = math.sqrt(max(energy, 0.0))
    peak = max(abs(int(s)) for s in samples) / 32768.0
    rms_dbfs = 10.0 * math.log10(max(energy, 1.0e-30))
    crest_db = 20.0 * math.log10(max(peak, 1.0e-30) / max(rms, 1.0e-30))
    saturation_fraction = sum(abs(int(s)) >= 32767 for s in samples) / n
    return {
        "energy": energy,
        "rms_dbfs": rms_dbfs,
        "peak_abs": peak,
        "crest_db": crest_db,
        "exact_saturation_fraction": saturation_fraction,
    }


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "pure-far-source-level-shape-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget")
    require(manifest["selection"]["subsampling_allowed"] is False, "subsampling forbidden")
    require(manifest["selection"]["result_dependent_selection"] is False, "result-dependent selection forbidden")
    obs = manifest["observation_method"]
    require(obs["signal_correction_applied"] is False, "signal correction forbidden")
    require(obs["threshold_search_performed"] is False, "threshold search forbidden")
    require(obs["near_clipping_threshold_defined"] is False, "near-clipping threshold forbidden")


def validate_inventory(inventory: dict, manifest: dict) -> list[dict]:
    s = manifest["selection"]
    require(inventory["complete_pair_count"] == s["expected_complete_pair_count"], "pair-count drift")
    require(inventory["total_lfs_bytes"] == s["expected_total_lfs_bytes"], "byte-count drift")
    require(inventory["selection_fingerprint_sha256"] == s["expected_selection_fingerprint_sha256"],
            "selection fingerprint drift")
    cases = inventory["cases"]
    require(len(cases) == s["expected_complete_pair_count"], "case-count drift")
    return cases


def run_case(case: dict, source_root: Path, helper, predecessor_case: dict, manifest: dict) -> dict:
    mic_path = helper.verify_file(source_root, case["mic"])
    lpb_path = helper.verify_file(source_root, case["lpb"])
    mic_rate, mic = helper.read_wav(mic_path)
    lpb_rate, lpb = helper.read_wav(lpb_path)
    require(mic_rate == lpb_rate == int(manifest["source"]["source_rate_hz"]), "source-rate drift")
    common = min(len(mic), len(lpb))
    require(common > 0, "empty paired clip")
    mic = mic[:common]
    lpb = lpb[:common]
    mic_stats = pcm_stats(mic)
    lpb_stats = pcm_stats(lpb)
    ratio = mic_stats["energy"] / (lpb_stats["energy"] + 1.0e-30)
    predecessor_ratio = float(predecessor_case["source_full_clip"]["mic_lpb_ratio"])
    require(math.isclose(ratio, predecessor_ratio, rel_tol=2e-6, abs_tol=1e-12), "source-ratio cross-check drift")
    return {
        "guid": case["guid"],
        "source_sample_rate_hz": mic_rate,
        "clip_duration_seconds": common / mic_rate,
        "public_dtd_fraction": float(predecessor_case["activity"]["double_talk_fraction"]),
        "source_mic_lpb_ratio": ratio,
        "mic": mic_stats,
        "lpb": lpb_stats,
    }


def aggregate(cases: list[dict]) -> dict:
    dtd = [c["public_dtd_fraction"] for c in cases]
    mic_rms = [c["mic"]["rms_dbfs"] for c in cases]
    lpb_rms = [c["lpb"]["rms_dbfs"] for c in cases]
    mic_peak = [c["mic"]["peak_abs"] for c in cases]
    lpb_peak = [c["lpb"]["peak_abs"] for c in cases]
    mic_crest = [c["mic"]["crest_db"] for c in cases]
    lpb_crest = [c["lpb"]["crest_db"] for c in cases]
    mic_sat = [c["mic"]["exact_saturation_fraction"] for c in cases]
    lpb_sat = [c["lpb"]["exact_saturation_fraction"] for c in cases]
    ratio = [c["source_mic_lpb_ratio"] for c in cases]
    return {
        "case_count": len(cases),
        "distributions": {
            "public_dtd_fraction": distribution(dtd),
            "mic_rms_dbfs": distribution(mic_rms),
            "lpb_rms_dbfs": distribution(lpb_rms),
            "mic_peak_abs": distribution(mic_peak),
            "lpb_peak_abs": distribution(lpb_peak),
            "mic_crest_db": distribution(mic_crest),
            "lpb_crest_db": distribution(lpb_crest),
            "mic_exact_saturation_fraction": distribution(mic_sat),
            "lpb_exact_saturation_fraction": distribution(lpb_sat),
            "source_mic_lpb_ratio": distribution(ratio),
        },
        "spearman_associations": {
            "dtd_vs_mic_rms_dbfs": spearman(dtd, mic_rms),
            "dtd_vs_lpb_rms_dbfs": spearman(dtd, lpb_rms),
            "dtd_vs_mic_peak_abs": spearman(dtd, mic_peak),
            "dtd_vs_lpb_peak_abs": spearman(dtd, lpb_peak),
            "dtd_vs_mic_crest_db": spearman(dtd, mic_crest),
            "dtd_vs_lpb_crest_db": spearman(dtd, lpb_crest),
            "dtd_vs_mic_exact_saturation_fraction": spearman(dtd, mic_sat),
            "dtd_vs_lpb_exact_saturation_fraction": spearman(dtd, lpb_sat),
            "dtd_vs_source_mic_lpb_ratio": spearman(dtd, ratio),
            "source_ratio_vs_mic_rms_dbfs": spearman(ratio, mic_rms),
            "source_ratio_vs_lpb_rms_dbfs": spearman(ratio, lpb_rms),
        },
    }


def self_test() -> None:
    s = pcm_stats([0, 32767, -32768, 0])
    require(s["exact_saturation_fraction"] == 0.5, "exact saturation self-test")
    require(abs(spearman([1, 2, 3], [3, 2, 1])["rho"] + 1.0) < 1.0e-12, "Spearman self-test")
    print("pure-far source-level shape analyzer self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--predecessor-result", type=Path)
    parser.add_argument("--helper", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = [args.manifest, args.inventory, args.source_root, args.predecessor_result, args.helper, args.output]
    if any(v is None for v in required):
        parser.error("manifest/inventory/source-root/predecessor-result/helper/output are required")
    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    inventory = load_json(args.inventory)
    inventory_cases = validate_inventory(inventory, manifest)
    predecessor = load_json(args.predecessor_result)
    require(predecessor["inventory"]["complete_pair_count"] == len(inventory_cases), "predecessor count drift")
    pred_by_guid = {c["guid"]: c for c in predecessor["cases"]}
    require(len(pred_by_guid) == len(inventory_cases), "predecessor GUID drift")
    helper = import_module(args.helper)
    cases = [run_case(c, args.source_root, helper, pred_by_guid[c["guid"]], manifest) for c in inventory_cases]
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
        "signal_correction_applied": False,
        "threshold_search_performed": False,
        "near_clipping_threshold_defined": False,
        "candidate_selection_performed": False,
        "cases": cases,
        "aggregate": aggregate(cases),
        "interpretation_rule": manifest["interpretation_rule"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "pure-far-source-level-shape-result.json", payload)
    (args.output / "summary.md").write_text(
        "## Pure-far source-level shape v1\n\n" +
        "- Authority: `research-diagnostic-only`\n- Candidate budget: `0`\n" +
        "- Near-clipping threshold: `not defined`\n\n" +
        "### Distributions\n" + "\n".join(
            f"- {k}: `{json.dumps(v, sort_keys=True)}`" for k, v in sorted(payload["aggregate"]["distributions"].items())
        ) + "\n\n### Descriptive Spearman associations\n" + "\n".join(
            f"- {k}: `{json.dumps(v, sort_keys=True)}`" for k, v in sorted(payload["aggregate"]["spearman_associations"].items())
        ) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
