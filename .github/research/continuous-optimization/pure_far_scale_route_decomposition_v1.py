#!/usr/bin/env python3
"""Candidate-zero scale-vs-route decomposition for the frozen pure-far corpus."""
from __future__ import annotations

import argparse
import array
import hashlib
import importlib.util
import json
import math
import statistics
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


def verify_file(root: Path, meta: dict) -> Path:
    path = root / meta["path"]
    require(path.is_file(), f"missing materialized LFS object: {path}")
    require(path.stat().st_size == int(meta["size"]), f"size mismatch: {path}")
    require(sha256_file(path) == meta["sha256"], f"sha256 mismatch: {path}")
    return path


def read_mono16(path: Path) -> tuple[int, list[int]]:
    with wave.open(str(path), "rb") as wav:
        require(wav.getnchannels() == 1, f"mono WAV required: {path}")
        require(wav.getsampwidth() == 2, f"PCM16 WAV required: {path}")
        require(wav.getcomptype() == "NONE", f"uncompressed PCM required: {path}")
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    values = array.array("h")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    return rate, list(values)


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


def power_dbfs(energy: float, count: int) -> float | None:
    if count <= 0 or energy <= 0.0:
        return None
    mean_square = energy / count
    full_scale_square = 32768.0 * 32768.0
    return 10.0 * math.log10(mean_square / full_scale_square)


def ratio_db(numerator_energy: float, denominator_energy: float) -> float | None:
    if numerator_energy <= 0.0 or denominator_energy <= 0.0:
        return None
    return 10.0 * math.log10(numerator_energy / denominator_energy)


def scalar_db(scale: float) -> float | None:
    magnitude = abs(scale)
    if magnitude <= 0.0:
        return None
    return 20.0 * math.log10(magnitude)


def projection_stats(mic: list[int], render: list[int], delay: int, start: int, end: int) -> dict:
    first = max(int(start), int(delay), 0)
    last = min(int(end), len(mic), len(render) + int(delay))
    require(last - first >= 160, "aligned interval too short")
    xx = 0.0
    yy = 0.0
    xy = 0.0
    for i in range(first, last):
        x = float(render[i - delay])
        y = float(mic[i])
        xx += x * x
        yy += y * y
        xy += x * y
    count = last - first
    require(xx > 0.0 and yy > 0.0, "non-zero aligned energy required")
    scale = xy / xx
    score = (xy * xy) / (xx * yy)
    score = min(1.0, max(0.0, score))
    residual_fraction = 1.0 - score
    scale_mag_db = scalar_db(scale)
    rms_ratio = ratio_db(yy, xx)
    return {
        "sample_count": count,
        "start_sample": first,
        "end_sample": last,
        "mic_rms_dbfs": power_dbfs(yy, count),
        "render_rms_dbfs": power_dbfs(xx, count),
        "mic_render_rms_ratio_db": rms_ratio,
        "aligned_scalar": scale,
        "aligned_scalar_sign": 1 if scale > 0.0 else (-1 if scale < 0.0 else 0),
        "aligned_scalar_magnitude_db": scale_mag_db,
        "aligned_score_squared": score,
        "scalar_projection_residual_energy_fraction": residual_fraction,
        "noncoherent_excess_db": None if rms_ratio is None or scale_mag_db is None else rms_ratio - scale_mag_db,
    }


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    pos = 0
    while pos < len(order):
        end = pos + 1
        while end < len(order) and values[order[end]] == values[order[pos]]:
            end += 1
        rank = (pos + 1 + end) / 2.0
        for k in range(pos, end):
            ranks[order[k]] = rank
        pos = end
    return ranks


def pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(x) != len(y):
        return None
    mx = statistics.fmean(x)
    my = statistics.fmean(y)
    xx = sum((v - mx) * (v - mx) for v in x)
    yy = sum((v - my) * (v - my) for v in y)
    if xx <= 0.0 or yy <= 0.0:
        return None
    xy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return xy / math.sqrt(xx * yy)


