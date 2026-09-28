#!/usr/bin/env python3
"""I024 candidate-zero feature separability for VAD disagreement speech vs noise."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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
    "upstream_margin",
    "ratio_db",
    "crest_db",
    "raw_probability",
    "pre_blend_probability",
    "shipping_probability",
    "pre_hangover",
    "upstream_margin_mean3",
    "upstream_margin_min3",
    "ratio_db_mean3",
    "pre_blend_probability_mean3",
    "disagreement_run_length",
)
CATEGORICAL_FEATURES = ("noise_update_kind",)


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


def numeric_profile(values: list[float], labels: list[int]) -> dict[str, Any]:
    require(len(values) == len(labels) and values, "numeric feature population empty")
    require(all(math.isfinite(value) for value in values), "non-finite numeric feature")
    speech = [value for value, label in zip(values, labels) if label == 1]
    noise = [value for value, label in zip(values, labels) if label == 0]
    auc = signed_auc(values, labels)
    separability = None if auc is None else max(auc, 1.0 - auc)
    direction = None
    if auc is not None:
        if auc > 0.5:
            direction = "higher_in_speech"
        elif auc < 0.5:
            direction = "lower_in_speech"
        else:
            direction = "no_direction"
    return {
        "count": len(values),
        "speech_count": len(speech),
        "noise_count": len(noise),
        "signed_auc": auc,
        "separability_auc": separability,
        "direction": direction,
        "speech": {
            "median": statistics.median(speech) if speech else None,
            "p10": percentile(speech, 0.10),
            "p90": percentile(speech, 0.90),
        },
        "noise": {
            "median": statistics.median(noise) if noise else None,
            "p10": percentile(noise, 0.10),
            "p90": percentile(noise, 0.90),
        },
        "median_difference_speech_minus_noise": (
            statistics.median(speech) - statistics.median(noise)
            if speech and noise else None
        ),
    }


def categorical_profile(values: list[int], labels: list[int]) -> dict[str, Any]:
    require(len(values) == len(labels) and values, "categorical population empty")
    speech = Counter(value for value, label in zip(values, labels) if label == 1)
    noise = Counter(value for value, label in zip(values, labels) if label == 0)
    ns = sum(speech.values())
    nn = sum(noise.values())
    categories = sorted(set(speech) | set(noise))
    speech_fraction = {
        str(category): speech[category] / ns if ns else None
        for category in categories
    }
    noise_fraction = {
        str(category): noise[category] / nn if nn else None
        for category in categories
    }
    tv = None
    if ns and nn:
        tv = 0.5 * sum(
            abs(speech[category] / ns - noise[category] / nn)
            for category in categories
        )
    return {
        "count": len(values),
        "speech_count": ns,
        "noise_count": nn,
        "speech_fraction": speech_fraction,
        "noise_fraction": noise_fraction,
        "total_variation_distance": tv,
    }


def feature_values(
    rows: list[dict[str, Any]],
    index: int,
    upstream_guard: float,
    run_length: int,
) -> dict[str, float | int]:
    row = rows[index]
    history = rows[max(0, index - 2):index + 1]
    upstream_margins = [
        float(item["upstream_probability"]) - upstream_guard for item in history
    ]
    ratio_values = [float(item["ratio_db"]) for item in history]
    pre_blend_values = [float(item["pre_blend_probability"]) for item in history]
    result: dict[str, float | int] = {
        "upstream_margin": float(row["upstream_probability"]) - upstream_guard,
        "ratio_db": float(row["ratio_db"]),
        "crest_db": float(row["crest_db"]),
        "raw_probability": float(row["raw_probability"]),
        "pre_blend_probability": float(row["pre_blend_probability"]),
        "shipping_probability": float(row["shipping_probability"]),
        "pre_hangover": float(row["pre_hangover"]),
        "upstream_margin_mean3": statistics.fmean(upstream_margins),
        "upstream_margin_min3": min(upstream_margins),
        "ratio_db_mean3": statistics.fmean(ratio_values),
        "pre_blend_probability_mean3": statistics.fmean(pre_blend_values),
        "disagreement_run_length": float(run_length),
        "noise_update_kind": int(row["noise_update_kind"]),
    }
    for name in NUMERIC_FEATURES:
        require(math.isfinite(float(result[name])), "non-finite feature: " + name)
    return result


def disagreement(row: dict[str, Any], upstream_guard: float) -> bool:
    return (
        float(row["upstream_probability"]) > upstream_guard
        and not int(row["local_guard_pass"])
    )


def empty_population() -> dict[str, Any]:
    return {
        "labels": [],
        "numeric": {name: [] for name in NUMERIC_FEATURES},
        "categorical": {name: [] for name in CATEGORICAL_FEATURES},
    }


def append_population(
    population: dict[str, Any],
    label: int,
    features: dict[str, float | int],
) -> None:
    population["labels"].append(label)
    for name in NUMERIC_FEATURES:
        population["numeric"][name].append(float(features[name]))
    for name in CATEGORICAL_FEATURES:
        population["categorical"][name].append(int(features[name]))


def merge_population(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["labels"].extend(source["labels"])
    for name in NUMERIC_FEATURES:
        target["numeric"][name].extend(source["numeric"][name])
    for name in CATEGORICAL_FEATURES:
        target["categorical"][name].extend(source["categorical"][name])


def population_profile(population: dict[str, Any]) -> dict[str, Any]:
    labels = population["labels"]
    return {
        "frames": len(labels),
        "speech_frames": sum(labels),
        "noise_frames": len(labels) - sum(labels),
        "numeric_features": {
            name: numeric_profile(population["numeric"][name], labels)
            for name in NUMERIC_FEATURES
        },
        "categorical_features": {
            name: categorical_profile(population["categorical"][name], labels)
            for name in CATEGORICAL_FEATURES
        },
    }


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
    with tempfile.TemporaryDirectory(prefix="ap-i024-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    require(count > WARMUP, "case too short")
    rows = rows[WARMUP:count]
    labels = labels[WARMUP:count]

    mirror_delta = 0.0
    mirror_active = 0
    population = empty_population()
    run_length = 0

    for index, (row, label) in enumerate(zip(rows, labels)):
        require(label in (0, 1), "invalid label")
        public_probability = float(row["public_shipping_probability"])
        shipping_probability = float(row["shipping_probability"])
        require(math.isfinite(public_probability), "non-finite public probability")
        mirror_delta = max(
            mirror_delta, abs(public_probability - shipping_probability)
        )
        mirror_active += int(
            int(row["public_shipping_active"]) != int(row["shipping_active"])
        )

        if disagreement(row, upstream_guard):
            run_length += 1
            features = feature_values(rows, index, upstream_guard, run_length)
            append_population(population, label, features)
        else:
            run_length = 0

    return {
        "case_id": str(case["case_id"]),
        "scenario": str(case["scenario"]),
        "dimensions": case.get("dimensions", {}),
        "population": population,
        "shipping_mirror": {
            "max_probability_delta": mirror_delta,
            "active_mismatch_frames": mirror_active,
        },
    }


def cross_slice_feature_summary(
    slice_profiles: dict[str, dict[str, Any]],
    prefix: str,
) -> dict[str, Any]:
    selected = {
        key: value for key, value in slice_profiles.items()
        if key.startswith(prefix)
        and value["speech_frames"] > 0
        and value["noise_frames"] > 0
    }
    output: dict[str, Any] = {}
    for feature in NUMERIC_FEATURES:
        entries = {}
        aucs = []
        for key, profile in sorted(selected.items()):
            value = profile["numeric_features"][feature]
            entries[key] = {
                "signed_auc": value["signed_auc"],
                "separability_auc": value["separability_auc"],
                "direction": value["direction"],
            }
            if value["separability_auc"] is not None:
                aucs.append(float(value["separability_auc"]))
        output[feature] = {
            "slices": entries,
            "separability_auc_min": min(aucs) if aucs else None,
            "separability_auc_median": statistics.median(aucs) if aucs else None,
            "separability_auc_max": max(aucs) if aucs else None,
        }
    categorical: dict[str, Any] = {}
    for feature in CATEGORICAL_FEATURES:
        entries = {}
        tvs = []
        for key, profile in sorted(selected.items()):
            value = profile["categorical_features"][feature]
            entries[key] = {
                "total_variation_distance": value["total_variation_distance"]
            }
            if value["total_variation_distance"] is not None:
                tvs.append(float(value["total_variation_distance"]))
        categorical[feature] = {
            "slices": entries,
            "tv_min": min(tvs) if tvs else None,
            "tv_median": statistics.median(tvs) if tvs else None,
            "tv_max": max(tvs) if tvs else None,
        }
    return {
        "numeric_features": output,
        "categorical_features": categorical,
    }


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    require(
        contract["investigation_id"]
        == "i024-vad-disagreement-feature-separability-v1",
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
        "I024 budget drift",
    )

    upstream_guard = float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    expected_lock = contract["dataset_authority"]["dataset_lock_sha256"]

    actual_seeds: list[int] = []
    global_population = empty_population()
    slice_populations: dict[str, dict[str, Any]] = {}
    per_case: list[dict[str, Any]] = []
    mirror_delta = 0.0
    mirror_active = 0
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
            merge_population(global_population, result["population"])
            case_profile = population_profile(result["population"]) if result["population"]["labels"] else {
                "frames": 0, "speech_frames": 0, "noise_frames": 0
            }
            per_case.append({
                "case_id": result["case_id"],
                "scenario": result["scenario"],
                "dimensions": result["dimensions"],
                "disagreement_frames": case_profile["frames"],
                "disagreement_speech_frames": case_profile["speech_frames"],
                "disagreement_noise_frames": case_profile["noise_frames"],
            })
            mirror_delta = max(
                mirror_delta,
                float(result["shipping_mirror"]["max_probability_delta"]),
            )
            mirror_active += int(
                result["shipping_mirror"]["active_mismatch_frames"]
            )
            for key in slice_keys(case):
                slice_populations.setdefault(key, empty_population())
                merge_population(slice_populations[key], result["population"])

            dimensions = case.get("dimensions", {})
            domain = dimensions.get("noise_domain")
            if domain in domain_case_counts:
                if str(case["scenario"]).startswith("research-public-noisy"):
                    domain_case_counts[domain]["mix"] += 1
                elif case["scenario"] == "research-public-noise-only":
                    domain_case_counts[domain]["noise"] += 1

    require(actual_seeds == expected_seeds,
            f"fresh seed mismatch: {actual_seeds}")

    global_profile = population_profile(global_population)
    slice_profiles = {
        key: population_profile(population)
        for key, population in sorted(slice_populations.items())
        if population["labels"]
    }

    invalid_reasons: list[str] = []
    gates = contract["diagnostic_gates"]
    if len(per_case) < int(gates["minimum_total_cases"]):
        invalid_reasons.append("case_count")
    if int(global_profile["speech_frames"]) < int(
        gates["minimum_disagreement_speech_frames"]
    ):
        invalid_reasons.append("disagreement_speech_count")
    if int(global_profile["noise_frames"]) < int(
        gates["minimum_disagreement_noise_frames"]
    ):
        invalid_reasons.append("disagreement_noise_count")
    if mirror_delta > float(gates["max_shipping_mirror_probability_delta"]):
        invalid_reasons.append("shipping_mirror_probability")
    if mirror_active != int(gates["shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("shipping_mirror_active")

    domain_min = int(gates["minimum_per_domain_class_frames"])
    for domain in NOISE_DOMAINS:
        key = "noise_domain:" + domain
        profile = slice_profiles.get(key)
        if (
            profile is None
            or int(profile["speech_frames"]) < domain_min
            or int(profile["noise_frames"]) < domain_min
        ):
            invalid_reasons.append("domain_class_population:" + domain)
        counts = domain_case_counts[domain]
        if counts["mix"] < int(authority["minimum_mix_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_mix_coverage:" + domain)
        if counts["noise"] < int(authority["minimum_noise_only_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_noise_coverage:" + domain)

    domain_summary = cross_slice_feature_summary(slice_profiles, "noise_domain:")
    snr_summary = cross_slice_feature_summary(slice_profiles, "snr_db:")

    if invalid_reasons:
        decision = "I024_INPUT_INVALID_REVIEW_REQUIRED"
    elif int(global_profile["frames"]) > 0:
        decision = "VAD_DISAGREEMENT_FEATURE_SEPARABILITY_PROFILED_REVIEW_REQUIRED"
    else:
        decision = "VAD_DISAGREEMENT_NOT_REPRODUCED_REVIEW_REQUIRED"

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
        "shipping_mirror": {
            "max_probability_delta": mirror_delta,
            "active_mismatch_frames": mirror_active,
        },
        "global": global_profile,
        "slices": slice_profiles,
        "cross_domain": domain_summary,
        "cross_snr": snr_summary,
        "per_case": per_case,
        "domain_case_counts": domain_case_counts,
        "decision": decision,
        "invalid_reasons": sorted(set(invalid_reasons)),
        "interpretation_boundary": {
            "population": (
                "Only frames in the existing upstream-high/local-low disagreement "
                "state are profiled."
            ),
            "numeric_statistic": (
                "Univariate ROC-AUC only. separability_auc=max(AUC,1-AUC) is "
                "orientation-free and does not select a threshold or feature."
            ),
            "categorical_statistic": (
                "Total variation distance between speech/noise category "
                "distributions; no category is promoted to a rule."
            ),
            "temporal_context": (
                "Current plus up to two previous frames only; no future "
                "information and no learned weights."
            ),
            "no_model_fitting": True,
            "no_feature_selection": True,
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
    assert signed_auc([1.0, 1.0, 1.0, 1.0], [1, 1, 0, 0]) == 0.5

    profile = numeric_profile(
        [3.0, 4.0, 1.0, 2.0], [1, 1, 0, 0]
    )
    assert profile["separability_auc"] == 1.0
    assert profile["direction"] == "higher_in_speech"

    categorical = categorical_profile(
        [1, 1, 0, 0], [1, 1, 0, 0]
    )
    assert categorical["total_variation_distance"] == 1.0

    rows = [
        {
            "upstream_probability": 0.60,
            "ratio_db": -2.0,
            "crest_db": 7.0,
            "raw_probability": 0.10,
            "pre_blend_probability": 0.10,
            "shipping_probability": 0.30,
            "pre_hangover": 0,
            "noise_update_kind": 1,
        },
        {
            "upstream_probability": 0.70,
            "ratio_db": -1.0,
            "crest_db": 8.0,
            "raw_probability": 0.12,
            "pre_blend_probability": 0.12,
            "shipping_probability": 0.35,
            "pre_hangover": 1,
            "noise_update_kind": 0,
        },
        {
            "upstream_probability": 0.80,
            "ratio_db": 0.0,
            "crest_db": 9.0,
            "raw_probability": 0.14,
            "pre_blend_probability": 0.14,
            "shipping_probability": 0.40,
            "pre_hangover": 2,
            "noise_update_kind": 0,
        },
    ]
    features = feature_values(rows, 2, 0.55, 3)
    assert abs(float(features["upstream_margin_mean3"]) - 0.15) < 1e-12
    assert abs(float(features["upstream_margin_min3"]) - 0.05) < 1e-12
    assert float(features["disagreement_run_length"]) == 3.0
    print("I024 disagreement feature separability self-test: OK")


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
    summary = {
        name: {
            "signed_auc": value["signed_auc"],
            "separability_auc": value["separability_auc"],
            "direction": value["direction"],
        }
        for name, value in result["global"]["numeric_features"].items()
    }
    print(json.dumps({
        "decision": result["decision"],
        "invalid_reasons": result["invalid_reasons"],
        "numeric_features": summary,
        "noise_update_tv": result["global"]["categorical_features"][
            "noise_update_kind"
        ]["total_variation_distance"],
    }, sort_keys=True))
    return 0 if result["decision"] != "I024_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
