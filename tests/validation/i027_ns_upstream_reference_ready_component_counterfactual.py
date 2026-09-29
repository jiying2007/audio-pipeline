#!/usr/bin/env python3
"""I027 candidate-zero matched NS component counterfactual on disagreement frames."""

from __future__ import annotations

import argparse
from collections import Counter
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


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def disagreement(row: dict[str, Any], upstream_guard: float) -> bool:
    return (
        float(row["upstream_probability"]) > upstream_guard
        and not int(row["local_guard_pass"])
    )


def empty_accumulator() -> dict[str, Any]:
    return {
        "raw_noise_targets": 0,
        "raw_speech_targets": 0,
        "noise_targets": 0,
        "speech_targets": 0,
        "excluded_noise_targets": 0,
        "excluded_speech_targets": 0,
        "reference_frames": 0,
        "noise_mean_rescued": 0,
        "noise_concentration_rescued": 0,
        "noise_both_rescued": 0,
        "noise_mean_only": 0,
        "noise_concentration_only": 0,
        "noise_both_individual": 0,
        "noise_neither_individual": 0,
        "noise_joint_only": 0,
        "speech_mean_preserved": 0,
        "speech_concentration_preserved": 0,
        "speech_both_preserved": 0,
        "noise_base_minus_mean_cf": [],
        "noise_base_minus_concentration_cf": [],
        "noise_base_minus_both_cf": [],
        "speech_base_minus_mean_cf": [],
        "speech_base_minus_concentration_cf": [],
        "speech_base_minus_both_cf": [],
        "reference_mean": [],
        "reference_concentration": [],
        "reference_gap": [],
        "target_cases": 0,
        "target_cases_with_any_eligible_target": 0,
    }