def spearman(pairs: list[tuple[float | None, float | None]]) -> dict:
    clean = [
        (float(a), float(b))
        for a, b in pairs
        if a is not None and b is not None and math.isfinite(float(a)) and math.isfinite(float(b))
    ]
    if len(clean) < 3:
        return {"count": len(clean), "rho": None}
    x = [a for a, _ in clean]
    y = [b for _, b in clean]
    return {"count": len(clean), "rho": pearson(average_ranks(x), average_ranks(y))}


def load_route_module(path: Path):
    spec = importlib.util.spec_from_file_location("frozen_aec_route_probe", path)
    require(spec is not None and spec.loader is not None, "route probe import spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "pure-far-scale-route-decomposition-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget")
    require(manifest["selection"]["all_complete_pairs"] is True, "all-pair selection required")
    require(manifest["selection"]["optimized"] is False, "optimized selection forbidden")
    require(manifest["selection"]["result_dependent_selection"] is False, "result-dependent selection forbidden")
    require(manifest["selection"]["subsampling_allowed"] is False, "subsampling forbidden")
    provenance = manifest["provenance_limitations"]
    require(provenance["blind_test_guid_sidecar_metadata_present"] is False, "sidecar metadata must remain absent")
    require(provenance["per_guid_hardware_gain_available"] is False, "hardware gain must remain unavailable")
    require(provenance["physical_device_gain_attribution_authorized"] is False, "physical attribution forbidden")
    method = manifest["observation_method"]
    require(method["route_probe_decision_booleans_used"] is False, "route decision booleans forbidden")
    require(method["gain_correction_applied"] is False, "gain correction forbidden")
    require(method["signal_normalization_applied"] is False, "signal normalization forbidden")
    require(method["threshold_search_performed"] is False, "threshold search forbidden")
    require(method["selection_threshold"] is None, "selection threshold forbidden")
    require(method["candidate_selection"] is False and method["tuning_authority"] is False,
            "candidate/tuning authority forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority required")
    require(all(authority[k] is False for k in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority forbidden")


def validate_inventory(inventory: dict, manifest: dict) -> list[dict]:
    selection = manifest["selection"]
    require(inventory.get("source_revision") == manifest["source"]["revision"], "inventory revision")
    require(inventory.get("selection_rule") == selection["rule"], "inventory selection rule")
    require(int(inventory.get("complete_pair_count", -1)) == int(selection["expected_complete_pair_count"]),
            "inventory pair count")
    require(int(inventory.get("total_lfs_bytes", -1)) == int(selection["expected_total_lfs_bytes"]),
            "inventory byte count")
    require(inventory.get("selection_fingerprint_sha256") == selection["expected_selection_fingerprint_sha256"],
            "inventory fingerprint")
    cases = inventory.get("cases")
    require(isinstance(cases, list) and len(cases) == int(selection["expected_complete_pair_count"]),
            "inventory cases")
    guids = [case["guid"] for case in cases]
    require(guids == sorted(guids) and len(set(guids)) == len(guids), "sorted unique GUIDs")
    return cases


def validate_predecessor(result: dict, manifest: dict, inventory: dict) -> dict[str, dict]:
    require(result.get("investigation_id") == "pure-far-activity-ratio-coverage-v1", "predecessor identity")
    require(result.get("status") == "DIAGNOSTIC_ONLY", "predecessor status")
    require(result.get("candidate_budget") == 0, "predecessor candidate budget")
    require(result.get("all_complete_pairs_executed") is True, "predecessor all-pair execution")
    require(result.get("subsampling_performed") is False, "predecessor subsampling")
    require(result.get("threshold_search_performed") is False, "predecessor threshold search")
    require(result.get("tuning_performed") is False, "predecessor tuning")
    require(result.get("candidate_selection_performed") is False, "predecessor candidate selection")
    require(result.get("source_revision") == manifest["source"]["revision"], "predecessor revision")
    require(result["inventory"]["complete_pair_count"] == inventory["complete_pair_count"], "predecessor count")
    require(result["inventory"]["selection_fingerprint_sha256"] == inventory["selection_fingerprint_sha256"],
            "predecessor fingerprint")
    cases = result.get("cases")
    require(isinstance(cases, list) and len(cases) == inventory["complete_pair_count"], "predecessor cases")
    by_guid = {case["guid"]: case for case in cases}
    require(len(by_guid) == len(cases), "unique predecessor GUIDs")
    return by_guid


def analyze_case(route_module, route_probe_path: Path, source_root: Path, case: dict,
                 predecessor_case: dict, manifest: dict) -> dict:
    del route_probe_path
    mic_path = verify_file(source_root, case["mic"])
    render_path = verify_file(source_root, case["lpb"])
    mic_rate, mic = read_mono16(mic_path)
    render_rate, render = read_mono16(render_path)
    require(mic_rate == render_rate == 16000, f"16 kHz pair required: {case['guid']}")
    common = min(len(mic), len(render))
    require(common >= mic_rate * 6, f"clip too short for diagnostic: {case['guid']}")
    mic = mic[:common]
    render = render[:common]

    route = route_module.analyze_case(
        mic_path,
        render_path,
        int(manifest["observation_method"]["route_probe_max_delay_ms"]),
        float(manifest["observation_method"]["route_probe_initial_delay_ms"]),
    )
    require(route.get("diagnostic_only") is True, "route probe diagnostic-only contract")
    delay = int(route["best_delay_samples"])
    rating_start = common - (common // 2)
    full = projection_stats(mic, render, delay, rating_start, common)
    aligned_start = int(full["start_sample"])
    aligned_end = int(full["end_sample"])
    split = aligned_start + (aligned_end - aligned_start) // 2
    first_half = projection_stats(mic, render, delay, aligned_start, split)
    second_half = projection_stats(mic, render, delay, split, aligned_end)
    first_db = first_half["aligned_scalar_magnitude_db"]
    second_db = second_half["aligned_scalar_magnitude_db"]
    scale_delta = None if first_db is None or second_db is None else abs(first_db - second_db)

    predecessor_metrics = predecessor_case["metrics"]
    return {
        "guid": case["guid"],
        "scenario": case["scenario"],
        "clip_duration_seconds": common / mic_rate,
        "official_rating_start_seconds": rating_start / mic_rate,
        "predecessor": {
            "double_talk_fraction": predecessor_metrics["double_talk_fraction"],
            "double_talk_given_far_fraction": predecessor_metrics["double_talk_given_far_fraction"],
            "double_talk_given_high_direct_reference_far_fraction": predecessor_metrics[
                "double_talk_given_high_direct_reference_far_fraction"
            ],
            "far_frames_smoothed_ratio_median": predecessor_metrics["far_frames_ratio"]["smoothed_ratio_median"],
            "far_frames_instant_ratio_median": predecessor_metrics["far_frames_ratio"]["instant_ratio_median"],
            "aec_converged_fraction": predecessor_metrics["aec_converged_fraction"],
        },
        "route": {
            "best_delay_samples": route["best_delay_samples"],
            "best_delay_ms": route["best_delay_ms"],
            "best_score_squared": route["best_score_squared"],
            "runner_up_score_squared": route["runner_up_score_squared"],
            "peak_ratio": route["peak_ratio"],
        },
        "official_rating_projection": full,
        "scale_stability": {
            "first_half_scalar_magnitude_db": first_db,
            "second_half_scalar_magnitude_db": second_db,
            "absolute_half_delta_db": scale_delta,
            "first_half_score_squared": first_half["aligned_score_squared"],
            "second_half_score_squared": second_half["aligned_score_squared"],
        },
    }


def aggregate(cases: list[dict]) -> dict:
    paths = {
        "double_talk_fraction": ("predecessor", "double_talk_fraction"),
        "far_frames_smoothed_ratio_median": ("predecessor", "far_frames_smoothed_ratio_median"),
        "route_best_delay_ms": ("route", "best_delay_ms"),
        "route_best_score_squared": ("route", "best_score_squared"),
        "route_peak_ratio": ("route", "peak_ratio"),
        "mic_rms_dbfs": ("official_rating_projection", "mic_rms_dbfs"),
        "render_rms_dbfs": ("official_rating_projection", "render_rms_dbfs"),
        "mic_render_rms_ratio_db": ("official_rating_projection", "mic_render_rms_ratio_db"),
        "aligned_scalar_magnitude_db": ("official_rating_projection", "aligned_scalar_magnitude_db"),
        "aligned_score_squared": ("official_rating_projection", "aligned_score_squared"),
        "scalar_projection_residual_energy_fraction": (
            "official_rating_projection", "scalar_projection_residual_energy_fraction"
        ),
        "noncoherent_excess_db": ("official_rating_projection", "noncoherent_excess_db"),
        "scale_half_delta_db": ("scale_stability", "absolute_half_delta_db"),
    }

    def get(case: dict, path: tuple[str, ...]):
        value = case
        for key in path:
            value = value[key]
        return value

    distributions = {name: distribution([get(case, path) for case in cases]) for name, path in paths.items()}

    dtd = [case["predecessor"]["double_talk_fraction"] for case in cases]
    smoothed = [case["predecessor"]["far_frames_smoothed_ratio_median"] for case in cases]
    correlations = {
        "dtd_vs_aligned_scalar_magnitude_db": spearman(list(zip(
            dtd, [case["official_rating_projection"]["aligned_scalar_magnitude_db"] for case in cases]
        ))),
        "dtd_vs_mic_render_rms_ratio_db": spearman(list(zip(
            dtd, [case["official_rating_projection"]["mic_render_rms_ratio_db"] for case in cases]
        ))),
        "dtd_vs_aligned_score_squared": spearman(list(zip(
            dtd, [case["official_rating_projection"]["aligned_score_squared"] for case in cases]
        ))),
        "dtd_vs_scalar_projection_residual_energy_fraction": spearman(list(zip(
            dtd, [case["official_rating_projection"]["scalar_projection_residual_energy_fraction"] for case in cases]
        ))),
        "dtd_vs_noncoherent_excess_db": spearman(list(zip(
            dtd, [case["official_rating_projection"]["noncoherent_excess_db"] for case in cases]
        ))),
        "dtd_vs_route_best_delay_ms": spearman(list(zip(
            dtd, [case["route"]["best_delay_ms"] for case in cases]
        ))),
        "dtd_vs_route_best_score_squared": spearman(list(zip(
            dtd, [case["route"]["best_score_squared"] for case in cases]
        ))),
        "dtd_vs_route_peak_ratio": spearman(list(zip(
            dtd, [case["route"]["peak_ratio"] for case in cases]
        ))),
        "dtd_vs_scale_half_delta_db": spearman(list(zip(
            dtd, [case["scale_stability"]["absolute_half_delta_db"] for case in cases]
        ))),
        "smoothed_ratio_vs_aligned_scalar_magnitude_db": spearman(list(zip(
            smoothed, [case["official_rating_projection"]["aligned_scalar_magnitude_db"] for case in cases]
        ))),
        "smoothed_ratio_vs_aligned_score_squared": spearman(list(zip(
            smoothed, [case["official_rating_projection"]["aligned_score_squared"] for case in cases]
        ))),
    }
    return {"distributions": distributions, "spearman_associations": correlations}


def write_summary(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    agg = result["aggregate"]
    with path.open("w", encoding="utf-8") as fh:
        fh.write("## Pure-far scale/route decomposition v1\n\n")
        fh.write(f"- Authority: `{result['authority']}`\n")
        fh.write(f"- Candidate budget: `{result['candidate_budget']}`\n")
        fh.write(f"- Cases: `{len(result['cases'])}` (all complete pairs; no subsampling)\n")
        fh.write(f"- Selection fingerprint: `{result['inventory']['selection_fingerprint_sha256']}`\n")
        fh.write("- Gain correction applied: `false`; threshold search: `false`; candidate selection: `false`\n")
        fh.write("- Upstream per-GUID device/capture-gain sidecar metadata: `absent`\n\n")
        fh.write("### Descriptive distributions\n\n")
        for name, dist in agg["distributions"].items():
            fh.write(
                f"- `{name}`: n={dist['count']}, min={dist['min']}, median={dist['median']}, "
                f"p95={dist['p95']}, max={dist['max']}\n"
            )
        fh.write("\n### Spearman associations (descriptive only)\n\n")
        for name, item in agg["spearman_associations"].items():
            fh.write(f"- `{name}`: n={item['count']}, rho={item['rho']}\n")
        fh.write("\nNo association is a detector boundary, gain correction, source-candidate selector, or physical device-gain attribution.\n")


def self_test() -> None:
    state = 7
    render = []
    for _ in range(12000):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        render.append((((state >> 16) & 0xFFFF) - 32768) // 2)
    delay = 80
    mic = [0] * delay + [int(round(0.5 * x)) for x in render[:-delay]]
    stats = projection_stats(mic, render, delay, 2000, len(mic))
    require(abs(stats["aligned_scalar"] - 0.5) < 1e-3, "self-test scale")
    require(stats["aligned_score_squared"] > 0.999, "self-test coherence")
    require(stats["scalar_projection_residual_energy_fraction"] < 1e-3, "self-test residual")
    rho = spearman([(1.0, 10.0), (2.0, 20.0), (3.0, 30.0), (4.0, 40.0)])
    require(rho["rho"] is not None and abs(rho["rho"] - 1.0) < 1e-12, "self-test Spearman")
    print("pure-far scale/route decomposition self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--predecessor-result", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--route-probe", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not all((args.manifest, args.inventory, args.predecessor_result, args.source_root, args.route_probe, args.output)):
        parser.error("manifest/inventory/predecessor-result/source-root/route-probe/output are required")

    manifest = load_json(args.manifest)
    inventory = load_json(args.inventory)
    predecessor = load_json(args.predecessor_result)
    validate_manifest(manifest)
    cases = validate_inventory(inventory, manifest)
    predecessor_by_guid = validate_predecessor(predecessor, manifest, inventory)
    route_module = load_route_module(args.route_probe)
    require(hasattr(route_module, "analyze_case"), "route probe analyze_case required")

    output_cases = []
    for case in cases:
        require(case["guid"] in predecessor_by_guid, f"predecessor GUID missing: {case['guid']}")
        output_cases.append(analyze_case(
            route_module, args.route_probe, args.source_root, case, predecessor_by_guid[case["guid"]], manifest
        ))

    result = {
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
        "all_complete_pairs_executed": True,
        "subsampling_performed": False,
        "route_probe_decision_booleans_used": False,
        "gain_correction_applied": False,
        "signal_normalization_applied": False,
        "threshold_search_performed": False,
        "candidate_selection_performed": False,
        "tuning_performed": False,
        "physical_device_gain_attribution_performed": False,
        "provenance_limitations": manifest["provenance_limitations"],
        "cases": output_cases,
        "aggregate": aggregate(output_cases),
        "interpretation_rule": manifest["interpretation_rule"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / "pure-far-scale-route-decomposition-result.json"
    write_json(result_path, result)
    write_summary(args.output / "summary.md", result)
    print(json.dumps({
        "output": str(result_path),
        "cases": len(output_cases),
        "candidate_budget": 0,
        "gain_correction_applied": False,
        "candidate_selection_performed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
