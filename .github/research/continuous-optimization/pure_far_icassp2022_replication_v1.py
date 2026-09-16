#!/usr/bin/env python3
"""Candidate-zero ICASSP2022 pure-far replication using frozen Activity metrics."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import subprocess
import tempfile
from pathlib import Path

SUPPORTED_RATES = {8000, 16000, 24000, 32000, 48000}


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
    spec = importlib.util.spec_from_file_location("frozen_pure_far_coverage", path)
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
    require(manifest.get("investigation_id") == "pure-far-icassp2022-replication-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget")
    selection = manifest["selection"]
    require(selection["all_complete_pairs"] is True, "all-pair selection required")
    require(selection["movement_included"] is False, "movement forbidden")
    require(selection["optimized"] is False, "optimized selection forbidden")
    require(selection["result_dependent_selection"] is False, "result-dependent selection forbidden")
    require(selection["subsampling_allowed"] is False, "subsampling forbidden")
    require(selection["inventory_frozen"] is True, "inventory must be frozen before acoustic execution")
    require(isinstance(selection["expected_complete_pair_count"], int) and selection["expected_complete_pair_count"] > 0,
            "frozen pair count required")
    require(isinstance(selection["expected_total_lfs_bytes"], int) and selection["expected_total_lfs_bytes"] > 0,
            "frozen byte count required")
    fingerprint = selection["expected_selection_fingerprint_sha256"]
    require(isinstance(fingerprint, str) and len(fingerprint) == 64, "frozen fingerprint required")
    observation = manifest["observation_method"]
    require(observation["full_clip_observation"] is True, "full clip observation required")
    require(observation["numeric_tolerance_added"] is False, "numeric tolerance forbidden")
    require(observation["selection_threshold"] is None, "selection threshold forbidden")
    require(observation["threshold_search_performed"] is False, "threshold search forbidden")
    require(observation["candidate_selection"] is False, "candidate selection forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority required")
    require(all(authority[key] is False for key in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority forbidden")


def validate_inventory(inventory: dict, manifest: dict) -> list[dict]:
    require(inventory.get("source_revision") == manifest["source"]["revision"], "source revision drift")
    require(inventory.get("source_tree_sha") == manifest["source"]["dataset_tree_sha"], "dataset tree drift")
    require(inventory.get("selection_rule") == manifest["selection"]["rule"], "selection rule drift")
    cases = inventory.get("cases")
    require(isinstance(cases, list) and cases, "non-empty inventory required")
    selection = manifest["selection"]
    require(len(cases) == inventory["complete_pair_count"] == selection["expected_complete_pair_count"], "pair count drift")
    require(inventory["total_lfs_bytes"] == selection["expected_total_lfs_bytes"], "LFS bytes drift")
    require(inventory["selection_fingerprint_sha256"] == selection["expected_selection_fingerprint_sha256"],
            "selection fingerprint drift")
    guids = [case["guid"] for case in cases]
    require(guids == sorted(guids) and len(guids) == len(set(guids)), "sorted unique GUIDs required")
    for case in cases:
        require(case["scenario"] == "farend-singletalk", "ICASSP2022 pure-far scenario required")
        for role in ("lpb", "mic"):
            meta = case[role]
            require("with-movement" not in meta["path"], "movement path forbidden")
            require(meta["path"].endswith(f"_farend-singletalk_{role}.wav"), "exact no-movement suffix required")
            require(len(meta["sha256"]) == 64 and int(meta["size"]) > 0, "hash-bound LFS object required")
    return cases


def run_case(case: dict, source_root: Path, probe: Path, helper, constants: dict) -> dict:
    mic_path = helper.verify_file(source_root, case["mic"])
    render_path = helper.verify_file(source_root, case["lpb"])
    mic_rate, mic = helper.read_wav(mic_path)
    render_rate, render = helper.read_wav(render_path)
    require(mic_rate == render_rate, f"paired WAV rate mismatch: {case['guid']}")
    require(mic_rate in SUPPORTED_RATES, f"unsupported paired WAV rate: {case['guid']}/{mic_rate}")
    frame_samples = mic_rate // 100
    common = min(len(mic), len(render))
    require(common >= 2 * frame_samples, f"clip too short: {case['guid']}")
    mic = mic[:common]
    render = render[:common]
    with tempfile.TemporaryDirectory(prefix="pure-far-icassp2022-") as tmp:
        root = Path(tmp)
        mic_pcm = root / "mic.pcm"
        render_pcm = root / "render.pcm"
        trace = root / "trace.jsonl"
        helper.write_pcm16(mic_pcm, mic)
        helper.write_pcm16(render_pcm, render)
        subprocess.run([str(probe), str(mic_rate), str(mic_pcm), str(render_pcm), str(trace)], check=True)
        rows = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows and all(int(row["frame"]) == i for i, row in enumerate(rows)), "contiguous probe trace required")
    end_frame = min(len(rows), common // frame_samples)
    require(end_frame > 0, "no complete analysis frames")
    metrics = helper.summarize_rows(rows, 0, end_frame, constants)
    return {
        "guid": case["guid"],
        "scenario": case["scenario"],
        "source_sample_rate_hz": mic_rate,
        "resampling_performed": False,
        "clip_duration_seconds": common / mic_rate,
        "analysis_start_seconds": 0.0,
        "analysis_duration_seconds": end_frame * 0.01,
        "analysis_interval_is_full_common_clip": True,
        "analysis_interval_is_exact_onset_label": False,
        "metrics": metrics,
    }


def aggregate(cases: list[dict]) -> dict:
    def values(path: tuple[str, ...]) -> list[float]:
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
        "independent_dt_on_raw_mismatch_count": ("metrics", "independent_dt_on_raw_mismatch_count"),
        "independent_dt_hold_raw_mismatch_count": ("metrics", "independent_dt_hold_raw_mismatch_count"),
    }
    distributions = {name: distribution(values(path)) for name, path in fields.items()}
    dtd = values(fields["double_talk_fraction"])
    return {
        "sample_rate_hz_counts": {
            str(rate): sum(1 for case in cases if int(case["source_sample_rate_hz"]) == rate)
            for rate in sorted(SUPPORTED_RATES)
            if any(int(case["source_sample_rate_hz"]) == rate for case in cases)
        },
        "distributions": distributions,
        "spearman_associations": {
            "dtd_vs_far_frames_smoothed_ratio_median": spearman(dtd, values(fields["far_frames_smoothed_ratio_median"])),
            "dtd_vs_far_frames_instant_ratio_median": spearman(dtd, values(fields["far_frames_instant_ratio_median"])),
            "dtd_vs_high_ref_far_instant_ratio_median": spearman(dtd, values(fields["high_ref_far_instant_ratio_median"])),
        },
        "cases_with_nonzero_public_dtd": sum(
            1 for case in cases if float(case["metrics"]["double_talk_fraction"]) > 0.0
        ),
    }


def self_test() -> None:
    positive = spearman([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    require(positive["rho"] is not None and abs(positive["rho"] - 1.0) < 1.0e-12, "Spearman self-test")
    require(average_ranks([1.0, 1.0, 3.0]) == [1.5, 1.5, 3.0], "tie-rank self-test")
    print("pure-far ICASSP2022 replication analyzer self-test: OK")


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
    if any(value is None for value in required):
        parser.error("manifest/inventory/source-root/probe/helper/output are required")

    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    inventory = load_json(args.inventory)
    cases = validate_inventory(inventory, manifest)
    helper = import_module(args.helper)
    constants = manifest["baseline_code_lock"]["activity_constants_observed_not_tuned"]
    rows = [run_case(case, args.source_root, args.probe, helper, constants) for case in cases]
    unexplained = sum(
        int(case["metrics"]["independent_dt_on_unexplained_mismatch_count"]) +
        int(case["metrics"]["independent_dt_hold_unexplained_mismatch_count"])
        for case in rows
    )
    require(unexplained == 0, "unexplained independent evidence mismatches")
    raw_mismatch = sum(
        int(case["metrics"]["independent_dt_on_raw_mismatch_count"]) +
        int(case["metrics"]["independent_dt_hold_raw_mismatch_count"])
        for case in rows
    )
    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "source_revision": manifest["source"]["revision"],
        "source_tree_sha": manifest["source"]["dataset_tree_sha"],
        "inventory": {
            "complete_pair_count": inventory["complete_pair_count"],
            "total_lfs_bytes": inventory["total_lfs_bytes"],
            "selection_fingerprint_sha256": inventory["selection_fingerprint_sha256"],
        },
        "rating_formula": manifest["source"]["rating_formula"],
        "all_complete_pairs_executed": True,
        "subsampling_performed": False,
        "full_common_clip_observation": True,
        "resampling_performed": False,
        "threshold_search_performed": False,
        "numeric_tolerance_added": False,
        "tuning_performed": False,
        "candidate_selection_performed": False,
        "independent_evidence_raw_mismatch_total": raw_mismatch,
        "independent_evidence_unexplained_mismatch_total": unexplained,
        "cases": rows,
        "aggregate": aggregate(rows),
        "interpretation_rule": manifest["interpretation_rule"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "pure-far-icassp2022-replication-result.json", payload)
    summary = args.output / "summary.md"
    with summary.open("w", encoding="utf-8") as fh:
        fh.write("## Pure-far ICASSP2022 replication v1\n\n")
        fh.write("- Authority: `research-diagnostic-only`\n")
        fh.write("- Candidate budget: `0`\n")
        fh.write(f"- Complete no-movement pairs: `{inventory['complete_pair_count']}`\n")
        fh.write(f"- Total LFS bytes: `{inventory['total_lfs_bytes']}`\n")
        fh.write(f"- Selection fingerprint: `{inventory['selection_fingerprint_sha256']}`\n")
        fh.write("- Observation interval: `full common-length clip`\n")
        fh.write("- Resampling: `false`; exact source rate is passed to pipeline\n")
        fh.write(f"- Source-rate counts: `{json.dumps(payload['aggregate']['sample_rate_hz_counts'], sort_keys=True)}`\n")
        fh.write("- Subsampling: `false`\n")
        fh.write(f"- Independent evidence raw mismatch total: `{raw_mismatch}`\n")
        fh.write("- Independent evidence unexplained mismatch total: `0`\n")
        fh.write(f"- Cases with nonzero public DTD: `{payload['aggregate']['cases_with_nonzero_public_dtd']}`\n")
        fh.write("\n### Cross-case distributions\n")
        for key, dist in sorted(payload["aggregate"]["distributions"].items()):
            fh.write(f"- {key}: `{json.dumps(dist, sort_keys=True)}`\n")
        fh.write("\n### Descriptive Spearman associations\n")
        for key, assoc in sorted(payload["aggregate"]["spearman_associations"].items()):
            fh.write(f"- {key}: `{json.dumps(assoc, sort_keys=True)}`\n")
        fh.write("\nNo cross-dataset difference or association is a threshold, classifier, ranking, tuning rule, or source-candidate selector.\n")
    print(json.dumps(payload["aggregate"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())