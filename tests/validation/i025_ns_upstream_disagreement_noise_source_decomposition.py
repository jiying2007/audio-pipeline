#!/usr/bin/env python3
"""I025 candidate-zero decomposition of high NS upstream evidence on disagreement-noise."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))
import run_validation_engine as engine  # type: ignore

WARMUP = 80
NOISE_DOMAINS = ("kitchen", "traffic", "living", "office", "cafeteria", "bus", "field")
NUMERIC_FEATURES = (
    "mirror_mean",
    "mirror_mean_suppression",
    "mirror_concentration",
    "posterior_max",
    "posterior_variance",
    "positive_bin_fraction",
    "slow_update_bin_fraction",
    "mean_post_ratio",
    "max_post_ratio",
    "ns_noise_rms_dbfs",
    "gap_to_concentration",
    "upstream_probability_mean3",
    "concentration_mean3",
    "slow_update_bin_fraction_mean3",
    "upstream_high_run_length",
    "disagreement_run_length",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def run_probe(probe: Path, pcm: Path) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [str(probe), str(pcm)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    require(bool(rows) and all(isinstance(row, dict) for row in rows),
            "probe output invalid")
    return rows


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def average_ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda pair: (pair[1], pair[0]))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg = ((i + 1) + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg
        i = j
    return ranks


def signed_auc(values: list[float], labels: list[int]) -> float | None:
    require(len(values) == len(labels), "AUC geometry mismatch")
    require(all(label in (0, 1) for label in labels), "AUC labels invalid")
    pos = sum(labels)
    neg = len(labels) - pos
    if not pos or not neg:
        return None
    ranks = average_ranks(values)
    rank_sum = sum(rank for rank, label in zip(ranks, labels) if label == 1)
    return (rank_sum - pos * (pos + 1) / 2.0) / (pos * neg)


def pairwise_profile(
    positive: list[dict[str, float]],
    negative: list[dict[str, float]],
) -> dict[str, Any]:
    labels = [1] * len(positive) + [0] * len(negative)
    output: dict[str, Any] = {}
    for feature in NUMERIC_FEATURES:
        p = [float(item[feature]) for item in positive]
        n = [float(item[feature]) for item in negative]
        values = p + n
        require(all(math.isfinite(value) for value in values),
                "non-finite feature: " + feature)
        auc = signed_auc(values, labels)
        separability = None if auc is None else max(auc, 1.0 - auc)
        direction = None
        if auc is not None:
            direction = (
                "higher_in_positive" if auc > 0.5
                else "lower_in_positive" if auc < 0.5
                else "no_direction"
            )
        output[feature] = {
            "positive_count": len(p),
            "negative_count": len(n),
            "signed_auc": auc,
            "separability_auc": separability,
            "direction": direction,
            "positive": {
                "p10": percentile(p, 0.10),
                "median": statistics.median(p) if p else None,
                "p90": percentile(p, 0.90),
            },
            "negative": {
                "p10": percentile(n, 0.10),
                "median": statistics.median(n) if n else None,
                "p90": percentile(n, 0.90),
            },
        }
    return output


def empty_population() -> list[dict[str, float]]:
    return []


def feature_values(
    rows: list[dict[str, Any]],
    index: int,
    *,
    upstream_guard: float,
    upstream_high_run_length: int,
    disagreement_run_length: int,
) -> dict[str, float]:
    row = rows[index]
    history = rows[max(0, index - 2):index + 1]
    gap = float(row["mirror_gap"])
    concentration = float(row["mirror_concentration"])
    result = {
        "mirror_mean": float(row["mirror_mean"]),
        "mirror_mean_suppression": float(row["mirror_mean_suppression"]),
        "mirror_concentration": concentration,
        "posterior_max": float(row["posterior_max"]),
        "posterior_variance": float(row["posterior_variance"]),
        "positive_bin_fraction": float(row["positive_bin_fraction"]),
        "slow_update_bin_fraction": float(row["slow_update_bin_fraction"]),
        "mean_post_ratio": float(row["mean_post_ratio"]),
        "max_post_ratio": float(row["max_post_ratio"]),
        "ns_noise_rms_dbfs": float(row["ns_noise_rms_dbfs"]),
        "gap_to_concentration": gap / concentration if concentration > 1.0e-9 else 0.0,
        "upstream_probability_mean3": statistics.fmean(
            float(item["upstream_probability"]) for item in history
        ),
        "concentration_mean3": statistics.fmean(
            float(item["mirror_concentration"]) for item in history
        ),
        "slow_update_bin_fraction_mean3": statistics.fmean(
            float(item["slow_update_bin_fraction"]) for item in history
        ),
        "upstream_high_run_length": float(upstream_high_run_length),
        "disagreement_run_length": float(disagreement_run_length),
    }
    require(all(math.isfinite(value) for value in result.values()),
            "non-finite upstream diagnostic")
    return result


def disagreement(row: dict[str, Any], upstream_guard: float) -> bool:
    return (
        float(row["upstream_probability"]) > upstream_guard
        and not int(row["local_guard_pass"])
    )


def upstream_high(row: dict[str, Any], upstream_guard: float) -> bool:
    return float(row["upstream_probability"]) > upstream_guard


def slice_keys(case: dict[str, Any]) -> list[str]:
    dimensions = case.get("dimensions", {})
    keys = [f"scenario:{case['scenario']}"]
    domain = dimensions.get("noise_domain")
    if domain is not None:
        keys.append(f"noise_domain:{domain}")
    if "snr_db" in dimensions:
        keys.append(f"snr_db:{float(dimensions['snr_db']):g}")
    if "reverb" in dimensions:
        keys.append(f"reverb:{str(bool(dimensions['reverb'])).lower()}")
    if dimensions.get("clean_only") is True:
        keys.append("clean_only:true")
    return keys


def analyze_case(
    probe: Path,
    corpus_path: Path,
    case: dict[str, Any],
    upstream_guard: float,
) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    require(mic is not None and labels_path is not None,
            "case missing mic audio or VAD labels")
    with tempfile.TemporaryDirectory(prefix="ap-i025-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    require(count > WARMUP, "case too short")
    rows = rows[WARMUP:count]
    labels = labels[WARMUP:count]

    populations = {
        "noise_disagreement": empty_population(),
        "speech_disagreement": empty_population(),
        "noise_reference": empty_population(),
    }
    mirror_gap_delta = 0.0
    vad_probability_delta = 0.0
    vad_active_mismatch = 0
    high_run = 0
    disagreement_run = 0

    for index, (row, label) in enumerate(zip(rows, labels)):
        require(label in (0, 1), "invalid label")
        upstream = float(row["upstream_probability"])
        mirror_gap = float(row["mirror_gap"])
        public_probability = float(row["public_shipping_probability"])
        shipping_probability = float(row["shipping_probability"])
        require(all(math.isfinite(value) for value in (
            upstream, mirror_gap, public_probability, shipping_probability,
        )), "non-finite mirror metric")
        mirror_gap_delta = max(mirror_gap_delta, abs(upstream - mirror_gap))
        vad_probability_delta = max(
            vad_probability_delta,
            abs(public_probability - shipping_probability),
        )
        vad_active_mismatch += int(
            int(row["public_shipping_active"]) != int(row["shipping_active"])
        )

        high = upstream_high(row, upstream_guard)
        disagree = disagreement(row, upstream_guard)
        high_run = high_run + 1 if high else 0
        disagreement_run = disagreement_run + 1 if disagree else 0
        features = feature_values(
            rows,
            index,
            upstream_guard=upstream_guard,
            upstream_high_run_length=high_run,
            disagreement_run_length=disagreement_run,
        )

        if label == 0 and disagree:
            populations["noise_disagreement"].append(features)
        elif label == 1 and disagree:
            populations["speech_disagreement"].append(features)
        elif label == 0:
            populations["noise_reference"].append(features)

    return {
        "case_id": str(case["case_id"]),
        "scenario": str(case["scenario"]),
        "dimensions": case.get("dimensions", {}),
        "populations": populations,
        "mirror": {
            "max_ns_upstream_gap_delta": mirror_gap_delta,
            "max_vad_probability_delta": vad_probability_delta,
            "vad_active_mismatch_frames": vad_active_mismatch,
        },
    }


def merge_populations(
    target: dict[str, list[dict[str, float]]],
    source: dict[str, list[dict[str, float]]],
) -> None:
    for name in target:
        target[name].extend(source[name])


def cross_slice_pairwise(
    slices: dict[str, dict[str, list[dict[str, float]]]],
    prefix: str,
    positive_name: str,
    negative_name: str,
) -> dict[str, Any]:
    selected = {
        key: populations for key, populations in slices.items()
        if key.startswith(prefix)
        and populations[positive_name]
        and populations[negative_name]
    }
    features: dict[str, Any] = {}
    for feature in NUMERIC_FEATURES:
        entries: dict[str, Any] = {}
        aucs: list[float] = []
        for key, populations in sorted(selected.items()):
            profile = pairwise_profile(
                populations[positive_name],
                populations[negative_name],
            )[feature]
            entries[key] = {
                "signed_auc": profile["signed_auc"],
                "separability_auc": profile["separability_auc"],
                "direction": profile["direction"],
            }
            if profile["separability_auc"] is not None:
                aucs.append(float(profile["separability_auc"]))
        features[feature] = {
            "slices": entries,
            "separability_auc_min": min(aucs) if aucs else None,
            "separability_auc_median": statistics.median(aucs) if aucs else None,
            "separability_auc_max": max(aucs) if aucs else None,
        }
    return {"numeric_features": features}


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    require(
        contract["investigation_id"]
        == "i025-ns-upstream-disagreement-noise-source-decomposition-v1",
        "contract identity drift",
    )
    authority = contract["fresh_diagnostic_authority"]
    expected_seeds = [int(seed) for seed in authority["seeds"]]
    require(len(corpora) == len(expected_seeds), "corpus count mismatch")
    require(
        {
            "diagnostic_execution_limit": authority["diagnostic_execution_limit"],
            "candidate_limit": authority["candidate_limit"],
            "confirmation_limit": authority["confirmation_limit"],
        }
        == {
            "diagnostic_execution_limit": 1,
            "candidate_limit": 0,
            "confirmation_limit": 0,
        },
        "I025 budget drift",
    )
    upstream_guard = float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    expected_lock = contract["dataset_authority"]["dataset_lock_sha256"]

    actual_seeds: list[int] = []
    global_populations = {
        "noise_disagreement": empty_population(),
        "speech_disagreement": empty_population(),
        "noise_reference": empty_population(),
    }
    slice_populations: dict[str, dict[str, list[dict[str, float]]]] = {}
    per_case: list[dict[str, Any]] = []
    max_ns_delta = 0.0
    max_vad_delta = 0.0
    vad_active_mismatch = 0
    domain_case_counts = {domain: {"mix": 0, "noise": 0} for domain in NOISE_DOMAINS}

    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        require(corpus.get("tier") == "research-validation",
                "public development tier drift")
        require(corpus.get("dataset_lock_sha256") == expected_lock,
                "dataset lock binding drift")
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        cases = corpus.get("cases", [])
        require(len(cases) == int(authority["expected_cases_per_seed"]),
                f"unexpected case count for seed={seed}")

        for case in cases:
            result = analyze_case(probe, corpus_path, case, upstream_guard)
            merge_populations(global_populations, result["populations"])
            per_case.append({
                "case_id": result["case_id"],
                "scenario": result["scenario"],
                "dimensions": result["dimensions"],
                "noise_disagreement_frames":
                    len(result["populations"]["noise_disagreement"]),
                "speech_disagreement_frames":
                    len(result["populations"]["speech_disagreement"]),
                "noise_reference_frames":
                    len(result["populations"]["noise_reference"]),
            })
            max_ns_delta = max(
                max_ns_delta,
                float(result["mirror"]["max_ns_upstream_gap_delta"]),
            )
            max_vad_delta = max(
                max_vad_delta,
                float(result["mirror"]["max_vad_probability_delta"]),
            )
            vad_active_mismatch += int(
                result["mirror"]["vad_active_mismatch_frames"]
            )

            for key in slice_keys(case):
                slice_populations.setdefault(key, {
                    "noise_disagreement": empty_population(),
                    "speech_disagreement": empty_population(),
                    "noise_reference": empty_population(),
                })
                merge_populations(
                    slice_populations[key], result["populations"]
                )

            dimensions = case.get("dimensions", {})
            domain = dimensions.get("noise_domain")
            if domain in domain_case_counts:
                if str(case["scenario"]).startswith("research-public-noisy"):
                    domain_case_counts[domain]["mix"] += 1
                elif case["scenario"] == "research-public-noise-only":
                    domain_case_counts[domain]["noise"] += 1

    require(actual_seeds == expected_seeds,
            f"fresh seed mismatch: {actual_seeds}")

    source_profile = pairwise_profile(
        global_populations["noise_disagreement"],
        global_populations["noise_reference"],
    )
    class_profile = pairwise_profile(
        global_populations["speech_disagreement"],
        global_populations["noise_disagreement"],
    )

    invalid_reasons: list[str] = []
    gates = contract["diagnostic_gates"]
    if len(per_case) < int(gates["minimum_total_cases"]):
        invalid_reasons.append("case_count")
    for name, gate in (
        ("noise_disagreement", "minimum_noise_disagreement_frames"),
        ("speech_disagreement", "minimum_speech_disagreement_frames"),
        ("noise_reference", "minimum_noise_reference_frames"),
    ):
        if len(global_populations[name]) < int(gates[gate]):
            invalid_reasons.append(name + "_count")
    if max_ns_delta > float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta > float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if vad_active_mismatch != int(gates["vad_shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("vad_active_mirror")

    domain_min = int(gates["minimum_per_domain_population_frames"])
    for domain in NOISE_DOMAINS:
        key = "noise_domain:" + domain
        populations = slice_populations.get(key)
        if populations is None:
            invalid_reasons.append("domain_population:" + domain)
        else:
            if len(populations["noise_disagreement"]) < domain_min:
                invalid_reasons.append("domain_noise_disagreement:" + domain)
            if len(populations["noise_reference"]) < domain_min:
                invalid_reasons.append("domain_noise_reference:" + domain)
        counts = domain_case_counts[domain]
        if counts["mix"] < int(authority["minimum_mix_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_mix_coverage:" + domain)
        if counts["noise"] < int(authority["minimum_noise_only_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_noise_coverage:" + domain)

    if invalid_reasons:
        decision = "I025_INPUT_INVALID_REVIEW_REQUIRED"
    elif global_populations["noise_disagreement"]:
        decision = "NS_UPSTREAM_DISAGREEMENT_NOISE_SOURCE_DECOMPOSED_REVIEW_REQUIRED"
    else:
        decision = "NS_UPSTREAM_DISAGREEMENT_NOISE_NOT_REPRODUCED_REVIEW_REQUIRED"

    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "dataset_id": contract["dataset_authority"]["dataset_id"],
        "fresh_diagnostic_seeds": actual_seeds,
        "diagnostic_execution_consumed": 1,
        "candidate_budget_consumed": 0,
        "confirmation_budget_consumed": 0,
        "population_counts": {
            name: len(values) for name, values in global_populations.items()
        },
        "shipping_mirror": {
            "max_ns_upstream_gap_delta": max_ns_delta,
            "max_vad_probability_delta": max_vad_delta,
            "vad_active_mismatch_frames": vad_active_mismatch,
        },
        "noise_disagreement_vs_noise_reference": source_profile,
        "speech_disagreement_vs_noise_disagreement": class_profile,
        "cross_domain_noise_source": cross_slice_pairwise(
            slice_populations,
            "noise_domain:",
            "noise_disagreement",
            "noise_reference",
        ),
        "cross_snr_noise_source": cross_slice_pairwise(
            slice_populations,
            "snr_db:",
            "noise_disagreement",
            "noise_reference",
        ),
        "cross_domain_disagreement_class": cross_slice_pairwise(
            slice_populations,
            "noise_domain:",
            "speech_disagreement",
            "noise_disagreement",
        ),
        "per_case": per_case,
        "domain_case_counts": domain_case_counts,
        "decision": decision,
        "invalid_reasons": sorted(set(invalid_reasons)),
        "interpretation_boundary": {
            "tracker_slow_update_state": (
                "slow_update_bin_fraction counts existing EMA noise-tracker bins "
                "whose current per-bin speech_probability exceeds the native 0.35 "
                "alpha-switch threshold, causing alpha=0.995 rather than 0.92."
            ),
            "source_comparison": (
                "noise_disagreement vs oracle-noise non-disagreement frames "
                "localizes state/component shifts associated with false-high upstream."
            ),
            "class_comparison": (
                "speech_disagreement vs noise_disagreement checks whether the same "
                "upstream internals distinguish true speech from false-high noise."
            ),
            "short_context": (
                "Current plus up to two previous frames only; no future information."
            ),
            "no_component_reweighting": True,
            "no_mapping_selection": True,
            "no_threshold_search": True,
        },
        "authority_boundary": contract["authority_boundary"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    assert signed_auc([3.0, 4.0, 1.0, 2.0], [1, 1, 0, 0]) == 1.0
    assert signed_auc([1.0, 2.0, 3.0, 4.0], [1, 1, 0, 0]) == 0.0
    positive = [
        {name: 2.0 for name in NUMERIC_FEATURES},
        {name: 3.0 for name in NUMERIC_FEATURES},
    ]
    negative = [
        {name: 0.0 for name in NUMERIC_FEATURES},
        {name: 1.0 for name in NUMERIC_FEATURES},
    ]
    profile = pairwise_profile(positive, negative)
    assert all(
        item["separability_auc"] == 1.0 for item in profile.values()
    )

    rows = [
        {
            "upstream_probability": 0.60,
            "mirror_gap": 0.60,
            "mirror_mean": 0.10,
            "mirror_mean_suppression": 0.90,
            "mirror_concentration": 0.70,
            "posterior_max": 1.0,
            "posterior_variance": 0.02,
            "positive_bin_fraction": 0.2,
            "slow_update_bin_fraction": 0.1,
            "mean_post_ratio": 1.5,
            "max_post_ratio": 4.0,
            "ns_noise_rms_dbfs": -50.0,
            "local_guard_pass": 0,
        },
        {
            "upstream_probability": 0.70,
            "mirror_gap": 0.70,
            "mirror_mean": 0.10,
            "mirror_mean_suppression": 0.90,
            "mirror_concentration": 0.80,
            "posterior_max": 1.0,
            "posterior_variance": 0.03,
            "positive_bin_fraction": 0.25,
            "slow_update_bin_fraction": 0.12,
            "mean_post_ratio": 1.7,
            "max_post_ratio": 5.0,
            "ns_noise_rms_dbfs": -49.0,
            "local_guard_pass": 0,
        },
    ]
    f = feature_values(
        rows, 1, upstream_guard=0.55,
        upstream_high_run_length=2,
        disagreement_run_length=2,
    )
    assert abs(f["upstream_probability_mean3"] - 0.65) < 1e-12
    assert f["upstream_high_run_length"] == 2.0
    assert f["disagreement_run_length"] == 2.0
    print("I025 upstream disagreement-noise decomposition self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.output or not args.corpus:
        parser.error("--probe --contract --corpus --output are required")
    result = evaluate(args.probe, args.corpus, args.contract, args.output)
    source = result["noise_disagreement_vs_noise_reference"]
    summary = {
        name: {
            "signed_auc": value["signed_auc"],
            "separability_auc": value["separability_auc"],
            "direction": value["direction"],
        }
        for name, value in source.items()
    }
    print(json.dumps({
        "decision": result["decision"],
        "invalid_reasons": result["invalid_reasons"],
        "population_counts": result["population_counts"],
        "noise_source_features": summary,
    }, sort_keys=True))
    return 0 if result["decision"] != "I025_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
