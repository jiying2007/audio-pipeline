#!/usr/bin/env python3
"""I022 candidate-zero decomposition of low-local VAD false negatives."""

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


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
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
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("probe output invalid")
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


def empty_accumulator() -> dict[str, Any]:
    return {
        "tp": 0, "fn": 0, "fp": 0, "tn": 0, "frames": 0,
        "low_local_false_negatives": 0,
        "low_local_matrix": Counter(),
        "state_over_reference_db": [],
        "shipping_ratio_db_low_local": [],
        "reference_ratio_db_low_local": [],
        "upstream_probability_low_local": [],
        "reference_applicable_low_local": 0,
    }


def reference_probability(rms: float, noise_reference: float) -> tuple[float, float]:
    ratio_db = 20.0 * math.log10((rms + 1.0e-7) / (noise_reference + 1.0e-7))
    probability = min(1.0, max(0.0, (ratio_db - 2.0) / 12.0))
    return ratio_db, probability


def accumulate(
    acc: dict[str, Any],
    row: dict[str, Any],
    label: int,
    *,
    upstream_guard: float,
    local_guard: float,
    noise_reference: float | None,
) -> None:
    active = int(row["shipping_active"])
    if active not in (0, 1) or label not in (0, 1):
        raise ValueError("invalid binary state")
    for key in (
        "shipping_probability", "upstream_probability", "ratio_db",
        "rms", "noise_rms_before",
    ):
        if not math.isfinite(float(row[key])):
            raise ValueError("non-finite diagnostic value: " + key)

    if label and active:
        acc["tp"] += 1
    elif label and not active:
        acc["fn"] += 1
        if not int(row["local_guard_pass"]):
            acc["low_local_false_negatives"] += 1
            upstream_high = float(row["upstream_probability"]) > upstream_guard
            upstream_key = "upstream_high" if upstream_high else "upstream_not_high"
            acc["shipping_ratio_db_low_local"].append(float(row["ratio_db"]))
            acc["upstream_probability_low_local"].append(
                float(row["upstream_probability"])
            )
            if noise_reference is None:
                acc["low_local_matrix"][upstream_key + "__reference_unavailable"] += 1
            else:
                ref_ratio_db, ref_probability = reference_probability(
                    float(row["rms"]), noise_reference
                )
                ref_pass = ref_probability > local_guard
                ref_key = "reference_pass" if ref_pass else "reference_fail"
                acc["low_local_matrix"][upstream_key + "__" + ref_key] += 1
                acc["reference_applicable_low_local"] += 1
                acc["reference_ratio_db_low_local"].append(ref_ratio_db)
                acc["state_over_reference_db"].append(
                    20.0 * math.log10(
                        (float(row["noise_rms_before"]) + 1.0e-7)
                        / (noise_reference + 1.0e-7)
                    )
                )
    elif not label and active:
        acc["fp"] += 1
    else:
        acc["tn"] += 1
    acc["frames"] += 1


def merge_accumulator(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "tp", "fn", "fp", "tn", "frames",
        "low_local_false_negatives", "reference_applicable_low_local",
    ):
        target[key] += int(source[key])
    target["low_local_matrix"].update(source["low_local_matrix"])
    for key in (
        "state_over_reference_db",
        "shipping_ratio_db_low_local",
        "reference_ratio_db_low_local",
        "upstream_probability_low_local",
    ):
        target[key].extend(float(value) for value in source[key])


