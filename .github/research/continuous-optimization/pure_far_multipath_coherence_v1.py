#!/usr/bin/env python3
"""Candidate-zero multipath coherence aggregation for the frozen pure-far corpus."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import statistics
import subprocess
import sys
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


def percentile(values: list[float], q: float) -> float | None:
    clean = sorted(float(v) for v in values if math.isfinite(float(v)))
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
    x_values = [x for x, _ in pairs]
    y_values = [y for _, y in pairs]
    xr = average_ranks(x_values)
    yr = average_ranks(y_values)
    mx = statistics.mean(xr)
    my = statistics.mean(yr)
    num = sum((x - mx) * (y - my) for x, y in zip(xr, yr))
    dx = sum((x - mx) ** 2 for x in xr)
    dy = sum((y - my) ** 2 for y in yr)
    rho = None if dx <= 0.0 or dy <= 0.0 else num / math.sqrt(dx * dy)
    return {"count": len(pairs), "rho": rho}


def import_module(path: Path):
    spec = importlib.util.spec_from_file_location("frozen_route_probe", path)
    require(spec is not None and spec.loader is not None, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "pure-far-multipath-coherence-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget")
    selection = manifest["selection"]
    require(selection["all_complete_pairs"] is True, "all-pair selection required")
    require(selection["subsampling_allowed"] is False, "subsampling forbidden")
    require(selection["result_dependent_selection"] is False, "result-dependent selection forbidden")
    geometry = manifest["analysis_geometry"]
    require(int(geometry["baseline_aec_tail_ms"]) == 96, "frozen baseline AEC tail")
    require(int(geometry["sample_rate_hz"]) == 16000, "frozen sample rate")
    require(int(geometry["tail_samples"]) == 1536, "frozen tail samples")
    require(geometry["fft_rule"] == "next_power_of_two(2*tail_samples)", "FFT rule")
    require(int(geometry["expected_fft_size"]) == 4096, "frozen FFT size")
    require(geometry["window"] == "rectangular", "window geometry")
    require(int(geometry["overlap_samples"]) == 0, "overlap geometry")
    observation = manifest["observation_method"]
    require(observation["coherence_threshold"] is None, "coherence threshold forbidden")
    require(observation["threshold_search_performed"] is False, "threshold search forbidden")
    require(observation["filter_fit_performed"] is False, "filter fit forbidden")
    require(observation["signal_correction_applied"] is False, "signal correction forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority required")
    require(all(authority[key] is False for key in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority forbidden")


def validate_inventory(inventory: dict, manifest: dict) -> list[dict]:
    selection = manifest["selection"]
    require(inventory.get("source_revision") == manifest["source"]["revision"], "inventory source revision")
    require(inventory.get("selection_rule") == selection["rule"], "inventory selection rule")
    cases = inventory.get("cases")
    require(isinstance(cases, list) and cases, "non-empty inventory required")
    require(len(cases) == int(selection["expected_complete_pair_count"]), "pair count drift")
    require(int(inventory["total_lfs_bytes"]) == int(selection["expected_total_lfs_bytes"]), "LFS bytes drift")
    require(inventory["selection_fingerprint_sha256"] == selection["expected_selection_fingerprint_sha256"],
            "selection fingerprint drift")
    guids = [case["guid"] for case in cases]
    require(guids == sorted(guids) and len(guids) == len(set(guids)), "sorted unique GUIDs required")
    for case in cases:
        require(case["scenario"] == "farend_singletalk", "pure-far scenario required")
        for role in ("mic", "lpb"):
            meta = case[role]
            require("with_movement" not in meta["path"], "movement file forbidden")
            require(len(meta["sha256"]) == 64 and int(meta["size"]) > 0, "hash-bound source required")
    return cases


def validate_coverage(coverage: dict, inventory: dict) -> dict[str, dict]:
    require(coverage.get("status") == "DIAGNOSTIC_ONLY", "coverage diagnostic status")
    require(coverage.get("candidate_budget") == 0, "coverage candidate budget")
    require(coverage.get("all_complete_pairs_executed") is True, "coverage all-pair execution")
    require(coverage.get("subsampling_performed") is False, "coverage subsampling forbidden")
    require(coverage.get("threshold_search_performed") is False, "coverage threshold search forbidden")
    require(coverage["inventory"]["selection_fingerprint_sha256"] == inventory["selection_fingerprint_sha256"],
            "coverage fingerprint mismatch")
    cases = coverage.get("cases")
    require(isinstance(cases, list) and len(cases) == len(inventory["cases"]), "coverage case count")
    by_guid = {case["guid"]: case for case in cases}
    require(len(by_guid) == len(cases), "coverage GUID uniqueness")
    require(set(by_guid) == {case["guid"] for case in inventory["cases"]}, "coverage GUID set mismatch")
    return by_guid


def run_case(case: dict, coverage_case: dict, source_root: Path, route_module,
             coherence_probe: Path, manifest: dict) -> dict:
    mic_path = verify_file(source_root, case["mic"])
    render_path = verify_file(source_root, case["lpb"])
    route = route_module.analyze_case(
        mic_path,
        render_path,
        int(manifest["route_alignment"]["max_delay_ms"]),
        float(manifest["route_alignment"]["initial_delay_ms"]),
    )
    delay_samples = int(route["best_delay_samples"])
    tail_samples = int(manifest["analysis_geometry"]["tail_samples"])
    with tempfile.TemporaryDirectory(prefix="pure-far-multipath-") as tmp:
        result_path = Path(tmp) / "coherence.json"
        subprocess.run([
            str(coherence_probe), str(mic_path), str(render_path), str(delay_samples),
            str(tail_samples), str(result_path)
        ], check=True)
        coherence = load_json(result_path)
    require(coherence.get("schema_version") == 1 and coherence.get("diagnostic_only") is True,
            "coherence probe shape")
    require(int(coherence["sample_rate_hz"]) == int(manifest["analysis_geometry"]["sample_rate_hz"]),
            "coherence sample rate drift")
    require(int(coherence["tail_samples"]) == tail_samples, "coherence tail drift")
    require(int(coherence["official_rating"]["fft_size"]) == int(manifest["analysis_geometry"]["expected_fft_size"]),
            "coherence FFT drift")
    require(coherence["fft_rule"] == manifest["analysis_geometry"]["fft_rule"], "coherence FFT rule drift")
    require(coherence["window"] == manifest["analysis_geometry"]["window"], "coherence window drift")
    require(int(coherence["overlap_samples"]) == int(manifest["analysis_geometry"]["overlap_samples"]),
            "coherence overlap drift")
    require(coherence["all_frequency_bins_used"] is True, "all-frequency observation required")
    require(coherence["acoustic_threshold_used"] is False, "acoustic threshold forbidden")
    metrics = coverage_case["metrics"]
    return {
        "guid": case["guid"],
        "scenario": case["scenario"],
        "predecessor": {
            "double_talk_fraction": metrics["double_talk_fraction"],
            "double_talk_given_far_fraction": metrics["double_talk_given_far_fraction"],
            "far_frames_smoothed_ratio_median": metrics["far_frames_ratio"]["smoothed_ratio_median"],
            "far_frames_instant_ratio_median": metrics["far_frames_ratio"]["instant_ratio_median"],
            "aec_converged_fraction": metrics["aec_converged_fraction"],
        },
        "route_alignment": {
            "best_delay_samples": delay_samples,
            "best_delay_ms": route["best_delay_ms"],
            "best_score_squared": route["best_score_squared"],
            "runner_up_score_squared": route["runner_up_score_squared"],
            "peak_ratio": route["peak_ratio"],
        },
        "coherence": coherence,
    }


def aggregate(cases: list[dict]) -> dict:
    def path_values(path: tuple[str, ...]) -> list[float]:
        values = []
        for case in cases:
            value = case
            for key in path:
                value = value[key]
            values.append(value)
        return values

    fields = {
        "double_talk_fraction": ("predecessor", "double_talk_fraction"),
        "far_frames_smoothed_ratio_median": ("predecessor", "far_frames_smoothed_ratio_median"),
        "route_best_delay_ms": ("route_alignment", "best_delay_ms"),
        "route_best_score_squared": ("route_alignment", "best_score_squared"),
        "mic_energy_weighted_coherence": ("coherence", "official_rating", "mic_energy_weighted_coherence"),
        "render_energy_weighted_coherence": ("coherence", "official_rating", "render_energy_weighted_coherence"),
        "unweighted_mean_coherence": ("coherence", "official_rating", "unweighted_mean_coherence"),
        "coherence_median": ("coherence", "official_rating", "coherence_median"),
        "coherence_p25": ("coherence", "official_rating", "coherence_p25"),
        "coherence_p75": ("coherence", "official_rating", "coherence_p75"),
        "mic_weighted_half_delta": (
            "coherence", "split_half_delta", "mic_energy_weighted_coherence_abs_delta"
        ),
        "render_weighted_half_delta": (
            "coherence", "split_half_delta", "render_energy_weighted_coherence_abs_delta"
        ),
    }
    distributions = {name: distribution(path_values(path)) for name, path in fields.items()}
    dtd = path_values(fields["double_talk_fraction"])
    smoothed = path_values(fields["far_frames_smoothed_ratio_median"])
    associations = {
        "dtd_vs_mic_energy_weighted_coherence": spearman(dtd, path_values(fields["mic_energy_weighted_coherence"])),
        "dtd_vs_render_energy_weighted_coherence": spearman(dtd, path_values(fields["render_energy_weighted_coherence"])),
        "dtd_vs_unweighted_mean_coherence": spearman(dtd, path_values(fields["unweighted_mean_coherence"])),
        "dtd_vs_coherence_median": spearman(dtd, path_values(fields["coherence_median"])),
        "dtd_vs_mic_weighted_half_delta": spearman(dtd, path_values(fields["mic_weighted_half_delta"])),
        "smoothed_ratio_vs_mic_energy_weighted_coherence": spearman(
            smoothed, path_values(fields["mic_energy_weighted_coherence"])
        ),
        "smoothed_ratio_vs_render_energy_weighted_coherence": spearman(
            smoothed, path_values(fields["render_energy_weighted_coherence"])
        ),
        "coherence_vs_route_best_score_squared": spearman(
            path_values(fields["mic_energy_weighted_coherence"]), path_values(fields["route_best_score_squared"])
        ),
    }
    return {"distributions": distributions, "spearman_associations": associations}


def self_test() -> None:
    result = spearman([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0])
    require(result["rho"] is not None and abs(result["rho"] - 1.0) < 1.0e-12, "Spearman +1 self-test")
    result = spearman([1.0, 2.0, 3.0, 4.0], [40.0, 30.0, 20.0, 10.0])
    require(result["rho"] is not None and abs(result["rho"] + 1.0) < 1.0e-12, "Spearman -1 self-test")
    ranks = average_ranks([1.0, 1.0, 3.0])
    require(ranks == [1.5, 1.5, 3.0], "average-rank tie self-test")
    print("pure-far multipath coherence analyzer self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--coverage-result", type=Path)
    parser.add_argument("--route-probe", type=Path)
    parser.add_argument("--coherence-probe", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = [args.manifest, args.inventory, args.source_root, args.coverage_result,
                args.route_probe, args.coherence_probe, args.output]
    if any(value is None for value in required):
        parser.error("manifest/inventory/source-root/coverage-result/route-probe/coherence-probe/output are required")

    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    inventory = load_json(args.inventory)
    cases = validate_inventory(inventory, manifest)
    coverage = load_json(args.coverage_result)
    coverage_by_guid = validate_coverage(coverage, inventory)
    route_module = import_module(args.route_probe)

    rows = [
        run_case(case, coverage_by_guid[case["guid"]], args.source_root, route_module,
                 args.coherence_probe, manifest)
        for case in cases
    ]
    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "source_revision": manifest["source"]["revision"],
        "inventory": {
            "complete_pair_count": inventory["complete_pair_count"],
            "total_lfs_bytes": inventory["total_lfs_bytes"],
            "selection_fingerprint_sha256": inventory["selection_fingerprint_sha256"],
        },
        "baseline_geometry": manifest["analysis_geometry"],
        "all_complete_pairs_executed": True,
        "subsampling_performed": False,
        "coherence_threshold_used": False,
        "threshold_search_performed": False,
        "filter_fit_performed": False,
        "signal_correction_applied": False,
        "candidate_selection_performed": False,
        "tuning_performed": False,
        "segment_boundary_limitation_acknowledged": True,
        "cases": rows,
        "aggregate": aggregate(rows),
        "interpretation_rule": manifest["interpretation_rule"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "pure-far-multipath-coherence-result.json", payload)
    summary = args.output / "summary.md"
    with summary.open("w", encoding="utf-8") as fh:
        fh.write("## Pure-far multipath coherence v1\n\n")
        fh.write("- Authority: `research-diagnostic-only`\n")
        fh.write("- Candidate budget: `0`\n")
        fh.write(f"- Complete pairs: `{inventory['complete_pair_count']}`\n")
        fh.write(f"- Selection fingerprint: `{inventory['selection_fingerprint_sha256']}`\n")
        fh.write(f"- Frozen baseline AEC span: `{manifest['analysis_geometry']['baseline_aec_tail_ms']} ms / {manifest['analysis_geometry']['tail_samples']} samples`\n")
        fh.write(f"- FFT geometry: `{manifest['analysis_geometry']['expected_fft_size']}` / rectangular / no overlap\n")
        fh.write("- Coherence threshold: `none`\n")
        fh.write("- FIR/filter fit: `not performed`\n")
        fh.write("- Signal correction: `not applied`\n")
        fh.write("\n### Cross-case distributions\n")
        for key, dist in sorted(payload["aggregate"]["distributions"].items()):
            fh.write(f"- {key}: `{json.dumps(dist, sort_keys=True)}`\n")
        fh.write("\n### Descriptive Spearman associations\n")
        for key, assoc in sorted(payload["aggregate"]["spearman_associations"].items()):
            fh.write(f"- {key}: `{json.dumps(assoc, sort_keys=True)}`\n")
        fh.write("\nNo association is a classifier, threshold, tuning rule, candidate selector, or physical-cause attribution.\n")
    print(json.dumps(payload["aggregate"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