def append_case(
    acc: dict[str, Any],
    result: dict[str, Any],
) -> None:
    for key in (
        "raw_noise_targets", "raw_speech_targets",
        "noise_targets", "speech_targets",
        "excluded_noise_targets", "excluded_speech_targets", "reference_frames",
        "noise_mean_rescued", "noise_concentration_rescued",
        "noise_both_rescued", "noise_mean_only",
        "noise_concentration_only", "noise_both_individual",
        "noise_neither_individual", "noise_joint_only",
        "speech_mean_preserved", "speech_concentration_preserved",
        "speech_both_preserved", "target_cases",
        "target_cases_with_any_eligible_target",
    ):
        acc[key] += int(result[key])
    for key in (
        "noise_base_minus_mean_cf",
        "noise_base_minus_concentration_cf",
        "noise_base_minus_both_cf",
        "speech_base_minus_mean_cf",
        "speech_base_minus_concentration_cf",
        "speech_base_minus_both_cf",
        "reference_mean",
        "reference_concentration",
        "reference_gap",
    ):
        acc[key].extend(float(value) for value in result[key])


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def summary(acc: dict[str, Any]) -> dict[str, Any]:
    raw_noise = int(acc["raw_noise_targets"])
    raw_speech = int(acc["raw_speech_targets"])
    noise = int(acc["noise_targets"])
    speech = int(acc["speech_targets"])
    target_cases = int(acc["target_cases"])
    eligible_cases = int(acc["target_cases_with_any_eligible_target"])
    return {
        "raw_noise_targets": raw_noise,
        "raw_speech_targets": raw_speech,
        "noise_targets": noise,
        "speech_targets": speech,
        "excluded_noise_targets": int(acc["excluded_noise_targets"]),
        "excluded_speech_targets": int(acc["excluded_speech_targets"]),
        "eligible_target_fraction": {
            "noise": noise / raw_noise if raw_noise else None,
            "speech": speech / raw_speech if raw_speech else None,
        },
        "reference_frames": int(acc["reference_frames"]),
        "target_cases": target_cases,
        "target_cases_with_any_eligible_target": eligible_cases,
        "eligible_case_fraction": eligible_cases / target_cases if target_cases else None,
        "noise_rescue_fraction": {
            "mean_reference": acc["noise_mean_rescued"] / noise if noise else None,
            "concentration_reference":
                acc["noise_concentration_rescued"] / noise if noise else None,
            "both_reference": acc["noise_both_rescued"] / noise if noise else None,
        },
        "noise_individual_attribution_fraction": {
            "mean_only": acc["noise_mean_only"] / noise if noise else None,
            "concentration_only":
                acc["noise_concentration_only"] / noise if noise else None,
            "both_individual":
                acc["noise_both_individual"] / noise if noise else None,
            "neither_individual":
                acc["noise_neither_individual"] / noise if noise else None,
            "joint_only": acc["noise_joint_only"] / noise if noise else None,
        },
        "speech_preservation_fraction": {
            "mean_reference":
                acc["speech_mean_preserved"] / speech if speech else None,
            "concentration_reference":
                acc["speech_concentration_preserved"] / speech if speech else None,
            "both_reference":
                acc["speech_both_preserved"] / speech if speech else None,
        },
        "median_gap_reduction": {
            "noise_mean_reference": median(acc["noise_base_minus_mean_cf"]),
            "noise_concentration_reference":
                median(acc["noise_base_minus_concentration_cf"]),
            "noise_both_reference": median(acc["noise_base_minus_both_cf"]),
            "speech_mean_reference": median(acc["speech_base_minus_mean_cf"]),
            "speech_concentration_reference":
                median(acc["speech_base_minus_concentration_cf"]),
            "speech_both_reference": median(acc["speech_base_minus_both_cf"]),
        },
        "reference_medians_across_eligible_targets": {
            "mean": median(acc["reference_mean"]),
            "concentration": median(acc["reference_concentration"]),
            "gap": median(acc["reference_gap"]),
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
    minimum_reference_frames: int,
) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    require(mic is not None and labels_path is not None,
            "case missing mic audio or VAD labels")

    with tempfile.TemporaryDirectory(prefix="ap-i027-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)

    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    require(count > WARMUP, "case too short")
    rows = rows[WARMUP:count]
    labels = labels[WARMUP:count]

    mirror_ns_delta = 0.0
    mirror_vad_delta = 0.0
    mirror_active_mismatch = 0
    prior_reference_rows: list[dict[str, Any]] = []
    result = empty_accumulator()

    def apply_eligible_target(row: dict[str, Any], *, speech: bool) -> None:
        ref_mean = statistics.median(
            float(item["mirror_mean"]) for item in prior_reference_rows
        )
        ref_concentration = statistics.median(
            float(item["mirror_concentration"]) for item in prior_reference_rows
        )
        ref_gap = clamp01(ref_concentration - ref_mean)
        mean = float(row["mirror_mean"])
        concentration = float(row["mirror_concentration"])
        base = float(row["mirror_gap"])
        mean_cf = clamp01(concentration - ref_mean)
        concentration_cf = clamp01(ref_concentration - mean)
        both_cf = ref_gap

        result["reference_mean"].append(ref_mean)
        result["reference_concentration"].append(ref_concentration)
        result["reference_gap"].append(ref_gap)

        if speech:
            require(base > upstream_guard,
                    "speech target lost upstream-high identity")
            result["speech_mean_preserved"] += int(mean_cf > upstream_guard)
            result["speech_concentration_preserved"] += int(
                concentration_cf > upstream_guard
            )
            result["speech_both_preserved"] += int(both_cf > upstream_guard)
            result["speech_base_minus_mean_cf"].append(base - mean_cf)
            result["speech_base_minus_concentration_cf"].append(
                base - concentration_cf
            )
            result["speech_base_minus_both_cf"].append(base - both_cf)
            return

        require(base > upstream_guard,
                "noise target lost upstream-high identity")
        mean_rescue = mean_cf <= upstream_guard
        concentration_rescue = concentration_cf <= upstream_guard
        both_rescue = both_cf <= upstream_guard
        result["noise_mean_rescued"] += int(mean_rescue)
        result["noise_concentration_rescued"] += int(concentration_rescue)
        result["noise_both_rescued"] += int(both_rescue)
        result["noise_mean_only"] += int(mean_rescue and not concentration_rescue)
        result["noise_concentration_only"] += int(
            concentration_rescue and not mean_rescue
        )
        result["noise_both_individual"] += int(
            mean_rescue and concentration_rescue
        )
        result["noise_neither_individual"] += int(
            not mean_rescue and not concentration_rescue
        )
        result["noise_joint_only"] += int(
            both_rescue and not mean_rescue and not concentration_rescue
        )
        result["noise_base_minus_mean_cf"].append(base - mean_cf)
        result["noise_base_minus_concentration_cf"].append(
            base - concentration_cf
        )
        result["noise_base_minus_both_cf"].append(base - both_cf)

    for row, label in zip(rows, labels):
        require(label in (0, 1), "invalid label")
        upstream = float(row["upstream_probability"])
        gap = float(row["mirror_gap"])
        public = float(row["public_shipping_probability"])
        shipping = float(row["shipping_probability"])
        require(all(math.isfinite(value) for value in (
            upstream, gap, public, shipping,
            float(row["mirror_mean"]), float(row["mirror_concentration"]),
        )), "non-finite I027 metric")
        mirror_ns_delta = max(mirror_ns_delta, abs(upstream - gap))
        mirror_vad_delta = max(mirror_vad_delta, abs(public - shipping))
        mirror_active_mismatch += int(
            int(row["public_shipping_active"]) != int(row["shipping_active"])
        )

        is_disagreement = disagreement(row, upstream_guard)
        if label == 0 and not is_disagreement:
            prior_reference_rows.append(row)
            continue
        if label == 0 and is_disagreement:
            result["raw_noise_targets"] += 1
            if len(prior_reference_rows) < minimum_reference_frames:
                result["excluded_noise_targets"] += 1
                continue
            result["noise_targets"] += 1
            apply_eligible_target(row, speech=False)
        elif label == 1 and is_disagreement:
            result["raw_speech_targets"] += 1
            if len(prior_reference_rows) < minimum_reference_frames:
                result["excluded_speech_targets"] += 1
                continue
            result["speech_targets"] += 1
            apply_eligible_target(row, speech=True)

    raw_targets = result["raw_noise_targets"] + result["raw_speech_targets"]
    eligible_targets = result["noise_targets"] + result["speech_targets"]
    result["reference_frames"] = len(prior_reference_rows)
    result["target_cases"] = int(raw_targets > 0)
    result["target_cases_with_any_eligible_target"] = int(eligible_targets > 0)

    return {
        "case_id": str(case["case_id"]),
        "scenario": str(case["scenario"]),
        "dimensions": case.get("dimensions", {}),
        "counterfactual": result,
        "eligibility": {
            "minimum_prior_reference_frames": minimum_reference_frames,
            "raw_noise_targets": result["raw_noise_targets"],
            "eligible_noise_targets": result["noise_targets"],
            "excluded_noise_targets": result["excluded_noise_targets"],
            "raw_speech_targets": result["raw_speech_targets"],
            "eligible_speech_targets": result["speech_targets"],
            "excluded_speech_targets": result["excluded_speech_targets"],
            "causal_prior_only": True,
            "excluded_targets_enter_denominator": False,
        },
        "mirror": {
            "max_ns_upstream_gap_delta": mirror_ns_delta,
            "max_vad_probability_delta": mirror_vad_delta,
            "vad_active_mismatch_frames": mirror_active_mismatch,
        },
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
        == "i027-ns-upstream-reference-ready-component-counterfactual-v1",
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
        "I027 budget drift",
    )

    upstream_guard = float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    minimum_reference_frames = int(
        contract["counterfactual_reference"]["minimum_reference_frames_per_target"]
    )
    expected_lock = contract["dataset_authority"]["dataset_lock_sha256"]

    actual_seeds: list[int] = []
    global_acc = empty_accumulator()
    slice_acc: dict[str, dict[str, Any]] = {}
    per_case: list[dict[str, Any]] = []
    max_ns_delta = 0.0
    max_vad_delta = 0.0
    vad_active_mismatch = 0
    domain_case_counts = {
        domain: {"mix": 0, "noise": 0} for domain in NOISE_DOMAINS
    }

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
            result = analyze_case(
                probe, corpus_path, case,
                upstream_guard, minimum_reference_frames,
            )
            per_case.append({
                key: value for key, value in result.items()
                if key != "counterfactual"
            } | {"counterfactual": summary(result["counterfactual"])})
            append_case(global_acc, result["counterfactual"])

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
                slice_acc.setdefault(key, empty_accumulator())
                append_case(slice_acc[key], result["counterfactual"])

            dimensions = case.get("dimensions", {})
            domain = dimensions.get("noise_domain")
            if domain in domain_case_counts:
                if str(case["scenario"]).startswith("research-public-noisy"):
                    domain_case_counts[domain]["mix"] += 1
                elif case["scenario"] == "research-public-noise-only":
                    domain_case_counts[domain]["noise"] += 1

    require(actual_seeds == expected_seeds,
            f"fresh seed mismatch: {actual_seeds}")

    global_summary = summary(global_acc)
    slices = {
        key: summary(acc) for key, acc in sorted(slice_acc.items())
        if acc["raw_noise_targets"] or acc["raw_speech_targets"]
    }

    invalid_reasons: list[str] = []
    gates = contract["diagnostic_gates"]
    if len(per_case) < int(gates["minimum_total_cases"]):
        invalid_reasons.append("case_count")

    for label, raw_key, eligible_key in (
        ("noise", "raw_noise_targets", "noise_targets"),
        ("speech", "raw_speech_targets", "speech_targets"),
    ):
        raw = int(global_summary[raw_key])
        eligible = int(global_summary[eligible_key])
        if raw < int(gates["minimum_global_raw_targets_per_class"]):
            invalid_reasons.append("global_raw_target_count:" + label)
        if eligible < int(gates["minimum_global_eligible_targets_per_class"]):
            invalid_reasons.append("global_eligible_target_count:" + label)
        fraction = global_summary["eligible_target_fraction"][label]
        if (
            fraction is None
            or fraction < float(gates["minimum_global_eligible_fraction"])
        ):
            invalid_reasons.append("global_eligible_fraction:" + label)

    if max_ns_delta > float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta > float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if vad_active_mismatch != int(
        gates["vad_shipping_mirror_active_mismatch_frames"]
    ):
        invalid_reasons.append("vad_active_mirror")

    for domain in NOISE_DOMAINS:
        key = "noise_domain:" + domain
        item = slices.get(key)
        if item is None:
            invalid_reasons.append("domain_population:" + domain)
            continue
        for label, raw_key, eligible_key in (
            ("noise", "raw_noise_targets", "noise_targets"),
            ("speech", "raw_speech_targets", "speech_targets"),
        ):
            raw = int(item[raw_key])
            eligible = int(item[eligible_key])
            if raw < int(gates["minimum_raw_targets_per_noise_domain"]):
                invalid_reasons.append(
                    "domain_raw_target_count:" + domain + ":" + label
                )
                continue
            if eligible < int(gates["minimum_eligible_targets_per_noise_domain"]):
                invalid_reasons.append(
                    "domain_eligible_target_count:" + domain + ":" + label
                )
            fraction = item["eligible_target_fraction"][label]
            if (
                fraction is None
                or fraction < float(
                    gates["minimum_per_noise_domain_eligible_fraction"]
                )
            ):
                invalid_reasons.append(
                    "domain_eligible_fraction:" + domain + ":" + label
                )
        counts = domain_case_counts[domain]
        if counts["mix"] < int(
            authority["minimum_mix_cases_per_noise_domain_per_seed"]
        ) * len(expected_seeds):
            invalid_reasons.append("domain_mix_coverage:" + domain)
        if counts["noise"] < int(
            authority["minimum_noise_only_cases_per_noise_domain_per_seed"]
        ) * len(expected_seeds):
            invalid_reasons.append("domain_noise_coverage:" + domain)

    secondary_prefixes = ("scenario:", "snr_db:", "reverb:")
    for key, item in slices.items():
        if not key.startswith(secondary_prefixes):
            continue
        for label, raw_key, eligible_key in (
            ("noise", "raw_noise_targets", "noise_targets"),
            ("speech", "raw_speech_targets", "speech_targets"),
        ):
            raw = int(item[raw_key])
            if raw < int(gates["secondary_slice_gate_minimum_raw_targets"]):
                continue
            eligible = int(item[eligible_key])
            if eligible < int(
                gates["secondary_slice_minimum_eligible_targets"]
            ):
                invalid_reasons.append(
                    "secondary_slice_eligible_count:" + key + ":" + label
                )
            fraction = item["eligible_target_fraction"][label]
            if (
                fraction is None
                or fraction < float(
                    gates["secondary_slice_minimum_eligible_fraction"]
                )
            ):
                invalid_reasons.append(
                    "secondary_slice_eligible_fraction:" + key + ":" + label
                )

    if invalid_reasons:
        decision = "I027_INPUT_INVALID_REVIEW_REQUIRED"
    elif global_acc["raw_noise_targets"]:
        decision = (
            "NS_UPSTREAM_REFERENCE_READY_COMPONENT_COUNTERFACTUAL_"
            "DECOMPOSED_REVIEW_REQUIRED"
        )
    else:
        decision = "NS_UPSTREAM_FALSE_HIGH_NOT_REPRODUCED_REVIEW_REQUIRED"

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
            "max_ns_upstream_gap_delta": max_ns_delta,
            "max_vad_probability_delta": max_vad_delta,
            "vad_active_mismatch_frames": vad_active_mismatch,
        },
        "global": global_summary,
        "slices": slices,
        "per_case": per_case,
        "domain_case_counts": domain_case_counts,
        "decision": decision,
        "invalid_reasons": sorted(set(invalid_reasons)),
        "interpretation_boundary": {
            "reference": (
                "Per-target median mirror_mean and mirror_concentration use "
                "only prior same-case oracle-noise non-disagreement frames "
                "after the fixed warmup."
            ),
            "eligibility": (
                "A target enters counterfactual numerators and denominators "
                "only after the preregistered prior-reference pool is ready. "
                "Early excluded targets are counted only in eligibility coverage."
            ),
            "conditional_population": (
                "Any valid counterfactual fractions describe the preregistered "
                "reference-ready target cohort, not pre-ready disagreement targets."
            ),
            "coverage_bias_guarded": True,
            "excluded_targets_enter_counterfactual_denominator": False,
            "oracle_reference_not_shippable": True,
            "no_component_mapping_selected": True,
            "no_threshold_search": True,
            "no_shipping_candidate": True,
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
    acc = empty_accumulator()
    case = empty_accumulator()
    case["raw_noise_targets"] = 5
    case["raw_speech_targets"] = 4
    case["noise_targets"] = 4
    case["speech_targets"] = 3
    case["excluded_noise_targets"] = 1
    case["excluded_speech_targets"] = 1
    case["reference_frames"] = 20
    case["target_cases"] = 1
    case["target_cases_with_any_eligible_target"] = 1
    case["noise_mean_rescued"] = 3
    case["noise_concentration_rescued"] = 1
    case["noise_both_rescued"] = 4
    case["noise_mean_only"] = 2
    case["noise_concentration_only"] = 0
    case["noise_both_individual"] = 1
    case["noise_neither_individual"] = 1
    case["noise_joint_only"] = 1
    case["speech_mean_preserved"] = 1
    case["speech_concentration_preserved"] = 3
    case["speech_both_preserved"] = 1
    case["noise_base_minus_mean_cf"] = [0.2, 0.2, 0.1, 0.0]
    case["noise_base_minus_concentration_cf"] = [0.0, 0.0, 0.1, 0.0]
    case["noise_base_minus_both_cf"] = [0.2, 0.2, 0.2, 0.2]
    case["speech_base_minus_mean_cf"] = [0.1, 0.2, 0.1]
    case["speech_base_minus_concentration_cf"] = [0.0, 0.1, 0.0]
    case["speech_base_minus_both_cf"] = [0.1, 0.1, 0.1]
    case["reference_mean"] = [0.2]
    case["reference_concentration"] = [0.7]
    case["reference_gap"] = [0.5]
    append_case(acc, case)
    value = summary(acc)
    assert value["eligible_target_fraction"]["noise"] == 0.8
    assert value["eligible_target_fraction"]["speech"] == 0.75
    assert value["noise_rescue_fraction"]["mean_reference"] == 0.75
    assert value["speech_preservation_fraction"]["concentration_reference"] == 1.0
    assert value["excluded_noise_targets"] == 1
    print("I027 reference-ready component counterfactual self-test: OK")


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
    print(json.dumps({
        "decision": result["decision"],
        "invalid_reasons": result["invalid_reasons"],
        "eligible_target_fraction":
            result["global"]["eligible_target_fraction"],
        "noise_rescue_fraction":
            result["global"]["noise_rescue_fraction"],
        "speech_preservation_fraction":
            result["global"]["speech_preservation_fraction"],
    }, sort_keys=True))
    return 0 if result["decision"] != "I027_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