def metrics(acc: dict[str, Any]) -> dict[str, Any]:
    tp, fn, fp, tn = (int(acc[key]) for key in ("tp", "fn", "fp", "tn"))
    speech = tp + fn
    noise = fp + tn
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / speech if speech else None
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if recall is not None and precision + recall > 0.0
        else None
    )
    fpr = fp / noise if noise else None
    low = int(acc["low_local_false_negatives"])
    applicable = int(acc["reference_applicable_low_local"])
    matrix = dict(sorted(acc["low_local_matrix"].items()))
    reference_pass = sum(
        value for key, value in matrix.items() if key.endswith("__reference_pass")
    )
    upstream_high = sum(
        value for key, value in matrix.items() if key.startswith("upstream_high__")
    )
    return {
        "frames": int(acc["frames"]),
        "speech_frames": speech,
        "noise_frames": noise,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": fpr,
        "low_local_false_negatives": low,
        "low_local_fraction_of_false_negatives": low / fn if fn else None,
        "low_local_matrix": matrix,
        "upstream_high_fraction_of_low_local": (
            upstream_high / low if low else None
        ),
        "reference_applicable_low_local": applicable,
        "reference_pass_fraction_of_applicable_low_local": (
            reference_pass / applicable if applicable else None
        ),
        "state_over_reference_db": {
            "median": (
                statistics.median(acc["state_over_reference_db"])
                if acc["state_over_reference_db"] else None
            ),
            "p10": percentile(acc["state_over_reference_db"], 0.10),
            "p90": percentile(acc["state_over_reference_db"], 0.90),
        },
        "shipping_ratio_db_low_local_median": (
            statistics.median(acc["shipping_ratio_db_low_local"])
            if acc["shipping_ratio_db_low_local"] else None
        ),
        "reference_ratio_db_low_local_median": (
            statistics.median(acc["reference_ratio_db_low_local"])
            if acc["reference_ratio_db_low_local"] else None
        ),
        "upstream_probability_low_local_median": (
            statistics.median(acc["upstream_probability_low_local"])
            if acc["upstream_probability_low_local"] else None
        ),
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
    *,
    upstream_guard: float,
    local_guard: float,
) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError("case missing mic audio or VAD labels")
    with tempfile.TemporaryDirectory(prefix="ap-i022-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    if count <= WARMUP:
        raise ValueError("case too short")
    rows = rows[WARMUP:count]
    labels = labels[WARMUP:count]

    mirror_delta = 0.0
    mirror_active = 0
    noise_states = []
    for row, label in zip(rows, labels):
        public_prob = float(row["public_shipping_probability"])
        shipping_prob = float(row["shipping_probability"])
        if not math.isfinite(public_prob):
            raise ValueError("non-finite public shipping probability")
        mirror_delta = max(mirror_delta, abs(public_prob - shipping_prob))
        mirror_active += int(
            int(row["public_shipping_active"]) != int(row["shipping_active"])
        )
        if label == 0:
            value = float(row["noise_rms_before"])
            if math.isfinite(value) and value > 0.0:
                noise_states.append(value)
    noise_reference = statistics.median(noise_states) if noise_states else None

    acc = empty_accumulator()
    for row, label in zip(rows, labels):
        accumulate(
            acc, row, label,
            upstream_guard=upstream_guard,
            local_guard=local_guard,
            noise_reference=noise_reference,
        )
    return {
        "case_id": str(case["case_id"]),
        "scenario": str(case["scenario"]),
        "dimensions": case.get("dimensions", {}),
        "noise_state_reference_rms": noise_reference,
        "metrics": metrics(acc),
        "accumulator": acc,
        "shipping_mirror": {
            "max_probability_delta": mirror_delta,
            "active_mismatch_frames": mirror_active,
        },
    }


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    if contract["investigation_id"] != "i022-vad-low-local-evidence-disagreement-decomposition-v1":
        raise ValueError("contract identity drift")
    authority = contract["fresh_diagnostic_authority"]
    expected_seeds = [int(seed) for seed in authority["seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("corpus count mismatch")
    if {
        "diagnostic_execution_limit": authority["diagnostic_execution_limit"],
        "candidate_limit": authority["candidate_limit"],
        "confirmation_limit": authority["confirmation_limit"],
    } != {
        "diagnostic_execution_limit": 1,
        "candidate_limit": 0,
        "confirmation_limit": 0,
    }:
        raise ValueError("I022 budget drift")

    semantics = contract["fixed_shipping_semantics"]
    upstream_guard = float(semantics["vad_upstream_speech_guard"])
    local_guard = float(semantics["vad_local_speech_guard"])
    expected_lock = contract["dataset_authority"]["dataset_lock_blob_sha"]

    actual_seeds: list[int] = []
    global_acc = empty_accumulator()
    slices: dict[str, dict[str, Any]] = {}
    per_case: list[dict[str, Any]] = []
    mirror_delta = 0.0
    mirror_active = 0
    domain_case_counts = {domain: {"mix": 0, "noise": 0} for domain in NOISE_DOMAINS}

    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        if corpus.get("tier") != "research-validation":
            raise ValueError("public development tier drift")
        if corpus.get("dataset_lock_sha256") != expected_lock:
            raise ValueError("dataset lock binding drift")
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        cases = corpus.get("cases", [])
        if len(cases) != int(authority["expected_cases_per_seed"]):
            raise ValueError(f"unexpected case count for seed={seed}")
        for case in cases:
            result = analyze_case(
                probe, corpus_path, case,
                upstream_guard=upstream_guard,
                local_guard=local_guard,
            )
            per_case.append({
                key: value for key, value in result.items() if key != "accumulator"
            })
            merge_accumulator(global_acc, result["accumulator"])
            mirror_delta = max(
                mirror_delta,
                float(result["shipping_mirror"]["max_probability_delta"]),
            )
            mirror_active += int(
                result["shipping_mirror"]["active_mismatch_frames"]
            )
            for key in slice_keys(case):
                slices.setdefault(key, empty_accumulator())
                merge_accumulator(slices[key], result["accumulator"])
            dimensions = case.get("dimensions", {})
            domain = dimensions.get("noise_domain")
            if domain in domain_case_counts:
                if str(case["scenario"]).startswith("research-public-noisy"):
                    domain_case_counts[domain]["mix"] += 1
                elif case["scenario"] == "research-public-noise-only":
                    domain_case_counts[domain]["noise"] += 1

    if actual_seeds != expected_seeds:
        raise ValueError(f"fresh seed mismatch: {actual_seeds}")

    global_metrics = metrics(global_acc)
    slice_metrics = {key: metrics(acc) for key, acc in sorted(slices.items())}
    invalid_reasons: list[str] = []
    gates = contract["diagnostic_gates"]
    if len(per_case) < int(gates["minimum_total_cases"]):
        invalid_reasons.append("case_count")
    if int(global_metrics["low_local_false_negatives"]) < int(
        gates["minimum_low_local_false_negative_frames"]
    ):
        invalid_reasons.append("low_local_false_negative_count")
    if int(global_metrics["reference_applicable_low_local"]) < int(
        gates["minimum_reference_applicable_low_local_frames"]
    ):
        invalid_reasons.append("reference_applicable_low_local_count")
    if mirror_delta > float(gates["max_shipping_mirror_probability_delta"]):
        invalid_reasons.append("shipping_mirror_probability")
    if mirror_active != int(gates["shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("shipping_mirror_active")
    for domain, counts in domain_case_counts.items():
        if counts["mix"] < int(authority["minimum_mix_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_mix_coverage:" + domain)
        if counts["noise"] < int(authority["minimum_noise_only_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_noise_coverage:" + domain)

    low_local_slices = sorted(
        [
            {
                "slice": key,
                "low_local_false_negatives": value["low_local_false_negatives"],
                "low_local_fraction_of_false_negatives": value[
                    "low_local_fraction_of_false_negatives"
                ],
                "upstream_high_fraction_of_low_local": value[
                    "upstream_high_fraction_of_low_local"
                ],
                "reference_pass_fraction_of_applicable_low_local": value[
                    "reference_pass_fraction_of_applicable_low_local"
                ],
                "state_over_reference_db_median": value[
                    "state_over_reference_db"
                ]["median"],
            }
            for key, value in slice_metrics.items()
            if int(value["low_local_false_negatives"]) > 0
        ],
        key=lambda item: (
            -int(item["low_local_false_negatives"]),
            item["slice"],
        ),
    )

    if invalid_reasons:
        decision = "I022_INPUT_INVALID_REVIEW_REQUIRED"
    elif int(global_metrics["low_local_false_negatives"]) > 0:
        decision = "VAD_LOW_LOCAL_DISAGREEMENT_DECOMPOSED_REVIEW_REQUIRED"
    else:
        decision = "VAD_LOW_LOCAL_NOT_REPRODUCED_REVIEW_REQUIRED"

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
        "global": global_metrics,
        "slices": slice_metrics,
        "per_case": per_case,
        "domain_case_counts": domain_case_counts,
        "low_local_slices": low_local_slices,
        "decision": decision,
        "invalid_reasons": sorted(set(invalid_reasons)),
        "interpretation_boundary": {
            "noise_reference": (
                "Per-case median shipping noise_rms_before over oracle-labeled "
                "true-noise frames in the same post-NS diagnostic domain."
            ),
            "reference_pass": (
                "Recompute only the existing shipping local-evidence mapping with "
                "that diagnostic reference and the unchanged local guard; this is "
                "not a candidate or threshold search."
            ),
            "matrix_is_descriptive_only": True,
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
    noise = {
        "shipping_active": 0,
        "public_shipping_active": 0,
        "shipping_probability": 0.05,
        "public_shipping_probability": 0.05,
        "upstream_probability": 0.1,
        "ratio_db": 0.0,
        "rms": 0.1,
        "noise_rms_before": 0.1,
        "local_guard_pass": 0,
    }
    high_rescuable = dict(
        noise,
        upstream_probability=0.8,
        rms=0.2,
        noise_rms_before=0.2,
    )
    joint_weak = dict(
        noise,
        upstream_probability=0.2,
        rms=0.11,
        noise_rms_before=0.2,
    )
    acc = empty_accumulator()
    for row, label in ((noise, 0), (high_rescuable, 1), (joint_weak, 1)):
        accumulate(
            acc, row, label,
            upstream_guard=0.55,
            local_guard=0.15,
            noise_reference=0.1,
        )
    m = metrics(acc)
    assert m["fn"] == 2 and m["low_local_false_negatives"] == 2
    assert m["low_local_matrix"]["upstream_high__reference_pass"] == 1
    assert m["low_local_matrix"]["upstream_not_high__reference_fail"] == 1
    assert m["reference_pass_fraction_of_applicable_low_local"] == 0.5
    assert m["upstream_high_fraction_of_low_local"] == 0.5
    print("I022 low-local disagreement evaluator self-test: OK")


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
        "low_local_false_negatives": result["global"]["low_local_false_negatives"],
        "matrix": result["global"]["low_local_matrix"],
    }, sort_keys=True))
    return 0 if result["decision"] != "I022_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
