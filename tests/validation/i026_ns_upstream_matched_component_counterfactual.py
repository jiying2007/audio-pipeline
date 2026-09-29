#!/usr/bin/env python3
"""I026 candidate-zero matched NS component counterfactual on disagreement frames."""

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
        "noise_targets": 0,
        "speech_targets": 0,
        "reference_frames": 0,
        "missing_reference_targets": 0,
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
        "target_cases_with_reference": 0,
    }


def append_case(
    acc: dict[str, Any],
    result: dict[str, Any],
) -> None:
    for key in (
        "noise_targets", "speech_targets", "reference_frames",
        "missing_reference_targets", "noise_mean_rescued", "noise_concentration_rescued",
        "noise_both_rescued", "noise_mean_only",
        "noise_concentration_only", "noise_both_individual",
        "noise_neither_individual", "noise_joint_only",
        "speech_mean_preserved", "speech_concentration_preserved",
        "speech_both_preserved", "target_cases",
        "target_cases_with_reference",
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
    noise = int(acc["noise_targets"])
    speech = int(acc["speech_targets"])
    target_cases = int(acc["target_cases"])
    referenced = int(acc["target_cases_with_reference"])
    return {
        "noise_targets": noise,
        "speech_targets": speech,
        "reference_frames": int(acc["reference_frames"]),
        "missing_reference_targets": int(acc["missing_reference_targets"]),
        "target_cases": target_cases,
        "target_cases_with_reference": referenced,
        "reference_case_coverage": referenced / target_cases if target_cases else None,
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
        "reference_medians_across_cases": {
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

    with tempfile.TemporaryDirectory(prefix="ap-i026-") as tmp:
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
    missing_reference_targets = 0

    def apply_target(row: dict[str, Any], *, speech: bool) -> None:
        nonlocal missing_reference_targets
        if len(prior_reference_rows) < minimum_reference_frames:
            missing_reference_targets += 1
            result["missing_reference_targets"] += 1
            return

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
        )), "non-finite I026 metric")
        mirror_ns_delta = max(mirror_ns_delta, abs(upstream - gap))
        mirror_vad_delta = max(mirror_vad_delta, abs(public - shipping))
        mirror_active_mismatch += int(
            int(row["public_shipping_active"]) != int(row["shipping_active"])
        )

        is_disagreement = disagreement(row, upstream_guard)
        if label == 0 and not is_disagreement:
            # Causal ordering is intentional: a reference row becomes available
            # only after its own readout, so no target can observe future frames.
            prior_reference_rows.append(row)
            continue
        if label == 0 and is_disagreement:
            result["noise_targets"] += 1
            apply_target(row, speech=False)
        elif label == 1 and is_disagreement:
            result["speech_targets"] += 1
            apply_target(row, speech=True)

    has_target = bool(result["noise_targets"] or result["speech_targets"])
    result["reference_frames"] = len(prior_reference_rows)
    result["target_cases"] = int(has_target)
    result["target_cases_with_reference"] = int(
        has_target and missing_reference_targets == 0
    )
    reference_available = missing_reference_targets == 0

    payload = {
        "case_id": str(case["case_id"]),
        "scenario": str(case["scenario"]),
        "dimensions": case.get("dimensions", {}),
        "reference_available": reference_available,
        "counterfactual": result,
        "mirror": {
            "max_ns_upstream_gap_delta": mirror_ns_delta,
            "max_vad_probability_delta": mirror_vad_delta,
            "vad_active_mismatch_frames": mirror_active_mismatch,
        },
    }
    if has_target:
        payload["reference"] = {
            "ordinary_noise_frames_total": len(prior_reference_rows),
            "minimum_prior_frames_per_target": minimum_reference_frames,
            "missing_target_frames": missing_reference_targets,
            "median_prior_reference_mean":
                median(result["reference_mean"]),
            "median_prior_reference_concentration":
                median(result["reference_concentration"]),
            "median_prior_reference_gap":
                median(result["reference_gap"]),
            "causal_prior_only": True,
        }
    return payload

