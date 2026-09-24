#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))

import run_validation_engine as engine  # type: ignore

REQUIRED_CASES = {"stage-ns-stationary", "stage-ns-nonstationary"}
NONSTATIONARY_CASE = "stage-ns-nonstationary"
WARMUP_FRAMES = 80


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def roc_auc(scores: list[float], labels: list[int]) -> float:
    if len(scores) != len(labels) or not scores:
        raise ValueError("AUC requires aligned non-empty scores/labels")
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("AUC requires both positive and negative labels")

    ordered = sorted(zip(scores, labels), key=lambda item: item[0])
    rank = 1
    pos_rank_sum = 0.0
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        avg_rank = (rank + (rank + (j - i) - 1)) / 2.0
        pos_rank_sum += avg_rank * sum(label for _, label in ordered[i:j])
        rank += j - i
        i = j
    return (
        pos_rank_sum - n_pos * (n_pos + 1) / 2.0
    ) / (n_pos * n_neg)


def run_probe(probe: Path, raw_pcm: Path) -> list[dict[str, float | int]]:
    completed = subprocess.run(
        [str(probe), str(raw_pcm)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows: list[dict[str, float | int]] = []
    for number, line in enumerate(completed.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid I014 probe JSONL line {number}: {exc.msg}"
            ) from exc
    if not rows:
        raise ValueError("I014 probe produced no rows")
    return rows


def run_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError(f"I014 case missing mic/labels: {case.get('case_id')}")
    if int(case.get("sample_rate_hz", 0)) != 16000:
        raise ValueError("I014 requires 16 kHz")
    if int(case.get("mic_channels", 0)) != 1:
        raise ValueError("I014 requires mono input")

    with tempfile.TemporaryDirectory(prefix="ap-i014-stage-") as tmp:
        work = Path(tmp)
        _, raw = engine.stage_audio(mic, 16000, 1, work, "mic.pcm")
        rows = run_probe(probe, raw)

    labels = engine.load_labels(labels_path)
    count = min(len(labels), len(rows))
    if count <= WARMUP_FRAMES:
        raise ValueError("I014 case too short after warmup")
    return {
        "case_id": str(case["case_id"]),
        "labels": [int(x) for x in labels[:count]],
        "rows": rows[:count],
    }


def summarize(seed_cases: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    all_mean_suppression: list[float] = []
    all_concentration: list[float] = []
    all_shipping: list[float] = []
    all_labels: list[int] = []

    non_mean_suppression: list[float] = []
    non_concentration: list[float] = []
    non_shipping: list[float] = []
    non_labels: list[int] = []

    max_mirror_delta = 0.0
    max_floor_delta = 0.0
    mirror_mismatch_frames = 0
    per_seed: list[dict[str, Any]] = []

    for seed, cases in sorted(seed_cases.items()):
        seed_mean: list[float] = []
        seed_concentration: list[float] = []
        seed_shipping: list[float] = []
        seed_labels: list[int] = []

        seed_non_mean: list[float] = []
        seed_non_concentration: list[float] = []
        seed_non_shipping: list[float] = []
        seed_non_labels: list[int] = []

        case_summaries: list[dict[str, Any]] = []

        for case in cases:
            case_mean: list[float] = []
            case_concentration: list[float] = []
            case_shipping: list[float] = []
            case_labels: list[int] = []

            for index, (label, row) in enumerate(zip(case["labels"], case["rows"])):
                mean_score = float(row["mean_suppression_score"])
                concentration = float(row["concentration"])
                mirror_gap = float(row["mirror_gap"])
                shipping = float(row["base_speech_probability"])
                stress = float(row["stress_speech_probability"])

                values = (
                    mean_score, concentration, mirror_gap, shipping, stress
                )
                if not all(math.isfinite(value) for value in values):
                    raise ValueError(
                        f"non-finite I014 metric seed={seed} "
                        f"case={case['case_id']} frame={index}"
                    )
                if int(row["nfft"]) != 512 or int(row["speech_bins"]) != 215:
                    raise ValueError("I014 NS evidence geometry drifted")

                mirror_delta = abs(mirror_gap - shipping)
                floor_delta = abs(shipping - stress)
                max_mirror_delta = max(max_mirror_delta, mirror_delta)
                max_floor_delta = max(max_floor_delta, floor_delta)
                if mirror_delta > 1e-6:
                    mirror_mismatch_frames += 1

                if index < WARMUP_FRAMES:
                    continue

                case_mean.append(mean_score)
                case_concentration.append(concentration)
                case_shipping.append(shipping)
                case_labels.append(label)

                seed_mean.append(mean_score)
                seed_concentration.append(concentration)
                seed_shipping.append(shipping)
                seed_labels.append(label)

                all_mean_suppression.append(mean_score)
                all_concentration.append(concentration)
                all_shipping.append(shipping)
                all_labels.append(label)

                if case["case_id"] == NONSTATIONARY_CASE:
                    seed_non_mean.append(mean_score)
                    seed_non_concentration.append(concentration)
                    seed_non_shipping.append(shipping)
                    seed_non_labels.append(label)
                    non_mean_suppression.append(mean_score)
                    non_concentration.append(concentration)
                    non_shipping.append(shipping)
                    non_labels.append(label)

            case_summaries.append({
                "case_id": case["case_id"],
                "frames_after_warmup": len(case_labels),
                "mean_suppression_auc": roc_auc(case_mean, case_labels),
                "concentration_auc": roc_auc(case_concentration, case_labels),
                "shipping_gap_auc": roc_auc(case_shipping, case_labels),
            })

        per_seed.append({
            "seed": seed,
            "mean_suppression_auc": roc_auc(seed_mean, seed_labels),
            "concentration_auc": roc_auc(seed_concentration, seed_labels),
            "shipping_gap_auc": roc_auc(seed_shipping, seed_labels),
            "nonstationary_mean_suppression_auc": roc_auc(
                seed_non_mean, seed_non_labels
            ),
            "nonstationary_concentration_auc": roc_auc(
                seed_non_concentration, seed_non_labels
            ),
            "nonstationary_shipping_gap_auc": roc_auc(
                seed_non_shipping, seed_non_labels
            ),
            "case_summaries": case_summaries,
        })

    combined_mean = roc_auc(all_mean_suppression, all_labels)
    combined_concentration = roc_auc(all_concentration, all_labels)
    combined_shipping = roc_auc(all_shipping, all_labels)
    non_mean = roc_auc(non_mean_suppression, non_labels)
    non_concentration_auc = roc_auc(non_concentration, non_labels)
    non_shipping_auc = roc_auc(non_shipping, non_labels)

    return {
        "max_shipping_mirror_probability_delta": max_mirror_delta,
        "shipping_mirror_mismatch_frames": mirror_mismatch_frames,
        "max_floor_shipping_probability_delta": max_floor_delta,
        "combined_mean_suppression_auc": combined_mean,
        "combined_concentration_auc": combined_concentration,
        "combined_shipping_gap_auc": combined_shipping,
        "combined_nonstationary_mean_suppression_auc": non_mean,
        "combined_nonstationary_concentration_auc": non_concentration_auc,
        "combined_nonstationary_shipping_gap_auc": non_shipping_auc,
        "nonstationary_shipping_auc_gain_over_mean_suppression": (
            non_shipping_auc - non_mean
        ),
        "nonstationary_shipping_auc_gain_over_concentration": (
            non_shipping_auc - non_concentration_auc
        ),
        "per_seed": per_seed,
    }


def decide(
    summary: dict[str, Any], gates: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    input_checks = [
        (
            "shipping_mirror_identity",
            int(summary["shipping_mirror_mismatch_frames"]) == 0
            and float(summary["max_shipping_mirror_probability_delta"])
            <= float(gates["max_shipping_mirror_probability_delta"]),
            summary["max_shipping_mirror_probability_delta"],
            gates["max_shipping_mirror_probability_delta"],
        ),
        (
            "floor_shipping_probability_invariance",
            float(summary["max_floor_shipping_probability_delta"])
            <= float(gates["max_floor_shipping_probability_delta"]),
            summary["max_floor_shipping_probability_delta"],
            gates["max_floor_shipping_probability_delta"],
        ),
    ]
    min_seed_nonstationary = min(
        float(item["nonstationary_shipping_gap_auc"])
        for item in summary["per_seed"]
    )
    info_checks = [
        (
            "combined_nonstationary_shipping_auc",
            float(summary["combined_nonstationary_shipping_gap_auc"])
            >= float(gates["min_combined_nonstationary_shipping_auc"]),
            summary["combined_nonstationary_shipping_gap_auc"],
            gates["min_combined_nonstationary_shipping_auc"],
        ),
        (
            "nonstationary_shipping_auc_gain_over_mean_suppression",
            float(summary["nonstationary_shipping_auc_gain_over_mean_suppression"])
            >= float(gates["min_nonstationary_shipping_auc_gain_over_mean_suppression"]),
            summary["nonstationary_shipping_auc_gain_over_mean_suppression"],
            gates["min_nonstationary_shipping_auc_gain_over_mean_suppression"],
        ),
        (
            "nonstationary_shipping_auc_gain_over_concentration",
            float(summary["nonstationary_shipping_auc_gain_over_concentration"])
            >= float(gates["min_nonstationary_shipping_auc_gain_over_concentration"]),
            summary["nonstationary_shipping_auc_gain_over_concentration"],
            gates["min_nonstationary_shipping_auc_gain_over_concentration"],
        ),
        (
            "per_seed_nonstationary_shipping_auc",
            min_seed_nonstationary
            >= float(gates["min_per_seed_nonstationary_shipping_auc"]),
            min_seed_nonstationary,
            gates["min_per_seed_nonstationary_shipping_auc"],
        ),
    ]

    input_violations = [
        {"gate": name, "actual": actual, "limit": limit}
        for name, passed, actual, limit in input_checks
        if not passed
    ]
    synergy_violations = [
        {"gate": name, "actual": actual, "limit": limit}
        for name, passed, actual, limit in info_checks
        if not passed
    ]

    if input_violations:
        decision = "NS_UPSTREAM_COMPONENT_INPUT_INVALID_REVIEW_REQUIRED"
    elif synergy_violations:
        decision = "NS_UPSTREAM_COMPONENT_SYNERGY_NOT_SUPPORTED_REVIEW_REQUIRED"
    else:
        decision = "NS_UPSTREAM_COMPONENT_SYNERGY_SUPPORTED_REVIEW_REQUIRED"
    return decision, input_violations, synergy_violations


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    fresh = contract["fresh_diagnostic_authority"]
    seeds = [int(x) for x in fresh["seeds"]]

    if len(corpora) != len(seeds):
        raise ValueError("I014 corpus count must match preregistered seeds")
    if contract["budget"] != {
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "diagnostic_execution_limit": 1,
    }:
        raise ValueError("I014 budget drift")
    if (
        contract["parameter_search_allowed"] is not False
        or contract["threshold_tuning_allowed"] is not False
        or contract["shipping_source_change_allowed"] is not False
        or contract["promotion_allowed"] is not False
    ):
        raise ValueError("I014 authority boundary drift")

    seed_cases: dict[int, list[dict[str, Any]]] = {}
    actual_seeds: list[int] = []
    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        selected = {
            str(case.get("case_id")): case
            for case in corpus.get("cases", [])
            if case.get("processor_profile") == "ns-isolated"
            and case.get("vad_labels")
            and case.get("render_audio") is None
            and str(case.get("case_id")) in REQUIRED_CASES
        }
        if set(selected) != REQUIRED_CASES:
            raise ValueError(
                f"missing I014 required cases seed={seed}: "
                f"{sorted(REQUIRED_CASES - set(selected))}"
            )
        seed_cases[seed] = [
            run_case(probe, corpus_path, selected[case_id])
            for case_id in sorted(REQUIRED_CASES)
        ]

    if actual_seeds != seeds:
        raise ValueError(
            f"I014 seed drift: actual={actual_seeds} expected={seeds}"
        )

    summary = summarize(seed_cases)
    decision, input_violations, synergy_violations = decide(
        summary, contract["diagnostic_gates"]
    )
    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "decision": decision,
        "fresh_seeds": actual_seeds,
        "summary": summary,
        "input_violations": input_violations,
        "synergy_violations": synergy_violations,
        "candidate_budget_consumed": 0,
        "confirmation_budget_consumed": 0,
        "shipping_source_changed": False,
        "interpretation": {
            "component_reweighting_selected": False,
            "feature_mapping_selected": False,
            "vad_mapping_selected": False,
            "vad_threshold_selected": False,
            "note": (
                "This is decomposition of the existing shipping NS speech_probability "
                "only. The same data cannot authorize component reweighting or a new mapping."
            ),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    assert roc_auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0
    summary = {
        "shipping_mirror_mismatch_frames": 0,
        "max_shipping_mirror_probability_delta": 0.0,
        "max_floor_shipping_probability_delta": 0.0,
        "combined_nonstationary_shipping_gap_auc": 0.65,
        "nonstationary_shipping_auc_gain_over_mean_suppression": 0.03,
        "nonstationary_shipping_auc_gain_over_concentration": 0.04,
        "per_seed": [
            {"nonstationary_shipping_gap_auc": 0.62},
            {"nonstationary_shipping_gap_auc": 0.64},
            {"nonstationary_shipping_gap_auc": 0.61},
        ],
    }
    gates = {
        "max_shipping_mirror_probability_delta": 1e-6,
        "max_floor_shipping_probability_delta": 1e-7,
        "min_combined_nonstationary_shipping_auc": 0.62,
        "min_nonstationary_shipping_auc_gain_over_mean_suppression": 0.02,
        "min_nonstationary_shipping_auc_gain_over_concentration": 0.02,
        "min_per_seed_nonstationary_shipping_auc": 0.60,
    }
    decision, input_violations, synergy_violations = decide(summary, gates)
    assert decision == "NS_UPSTREAM_COMPONENT_SYNERGY_SUPPORTED_REVIEW_REQUIRED"
    assert not input_violations
    assert not synergy_violations
    print("I014 upstream component decomposition evaluator self-test: OK")


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
    if not args.probe or not args.contract or not args.corpus or not args.output:
        parser.error("--probe, --contract, --corpus and --output are required")

    result = evaluate(
        args.probe.resolve(),
        [path.resolve() for path in args.corpus],
        args.contract.resolve(),
        args.output.resolve(),
    )
    s = result["summary"]
    print(json.dumps({
        "decision": result["decision"],
        "fresh_seeds": result["fresh_seeds"],
        "combined_nonstationary_mean_suppression_auc":
            s["combined_nonstationary_mean_suppression_auc"],
        "combined_nonstationary_concentration_auc":
            s["combined_nonstationary_concentration_auc"],
        "combined_nonstationary_shipping_gap_auc":
            s["combined_nonstationary_shipping_gap_auc"],
        "shipping_gain_over_mean":
            s["nonstationary_shipping_auc_gain_over_mean_suppression"],
        "shipping_gain_over_concentration":
            s["nonstationary_shipping_auc_gain_over_concentration"],
        "input_violations": len(result["input_violations"]),
        "synergy_violations": len(result["synergy_violations"]),
    }, sort_keys=True))
    return 2 if result["decision"] == (
        "NS_UPSTREAM_COMPONENT_INPUT_INVALID_REVIEW_REQUIRED"
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