def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    require(
        contract["investigation_id"]
        == "i026-ns-upstream-matched-component-counterfactual-v1",
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
        "I026 budget drift",
    )

    upstream_guard = float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    minimum_reference_frames = int(
        contract["counterfactual_reference"]["minimum_reference_frames_per_target_case"]
    )
    expected_lock = contract["dataset_authority"]["dataset_lock_sha256"]

    actual_seeds: list[int] = []
    global_acc = empty_accumulator()
    slice_acc: dict[str, dict[str, Any]] = {}
    per_case: list[dict[str, Any]] = []
    max_ns_delta = 0.0
    max_vad_delta = 0.0
    vad_active_mismatch = 0
    missing_reference_cases: list[str] = []
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
            result = analyze_case(
                probe, corpus_path, case,
                upstream_guard, minimum_reference_frames,
            )
            per_case.append({
                key: value for key, value in result.items()
                if key != "counterfactual"
            } | {"counterfactual": summary(result["counterfactual"])})
            append_case(global_acc, result["counterfactual"])
            if (
                result["counterfactual"]["target_cases"]
                and not result["reference_available"]
            ):
                missing_reference_cases.append(result["case_id"])

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
        if acc["target_cases"]
    }

    invalid_reasons: list[str] = []
    gates = contract["diagnostic_gates"]
    if len(per_case) < int(gates["minimum_total_cases"]):
        invalid_reasons.append("case_count")
    if global_acc["noise_targets"] < int(gates["minimum_noise_targets"]):
        invalid_reasons.append("noise_target_count")
    if global_acc["speech_targets"] < int(gates["minimum_speech_targets"]):
        invalid_reasons.append("speech_target_count")
    if missing_reference_cases:
        invalid_reasons.append("missing_case_reference")
    if max_ns_delta > float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta > float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if vad_active_mismatch != int(gates["vad_shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("vad_active_mirror")

    domain_min = int(gates["minimum_per_domain_target_frames"])
    for domain in NOISE_DOMAINS:
        key = "noise_domain:" + domain
        item = slices.get(key)
        if (
            item is None
            or int(item["noise_targets"]) < domain_min
            or int(item["speech_targets"]) < domain_min
        ):
            invalid_reasons.append("domain_target_population:" + domain)
        counts = domain_case_counts[domain]
        if counts["mix"] < int(authority["minimum_mix_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_mix_coverage:" + domain)
        if counts["noise"] < int(authority["minimum_noise_only_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_noise_coverage:" + domain)

    if invalid_reasons:
        decision = "I026_INPUT_INVALID_REVIEW_REQUIRED"
    elif global_acc["noise_targets"]:
        decision = "NS_UPSTREAM_MATCHED_COMPONENT_COUNTERFACTUAL_DECOMPOSED_REVIEW_REQUIRED"
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
        "missing_reference_cases": sorted(missing_reference_cases),
        "domain_case_counts": domain_case_counts,
        "decision": decision,
        "invalid_reasons": sorted(set(invalid_reasons)),
        "interpretation_boundary": {
            "reference": (
                "Per-target causal median mirror_mean and mirror_concentration "
                "over prior oracle-noise non-disagreement frames after the fixed "
                "warmup; future frames are excluded."
            ),
            "counterfactuals": (
                "Replace only mean, only concentration, or both with the same-case "
                "ordinary-noise reference and recompute the existing "
                "clamp(concentration - mean, 0, 1) mapping."
            ),
            "readout": (
                "The unchanged shipping upstream guard 0.55 is used only to count "
                "false-high rescue on oracle-noise targets and high-evidence "
                "preservation on oracle-speech targets."
            ),
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
    case["noise_targets"] = 4
    case["speech_targets"] = 2
    case["reference_frames"] = 20
    case["target_cases"] = 1
    case["target_cases_with_reference"] = 1
    case["noise_mean_rescued"] = 3
    case["noise_concentration_rescued"] = 1
    case["noise_both_rescued"] = 4
    case["noise_mean_only"] = 2
    case["noise_concentration_only"] = 0
    case["noise_both_individual"] = 1
    case["noise_neither_individual"] = 1
    case["noise_joint_only"] = 1
    case["speech_mean_preserved"] = 1
    case["speech_concentration_preserved"] = 2
    case["speech_both_preserved"] = 1
    case["noise_base_minus_mean_cf"] = [0.2, 0.2, 0.1, 0.0]
    case["noise_base_minus_concentration_cf"] = [0.0, 0.0, 0.1, 0.0]
    case["noise_base_minus_both_cf"] = [0.2, 0.2, 0.2, 0.2]
    case["speech_base_minus_mean_cf"] = [0.1, 0.2]
    case["speech_base_minus_concentration_cf"] = [0.0, 0.1]
    case["speech_base_minus_both_cf"] = [0.1, 0.1]
    case["reference_mean"] = [0.2]
    case["reference_concentration"] = [0.7]
    case["reference_gap"] = [0.5]
    append_case(acc, case)
    s = summary(acc)
    assert s["noise_rescue_fraction"]["mean_reference"] == 0.75
    assert s["noise_rescue_fraction"]["concentration_reference"] == 0.25
    assert s["noise_rescue_fraction"]["both_reference"] == 1.0
    assert s["speech_preservation_fraction"]["concentration_reference"] == 1.0
    assert s["noise_individual_attribution_fraction"]["mean_only"] == 0.5
    print("I026 matched component counterfactual self-test: OK")


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
        "noise_rescue_fraction": result["global"]["noise_rescue_fraction"],
        "speech_preservation_fraction":
            result["global"]["speech_preservation_fraction"],
        "reference_case_coverage": result["global"]["reference_case_coverage"],
    }, sort_keys=True))
    return 0 if result["decision"] != "I026_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
